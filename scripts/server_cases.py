"""Server verification uses only standard-library host orchestration."""
import json
from pathlib import Path
from safety_harness.runner import preflight, run_harness
out=Path('results/server');out.mkdir(parents=True,exist_ok=True)
(out/'environment.json').write_text(json.dumps(preflight(),indent=2))
for category in ('path','command','sql'):
    case=Path('data/controlled')/f'{category}-01'
    record={v:run_harness(case/f'{v}.py',case/'reference.py',category) for v in ('buggy','fixed')}
    (out/f'{category}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(category,record['buggy']['status'],record['fixed']['status'],flush=True)
    assert record['buggy']['status']=='violation' and record['fixed']['status']=='pass'
