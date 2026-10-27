"""MCP only exposes bounded project operations, never arbitrary shell commands."""
# MCP适配层：让外部编排框架调用已有核心功能，不额外提供任意shell执行工具。
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from .analyze import analyze_project as analyze
from .experiment import summarize_run as summarize
from .io import within
from .runner import run_harness as run

# 所有工具参数都先经过工作区路径检查，再交给相同的分析器或隔离执行器。
# 下方工具docstring会作为协议描述暴露，中文说明不改动这些对外描述。
ROOT = Path(os.environ.get("HARNESS_WORKSPACE", os.getcwd())).resolve()
mcp = FastMCP("bjtu-safety-harness")


@mcp.tool()
def analyze_project(path: str) -> dict:
    """Analyze Python source under workspace, without executing it."""
    return analyze(str(within(ROOT, ROOT / path)))


@mcp.tool()
def run_harness(target: str, harness: str, category: str, seed: int = 0) -> dict:
    """Run a constrained harness in a verified rootless offline container."""
    return run(within(ROOT, ROOT / target), within(ROOT, ROOT / harness), category, seed)


@mcp.tool()
def summarize_run(path: str) -> dict:
    """Regenerate experiment metrics from existing local result records."""
    return summarize(within(ROOT, ROOT / path))


def main():
    # 使用标准输入/输出交换MCP消息，适合由DeepSeek Harness等框架启动子进程接入。
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
