import os
import shlex
import subprocess

def handle(value: str, root: str):
    return os.system("echo '" + value + "'")
