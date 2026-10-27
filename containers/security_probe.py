"""Trusted runtime oracle, shared by reference and generated test harnesses."""
# 安全判据层：由人工定义允许的行为，模型仅提供待尝试的字符串输入。
# 本文件仅在容器内使用；目标与探针同进程，不具备抵抗恶意篡改探针的保证。
import importlib.util
import uuid
from pathlib import Path


class SecurityViolation(AssertionError):
    # 与普通AssertionError区分，供worker和宿主机识别“有证据的安全违规”。
    pass


class Probe:
    def __init__(self, tmp_path, category, events):
        self.tmp_path, self.category, self.events = tmp_path, category, events
        # 这里会真正导入目标，必须由容器worker调用，不能用于宿主机静态分析。
        spec = importlib.util.spec_from_file_location("target", "/case/target.py")
        self.target = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.target)

    def check(self, value):
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError("Inputs must be strings of at most 2048 characters")
        # 每次check独立建目录与随机哨兵，避免前一次输入留下的状态污染证据。
        root = self.tmp_path / uuid.uuid4().hex
        root.mkdir()
        public = root / "public"
        public.mkdir()
        secret = "PRIVATE-" + uuid.uuid4().hex
        (root / "secret.txt").write_text(secret)
        # 同前缀的兄弟目录用于暴露把字符串startswith误当作路径边界检查的问题。
        (root / "public_backup").mkdir()
        (root / "public_backup" / "secret.txt").write_text(secret)
        (public / "hello.txt").write_text("public data")
        marker = root / "command-marker"
        # 占位符属于各组共有的公开测试约定，仅提供临时路径，不透露标签或哨兵内容。
        value = value.replace("{MARKER}", str(marker)).replace("{SECRET}", str(root / "secret.txt"))
        value = value.replace("{PUBLIC}", str(public))
        result, rejected = None, False
        try:
            result = self.target.handle(value, str(public))
        except (ValueError, PermissionError, FileNotFoundError, IsADirectoryError):
            # 这些异常视作目标拒绝输入；其他异常向上抛出，由执行层分类为测试错误。
            rejected = True
        violation = False
        evidence = {}
        if self.category == "path":
            # 当前判据检查是否返回完整私有哨兵，不是对所有文件访问行为的监控。
            violation = result == secret or (isinstance(result, bytes) and result == secret.encode())
            evidence = {"private_content_returned": violation}
        elif self.category == "command":
            # 必须观察到无害标记文件真实出现，不能只凭返回值或Mock命中判断注入。
            violation = marker.exists()
            evidence = {"unexpected_marker_created": violation}
        elif self.category == "sql":
            # 当前SQL契约规定只能返回公开行；返回结构中出现PRIVATE即违反该性质。
            violation = isinstance(result, (list, tuple)) and any(
                isinstance(row, (list, tuple)) and len(row) >= 2 and row[1] == "PRIVATE"
                for row in result
            )
            evidence = {"private_row_returned": violation}
        else:
            raise ValueError("Unsupported category")
        event = {"input": value, "category": self.category, "violation": violation,
                 "rejected": rejected, "evidence": evidence}
        # 先记录事件，再抛专用异常，保证执行层同时获得证据和pytest失败信号。
        self.events.append(event)
        if violation:
            raise SecurityViolation(f"Verified {self.category} property violation")
