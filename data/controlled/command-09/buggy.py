import os
import shlex
import subprocess

def handle(value: str, root: str):
    if any(w in value for w in ("sudo", "rm ")):
        raise ValueError("blocked")
    return os.system("echo " + value)
