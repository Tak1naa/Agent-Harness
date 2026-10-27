import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    if value.startswith("../"):
        raise ValueError("relative traversal")
    return open(os.path.join(root, value)).read()
