"""Bounded, explicitly logged recovery of this frozen batch only.

Does not change the frozen experiment. Every failed request remains reserved and
counts toward the conservative cap audit; over-cap matched blocks are excluded.
"""
from pathlib import Path
import datetime
import json
import subprocess

root=Path('results/private/frozen-eval-20261022')
command=['.venv/bin/safety-harness','experiment','--split','eval','--repeats','3',
         '--out',str(root),'--model','deepseek-flash','--input-price','2',
         '--output-price','8','--budget-cny','100','--image','localhost/bjtu-safety-harness:0.2']
for recovery in range(3):
    pending=[p for p in root.glob('*/blocked.json') if not (p.parent/'result.json').exists()]
    if not pending and len(list(root.glob('*/result.json')))==216:break
    if len(pending)!=1:raise SystemExit('Expected exactly one recorded failure')
    failure=json.loads(pending[0].read_text())
    if not failure['reason'].startswith('API transport failure:'):raise SystemExit('Not a transport failure')
    event={'kind':'bounded_transport_recovery','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'trial':pending[0].parent.name,'failure':failure,'ambiguous_requests':1,
           'action':'Resume unchanged frozen configuration. Retain failed reservation. Exclude over-cap matched blocks; report full results too.'}
    with (root/'infrastructure-events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
    print(f"Recovery {recovery+1}/3: {event['trial']}",flush=True)
    with (root/'run.log').open('a') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode==0:break
else:
    raise SystemExit('Three bounded recoveries exhausted; inspect latest pending failure')
