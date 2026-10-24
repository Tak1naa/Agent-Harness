"""Frozen experiments, resumable per trial, with raw evidence retained."""
# 实验总流程：组织A/B/C对照，保存每次模型输出和执行证据，再生成汇总。
# 阅读顺序：run_experiment -> build_prompt -> model.complete -> run_harness。
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .analyze import analyze_project
from .dataset import verify_dataset
from .io import digest, read_json, write_json
from .model import ModelError
from .policy import validate_harness
from .prompts import build_prompt
from .runner import DEFAULT_IMAGE, preflight, run_harness


def pair_result(case, harness, seed, image):
    # 同一个参考测试分别跑缺陷版和修复版，两边结果共同决定是否配对复现。
    buggy = run_harness(case / "buggy.py", harness, read_json(case / "task.json")["category"], seed, image=image)
    fixed = run_harness(case / "fixed.py", harness, read_json(case / "task.json")["category"], seed, image=image)
    return {"buggy": buggy, "fixed": fixed,
            "confirmed": buggy["status"] == "violation" and fixed["status"] == "pass",
            "false_positive": fixed["status"] == "violation",
            "runnable": buggy["status"] in {"pass", "violation"} and fixed["status"] in {"pass", "violation"}}


def run_reference(data_root, output, split="all", image=DEFAULT_IMAGE, workers=3):
    # 人工参考测试用于验证样本和执行链路；这部分不能统计成模型生成效果。
    data_root, output = Path(data_root), Path(output)
    verify_dataset(data_root)
    identity = preflight(image)
    output.mkdir(parents=True, exist_ok=True)
    config = {"kind": "reference_validation", "image": identity,
              "manifest_sha256": digest(data_root / "manifest.json"), "split": split}
    _freeze_config(output, config)
    def execute(case):
        if split != "all" and case["split"] != split:
            return
        dest = output / f"{case['id']}.json"
        if dest.exists():
            return
        folder = data_root / case["id"]
        record = {"kind": "reference_validation", "id": case["id"], "category": case["category"],
                  "split": case["split"], "group": "reference", "repeat": 0,
                  **pair_result(folder, folder / "reference.py", 0, image)}
        write_json(dest, record)
        print(f"{case['id']}: buggy={record['buggy']['status']} fixed={record['fixed']['status']}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(execute, read_json(data_root / "manifest.json")["cases"]))
    return summarize_run(output)


def _freeze_config(output, config):
    # 同一输出目录只能续跑相同配置，防止把不同模型、提示或镜像的结果混在一起。
    path = output / "config.json"
    if path.exists() and read_json(path) != config:
        raise ValueError("Existing run uses different settings; choose a fresh output directory")
    write_json(path, config)


def run_experiment(data_root, output, model, split="eval", repeats=3, image=DEFAULT_IMAGE, corpus="controlled"):
    # 受控集有缺陷/修复配对；真实生成集保留全部12份输出，另依赖人工标签。
    data_root, output = Path(data_root), Path(output)
    if not 1 <= repeats <= 3:
        raise ValueError("Repetitions must be between 1 and 3")
    if corpus == "controlled":
        verify_dataset(data_root)
        cases = [c for c in read_json(data_root / "manifest.json")["cases"] if c["split"] == split]
        dataset_hash = digest(data_root / "manifest.json")
    else:
        cases, fingerprints = [], []
        for task_path in sorted(data_root.glob("*/task.json")):
            task = read_json(task_path)
            folder = task_path.parent
            if not (folder / "response.json").exists():
                continue
            review = read_json(folder / "review.json")
            if review["target_sha256"] != digest(folder / "target.py"):
                raise ValueError("Generated target changed after review was initialized")
            # 只有两名不同复核者、证据和完成状态齐全时才采用标签，否则继续记unknown。
            # 这是记录完整性检查，本身不能证明复核者身份或实际完成了人工审查。
            reviewed = bool(review.get("reviewer_1") and review.get("reviewer_2")
                            and review["reviewer_1"] != review["reviewer_2"]
                            and review.get("evidence") and review.get("status") == "reviewed")
            label = review.get("label", "unknown") if reviewed else "unknown"
            if label not in {"safe", "vulnerable", "unknown"}:
                raise ValueError("Unknown human review label")
            cases.append({**task, "split": "generated", "ground_truth": label})
            fingerprints.append([task["id"], digest(folder / "target.py"), digest(task_path), digest(folder / "review.json")])
        if len(cases) != 12:
            raise ValueError("Generated corpus must retain all 12 outputs before evaluation")
        dataset_hash = hashlib.sha256(json.dumps(fingerprints).encode()).hexdigest()
    identity = preflight(image)
    output.mkdir(parents=True, exist_ok=True)
    # 源码按字节记录哈希：即使只改注释，也应新建批次，不能覆盖旧冻结配置续跑。
    config = {"kind": "model_experiment", "dataset": corpus, "split": split,
              "repeats": repeats, "model": model.model, "temperature": 0, "thinking": "disabled", "max_tokens": 1800,
              "max_attempts": 3, "image": identity, "manifest_sha256": dataset_hash,
              "prompt_code_sha256": digest(Path(__file__).with_name("prompts.py")),
              "model_client_sha256": digest(Path(__file__).with_name("model.py")),
              "runner_code_sha256": digest(Path(__file__).with_name("runner.py")),
              "experiment_code_sha256": digest(Path(__file__)),
              "input_price_per_million": model.budget.input_rate, "output_price_per_million": model.budget.output_rate}
    _freeze_config(output, config)
    # 固定随机种子打乱样本/重复块顺序，便于重建调度；重复不增加独立样本数量。
    schedule = [(case, repeat) for case in cases for repeat in range(repeats)]
    random.Random(20261020).shuffle(schedule)
    for case, repeat in schedule:
        # 每个“样本+重复”连续运行A/B/C三组，组序同样按可复现的种子打乱。
        groups = ["A", "B", "C"]
        random.Random(case["id"] + str(repeat)).shuffle(groups)
        for group in groups:
            trial = output / f"{case['id']}-{repeat}-{group}"
            if (trial / "result.json").exists():
                # 已完成试验直接跳过；未完成试验会复用已保存响应，但可能重新执行测试。
                continue
            trial.mkdir(exist_ok=True)
            folder = data_root / case["id"]
            target = folder / ("buggy.py" if corpus == "controlled" else "target.py")
            source = target.read_text()
            analysis = analyze_project(str(target))
            write_json(trial / "analysis.json", analysis)
            prompt = build_prompt(read_json(folder / "task.json"), source, analysis, group)
            messages = [{"role": "user", "content": prompt}]
            record = {"kind": "model_experiment", "dataset": corpus, "id": case["id"],
                      "category": case["category"], "split": case["split"], "group": group, "repeat": repeat,
                      "ground_truth": case.get("ground_truth", "paired"),
                      "attempts": [], "confirmed": False, "false_positive": False, "runnable": False}
            # 最多一次初始生成、两次根据执行反馈修订；只修改测试，不修改目标代码。
            for attempt in range(3):
                write_json(trial / f"messages-{attempt}.json", messages)
                try:
                    response_path = trial / f"response-{attempt}.json"
                    # 响应先落盘再执行，恢复时不重复请求同一已保存响应。
                    # 传输失败不在这里自动重试，其不确定调用次数需额外审计。
                    generated = read_json(response_path) if response_path.exists() else model.complete(messages)
                except ModelError as e:
                    write_json(trial / "blocked.json", {"reason": str(e), "completed_attempts": attempt})
                    raise
                write_json(trial / f"response-{attempt}.json", generated)
                harness = trial / f"test-{attempt}.py"
                harness.write_text(generated["code"])
                try:
                    validate_harness(generated["code"])
                    # 生成期间只执行缺陷版；修复版结果不能作为模型修订提示。
                    observed = run_harness(target, harness, case["category"], repeat, image=image)
                    feedback = {"status": observed["status"], "reports": (observed.get("payload") or {}).get("reports", [])}
                except ValueError as e:
                    observed = {"status": "invalid_harness", "reason": str(e)}
                    feedback = observed
                record["attempts"].append({"usage": generated["usage"], "observed": observed,
                                           "response_model": generated["response_model"],
                                           "model_duration_seconds": generated.get("duration_seconds")})
                write_json(trial / f"execution-{attempt}.json", observed)
                if observed["status"] == "violation" or attempt == 2:
                    # 已发现违规或耗尽生成次数后，用最终测试评估修复版，避免挑选不同测试配对。
                    if observed["status"] != "invalid_harness" and corpus == "controlled":
                        fixed = run_harness(folder / "fixed.py", harness, case["category"], repeat, image=image)
                        record.update(buggy=observed, fixed=fixed,
                                      confirmed=observed["status"] == "violation" and fixed["status"] == "pass",
                                      false_positive=fixed["status"] == "violation",
                                      runnable=observed["status"] in {"pass", "violation"} and fixed["status"] in {"pass", "violation"})
                    elif observed["status"] != "invalid_harness":
                        # 真实生成代码没有配对修复版：先记录违规候选，再结合人工标签统计。
                        record.update(buggy=observed,
                                      candidate_violation=observed["status"] == "violation",
                                      confirmed=observed["status"] == "violation" and case["ground_truth"] == "vulnerable",
                                      false_positive=observed["status"] == "violation" and case["ground_truth"] == "safe",
                                      runnable=observed["status"] in {"pass", "violation"})
                    break
                # 反馈仅含该轮测试状态和报告；完整事件保存供审计，不直接传回模型。
                messages += [{"role": "assistant", "content": generated["code"]},
                             {"role": "user", "content": "Revise the harness using this execution feedback. "
                              "Return Python only. " + json.dumps(feedback)}]
            write_json(trial / "result.json", record)
            print(f"{case['id']} repeat={repeat} group={group} confirmed={record['confirmed']}", flush=True)
    return summarize_run(output)


def generate_targets(tasks_path, output, model):
    # 从正常功能需求生成代码并全部保留；生成完成不等于功能验收或安全标签完成。
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _freeze_config(output, {"kind": "generated_targets", "model": model.model,
                           "tasks_sha256": digest(tasks_path)})
    for task in read_json(tasks_path):
        folder = output / task["id"]
        if (folder / "response.json").exists():
            continue
        folder.mkdir(exist_ok=True)
        write_json(folder / "task.json", task)
        response = model.complete([{"role": "user", "content": task["prompt"]}])
        write_json(folder / "response.json", response)
        (folder / "target.py").write_text(response["code"])
        write_json(folder / "review.json", {
            "status": "pending_two_reviewers", "reviewer_1": None, "reviewer_2": None,
            "label": "unknown", "evidence": None, "target_sha256": digest(folder / "target.py"),
        })
    return {"status": "generated_pending_human_review", "count": len(list(output.glob("*/response.json")))}


def summarize_run(output):
    # 只读取带指定kind和group的完整记录，不把analysis、response等中间文件当成试验。
    output = Path(output)
    records = []
    for path in sorted(output.rglob("*.json")):
        if path.name in {"summary.json", "config.json"}:
            continue
        data = read_json(path)
        if isinstance(data, dict) and data.get("kind") in {"reference_validation", "model_experiment"} and "group" in data:
            records.append(data)
    # 人工参考、模型试验、数据来源和开发/评测划分分别统计，禁止混合分母。
    groups = defaultdict(list)
    for r in records:
        groups[(r["kind"], r.get("dataset", "controlled"), r.get("split"), r["group"])].append(r)
    summary = {"schema_version": 1, "records": len(records), "groups": [], "complete_abc_blocks": 0,
               "note": "Reference validation is engineering evidence, not model-generated A/B/C results."}
    blocks = defaultdict(set)
    for r in records:
        if r["kind"] == "model_experiment":
            blocks[(r["id"], r["repeat"])].add(r["group"])
    # 这里只检查三组是否齐全；网络失败造成的超预算块由冻结审计脚本另行筛除。
    summary["complete_abc_blocks"] = sum(g == {"A", "B", "C"} for g in blocks.values())
    for (kind, dataset, split, group), rows in groups.items():
        n = len(rows)
        statuses = Counter((r.get("buggy") or {}).get("status", "invalid_harness") for r in rows)
        coverage = [r["buggy"]["payload"]["coverage"] for r in rows
                    if r.get("buggy", {}).get("payload") and r["buggy"]["payload"].get("coverage")]
        # 零分支目标不按100%覆盖处理；均值只纳入有分支记录，并同时公开分母。
        valid_coverage = [c for c in coverage if c.get("num_branches", 0)]
        entry = {"kind": kind, "dataset": dataset, "split": split, "group": group, "denominator": n,
                 "confirmed": sum(r["confirmed"] for r in rows),
                 "runnable": sum(r["runnable"] for r in rows),
                 "false_positives": sum(r["false_positive"] for r in rows),
                 "statuses": dict(statuses), "coverage_denominator": len(valid_coverage),
                 "mean_branch_coverage": sum(c["covered_branches"] / c["num_branches"] for c in valid_coverage) / len(valid_coverage) if valid_coverage else None,
                 "duration_seconds": sum((sum(a["observed"].get("duration_seconds", 0) for a in r["attempts"]) if r.get("attempts") else r.get("buggy", {}).get("duration_seconds", 0)) + r.get("fixed", {}).get("duration_seconds", 0) for r in rows),
                 "prompt_tokens": sum(a["usage"].get("prompt_tokens", 0) for r in rows for a in r.get("attempts", [])),
                 "completion_tokens": sum(a["usage"].get("completion_tokens", 0) for r in rows for a in r.get("attempts", []))}
        attempts = [a for r in rows for a in r.get("attempts", [])]
        entry["model_duration_seconds"] = sum(a.get("model_duration_seconds") or 0 for a in attempts)
        entry["missing_model_timing"] = sum(a.get("model_duration_seconds") is None for a in attempts)
        entry["missing_token_usage"] = sum(not all(k in a["usage"] for k in ("prompt_tokens", "completion_tokens")) for a in attempts)
        # 受控集每份记录含一个已知缺陷版和一个修复版；生成集未知标签不计作安全。
        known_positive = n if dataset == "controlled" else sum(r["ground_truth"] == "vulnerable" for r in rows)
        known_negative = n if dataset == "controlled" else sum(r["ground_truth"] == "safe" for r in rows)
        entry["positive_denominator"], entry["negative_denominator"] = known_positive, known_negative
        entry["unknown_labels"] = sum(r.get("ground_truth") == "unknown" for r in rows)
        entry["candidate_violations"] = sum(r.get("candidate_violation", False) for r in rows)
        entry["confirmed_rate"] = entry["confirmed"] / known_positive if known_positive else None
        entry["runnable_rate"] = entry["runnable"] / n
        entry["false_positive_rate"] = entry["false_positives"] / known_negative if known_negative else None
        negative_rows = rows if dataset == "controlled" else [r for r in rows if r.get("ground_truth") == "safe"]
        negative_statuses = Counter(r.get("fixed" if dataset == "controlled" else "buggy", {}).get("status", "not_run")
                                    for r in negative_rows)
        # 误报统计同时公开有效判定数和未判定数，避免把超时/测试错误算成安全通过。
        entry["negative_valid_evaluations"] = negative_statuses["pass"] + negative_statuses["violation"]
        entry["negative_unresolved"] = known_negative - entry["negative_valid_evaluations"]
        entry["observed_false_positive_rate"] = (negative_statuses["violation"] / entry["negative_valid_evaluations"]
                                                   if entry["negative_valid_evaluations"] else None)
        summary["groups"].append(entry)
    write_json(output / "summary.json", summary)
    with (output / "summary.csv").open("w", newline="") as handle:
        fields = ["kind", "dataset", "split", "group", "denominator", "positive_denominator", "negative_denominator",
                  "unknown_labels", "candidate_violations", "confirmed", "confirmed_rate",
                  "runnable", "runnable_rate", "false_positives", "false_positive_rate",
                  "negative_valid_evaluations", "negative_unresolved", "observed_false_positive_rate",
                  "coverage_denominator", "mean_branch_coverage", "duration_seconds", "model_duration_seconds", "missing_model_timing", "missing_token_usage", "prompt_tokens", "completion_tokens"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["groups"])
    return summary
