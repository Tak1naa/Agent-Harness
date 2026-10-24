import os
import shlex
import subprocess

def handle(value: str, root: str):
    parts = shlex.split(value)
    return os.system("echo " + " ".join(parts))
