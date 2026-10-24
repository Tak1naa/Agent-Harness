"""Build a deliberate allowlist archive; never include secrets or proposal originals."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parents[1]
paths=[]
for directory in ['safety_harness','containers','scripts','tests','data/controlled','data/generated','docs','integrations','results/reference','results/server','results/static','results/frozen-20261022','results/private/frozen-eval-20261022','deliverables']:
 for p in (root/directory).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.zip'}:paths.append(p)
for file in ['README.md','.gitignore','.dockerignore','.env.example','pyproject.toml','requirements.lock.txt','react_agent_deepseek.py','data/README.md','data/generation_tasks.json','data/generation_tasks_v2.json','results/unit-tests.xml','results/container-tests.xml','results/unit-tests-frozen-20261022.xml','results/container-tests-frozen-20261022.xml','results/dsh-integration.json','results/verification.json','results/README.md']:
 p=root/file
 if p.exists():paths.append(p)
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
archive=root/'deliverables/中期研究交付包-20261022.zip'
# Read only the configured secret for an in-memory exclusion check. Never emit it.
from dotenv import dotenv_values
key=dotenv_values(root/'.env').get('DEEPSEEK_API_KEY','')
if key:
 assert all(key.encode() not in p.read_bytes() for p in set(paths)), 'Secret found in package input; packaging stopped'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(set(paths)):z.write(p,'Agent-Harness/'+str(p.relative_to(root)))
 z.writestr('Agent-Harness/SHA256SUMS.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all('/.env' not in n or n.endswith('.env.example') for n in z.namelist())
 assert not any('.venv' in n or n.endswith('.pdf') for n in z.namelist())
print(json.dumps({'archive':str(archive),'files':len(manifest),'bytes':archive.stat().st_size,'integrity':'passed'},ensure_ascii=False))
