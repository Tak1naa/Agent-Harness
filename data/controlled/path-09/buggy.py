import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    if not value.endswith(".txt"):
        raise ValueError("extension")
    return open(os.path.join(root, value)).read()
