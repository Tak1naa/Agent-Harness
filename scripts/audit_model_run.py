"""Rebuild a model-run audit without printing credentials or raw responses."""
import argparse,json
from collections import Counter
from pathlib import Path
from safety_harness.experiment import summarize_run
from safety_harness.io import write_json


def audit(root):
    root=Path(root)
    summary=summarize_run(root)
    responses=[json.loads(p.read_text()) for p in root.glob('*/response-*.json')]
    trials=[json.loads(p.read_text()) for p in root.glob('*/result.json')]
    usage=Counter()
    missing=0
    for r in responses:
        u=r.get('usage',{})
        if not all(k in u for k in ('prompt_tokens','completion_tokens')):missing+=1
        for k in ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'):
            usage[k]+=u.get(k,0)
    rate_config=json.loads((root/'config.json').read_text())
    upper=(usage['prompt_tokens']*rate_config['input_price_per_million']+usage['completion_tokens']*rate_config['output_price_per_million'])/1e6
    matrix=[]
    for case in sorted({r['id'] for r in trials}):
        row={'sample':case}
        for group in 'ABC':
            rows=[r for r in trials if r['id']==case and r['group']==group]
            row[group]=[{'repeat':r['repeat'],'confirmed':r['confirmed'],'runnable':r['runnable'],
                         'buggy_status':r.get('buggy',{}).get('status','invalid_harness'),
                         'fixed_status':r.get('fixed',{}).get('status','not_run'),
                         'attempts':len(r['attempts'])} for r in rows]
        matrix.append(row)
    group_diagnostics={}
    for group in 'ABC':
        rows=[r for r in trials if r['group']==group]
        statuses=Counter(r.get('fixed',{}).get('status','not_run') for r in rows)
        evaluated=statuses['pass']+statuses['violation']
        group_diagnostics[group]={
            'completed_trials':len(rows),
            'fixed_statuses':dict(statuses),
            'fixed_valid_evaluations':evaluated,
            'fixed_unresolved':len(rows)-evaluated,
            'fixed_observed_false_positive_rate':statuses['violation']/evaluated if evaluated else None,
            'attempts':sum(len(r['attempts']) for r in rows),
            'first_attempt_buggy_violation':sum(r['attempts'][0]['observed']['status']=='violation' for r in rows),
        }
    result={'kind':'model_run_audit','group_diagnostics':group_diagnostics,'summary':summary,'api_responses':len(responses),
            'usage':dict(usage),'missing_usage_responses':missing,
            'usage_cost_upper_cny':round(upper,6),
            'reserved_upper_cny':round(sum(r.get('reserved_cny',0) for r in responses),6),
            'cost_note':'Upper estimate from documented peak rates with all input treated uncached; actual platform billing can be lower. Failed requests absent from responses remain charged to shared reservation ledger.',
            'finish_reasons':dict(Counter(r.get('finish_reason') for r in responses)),
            'returned_models':dict(Counter(r.get('response_model') for r in responses)),
            'attempt_statuses':dict(Counter(a['observed']['status'] for r in trials for a in r['attempts'])),
            'cases':matrix}
    write_json(root/'audit.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path');args=p.parse_args()
    print(json.dumps(audit(args.path),ensure_ascii=False,indent=2))
