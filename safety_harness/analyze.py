"""Local AST context + Bandit findings, without importing source code."""
# 静态分析层：只读取和解析源码，不在宿主机导入、运行被测程序。
import ast
import json
import subprocess
import sys
from pathlib import Path

from .io import digest

# 按调用名称标记三类敏感操作，提供待检查线索，不据此直接认定漏洞。
# 这里只匹配名称，没有解析别名、接收者类型或完整数据流，可能漏报或误匹配。
SINKS = {
    "open": "path",
    "read_text": "path",
    "read_bytes": "path",
    "write_text": "path",
    "write_bytes": "path",
    "system": "command",
    "popen": "command",
    "run": "command",
    "Popen": "command",
    "check_output": "command",
    "execute": "sql",
    "executescript": "sql",
}


def analyze_project(path: str) -> dict:
    # 接受单文件或目录；目录扫描跳过隐藏目录、依赖目录和符号链接文件。
    root = Path(path).resolve()
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob("*.py")
        if not any(x.startswith(".") or x in {"__pycache__", "node_modules"} for x in p.relative_to(root).parts)
        and not p.is_symlink()
    )
    if len(files) > 200:
        raise ValueError("Maximum 200 Python files per analysis")
    report = {"schema_version": 1, "files": [], "bandit": {"status": "ok", "findings": []}}
    for p in files:
        if p.suffix != ".py" or p.stat().st_size > 200_000:
            raise ValueError("Only Python text files up to 200 KB are supported")
        source = p.read_text(encoding="utf-8")
        name = p.name if root.is_file() else str(p.relative_to(root))
        record = {"path": name, "sha256": digest(p), "imports": [], "functions": [], "errors": []}
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            record["errors"].append({"type": "syntax_error", "line": e.lineno})
            report["files"].append(record)
            continue
        # 保存顶层导入和函数源码，后续C组用它们组织局部上下文。
        # ast.walk会进入嵌套函数；这里不是精确的函数调用图或依赖切片。
        record["imports"] = [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = []
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    leaf = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                    if leaf in SINKS:
                        calls.append({"line": node.lineno, "call": ast.unparse(node.func), "category": SINKS[leaf]})
            record["functions"].append({
                "name": fn.name, "line": fn.lineno, "end_line": fn.end_lineno,
                "signature": f"{fn.name}({ast.unparse(fn.args)})",
                "sensitive_calls": calls,
                "source": ast.get_source_segment(source, fn),
            })
        # 复用Bandit已有规则，并使用当前Python环境中的固定依赖版本。
        # Bandit返回1可表示发现告警，不能一律当作工具执行失败。
        proc = subprocess.run([sys.executable, "-m", "bandit", "-f", "json", "-q", str(p)],
                              capture_output=True, text=True, timeout=30)
        try:
            bandit = json.loads(proc.stdout)
        except json.JSONDecodeError:
            report["bandit"]["status"] = "tool_error"
            bandit = {}
        if proc.returncode not in (0, 1) or bandit.get("errors"):
            report["bandit"]["status"] = "tool_error"
        for finding in bandit.get("results", []):
            report["bandit"]["findings"].append({
                "path": name,
                **{k: finding.get(k) for k in ("test_id", "issue_text", "issue_severity",
                                             "issue_confidence", "line_number", "issue_cwe")},
            })
        report["files"].append(record)
    return report
