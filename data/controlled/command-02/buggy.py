import os
import shlex
import subprocess

def handle(value: str, root: str):
    return subprocess.run("echo " + value, shell=True, capture_output=True).stdout
