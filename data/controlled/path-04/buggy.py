import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    p = os.path.abspath(os.path.join(root, value))
    if not p.startswith(root):
        raise ValueError("outside")
    return open(p).read()
