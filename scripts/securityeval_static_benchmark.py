"""对固定版本 SecurityEval 做静态分析；不执行或导入样本。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
import json
from pathlib import Path
import re

from safety_harness.analyze import analyze_project
from safety_harness.io import digest, write_json


def run(dataset, source, output):
    dataset, source, output = Path(dataset), Path(source), Path(output)
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    ids = [row['ID'] for row in rows]
    if len(set(ids)) != len(ids) or not all(re.fullmatch(r'CWE-\d+_[\w.-]+\.py', i) for i in ids):
        raise ValueError('Unexpected or duplicate sample IDs')
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    # 只分析原始 Insecure_code，不补齐语法、不筛除不支持的样本。
    for row in rows:
        (inputs / row['ID']).write_text(row['Insecure_code'])

    def analyze(row):
        report = analyze_project(str(inputs / row['ID']))
        write_json(output / 'analysis' / (row['ID'] + '.json'), report)
        expected_cwe = int(row['ID'].split('_')[0].split('-')[1])
        findings = report['bandit']['findings']
        calls = [call for f in report['files'] for fn in f['functions'] for call in fn['sensitive_calls']]
        return {
            'id': row['ID'], 'declared_cwe': expected_cwe,
            'source_sha256': digest(inputs / row['ID']),
            'syntax_valid': not any(f['errors'] for f in report['files']),
            'bandit_status': report['bandit']['status'],
            'bandit_any_alert': bool(findings),
            'bandit_exact_cwe_alert': any((f.get('issue_cwe') or {}).get('id') == expected_cwe for f in findings),
            'ast_sensitive_call': bool(calls),
            'ast_categories': sorted({call['category'] for call in calls}),
            'bandit_rule_ids': sorted({f['test_id'] for f in findings}),
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(analyze, rows))
    report = {
        'kind': 'securityeval_static_diagnostic', 'source': json.loads(source.read_text()),
        'dataset_sha256': digest(dataset), 'analyzer_sha256': digest(Path('safety_harness/analyze.py')),
        'bandit_version': version('bandit'), 'samples': len(records),
        'syntax_valid': sum(r['syntax_valid'] for r in records),
        'syntax_invalid': sum(not r['syntax_valid'] for r in records),
        'bandit_tool_errors': sum(r['bandit_status'] != 'ok' for r in records),
        'bandit_any_alert': sum(r['bandit_any_alert'] for r in records),
        'bandit_exact_cwe_alert': sum(r['bandit_exact_cwe_alert'] for r in records),
        'ast_sensitive_call': sum(r['ast_sensitive_call'] for r in records),
        'either_static_signal': sum(r['bandit_any_alert'] or r['ast_sensitive_call'] for r in records),
        'declared_cwe_counts': dict(Counter(str(r['declared_cwe']) for r in records)),
        'records': records,
        'limitations': [
            'Static diagnostics only; zero target executions and zero LLM calls.',
            'Any-alert and AST sink presence are not confirmed vulnerability detection.',
            'Exact CWE matching misses parent/child relations and is diagnostic, not semantic correctness.',
            'Upstream Insecure_code labels are used without independent validation.',
            'No safe negatives: precision, false-positive rate and accuracy are undefined.',
            'No official SecurityEval leaderboard score or full-harness dynamic score is claimed.',
        ],
    }
    write_json(output / 'summary.json', report)
    return {k: v for k, v in report.items() if k not in {'records', 'declared_cwe_counts'}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.source, args.out), ensure_ascii=False, indent=2))
