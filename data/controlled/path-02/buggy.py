import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    return (Path(root) / value).read_text()
