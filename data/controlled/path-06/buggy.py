import os
from pathlib import Path
from urllib.parse import unquote

def handle(value: str, root: str):
    return open(os.path.join(root, os.path.normpath(value))).read()
