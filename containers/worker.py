"""Runs only inside the container; host code never imports tested modules."""
# 容器内入口：运行pytest、收集安全事件与目标覆盖率，再输出结构化结果。
import json
import os
import sys
import time
from pathlib import Path

import coverage
import pytest
from hypothesis import HealthCheck, settings
from security_probe import Probe, SecurityViolation

events, reports = [], []
category = sys.argv[1]
seed = int(sys.argv[2])
# 限制Hypothesis每个性质测试的生成次数，关闭跨批次样例数据库。
# 单例deadline关闭，但整次容器运行仍由宿主机执行器超时终止。
settings.register_profile("bounded", max_examples=30, deadline=None,
                          database=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
settings.load_profile("bounded")


class Plugin:
    @pytest.fixture
    def probe(self, tmp_path):
        # 把可信probe作为fixture交给测试，目标导入和资源创建都留在容器内。
        return Probe(tmp_path, category, events)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item, call):
        report = yield
        if report.when == "call" or report.failed:
            # 反馈只定位模型自己提交的测试行；不返回目标局部变量或可能含哨兵的异常正文。
            generated_lines = [entry.lineno + 1 for entry in call.excinfo.traceback
                               if Path(str(entry.path)).name == "test_generated.py"] if call.excinfo else []
            reports.append({
                "nodeid": report.nodeid, "phase": report.when, "outcome": report.outcome,
                "security_failure": bool(call.excinfo and call.excinfo.type is SecurityViolation),
                "error_type": call.excinfo.type.__name__ if call.excinfo else None,
                "generated_test_line": generated_lines[-1] if generated_lines else None,
            })
        return report


# 启用分支覆盖，最终只提取target.py，避免把生成测试的覆盖率算成被测代码覆盖率。
cov = coverage.Coverage(branch=True, source=["/case"], data_file="/tmp/.coverage")
cov.start()
code = pytest.main(["/case/test_generated.py", "-q", "-p", "no:cacheprovider",
                    "--basetemp=/tmp/tests", f"--hypothesis-seed={seed}"],
                   plugins=[Plugin(), __import__("hypothesis.extra.pytestplugin", fromlist=[""])])
cov.stop()
cov.save()
cov.json_report(outfile="/tmp/coverage.json")
data = json.loads(Path("/tmp/coverage.json").read_text())
target = next((v for k, v in data.get("files", {}).items() if k.endswith("target.py")), {})
payload = {"exit_code": int(code), "reports": reports, "events": events,
           "coverage": target.get("summary", {}), "uid": os.getuid()}
# 临时文件写完后再重命名，避免宿主机读到半份JSON；不解析任意stdout作为证据。
Path("/out/result.tmp").write_text(json.dumps(payload))
Path("/out/result.tmp").rename("/out/result.json")
# 短暂保留进程，让tmpfs中的结果等待宿主机读取；宿主机最终会强制清理容器。
time.sleep(120)
