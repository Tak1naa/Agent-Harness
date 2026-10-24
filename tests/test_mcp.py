import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_protocol():
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-m", "safety_harness.mcp_server"],
                                       env={"PATH": os.environ["PATH"],
                                            "HARNESS_WORKSPACE": str(Path(__file__).resolve().parents[1])})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert names == {"analyze_project", "run_harness", "summarize_run"}
                result = await session.call_tool("analyze_project", {"path": "data/controlled/sql-01/buggy.py"})
                assert not result.isError
                denied = await session.call_tool("analyze_project", {"path": "/etc/passwd"})
                assert denied.isError
    asyncio.run(check())
