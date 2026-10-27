import os
import shlex
import subprocess

def handle(value: str, root: str):
    return subprocess.check_output("echo " + value, shell=True)
