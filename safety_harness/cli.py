# 命令行入口：解析参数并调用核心模块；具体研究逻辑不在此处重复实现。
import argparse
import json
import sys
from dotenv import load_dotenv
from pathlib import Path

from .analyze import analyze_project
from .dataset import verify_dataset
from .experiment import generate_targets, run_experiment, run_reference, summarize_run
from .io import write_json
from .model import Budget, DeepSeek, ModelError
from .runner import DEFAULT_IMAGE, IsolationError, preflight, run_harness


def main():
    # 仅加载当前工作目录的.env，已有环境变量优先；密钥不打印、不传入测试容器。
    load_dotenv(Path.cwd() / ".env", override=False)
    parser = argparse.ArgumentParser(description="Python security harness research prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("path")
    p.add_argument("--out")
    p = sub.add_parser("verify-data")
    p.add_argument("--data", default="data/controlled")
    p = sub.add_parser("doctor")
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p = sub.add_parser("run")
    p.add_argument("target")
    p.add_argument("harness")
    p.add_argument("--category", required=True, choices=["path", "command", "sql"])
    p.add_argument("--out", required=True)
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p.add_argument("--seed", type=int, default=0)
    p = sub.add_parser("reference")
    p.add_argument("--data", default="data/controlled")
    p.add_argument("--out", default="results/reference")
    p.add_argument("--split", default="all", choices=["all", "dev", "eval"])
    p.add_argument("--image", default=DEFAULT_IMAGE)
    p = sub.add_parser("summarize")
    p.add_argument("path")
    # 需要模型的命令共用显式价格、预算和账本参数，避免把单价硬编码成长期常量。
    for command in ("experiment", "generate-targets"):
        p = sub.add_parser(command)
        p.add_argument("--out", required=True)
        p.add_argument("--model", required=True)
        p.add_argument("--budget-cny", type=float, default=100)
        p.add_argument("--input-price", type=float, required=True, help="Current CNY per million uncached input tokens")
        p.add_argument("--output-price", type=float, required=True, help="Current CNY per million output tokens")
        p.add_argument("--ledger", default="results/private/budget.json", help="Shared across generation and experiments")
        if command == "experiment":
            p.add_argument("--data", default="data/controlled")
            p.add_argument("--split", choices=["dev", "eval"], default="eval")
            p.add_argument("--repeats", type=int, default=3)
            p.add_argument("--image", default=DEFAULT_IMAGE)
            p.add_argument("--corpus", choices=["controlled", "generated"], default="controlled")
        else:
            # 旧任务文件仍是CLI默认值；12份真实生成批次需显式指定generation_tasks_v2.json。
            p.add_argument("--tasks", default="data/generation_tasks.json")
    args = parser.parse_args()
    try:
        if args.command == "analyze":
            result = analyze_project(args.path)
            if args.out:
                write_json(args.out, result)
        elif args.command == "verify-data":
            result = verify_dataset(args.data)
        elif args.command == "doctor":
            result = preflight(args.image)
        elif args.command == "run":
            result = run_harness(args.target, args.harness, args.category, args.seed, image=args.image)
            write_json(args.out, result)
        elif args.command == "reference":
            result = run_reference(args.data, args.out, args.split, args.image)
        elif args.command == "summarize":
            result = summarize_run(args.path)
        else:
            # 只有生成/模型实验才初始化API客户端；分析、校验和汇总不需要Key。
            model = DeepSeek(args.model, Budget(args.ledger, args.budget_cny, args.input_price, args.output_price))
            if args.command == "experiment":
                result = run_experiment(args.data, args.out, model, args.split, args.repeats, args.image, args.corpus)
            else:
                result = generate_targets(args.tasks, args.out, model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, IsolationError, ModelError) as e:
        # 配置、隔离或模型调用失败统一返回blocked和非零退出码，不伪装成成功试验。
        print(json.dumps({"status": "blocked", "reason": str(e)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
