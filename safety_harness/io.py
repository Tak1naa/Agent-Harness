"""Small, auditable file helpers. Never import a target on the host."""
# 通用文件操作：JSON读写、字节哈希和工作区路径边界检查。
import hashlib
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    # 保留中文并缩进，便于成员直接审查原始证据；调用方决定输出内容和保存位置。
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    # 对原始字节计算SHA-256，所以注释、换行和编码变化也会改变指纹。
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def within(root, path):
    # 先解析..和符号链接，再检查目录归属，不能用字符串前缀判断路径是否越界。
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path is outside the configured workspace")
    return path
