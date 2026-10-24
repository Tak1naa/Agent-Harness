import json
from pathlib import Path
from unittest.mock import patch

import pytest

from safety_harness.analyze import analyze_project
from safety_harness.dataset import verify_dataset
from safety_harness.experiment import summarize_run
from safety_harness.io import within, write_json
from safety_harness.model import Budget, ModelError
from safety_harness.policy import validate_harness
from safety_harness.prompts import build_prompt
from safety_harness.runner import IsolationError, classify, preflight

ROOT = Path(__file__).resolve().parents[1]


def test_dataset_frozen():
    assert verify_dataset(ROOT / "data/controlled") == {
        "status": "passed", "pairs": 30, "development": 6, "evaluation": 24}


def test_bandit_and_context(tmp_path):
    p = tmp_path / "target.py"
    p.write_text("import subprocess\n\ndef handle(value, root):\n    return subprocess.run(value, shell=True)\n")
    report = analyze_project(str(p))
    assert report["bandit"]["status"] == "ok"
    assert "B602" in {r["test_id"] for r in report["bandit"]["findings"]}
    assert report["files"][0]["functions"][0]["sensitive_calls"][0]["category"] == "command"


def test_syntax_is_not_executed(tmp_path):
    p = tmp_path / "target.py"
    p.write_text("def broken(")
    report = analyze_project(str(p))
    assert report["files"][0]["errors"][0]["type"] == "syntax_error"


@pytest.mark.parametrize("source", [
    "import os\nos.system('true')",
    "def test_bad(probe):\n    assert False",
    "def test_bad(probe):\n    probe.__class__",
    "def test_bad(probe):\n    open('/tmp/fake', 'w')",
    "def test_bad(probe):\n    probe.check(__import__('os'))",
    "def test_bad(probe):\n    probe.check(value for value in [])",
    "@print('unsafe')\ndef test_bad(probe):\n    probe.check('x')",
])
def test_harness_rejects_fabrication_and_escape(source):
    with pytest.raises(ValueError):
        validate_harness(source)


def test_hypothesis_harness_accepted():
    validate_harness("""from hypothesis import given, strategies as st
@given(value=st.sampled_from(["hello.txt", "../secret.txt"]))
def test_safety(probe, value):
    probe.check(value)
""")


def test_groups_and_no_label_leak():
    task = {"requirement": "read public files", "contract": "handle(value, root)",
            "label": "HIDDEN_LABEL", "reference": "HIDDEN_REFERENCE"}
    analysis = {"bandit": {"findings": ["ALERT_SENTINEL"]},
                "files": [{"imports": [], "functions": [{"source": "CONTEXT_SENTINEL", "sensitive_calls": [1]}]}]}
    a, b, c = [build_prompt(task, "CODE", analysis, g) for g in "ABC"]
    assert "ALERT_SENTINEL" not in a and "ALERT_SENTINEL" in b
    assert "CONTEXT_SENTINEL" not in b and "CONTEXT_SENTINEL" in c
    assert not any("HIDDEN" in p for p in [a, b, c])


def test_false_assertion_not_vulnerability():
    payload = {"uid": 65532, "exit_code": 1,
               "reports": [{"outcome": "failed", "security_failure": False}],
               "events": [{"violation": False}]}
    assert classify(payload) == "harness_error"
    payload["reports"][0]["security_failure"] = True
    assert classify(payload) == "harness_error"
    payload["events"][0]["violation"] = True
    assert classify(payload) == "violation"


def test_rootless_fail_closed():
    with patch("safety_harness.runner.shutil.which", return_value=None):
        with pytest.raises(IsolationError):
            preflight()


def test_path_symlink_escape(tmp_path):
    (tmp_path / "escape").symlink_to("/etc")
    with pytest.raises(ValueError):
        within(tmp_path, tmp_path / "escape/passwd")


def test_budget_enforced_before_network(tmp_path):
    budget = Budget(tmp_path / "budget.json", .001, 100, 100)
    with pytest.raises(ModelError):
        budget.reserve([{"content": "hello"}], 1800)
    assert not (tmp_path / "budget.json").exists()


def test_budget_shared_across_clients(tmp_path):
    path = tmp_path / "budget.json"
    a = Budget(path, 1, 1, 1)
    a.reserve([{"content": "hello"}], 10)
    before = json.loads(path.read_text())["reserved_cny"]
    Budget(path, 1, 1, 1).reserve([{"content": "hello"}], 10)
    assert json.loads(path.read_text())["reserved_cny"] == 2 * before


def test_summary_keeps_reference_distinct_and_failed_in_denominator(tmp_path):
    for i in range(2):
        write_json(tmp_path / f"{i}.json", {"kind": "reference_validation", "id": str(i), "group": "reference",
                                          "repeat": 0, "split": "dev", "confirmed": not i,
                                          "runnable": not i, "false_positive": False,
                                          "buggy": {"status": "violation" if not i else "harness_error"}})
    report = summarize_run(tmp_path)
    assert report["records"] == 2 and report["groups"][0]["confirmed_rate"] == .5
    assert report["complete_abc_blocks"] == 0


def test_api_explicit_non_thinking_budget_and_redacted_failure(tmp_path, monkeypatch):
    from safety_harness.model import DeepSeek
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-placeholder')
    client = DeepSeek('deepseek-flash', Budget(tmp_path/'budget.json', 10, 2, 8))
    with patch('safety_harness.model.requests.post') as post:
        post.return_value.status_code = 401
        with pytest.raises(ModelError, match='HTTP 401'):
            client.complete([{'role':'user', 'content':'test'}])
        payload = post.call_args.kwargs['json']
        assert payload['thinking'] == {'type':'disabled'}
        assert payload['temperature'] == 0 and payload['max_tokens'] == 1800
        assert json.loads((tmp_path/'budget.json').read_text())['reserved_cny'] > 0
