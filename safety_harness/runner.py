"""Fail-closed rootless Podman runner. Never runs tested code on the host."""
# 宿主机执行器：只负责容器生命周期和证据收集，不导入被测程序。
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from .io import digest
from .policy import validate_harness

# 保留早期入口的默认版本；2026-10-22冻结批次通过参数显式使用v0.2。
DEFAULT_IMAGE = "localhost/bjtu-safety-harness:0.1"


class IsolationError(RuntimeError):
    pass


def _podman(args, timeout=30, binary=False):
    return subprocess.run(["podman", *args], capture_output=True, text=not binary, timeout=timeout)


def preflight(image=DEFAULT_IMAGE):
    # 隔离能力缺失即停止，不降级为宿主机执行；记录镜像ID而非只记可变标签。
    if not shutil.which("podman"):
        raise IsolationError("Podman is unavailable")
    check = _podman(["info", "--format", "{{.Host.Security.Rootless}}"])
    if check.returncode or check.stdout.strip() != "true":
        raise IsolationError("Rootless Podman unavailable; no host execution fallback")
    info = _podman(["image", "inspect", image, "--format", "{{.Id}}"])
    if info.returncode:
        raise IsolationError("Test image missing; build containers/Containerfile first")
    return {"rootless": True, "image_id": info.stdout.strip()}


def classify(payload):
    # 一次违规必须同时有真实事件、专用安全异常和pytest失败退出码。
    # 普通断言失败或混入其他运行错误会使整套测试记为harness_error。
    reports, events = payload.get("reports", []), payload.get("events", [])
    if payload.get("uid") == 0:
        raise IsolationError("Container worker ran as root")
    if not reports or not events:
        return "harness_error"
    if any(r["outcome"] == "failed" and not r["security_failure"] for r in reports):
        return "harness_error"
    verified = any(e.get("violation") for e in events)
    failed = any(r.get("security_failure") for r in reports)
    if verified and failed and payload.get("exit_code") == 1:
        return "violation"
    if not verified and not failed and payload.get("exit_code") == 0:
        # pass只表示本轮未观察到规定的安全违规，不代表功能正确或不存在漏洞。
        return "pass"
    return "harness_error"


def run_harness(target, harness, category, seed=0, timeout=20, image=DEFAULT_IMAGE):
    if category not in {"path", "command", "sql"}:
        raise ValueError("Unsupported category")
    if not 1 <= timeout <= 120:
        raise ValueError("Timeout must be between 1 and 120 seconds")
    target, harness = Path(target).resolve(), Path(harness).resolve()
    if target.stat().st_size > 200_000:
        raise ValueError("Target exceeds 200 KB")
    validate_harness(harness.read_text())
    identity = preflight(image)
    started = time.monotonic()
    result = {"schema_version": 1, "target_sha256": digest(target), "harness_sha256": digest(harness),
              "category": category, "seed": seed, "isolation": identity}
    with tempfile.TemporaryDirectory(prefix="safety-harness-") as temp:
        temp = Path(temp)
        os.chmod(temp, 0o755)
        case = temp / "case"
        case.mkdir(mode=0o755)
        shutil.copyfile(target, case / "target.py")
        shutil.copyfile(harness, case / "test_generated.py")
        for p in case.iterdir():
            p.chmod(0o444)
        # 只挂载当前目标和测试的只读副本；不挂载项目、个人目录或API密钥。
        # 可写数据限制在临时内存文件系统中，并禁网、删权限、限制资源。
        args = [
            "create", "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=65532:65532", "--pids-limit=64",
            "--memory=256m", "--cpus=1", "--log-driver=none",
            "--tmpfs=/tmp:rw,size=64m,mode=1777", "--tmpfs=/work:rw,size=16m,mode=1777",
            "--tmpfs=/out:rw,size=16m,mode=1777",
            "-v", f"{case}:/case:ro,Z",
            identity["image_id"], category, str(seed),
        ]
        created = _podman(args)
        if created.returncode:
            raise IsolationError("Container creation failed (no host fallback)")
        cid = created.stdout.strip()
        try:
            # 先创建再核对实际容器配置，核验通过后才启动目标。
            inspection = _podman(["inspect", cid])
            if inspection.returncode:
                raise IsolationError("Cannot inspect container before execution")
            config = json.loads(inspection.stdout)[0]
            host = config["HostConfig"]
            if (host["NetworkMode"] != "none" or host["Privileged"] or not host["ReadonlyRootfs"]
                    or not any("no-new-privileges" in s for s in host["SecurityOpt"])
                    or config["Config"]["User"] != "65532:65532"
                    or config.get("EffectiveCaps", ["unknown"])
                    or host["Memory"] != 256 * 1024 * 1024
                    or host["PidsLimit"] != 64):
                raise IsolationError("Isolation configuration verification failed: " + json.dumps({
                    "network": host["NetworkMode"], "privileged": host["Privileged"],
                    "read_only": host["ReadonlyRootfs"], "security_opt": host["SecurityOpt"],
                    "user": config["Config"]["User"], "effective_caps": config.get("EffectiveCaps"),
                    "memory": host["Memory"], "pids": host["PidsLimit"]}))
            launched = _podman(["start", cid])
            if launched.returncode:
                raise IsolationError("Container start failed")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # 只读取专用JSON证据文件，不把目标打印的stdout当作判定依据。
                copied = _podman(["cp", f"{cid}:/out/result.json", "-"], binary=True)
                if copied.returncode:
                    state = _podman(["inspect", cid, "--format", "{{.State.Running}}"])
                    if state.stdout.strip() != "true":
                        result.update(status="harness_error", payload=None)
                        break
                    time.sleep(0.2)
                else:
                    try:
                        with tarfile.open(fileobj=io.BytesIO(copied.stdout)) as archive:
                            # podman cp返回tar数据；只读一个限大小的普通文件，不解包到宿主目录。
                            members = archive.getmembers()
                            if len(members) != 1 or not members[0].isfile() or members[0].size > 1_000_000:
                                raise ValueError("Invalid result archive")
                            payload = json.load(archive.extractfile(members[0]))
                        result.update(status=classify(payload), payload=payload)
                    except (ValueError, KeyError, tarfile.TarError, TypeError):
                        result.update(status="harness_error", payload=None)
                    break
            else:
                result.update(status="timeout", payload=None)
        finally:
            # 无论成功、超时还是异常都清理容器。一次性worker无需等待数据落盘，
            # 使用零宽限时间避免每个试验额外等待；清理失败则停止后续执行。
            removed = _podman(["rm", "--force", "--time", "0", cid])
            if removed.returncode:
                raise IsolationError("Test container cleanup failed; stop before further execution")
    result["duration_seconds"] = round(time.monotonic() - started, 4)
    return result
