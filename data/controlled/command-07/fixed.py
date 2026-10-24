import os
import shlex
import subprocess

def handle(value: str, root: str):
    return subprocess.run(["echo", value], shell=False, capture_output=True, timeout=2).stdout
