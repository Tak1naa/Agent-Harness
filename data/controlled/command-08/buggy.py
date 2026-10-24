import os
import shlex
import subprocess

def handle(value: str, root: str):
    if ";" in value:
        raise ValueError("semicolon")
    return os.system("echo " + value)
