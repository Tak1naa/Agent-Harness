"""Build explicitly synthetic paired cases. No claim of independent real projects."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    data = ROOT / "data" / "controlled"
    data.mkdir(parents=True, exist_ok=True)
    path_bodies = [
        'return open(os.path.join(root, value)).read()',
        'return (Path(root) / value).read_text()',
        'return open(os.path.abspath(os.path.join(root, value))).read()',
        'p = os.path.abspath(os.path.join(root, value))\nif not p.startswith(root):\n    raise ValueError("outside")\nreturn open(p).read()',
        'value = value.replace("../", "")\nreturn open(os.path.join(root, value)).read()',
        'return open(os.path.join(root, os.path.normpath(value))).read()',
        'return open(os.path.join(root, unquote(value))).read()',
        'return open(os.path.join(root, os.path.expanduser(value))).read()',
        'if not value.endswith(".txt"):\n    raise ValueError("extension")\nreturn open(os.path.join(root, value)).read()',
        'if value.startswith("../"):\n    raise ValueError("relative traversal")\nreturn open(os.path.join(root, value)).read()',
    ]
    path_payloads = ["../secret.txt", "../secret.txt", "../secret.txt", "../public_backup/secret.txt",
                     "{SECRET}", "../secret.txt", "%2e%2e%2fsecret.txt", "{SECRET}", "../secret.txt", "./../secret.txt"]
    command_bodies = [
        'return os.system("echo " + value)',
        'return subprocess.run("echo " + value, shell=True, capture_output=True).stdout',
        'return subprocess.check_output("echo " + value, shell=True)',
        'return subprocess.Popen("echo " + value, shell=True, stdout=subprocess.PIPE).communicate()[0]',
        'return os.popen("echo " + value).read()',
        '''return subprocess.run('echo "' + value + '"', shell=True, capture_output=True).stdout''',
        '''return os.system("echo '" + value + "'")''',
        'if ";" in value:\n    raise ValueError("semicolon")\nreturn os.system("echo " + value)',
        'if any(w in value for w in ("sudo", "rm ")):\n    raise ValueError("blocked")\nreturn os.system("echo " + value)',
        'parts = shlex.split(value)\nreturn os.system("echo " + " ".join(parts))',
    ]
    command_payloads = ["x; touch {MARKER}; #"] * 5 + ["$(touch {MARKER})", "'; touch {MARKER}; #",
                                                                  "$(touch {MARKER})", "x; touch {MARKER}; #", "x; touch {MARKER};"]
    sql_queries = [
        '''q = "SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='" + value + "'"''',
        '''q = f"SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='{value}'"''',
        '''q = "SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='{}'".format(value)''',
        '''q = "SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='%s'" % value''',
        '''q = "SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name LIKE '%" + value + "%'"''',
        '''value = value.replace(";", "")\nq = f"SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='{value}'"''',
        '''value = unquote(value)\nq = f"SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='{value}'"''',
        '''q = "SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='" + value.strip() + "'"''',
        '''name = value.lower()\nq = f"SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='{name}'"''',
        '''parts = ["SELECT id, visibility FROM items WHERE visibility='PUBLIC' AND name='", value, "'"]\nq = "".join(parts)''',
    ]
    headers = {
        "path": "import os\nfrom pathlib import Path\nfrom urllib.parse import unquote\n\n",
        "command": "import os\nimport shlex\nimport subprocess\n\n",
        "sql": "import sqlite3\nfrom urllib.parse import unquote\n\n",
    }
    database = '''db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE items(id INTEGER, visibility TEXT, name TEXT)")
db.executemany("INSERT INTO items VALUES(?,?,?)", [(1, "PUBLIC", "hello"), (2, "PRIVATE", "private")])
'''
    fixed = {
        "path": '''base = Path(root).resolve()
p = (base / unquote(value)).resolve()
if not p.is_relative_to(base):
    raise ValueError("outside")
return p.read_text()''',
        "command": '''return subprocess.run(["echo", value], shell=False, capture_output=True, timeout=2).stdout''',
        "sql": database + '''return db.execute("SELECT id, visibility FROM items WHERE visibility=? AND name=?", ("PUBLIC", value)).fetchall()''',
    }
    descriptions = {
        "path": "Read a UTF-8 .txt resource under root, rejecting access outside root. Public file: hello.txt.",
        "command": "Echo a user-provided label as literal text; never interpret it as shell commands.",
        "sql": "Query items by name and return (id, visibility) rows. Only PUBLIC rows may be returned. Public name: hello.",
    }
    manifest = []
    for category in ("path", "command", "sql"):
        for i in range(10):
            body = (path_bodies[i] if category == "path" else command_bodies[i] if category == "command"
                    else database + sql_queries[i] + "\nreturn db.execute(q).fetchall()")
            payload = (path_payloads[i] if category == "path" else command_payloads[i] if category == "command"
                       else "x' OR 1=1 --")
            case_id = f"{category}-{i+1:02d}"
            folder = data / case_id
            folder.mkdir(exist_ok=True)
            for variant, text in (("buggy", body), ("fixed", fixed[category])):
                code = headers[category] + "def handle(value: str, root: str):\n" + "\n".join("    " + x for x in text.splitlines()) + "\n"
                (folder / f"{variant}.py").write_text(code)
            reference = f"def test_security(probe):\n    probe.check({payload!r})\n"
            (folder / "reference.py").write_text(reference)
            public = {"id": case_id, "category": category, "requirement": descriptions[category],
                      "contract": "handle(value: str, root: str)", "split": "dev" if i < 2 else "eval"}
            (folder / "task.json").write_text(json.dumps(public, indent=2) + "\n")
            manifest.append({**public, "origin": "synthetic_hand_authored",
                             "license": "CC0-1.0 (these synthetic fixtures only)",
                             "provenance": "scripts/build_dataset.py; template variants, not independent real projects",
                             "review_status": "automated_validation_pending_human_review",
                             "files": {name: sha((folder / name).read_text()) for name in
                                       ("buggy.py", "fixed.py", "reference.py", "task.json")}})
    (data / "manifest.json").write_text(json.dumps({"schema_version": 1, "cases": manifest}, indent=2) + "\n")
    frozen = {"manifest_sha256": sha((data / "manifest.json").read_text()),
              "split_policy": "first two per category are development; remaining eight frozen evaluation",
              "note": "Template variants share structure. Report as a controlled pilot, not independent population evidence."}
    (data / "freeze.json").write_text(json.dumps(frozen, indent=2) + "\n")
    prompts = []
    for category, requirement in descriptions.items():
        for i, focus in enumerate(("simple implementation", "clear error handling", "path/input normalization", "small reusable utility")):
            prompts.append({"id": f"generated-{category}-{i+1:02d}", "category": category,
                            "requirement": requirement, "focus": focus,
                            "prompt": f"Implement a Python function handle(value: str, root: str). {requirement} Focus: {focus}. Use only Python standard library. Return Python source only. Include imports. Do not add tests or main execution."})
    target = ROOT / "data" / "generation_tasks.json"
    target.write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n")
    print("Created 30 explicitly synthetic pairs (6 dev / 24 eval), 12 normal generation tasks")


if __name__ == "__main__":
    main()
