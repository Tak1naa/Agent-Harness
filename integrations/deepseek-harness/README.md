# DeepSeek Harness 接入记录

上游源码审阅固定至 `687f282e8625c6b8d11ff58211a90524be2e4317`，Python SDK/runtime 固定 `0.2.1rc2`。SDK和MCP服务使用独立虚拟环境，避免Pydantic版本冲突。

```bash
python3.12 -m venv .venv-dsh
.venv-dsh/bin/python -m pip install deepseek-harness-sdk==0.2.1rc2
.venv-dsh/bin/python scripts/check_dsh.py
```

脚本根据当前目录生成忽略的 `.dsh/safety.patch.yml`，启动官方SDK并要求MCP启动失败时报错；不发送模型prompt，不需要Key。输出记录 `results/dsh-integration.json`。三个工具：`analyze_project`、`run_harness`、`summarize_run`。路径限制在 HARNESS_WORKSPACE 下，动态执行仍由Podman完成。

当前已验证SDK initialize和独立MCP initialize/list_tools/call_tool。尚未验证带模型的工具选择和完整agent回合；主对照实验使用有预算约束的直接API，避免上游工具和重试改变预算。该SDK检查脚本不是正式实验入口。

依据：[官方MCP插件](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/mcp/mcp-client/README.md)、[官方Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/python/sdk/README.md)。
