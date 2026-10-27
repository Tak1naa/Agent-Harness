# 数据冻结校验：核对清单及每个样本文件的字节哈希，不执行目标代码。
from pathlib import Path
from .io import digest, read_json


def verify_dataset(root):
    root = Path(root)
    frozen, manifest = read_json(root / "freeze.json"), read_json(root / "manifest.json")
    if digest(root / "manifest.json") != frozen["manifest_sha256"]:
        raise ValueError("Frozen manifest changed")
    cases = manifest["cases"]
    if len(cases) != 30 or len({c["id"] for c in cases}) != 30:
        raise ValueError("Expected 30 unique pairs")
    # 修复版、参考测试或任务文本一旦变化也会被检出，避免评测中途悄悄改样本。
    for case in cases:
        for name, expected in case["files"].items():
            if digest(root / case["id"] / name) != expected:
                raise ValueError(f"Frozen sample changed: {case['id']}/{name}")
    return {"status": "passed", "pairs": len(cases),
            "development": sum(c["split"] == "dev" for c in cases),
            "evaluation": sum(c["split"] == "eval" for c in cases)}
