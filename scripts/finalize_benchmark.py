"""从原始日志重建一次受控 benchmark；网络失败与不完整结果不隐藏。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from audit_model_run import audit
from verify_model_evidence import verify
from safety_harness.experiment import summarize_run
from safety_harness.io import digest, read_json, write_json


def finalize(root, output):
    root, output = Path(root), Path(output)
    full = audit(root)
    verification = verify(root, 'data/controlled')
    if verification['status'] != 'passed':
        raise ValueError('Incomplete or inconsistent run; see evidence-verification.json')
    provenance = read_json(root / 'provenance.json')
    if not all(digest(path) == expected for path, expected in provenance['source_sha256'].items()):
        raise ValueError('Source changed during benchmark')
    events_path = root / 'infrastructure-events.jsonl'
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    ambiguous = Counter()
    for event in events:
        ambiguous[event['trial']] += event['ambiguous_requests']
    records = [read_json(p) for p in sorted(root.glob('*/result.json'))]
    excluded = {(r['id'], r['repeat']) for r in records
                if len(r['attempts']) + ambiguous[f"{r['id']}-{r['repeat']}-{r['group']}"] > 3}
    primary = [r for r in records if (r['id'], r['repeat']) not in excluded]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for index, record in enumerate(primary):
            write_json(Path(tmp) / f'{index}.json', record)
        sensitivity = summarize_run(tmp)
        (output / 'within-budget-summary.csv').write_bytes((Path(tmp) / 'summary.csv').read_bytes())
    ledger = read_json('results/private/budget.json')
    report = {
        'kind': 'controlled_benchmark', 'full_summary': full['summary'],
        'within_budget_summary': sensitivity,
        'excluded_matched_blocks': [{'sample': x, 'repeat': y} for x, y in sorted(excluded)],
        'transport_events': events, 'ambiguous_requests': sum(ambiguous.values()),
        'retry_policy': provenance['retry_policy'],
        'api_responses': full['api_responses'], 'returned_models': full['returned_models'],
        'usage': full['usage'], 'usage_cost_upper_cny': full['usage_cost_upper_cny'],
        'cost_note': full['cost_note'],
        'shared_ledger_reservations_delta': len(ledger['reservations']) - provenance['reservations_before'],
        'shared_ledger_reserved_delta_cny': ledger['reserved_cny'] - provenance['budget_before_cny'],
        'ledger_note': 'Shared ledger delta assumes no unrelated concurrent API runs; reservation is not actual spend.',
        'evidence_verification': verification,
        'limitations': '24 synthetic template variants; one repetition; descriptive comparison, not public leaderboard performance or statistical significance.',
    }
    write_json(output / 'analysis.json', report)
    write_json(output / 'full-audit.json', full)
    write_json(output / 'evidence-verification.json', verification)
    write_json(output / 'config.json', read_json(root / 'config.json'))
    write_json(output / 'provenance.json', provenance)
    (output / 'full-summary.csv').write_bytes((root / 'summary.csv').read_bytes())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.run, args.out), ensure_ascii=False, indent=2))
