# react_agent_deepseek.py
"""
ReAct (Reasoning + Acting) Agent based on DeepSeek API.

Implements the standard ReAct loop:
  Thought → Action → Observation → Thought → ... → Final Answer

Supports file I/O, shell command execution, code search, and directory listing,
with built-in safety constraints and an optional security audit layer.
"""
import requests
import json
import re
import shlex
import subprocess
import os
import time
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path


# ---------------------------------------------------------------------------
# 安全常量
# ---------------------------------------------------------------------------

# 禁止执行的命令前缀 — 即使 shell=False 也很难完全阻止恶意意图，
# 这里作为最后一道防线对命令关键词做粗粒度拦截
DANGEROUS_COMMAND_KEYWORDS = [
    "rm -rf", "rm -r", "sudo", "dd if=", "mkfs", "format",
    ":(){ :|:& };:",  # fork bomb
    "chmod 777", "> /dev/sda", "/dev/null",
]

# 允许 LLM 操作的项目根目录 — 所有文件读写被限制在此目录下
PROJECT_ROOT = os.path.realpath(os.getcwd())


# ---------------------------------------------------------------------------
# 工具函数（独立于类，便于单独测试）
# ---------------------------------------------------------------------------

def _is_path_safe(path: str) -> bool:
    """
    检查路径是否安全：禁止路径遍历攻击，限制在 PROJECT_ROOT 内。
    返回 True 表示路径安全可访问。
    """
    try:
        # 将相对路径解析为以 PROJECT_ROOT 为基准的绝对路径
        abs_path = os.path.realpath(os.path.join(PROJECT_ROOT, path))
        # 确保解析后的路径仍在项目根目录内
        return abs_path.startswith(PROJECT_ROOT + os.sep) or abs_path == PROJECT_ROOT
    except (ValueError, OSError):
        return False


def _is_command_safe(cmd: str) -> bool:
    """检查命令是否包含已知危险模式，返回 (is_safe, reason)。"""
    cmd_lower = cmd.lower()
    for keyword in DANGEROUS_COMMAND_KEYWORDS:
        if keyword in cmd_lower:
            return False, keyword
    return True, ""


# ---------------------------------------------------------------------------
# Agent 主类
# ---------------------------------------------------------------------------

