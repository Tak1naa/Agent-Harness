import os
import shlex
import subprocess

def handle(value: str, root: str):
    return os.popen("echo " + value).read()
