"""本机中文工作台：薄 HTTP 适配层，复用分析器、实验流程与隔离执行器。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
from threading import Lock
import uuid

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .analyze import analyze_project
from .dataset import verify_dataset
from .experiment import run_experiment, summarize_run
from .io import read_json, within, write_json as _write_json
from .model import Budget, DeepSeek, ModelError
from .policy import validate_harness
from .runner import IsolationError, preflight, run_harness
from .agent_client import AgentClient

IMAGE = "localhost/bjtu-safety-harness:0.2"
STATIC = Path(__file__).with_name("web_assets")
HISTORY = {
    "benchmark-20261025": ("2026-10-25 · 单轮评测", "benchmark-20261025", "benchmark-20261025"),
    "frozen-20261022": ("2026-10-22 · 冻结评测", "frozen-20261022", "frozen-eval-20261022"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    """任务状态原子替换，页面轮询不会读到写了一半的JSON。"""
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    _write_json(temporary, value)
    temporary.replace(path)


class Workbench:
    def __init__(self, root, image=IMAGE):
        self.root = Path(root).resolve()
        self.data = self.root / "data/controlled"
        self.output = within(self.root, self.root / "results/private/web")
        self.output.mkdir(parents=True, exist_ok=True)
        self.image = image
        self.csrf = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="harness-web")
        self.lock = Lock()
        self.active = None
        # 重启不能把未完成任务显示为成功，也不能自动再发送收费请求。
        for p in self.output.glob("*/job.json"):
            job = read_json(p)
            if job["status"] in {"queued", "running"}:
                job.update(status="interrupted", message="服务已重启；可查看已有记录。", updated_at=now())
                write_json(p, job)

    def cases(self):
        return read_json(self.data / "manifest.json")["cases"]

    def case(self, case_id):
        case = next((c for c in self.cases() if c["id"] == case_id), None)
        if not case:
            raise ValueError("样本不存在，请从列表中选择。")
        folder = within(self.data, self.data / case_id)
        return case, folder

    def folder(self, job_id):
        if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("任务编号无效。")
        return within(self.output, self.output / job_id)

    def get_job(self, job_id):
        folder = self.folder(job_id)
        if not (folder / "job.json").is_file():
            raise ValueError("任务不存在。")
        job = read_json(folder / "job.json")
        if job["kind"] == "experiment":
            records = []
            for p in (folder / "run").glob("*/result.json"):
                try:
                    records.append(read_json(p))
                except json.JSONDecodeError:
                    # 核心实验器正在落盘的trial留到下一次轮询读取。
                    continue
            job["completed"] = len(records)
            job["trials"] = [{k: r[k] for k in ("id", "group", "repeat", "confirmed", "runnable")} for r in records]
        result = folder / "result.json"
        if job["status"] not in {"queued", "running"} and result.exists():
            job["result"] = read_json(result)
        return job

    def submit(self, params):
        kind = params.get("kind")
        if kind not in {"analyze", "run", "experiment"}:
            raise ValueError("不支持的操作。")
        clean = {"kind": kind}
        if kind in {"analyze", "run"}:
            case, _ = self.case(params.get("case_id"))
            clean["case_id"] = case["id"]
        if kind == "analyze":
            clean["variant"] = params.get("variant", "buggy")
            if clean["variant"] not in {"buggy", "fixed"}:
                raise ValueError("请选择缺陷版或修复版。")
        if kind == "run":
            code = params.get("harness")
            if code is not None:
                if not isinstance(code, str) or len(code.encode()) > 32000:
                    raise ValueError("测试代码超过32KB限制。")
                validate_harness(code)
                clean["harness"] = code
        if kind == "experiment":
            if not os.getenv("DEEPSEEK_API_KEY"):
                raise ValueError("未配置 API Key，请在项目 .env 中填写后重启工作台。")
            clean["split"] = params.get("split", "dev")
            if clean["split"] not in {"dev", "eval"}:
                raise ValueError("请选择开发集或评测集。")
            # Web端固定一次重复和模型，费用参数可显式更新；共享总预算不能超过100元。
            clean["model"] = "deepseek-flash"
            for key, default, ceiling in [("input_price", 2, 100), ("output_price", 8, 200), ("budget", 100, 100)]:
                value = params.get(key, default)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= ceiling:
                    raise ValueError("价格或共享预算无效。")
                clean[key] = value
        with self.lock:
            if self.active:
                raise RuntimeError("已有任务正在运行，请等待它结束。")
            job_id = uuid.uuid4().hex
            folder = self.folder(job_id)
            job = {"id": job_id, "kind": kind, "params": clean, "status": "queued", "created_at": now(),
                   "updated_at": now(), "message": "任务已加入队列", "total": (18 if clean.get("split") == "dev" else 72) if kind == "experiment" else 1}
            write_json(folder / "job.json", job)
            self.active = job_id
            self.pool.submit(self.execute, job)
        return job_id

    def execute(self, job):
        folder = self.folder(job["id"])
        params = job["params"]
        try:
            job.update(status="running", message="正在执行，请保持页面打开或稍后回到任务记录。", updated_at=now())
            write_json(folder / "job.json", job)
            verify_dataset(self.data)
            if job["kind"] == "analyze":
                _, case_dir = self.case(params["case_id"])
                result = analyze_project(str(case_dir / (params["variant"] + ".py")))
            elif job["kind"] == "run":
                case, case_dir = self.case(params["case_id"])
                # 先验证隔离，再运行。同一份测试配对执行，绝不在宿主机导入目标。
                preflight(self.image)
                harness = folder / "test_safety.py"
                harness.write_text(params.get("harness", (case_dir / "reference.py").read_text()))
                bad = run_harness(case_dir / "buggy.py", harness, case["category"], image=self.image)
                write_json(folder / "buggy.json", bad)
                good = run_harness(case_dir / "fixed.py", harness, case["category"], image=self.image)
                result = {"kind": "manual_validation", "case_id": case["id"], "buggy": bad, "fixed": good,
                          "confirmed": bad["status"] == "violation" and good["status"] == "pass",
                          "note": "参考/手写测试的工程验证，不能计入模型A/B/C成绩。"}
            else:
                model = DeepSeek(params["model"], Budget(self.root / "results/private/budget.json", params["budget"],
                                                         params["input_price"], params["output_price"]))
                result = run_experiment(self.data, folder / "run", model, params["split"], 1, self.image)
            write_json(folder / "result.json", result)
            job.update(status="completed", message="任务完成，结果已保存。")
        except (ValueError, IsolationError, ModelError) as exc:
            job.update(status="blocked", message=str(exc))
            # 不自动重试收费请求；保留中断位置和已完成trial，避免掩盖不完整分母。
            if job["kind"] == "experiment" and (folder / "run").exists():
                write_json(folder / "result.json", summarize_run(folder / "run"))
        except Exception as exc:
            job.update(status="failed", message=f"执行未完成（{type(exc).__name__}），请检查本机环境。")
        finally:
            job["updated_at"] = now()
            write_json(folder / "job.json", job)
            with self.lock:
                self.active = None

    def runs(self):
        return [{"id": key, "label": label} for key, (label, folder, _) in HISTORY.items()
                if (self.root / "results" / folder / "analysis.json").is_file()]

    def report(self, run_id):
        if run_id not in HISTORY:
            raise ValueError("评测批次不存在。")
        label, folder, _ = HISTORY[run_id]
        base = self.root / "results" / folder
        if not (base / "analysis.json").exists():
            raise ValueError("本地没有该批次的统计文件。")
        report = read_json(base / "analysis.json")
        audit = read_json(base / "full-audit.json")
        return {"id": run_id, "label": label, "summary": report.get("within_budget_summary", report.get("primary_summary")),
                "full_summary": report["full_summary"], "cases": audit["cases"], "usage": report["usage"],
                "api_responses": report["api_responses"], "ambiguous_requests": report["ambiguous_requests"],
                "cost_upper": report["usage_cost_upper_cny"], "verification": report["evidence_verification"],
                "excluded": report["excluded_matched_blocks"],
                "static": read_json(base / "securityeval-static.json") if (base / "securityeval-static.json").exists() else None}


def create_app(root=None, image=IMAGE):
    workbench = Workbench(root or Path.cwd(), image)
    agent = AgentClient(workbench.root, image)

    @asynccontextmanager
    async def lifespan(app):
        yield
        workbench.pool.shutdown(wait=True)
        agent.shutdown()

    def index(request):
        return FileResponse(STATIC / "index.html")

    def research(request):
        return FileResponse(STATIC / "research.html")

    def client_info(request):
        ledger = workbench.root / "results/private/budget.json"
        return JSONResponse({"workspace": workbench.root.name, "root": str(workbench.root),
                             "backend": "项目 Harness Agent", "model": "deepseek-flash",
                             "key_configured": bool(os.getenv("DEEPSEEK_API_KEY")), "csrf": workbench.csrf,
                             "reserved_cny": read_json(ledger)["reserved_cny"] if ledger.exists() else 0,
                             "budget_cny": 100, "files": agent.files(), "sessions": agent.sessions()})

    def client_sessions(request):
        return JSONResponse(agent.sessions())

    def client_session(request):
        return JSONResponse(agent.public(agent.get(request.path_params['sid'])))

    def client_file(request):
        return JSONResponse(agent.read(request.query_params.get('path')))

    async def client_action(request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>64000:return JSONResponse({'error':'请求过大。'},status_code=413)
        try: body=json.loads(raw or b'{}')
        except ValueError:raise ValueError('请求必须是JSON对象。') from None
        if not isinstance(body,dict):raise ValueError('请求必须是JSON对象。')
        action=request.path_params['action']
        if action=='create':result=agent.create()
        elif action=='send':result=agent.send(body.get('session_id'),body.get('text'),body.get('attachments',[]))
        elif action=='stop':result=agent.stop(body.get('session_id'))
        elif action=='decide':
            if not isinstance(body.get('approve'),bool):raise ValueError('请选择应用或拒绝。')
            result=agent.decide(body.get('session_id'),body.get('change_id'),body['approve'])
        else:raise ValueError('操作不存在。')
        return JSONResponse(result)

    def bootstrap(request):
        ledger = workbench.root / "results/private/budget.json"
        return JSONResponse({"csrf": workbench.csrf, "key_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
                             "reserved_cny": read_json(ledger)["reserved_cny"] if ledger.exists() else 0,
                             "image": image, "cases": workbench.cases(), "runs": workbench.runs()})

    def case(request):
        info, folder = workbench.case(request.path_params["case_id"])
        files = {name: within(workbench.data, folder / name).read_text() for name in ("buggy.py", "fixed.py", "reference.py")}
        return JSONResponse({"info": info, "files": files})

    def environment(request):
        try:
            return JSONResponse({"status": "ready", **preflight(image)})
        except (IsolationError, OSError) as exc:
            return JSONResponse({"status": "blocked", "message": str(exc) if isinstance(exc, IsolationError) else "无法访问容器引擎。"})

    def report(request):
        return JSONResponse(workbench.report(request.path_params["run_id"]))

    def trial(request):
        run_id = request.path_params["run_id"]
        workbench.report(run_id)
        case_id = request.query_params.get("case", "")
        workbench.case(case_id)
        group = request.query_params.get("group")
        repeat = request.query_params.get("repeat", "0")
        if group not in {"A", "B", "C"} or repeat not in {"0", "1", "2"}:
            raise ValueError("试验参数无效。")
        folder = within(workbench.root, workbench.root / "results/private" / HISTORY[run_id][2] / f"{case_id}-{repeat}-{group}")
        if not (folder / "result.json").exists():
            return JSONResponse({"error": "原始记录未随公开仓库分发；本机没有该试验日志。"}, status_code=404)
        record = read_json(folder / "result.json")
        tests = [{"attempt": i + 1, "code": (folder / f"test-{i}.py").read_text(), "status": a["observed"]["status"]}
                 for i, a in enumerate(record["attempts"])]
        return JSONResponse({"record": record, "tests": tests})

    async def submit(request):
        # 同源令牌与Host校验阻止其他网站借本地接口触发执行或消耗API预算。
        if request.headers.get("x-harness-csrf") != workbench.csrf:
            return JSONResponse({"error": "页面会话已失效，请刷新后重试。"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "不允许跨站操作。"}, status_code=403)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 64000:
                return JSONResponse({"error": "请求过大。"}, status_code=413)
        try:
            params = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("请求必须是JSON对象。") from None
        if not isinstance(params, dict):
            raise ValueError("请求必须是JSON对象。")
        try:
            job_id = workbench.submit(params)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse({"id": job_id}, status_code=202)

    def jobs(request):
        paths = sorted(workbench.output.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        return JSONResponse([workbench.get_job(p.parent.name) for p in paths])

    def job(request):
        return JSONResponse(workbench.get_job(request.path_params["job_id"]))

    async def bad_request(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    routes = [Route("/", index), Route("/research", research),
              Route("/api/client/info", client_info), Route("/api/client/sessions", client_sessions),
              Route("/api/client/sessions/{sid}", client_session), Route("/api/client/file", client_file),
              Route("/api/client/actions/{action}", client_action, methods=['POST']),
              Route("/api/bootstrap", bootstrap), Route("/api/environment", environment),
              Route("/api/cases/{case_id}", case), Route("/api/reports/{run_id}", report),
              Route("/api/reports/{run_id}/trial", trial), Route("/api/jobs", jobs),
              Route("/api/jobs", submit, methods=["POST"]), Route("/api/jobs/{job_id}", job),
              Mount("/assets", StaticFiles(directory=STATIC), name="assets")]
    app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={ValueError: bad_request})
    app.state.workbench = workbench
    app.state.agent = agent
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def headers(request, call_next):
        if request.method=='POST' and request.url.path.startswith('/api/client/'):
            if request.headers.get('x-harness-csrf')!=workbench.csrf:
                return JSONResponse({'error':'页面会话已失效，请刷新后重试。'},status_code=403)
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'error':'不允许跨站操作。'},status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description="启动本机 Harness 会话客户端")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", default=str(Path.cwd()))
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    load_dotenv(root / ".env", override=False)
    # 仅回环监听；远程演示通过既有SSH转发，不开放未鉴权的公网服务。
    uvicorn.run(create_app(root), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
