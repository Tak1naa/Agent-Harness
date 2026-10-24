import os
import shlex
import subprocess

def handle(value: str, root: str):
    return subprocess.Popen("echo " + value, shell=True, stdout=subprocess.PIPE).communicate()[0]