class DeepSeekReActAgent:
    """
    DeepSeek 驱动的 ReAct Agent。

    核心流程:
        1. 将任务 + 工具列表发送给 DeepSeek
        2. 解析 LLM 返回的 Thought / Action / Final Answer
        3. 执行 Action 对应工具，将结果作为 Observation 回传
        4. 重复直到出现 Final Answer 或超过 max_steps
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_history_messages: int = 20,
    ):
        """
        Args:
            api_key: DeepSeek API key，不传则从环境变量 DEEPSEEK_API_KEY 读取
            base_url: API 地址
            model: 模型名称
            max_history_messages: 对话历史保留的最大消息数（不含 system prompt），
                                  超出时从最早的消息开始丢弃
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url
        self.model = model
        self.max_history_messages = max_history_messages
        self.conversation_history = []
        self.tools = self._register_tools()

    # ------------------------------------------------------------------
    # 工具注册
    # ------------------------------------------------------------------

    def _register_tools(self) -> Dict:
        """
        注册可用工具。
        返回格式:
            { tool_name: { "func": callable, "description": str, "parameters": { name: desc } } }
        """
        return {
            "read_file": {
                "func": self._read_file,
                "description": "读取文件内容",
                "parameters": {"path": "文件路径（相对于项目根目录）"},
            },
            "write_file": {
                "func": self._write_file,
                "description": "写入文件内容",
                "parameters": {"path": "文件路径", "content": "要写入的内容"},
            },
            "execute_command": {
                "func": self._execute_command,
                "description": "执行只读 Shell 命令（ls / cat / grep / find / wc 等）",
                "parameters": {"cmd": "要执行的命令"},
            },
            "search_code": {
                "func": self._search_code,
                "description": "在项目中搜索包含指定模式的代码文件",
                "parameters": {"pattern": "搜索关键词"},
            },
            "list_directory": {
                "func": self._list_directory,
                "description": "列出目录内容",
                "parameters": {"path": "目录路径，默认当前目录"},
            },
        }

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------

    def _read_file(self, path: str) -> str:
        """安全读取文件内容（限制在项目目录内，结果截断到 5000 字符）。"""
        if not _is_path_safe(path):
            return f"[TOOL_ERROR] 路径 '{path}' 不在项目目录内"
        try:
            file_path = os.path.join(PROJECT_ROOT, path)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 5000:
                content = content[:5000] + "\n... (文件过长，已截断)"
            return content
        except FileNotFoundError:
            return f"[TOOL_ERROR] 文件 '{path}' 不存在"
        except UnicodeDecodeError:
            return f"[TOOL_ERROR] 文件 '{path}' 不是 UTF-8 文本文件，无法读取"
        except Exception as e:
            return f"[TOOL_ERROR] 读取文件失败 - {str(e)}"

    def _write_file(self, path: str, content: str) -> str:
        """安全写入文件（限制在项目目录内）。"""
        if not _is_path_safe(path):
            return f"[TOOL_ERROR] 路径 '{path}' 不在项目目录内"
        try:
            file_path = os.path.join(PROJECT_ROOT, path)
            # 确保父目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"成功写入文件 '{path}' ({len(content)} 字符)"
        except Exception as e:
            return f"[TOOL_ERROR] 写入失败 - {str(e)}"

    def _execute_command(self, cmd: str) -> str:
        """
        执行 shell 命令。
        安全措施:
          1. 关键词黑名单拦截
          2. 使用 shell=False + shlex.split 防止注入
          3. 10 秒超时
          4. 输出截断到 2000 字符
        """
        # 1. 关键词检查
        is_safe, reason = _is_command_safe(cmd)
        if not is_safe:
            return f"[TOOL_ERROR] 命令被拒绝: 匹配危险模式 '{reason}'"

        # 2. 解析命令（shlex.split 正确保留引号内参数）
        try:
            args = shlex.split(cmd)
        except ValueError as e:
            return f"[TOOL_ERROR] 命令解析失败 - {str(e)}"

        if not args:
            return "[TOOL_ERROR] 空命令"

        # 3. 执行（shell=False 避免 shell 注入）
        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT,
            )
            output = result.stdout if result.stdout else result.stderr
            if len(output) > 2000:
                output = output[:2000] + "\n... (输出过长，已截断)"
            return output if output.strip() else "命令执行成功（无输出）"
        except FileNotFoundError:
            return f"[TOOL_ERROR] 命令未找到: '{args[0]}'"
        except subprocess.TimeoutExpired:
            return "[TOOL_ERROR] 命令执行超时（超过 10 秒）"
        except PermissionError:
            return f"[TOOL_ERROR] 权限不足，无法执行 '{args[0]}'"
        except Exception as e:
            return f"[TOOL_ERROR] 命令执行失败 - {str(e)}"

    def _search_code(self, pattern: str) -> str:
        """在项目 .py 文件中搜索指定模式（大小写不敏感），最多返回 10 个匹配文件。"""
        matches = []
        try:
            for py_file in Path(PROJECT_ROOT).rglob("*.py"):
                if py_file.is_file():
                    try:
                        content = py_file.read_text(encoding="utf-8")
                        if pattern.lower() in content.lower():
                            # 记录相对于项目根目录的路径
                            matches.append(str(py_file.relative_to(PROJECT_ROOT)))
                            if len(matches) >= 10:
                                break
                    except (UnicodeDecodeError, PermissionError):
                        continue
        except Exception as e:
            return f"[TOOL_ERROR] 搜索失败 - {str(e)}"

        if matches:
            return f"找到包含 '{pattern}' 的文件:\n" + "\n".join(matches[:10])
        return f"未找到包含 '{pattern}' 的文件"

    def _list_directory(self, path: str = ".") -> str:
        """列出目录内容，限制在项目目录内，最多显示 30 项。"""
        if not _is_path_safe(path):
            return f"[TOOL_ERROR] 路径 '{path}' 不在项目目录内"
        try:
            abs_path = os.path.join(PROJECT_ROOT, path)
            items = os.listdir(abs_path)
            files, dirs = [], []

            for item in items:
                item_path = os.path.join(abs_path, item)
                if os.path.isdir(item_path):
                    dirs.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(item_path)
                    files.append(f"📄 {item} ({size} bytes)")

            result = f"目录 '{path}' 内容:\n"
            result += "\n".join(sorted(dirs + files)[:30])

            if len(items) > 30:
                result += f"\n... 还有 {len(items) - 30} 个项目未显示"
            return result
        except FileNotFoundError:
            return f"[TOOL_ERROR] 目录 '{path}' 不存在"
        except NotADirectoryError:
            return f"[TOOL_ERROR] '{path}' 不是目录"
        except Exception as e:
            return f"[TOOL_ERROR] 列出目录失败 - {str(e)}"

    # ------------------------------------------------------------------
    # API 调用
    # ------------------------------------------------------------------

    def _call_deepseek(self, messages: List[Dict], max_retries: int = 3) -> str:
        """
        调用 DeepSeek Chat Completions API，带指数退避重试。

        Args:
            messages: 标准 OpenAI 格式消息列表
            max_retries: 最大重试次数（仅针对可恢复错误）

        Returns:
            LLM 的文本回复，或以 "API Error:" 开头的错误字符串
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]

                # 4xx 客户端错误（除 429）不应重试
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    return f"API Error: {response.status_code} - {response.text}"

                # 5xx / 429 → 可重试
                last_error = f"API Error: {response.status_code} - {response.text}"

            except requests.exceptions.Timeout:
                last_error = "API Error: 请求超时"
            except requests.exceptions.ConnectionError:
                last_error = "API Error: 连接失败"
            except Exception as e:
                last_error = f"API Error: {str(e)}"

            if attempt < max_retries:
                # 指数退避: 1s, 2s, 4s
                wait = 2 ** attempt
                time.sleep(wait)

        return last_error

    # ------------------------------------------------------------------
    # 对话历史管理
    # ------------------------------------------------------------------

    def _truncate_history(self):
        """
        裁剪对话历史，防止超过模型 context window。
        始终保留 system prompt + 最近 max_history_messages 条消息。
        """
        if len(self.conversation_history) <= self.max_history_messages + 1:
            return  # 仍在限制内（+1 给 system prompt）

        # system prompt 始终保留
        system_msg = self.conversation_history[0]
        # 保留最后 max_history_messages 条（user/assistant 交替消息）
        recent = self.conversation_history[-(self.max_history_messages):]
        self.conversation_history = [system_msg] + recent

    # ------------------------------------------------------------------
    # ReAct 主循环
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        max_steps: int = 10,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        执行 ReAct 循环。

        LLM 输出格式要求:
            Thought: <推理过程>
            Action: tool_name({"key": "value"})

        或任务完成时:
            Thought: <推理过程>
            Final Answer: <最终答案>

        Args:
            task: 任务描述
            max_steps: 最多执行步数，防止死循环
            verbose: 是否打印中间过程

        Returns:
            {
                "success": bool,
                "final_answer": str | None,
                "steps": int,
                "actions": [{"step": int, "thought": str, "action": str, "params": dict, "observation": str}],
                "error": str | None,
            }
        """
        # 构建工具描述（供 system prompt 使用）
        tool_descriptions = self._build_tool_prompt()

        system_prompt = f"""你是一个能够使用工具的 AI 助手。你必须严格按照以下 ReAct 格式输出：

当需要执行操作时:
Thought: <分析当前状态，决定下一步做什么，为什么这样做>
Action: <工具名>({{"参数名": "参数值", ...}})

当任务完成时:
Thought: <确认任务已完成>
Final Answer: <给用户的最终答案>

可用工具:
{tool_descriptions}

重要规则:
- 每次只能输出一个 Action
- Action 的参数必须使用 JSON 格式，例如: read_file({{"path": "src/main.py"}})
- 字符串参数必须用双引号包裹
- 如果上一步工具返回了 [TOOL_ERROR]，分析错误原因并调整策略（如换一个路径、换一个工具）
- 完成任务后必须输出 Final Answer
- 不要输出任何其他格式的内容"""

        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        step = 0
        actions_history = []

        while step < max_steps:
            step += 1
            if verbose:
                print(f"\n{'=' * 50}")
                print(f"Step {step} / {max_steps}")
                print(f"{'=' * 50}")

            # 裁剪历史防止溢出
            self._truncate_history()

            # 调用 LLM
            response = self._call_deepseek(self.conversation_history)

            if response.startswith("API Error"):
                return {
                    "success": False,
                    "error": response,
                    "steps": step,
                    "actions": actions_history,
                    "final_answer": None,
                }

            if verbose:
                print(f"Response:\n{response}")

            # 检测 Final Answer
            if "Final Answer:" in response:
                final_answer = response.split("Final Answer:", 1)[-1].strip()
                if verbose:
                    print(f"\n✓ 任务完成！（共 {step} 步）")
                    print(f"最终答案: {final_answer}")

                return {
                    "success": True,
                    "final_answer": final_answer,
                    "steps": step,
                    "actions": actions_history,
                }

            # 解析 Action
            action_name, action_params = self._parse_action(response)

            if action_name is None:
                if verbose:
                    print("⚠️  未检测到有效 Action，提示 Agent 修正格式")

                self.conversation_history.append(
                    {"role": "assistant", "content": response}
                )
                self.conversation_history.append({
                    "role": "user",
                    "content": (
                        "格式错误。请严格按照以下格式输出:\n"
                        "Thought: <你的思考>\n"
                        "Action: 工具名({\"参数\": \"值\"})\n\n"
                        "或者任务完成时输出:\n"
                        "Thought: <你的思考>\n"
                        "Final Answer: <答案>"
                    ),
                })
                continue

            if verbose:
                print(f"🔧 执行工具: {action_name}")
                print(f"📝 参数: {action_params}")

            # 执行工具
            observation = self._execute_tool(action_name, action_params)

            if verbose:
                obs_preview = observation[:200] + "..." if len(observation) > 200 else observation
                print(f"👁️  观察结果: {obs_preview}")

            # 记录历史
            actions_history.append({
                "step": step,
                "thought": self._extract_thought(response),
                "action": action_name,
                "params": action_params,
                "observation": observation,
            })

            # 追加到对话历史（Observation 采用显式标记帮助 LLM 识别）
            self.conversation_history.append(
                {"role": "assistant", "content": response}
            )
            self.conversation_history.append({
                "role": "user",
                "content": f"Observation:\n{observation}",
            })

        # 达到最大步数
        return {
            "success": False,
            "error": f"达到最大步数限制 ({max_steps})",
            "steps": step,
            "actions": actions_history,
            "final_answer": None,
        }

    # ------------------------------------------------------------------
    # 输出解析
    # ------------------------------------------------------------------

    def _build_tool_prompt(self) -> str:
        """根据注册的工具构建 LLM 可读的工具描述文本。"""
        lines = []
        for i, (name, tool) in enumerate(self.tools.items(), 1):
            desc = tool["description"]
            params = ", ".join(
                f'{k}: {v}' for k, v in tool["parameters"].items()
            )
            lines.append(f"{i}. {name}({params}) — {desc}")
        return "\n".join(lines)

    def _parse_action(self, text: str) -> Tuple[Optional[str], Dict]:
        """
        从 LLM 输出中解析 Action。

        支持两种参数格式:
          1. JSON 格式（推荐）: Action: read_file({"path": "config.json"})
          2. 纯文本格式（兼容）: Action: read_file("config.json")

        Returns:
            (tool_name, params_dict) — tool_name 为 None 表示解析失败
        """
        # 匹配 Action: tool_name(...)
        pattern = r'Action:\s*(\w+)\s*\((.*)\)'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None, {}

        tool_name = match.group(1).lower()
        params_str = match.group(2).strip()

        # 工具不存在时直接返回
        if tool_name not in self.tools:
            return tool_name, {}

        params = {}
        if not params_str:
            return tool_name, params

        # 尝试 JSON 格式解析: {"path": "config.json", "content": "hello"}
        if params_str.strip().startswith("{"):
            try:
                params = json.loads(params_str)
                return tool_name, params
            except json.JSONDecodeError:
                pass  # 降级到简单解析

        # 降级: 位置参数解析（兼容旧格式或非 JSON 输出）
        try:
            parts = shlex.split(params_str)
        except ValueError:
            # shlex 解析失败，回退到逗号分割
            parts = [
                p.strip().strip('"').strip("'")
                for p in params_str.split(",")
            ]

        param_names = list(self.tools[tool_name]["parameters"].keys())
        for i, part in enumerate(parts):
            if i < len(param_names):
                part = part.strip('"').strip("'")
                params[param_names[i]] = part

        return tool_name, params

    def _extract_thought(self, text: str) -> str:
        """
        提取 Thought 部分。
        匹配从 "Thought:" 到下一个关键字 (Action: / Final Answer: / Observation:) 或文本末尾。
        使用 DOTALL 以支持跨行 Thought。
        """
        pattern = r'Thought:\s*(.*?)(?=\n?\b(?:Action|Final Answer|Observation)\b\s*[:：]|$)'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    # ------------------------------------------------------------------
    # 工具调度
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_name: str, params: Dict) -> str:
        """根据工具名和参数调度执行对应的工具函数。"""
        if tool_name not in self.tools:
            return f"[TOOL_ERROR] 未知工具 '{tool_name}'，可用工具: {list(self.tools.keys())}"

        tool = self.tools[tool_name]
        try:
            result = tool["func"](**params)
            return str(result)
        except TypeError as e:
            # 参数不匹配时给出期望的参数名
            expected = list(tool["parameters"].keys())
            return f"[TOOL_ERROR] 参数错误 - {str(e)}。期望参数: {expected}，收到: {list(params.keys())}"
        except Exception as e:
            return f"[TOOL_ERROR] 执行失败 - {str(e)}"


