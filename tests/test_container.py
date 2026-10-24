import os
from pathlib import Path
import pytest
from safety_harness.runner import DEFAULT_IMAGE, run_harness

pytestmark = [pytest.mark.container, pytest.mark.skipif(os.getenv("RUN_CONTAINER_TESTS") != "1",
                                                       reason="Set RUN_CONTAINER_TESTS=1 for isolated runtime verification")]
ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.getenv("HARNESS_TEST_IMAGE", DEFAULT_IMAGE)


@pytest.mark.parametrize("category", ["path", "command", "sql"])
def test_real_effects_and_fixed_pairs(category):
    folder = ROOT / f"data/controlled/{category}-01"
    bad = run_harness(folder / "buggy.py", folder / "reference.py", category, image=IMAGE)
    good = run_harness(folder / "fixed.py", folder / "reference.py", category, image=IMAGE)
    assert bad["status"] == "violation"
    assert good["status"] == "pass"
    assert bad["isolation"]["rootless"]


def test_timeout(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("def handle(value, root):\n    while True:\n        pass\n")
    harness = tmp_path / "test_safety.py"
    harness.write_text("def test_safety(probe):\n    probe.check('hello')\n")
    assert run_harness(target, harness, "path", timeout=3, image=IMAGE)["status"] == "timeout"


def test_hypothesis_real_runtime(tmp_path):
    harness = tmp_path / "test_safety.py"
    harness.write_text('from hypothesis import given, strategies as st\n'
                       '@given(value=st.sampled_from(["hello.txt", "../secret.txt"]))\n'
                       'def test_safety(probe, value):\n    probe.check(value)\n')
    folder = ROOT / "data/controlled/path-01"
    assert run_harness(folder / "buggy.py", harness, "path", image=IMAGE)["status"] == "violation"


def test_feedback_locates_ordinary_error_without_counting_violation(tmp_path):
    harness = tmp_path / "test_safety.py"
    harness.write_text('def test_safety(probe):\n'
                       '    probe.check("hello.txt")\n'
                       '    probe.check("hello.txt/../secret.txt")\n')
    result = run_harness(ROOT / "data/controlled/path-01/buggy.py", harness, "path", image=IMAGE)
    assert result["status"] == "harness_error"
    failed = [r for r in result["payload"]["reports"] if r["outcome"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error_type"] == "NotADirectoryError"
    assert failed[0]["generated_test_line"] == 3
    assert not failed[0]["security_failure"]
