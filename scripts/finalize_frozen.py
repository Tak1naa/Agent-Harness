"""Rebuild frozen results and conservatively audit ambiguous transport requests."""
import json
import hashlib
import tempfile
from pathlib import Path
from collections import Counter
from safety_harness.experiment import summarize_run
from audit_model_run import audit
from verify_model_evidence import verify

ROOT = Path('results/private/frozen-eval-20261022')
OUT = Path('results/frozen-20261022')

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def main():
    records = [json.loads(p.read_text()) for p in ROOT.glob('*/result.json')]
    assert len(records) == 216, 'Complete all trials before finalization'
    a = audit(ROOT)
    v = verify(ROOT, Path('data/controlled'))
    assert v['status'] == 'passed', v
    provenance = json.loads((ROOT/'provenance.json').read_text())
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
               for p,h in provenance['source_sha256'].items()), 'Frozen source changed'
    events = [json.loads(x) for x in (ROOT/'infrastructure-events.jsonl').read_text().splitlines()]
    ambiguous = Counter()
    for e in events: ambiguous[e['trial']] += e['ambiguous_requests']
    excluded, affected = set(), []
    for r in records:
        name = f"{r['id']}-{r['repeat']}-{r['group']}"
        if name not in ambiguous: continue
        count = len(r['attempts']) + ambiguous[name]
        affected.append({'trial':name,'saved_responses':len(r['attempts']),
                         'ambiguous_requests':ambiguous[name],'conservative_requests':count,
                         'over_cap':count > 3})
        if count > 3: excluded.add((r['id'],r['repeat']))
    primary = [r for r in records if (r['id'],r['repeat']) not in excluded]
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp)
        for i,r in enumerate(primary):save(t/f'{i}.json',r)
        summary = summarize_run(t)
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'primary-summary.csv').write_bytes((t/'summary.csv').read_bytes())
    diagnostics={}
    for group in 'ABC':
        rows=[r for r in primary if r['group']==group]
        diagnostics[group]={'responses':sum(len(r['attempts']) for r in rows),
            'first_attempt_violation':sum(r['attempts'][0]['observed']['status']=='violation' for r in rows),
            'categories':{cat:{'confirmed':sum(r['confirmed'] for r in rows if r['category']==cat),
                              'denominator':sum(r['category']==cat for r in rows)} for cat in ['path','command','sql']}}
    result={'kind':'frozen_final_analysis','full_summary':a['summary'],'primary_summary':summary,
            'primary_diagnostics':diagnostics,'transport_events':events,'affected_trials':affected,
            'excluded_matched_blocks':[{'sample':x,'repeat':y} for x,y in sorted(excluded)],
            'exclusion_rule':'Count every ambiguous transport failure as a request. If total exceeds 3, exclude its entire matched A/B/C block from primary comparison; retain all raw trials.',
            'exclusion_timing':'Rule recorded after first transport failure and before its retry; not part of original preregistration. Report full results alongside sensitivity analysis.',
            'api_responses':a['api_responses'],'ambiguous_requests':sum(ambiguous.values()),
            'usage':a['usage'],'usage_cost_upper_cny':a['usage_cost_upper_cny'],
            'cost_note':a['cost_note'],'evidence_verification':v,'frozen_source_unchanged':True,
            'independent_sample_note':'24 synthetic template variants, not 216 independent programs. Descriptive results only.'}
    save(OUT/'analysis.json',result)
    save(OUT/'full-audit.json',a)
    save(OUT/'provenance.json',provenance)
    save(OUT/'config.json',json.loads((ROOT/'config.json').read_text()))
    save(OUT/'evidence-verification.json',v)
    save(ROOT/'infrastructure-audit.json',{'affected_trials':affected,'excluded_matched_blocks':result['excluded_matched_blocks']})
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