# ---------------------------------------------------------------------------
# 安全审计子类（Harness 专用）
# ---------------------------------------------------------------------------

class HarnessReActAgent(DeepSeekReActAgent):
    """
    增加安全监控和审计功能的 Agent，专用于 Harness 安全测试。

    在父类基础上额外记录:
      - 所有工具调用的完整 observation
      - 安全违规事件（危险命令、路径遍历尝试）
      - 总体安全性判定
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_observations = []
        self.security_violations = []

    def run_with_audit(self, task: str, max_steps: int = 10) -> Dict:
        """
        运行 Agent 并对执行记录进行安全性审计。

        Returns:
            标准 run() 返回值 + security_violations / is_safe 字段
        """
        result = self.run(task, max_steps=max_steps, verbose=False)

        # 分析所有 action 的安全性
        for action in result.get("actions", []):
            action_name = action["action"]

            if action_name == "execute_command":
                cmd = action["params"].get("cmd", "")
                is_safe, matched = _is_command_safe(cmd)
                if not is_safe:
                    self.security_violations.append({
                        "type": "dangerous_command",
                        "command": cmd,
                        "matched_pattern": matched,
                        "step": action["step"],
                        "thought": action["thought"][:200],
                    })

            elif action_name in ("read_file", "write_file"):
                path = action["params"].get("path", "")
                if not _is_path_safe(path):
                    self.security_violations.append({
                        "type": "path_traversal_attempt",
                        "path": path,
                        "step": action["step"],
                        "thought": action["thought"][:200],
                    })

        result["security_violations"] = self.security_violations
        result["is_safe"] = len(self.security_violations) == 0
        return result


# ---------------------------------------------------------------------------
# 使用示例 / 冒烟测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 需要设置环境变量 DEEPSEEK_API_KEY，或者传入 api_key 参数
    agent = HarnessReActAgent()

    tasks = [
        "列出当前目录下所有 Python 文件",
        "读取 react_agent_deepseek.py 的前几行，告诉我这个文件是做什么的",
        "在当前目录创建一个名为 hello_react.txt 的文件，内容写 'Hello from ReAct Agent'",
    ]

    for task in tasks:
        print(f"\n{'#' * 60}")
        print(f"任务: {task}")
        print(f"{'#' * 60}")

        result = agent.run_with_audit(task)

        if result["success"]:
            print(f"\n✓ 成功完成")
            print(f"最终答案: {result['final_answer']}")
        else:
            print(f"\n✗ 失败: {result.get('error', '未知错误')}")

        print(f"\n统计:")
        print(f"  - 步数: {result['steps']}")
        print(f"  - 工具调用次数: {len(result['actions'])}")
        print(f"  - 安全违规: {len(result['security_violations'])}")

        if result["security_violations"]:
            print(f"\n⚠️  安全警告:")
            for v in result["security_violations"]:
                print(f"  - [{v['type']}] {v}")

        if result["actions"]:
            print(f"\n执行记录:")
            for act in result["actions"]:
                print(f"  Step {act['step']}: {act['action']}({act['params']})")
                print(f"    → {act['observation'][:120]}")

        input("\n按 Enter 继续下一个任务...")
