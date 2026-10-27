"""Check controlled model-run evidence against saved responses and dataset hashes."""
import argparse
import json
from pathlib import Path

from safety_harness.io import digest, read_json, write_json


def verify(root, data):
    root, data = Path(root), Path(data)
    config = read_json(root / "config.json")
    errors = []

    def check(condition, location, reason):
        if not condition:
            errors.append({"location": location, "reason": reason})

    if config.get("dataset") != "controlled":
        raise ValueError("This verifier currently supports only paired controlled runs")
    check(digest(data / "manifest.json") == config["manifest_sha256"], "config", "manifest hash mismatch")
    cases = [c for c in read_json(data / "manifest.json")["cases"] if c["split"] == config["split"]]
    expected = {(c["id"], repeat, group) for c in cases for repeat in range(config["repeats"]) for group in "ABC"}
    seen = set()
    response_count = 0
    for path in sorted(root.glob("*/result.json")):
        record = read_json(path)
        trial = path.parent
        key = (record["id"], record["repeat"], record["group"])
        check(key not in seen, trial.name, "duplicate trial")
        seen.add(key)
        attempts = record["attempts"]
        check(1 <= len(attempts) <= config["max_attempts"], trial.name, "attempt count out of bounds")
        messages = None
        for i, attempt in enumerate(attempts):
            location = f"{trial.name}/attempt-{i}"
            response = read_json(trial / f"response-{i}.json")
            response_count += 1
            submitted = read_json(trial / f"messages-{i}.json")
            if messages is None:
                check(len(submitted) == 1 and submitted[0]["role"] == "user", location, "unexpected initial messages")
            else:
                check(submitted == messages, location, "feedback differs from saved buggy execution")
            check(response["requested_model"] == config["model"], location, "requested model mismatch")
            harness = trial / f"test-{i}.py"
            check(harness.read_text() == response["code"], location, "test differs from saved model output")
            observed = read_json(trial / f"execution-{i}.json")
            check(observed == attempt["observed"], location, "execution record mismatch")
            check(response["usage"] == attempt["usage"], location, "usage mismatch")
            if observed["status"] != "invalid_harness":
                check(observed["harness_sha256"] == digest(harness), location, "executed test hash mismatch")
                check(observed["target_sha256"] == digest(data / record["id"] / "buggy.py"), location, "buggy target hash mismatch")
                check(observed["isolation"] == config["image"], location, "execution image mismatch")
                feedback = {"status": observed["status"], "reports": (observed.get("payload") or {}).get("reports", [])}
            else:
                feedback = observed
            messages = submitted + [{"role": "assistant", "content": response["code"]},
                                    {"role": "user", "content": "Revise the harness using this execution feedback. "
                                     "Return Python only. " + json.dumps(feedback)}]
        if record.get("fixed"):
            fixed = record["fixed"]
            check(fixed["harness_sha256"] == digest(harness), trial.name, "fixed variant used different test")
            check(fixed["target_sha256"] == digest(data / record["id"] / "fixed.py"), trial.name, "fixed target hash mismatch")
            check(fixed["isolation"] == config["image"], trial.name, "fixed execution image mismatch")
        confirmed = record.get("buggy", {}).get("status") == "violation" and record.get("fixed", {}).get("status") == "pass"
        check(record["confirmed"] == confirmed, trial.name, "paired conclusion mismatch")
    check(seen == expected, "run", "missing or unexpected trial blocks")
    result = {"kind": "evidence_verification", "status": "passed" if not errors else "failed",
              "expected_trials": len(expected), "observed_trials": len(seen),
              "responses_checked": response_count, "errors": errors,
              "scope": "Saved response/test identity, usage, executed target/image hashes, paired verdicts, and buggy-only revision feedback. Not an independent security-oracle review."}
    write_json(root / "evidence-verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--data", default="data/controlled")
    args = parser.parse_args()
    result = verify(args.run, args.data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
