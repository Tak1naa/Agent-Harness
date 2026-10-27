import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    base = Path(root).resolve()
    p = (base / unquote(value)).resolve()
    if not p.is_relative_to(base):
        raise ValueError("outside")
    return p.read_text()
