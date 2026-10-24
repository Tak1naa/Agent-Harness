"""Direct DeepSeek fallback with a conservative, persistent budget ledger."""
# 模型调用层：在容器外调用API；预算预留与实际Token用量分别记录。
import fcntl
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .io import read_json, write_json


class ModelError(RuntimeError):
    pass


class Budget:
    # 多个生成/评测批次可以共享同一账本，避免分别计费时突破总预算。
    def __init__(self, ledger, limit_cny, input_per_million, output_per_million):
        self.path = Path(ledger)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limit, self.input_rate, self.output_rate = limit_cny, input_per_million, output_per_million
        if min(limit_cny, input_per_million, output_per_million) <= 0:
            raise ValueError("Explicit positive budget and current price rates are required")

    def reserve(self, messages, max_tokens):
        # 以UTF-8字节数加消息开销保守估算输入，再按最大输出预留费用。
        # 这不是实际账单；未使用的输出额度和失败请求的预留均不会自动退回。
        estimated_input = sum(len(m["content"].encode()) + 128 for m in messages) + 512
        cost = (estimated_input * self.input_rate + max_tokens * self.output_rate) / 1_000_000
        # 文件锁覆盖“读账本、检查上限、写入”全过程，防止并发请求重复占用余额。
        with self.path.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = read_json(self.path) if self.path.exists() else {"reservations": [], "reserved_cny": 0}
            if ledger["reserved_cny"] + cost > self.limit:
                raise ModelError("Budget cap reached; no API request sent")
            ledger["reserved_cny"] += cost
            ledger["reservations"].append({"upper_bound_cny": cost,
                                          "timestamp": datetime.now(timezone.utc).isoformat()})
            write_json(self.path, ledger)
        return cost


class DeepSeek:
    def __init__(self, model, budget):
        self.key = os.getenv("DEEPSEEK_API_KEY")
        if not self.key:
            raise ModelError("DEEPSEEK_API_KEY is not configured")
        self.model, self.budget = model, budget

    def complete(self, messages, max_tokens=1800):
        # 先预留、后发送：额度不足时不会发起收费请求。
        reserved = self.budget.reserve(messages, max_tokens)
        # 不做隐式重试：连接失败时无法保证服务端未处理，请求预留继续保留。
        started = time.monotonic()
        try:
            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": "Bearer " + self.key},
                json={"model": self.model, "messages": messages, "temperature": 0,
                      "thinking": {"type": "disabled"},
                      "max_tokens": max_tokens, "stream": False},
                timeout=(10, 90),
            )
        except requests.RequestException as e:
            # 只记录异常类型，不把请求对象、鉴权头或响应正文写入错误日志。
            raise ModelError(f"API transport failure: {type(e).__name__}") from None
        if response.status_code != 200:
            raise ModelError(f"API returned HTTP {response.status_code}; response body omitted")
        try:
            data = response.json()
            raw = data["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise ValueError()
        except (KeyError, ValueError, IndexError):
            raise ModelError("Malformed API response") from None
        # 仅剥离常见Markdown代码围栏；原始响应另存，便于追溯提取过程。
        # 返回代码还需通过policy校验，不能在这里直接执行。
        code = raw.strip()
        if code.startswith("```"):
            code = re.sub(r"^```(?:python)?\s*\n?", "", code)
            code = re.sub(r"\n?```\s*$", "", code)
        return {"code": code + "\n", "raw_response": raw, "usage": data.get("usage", {}),
                "requested_model": self.model, "response_model": data.get("model"),
                "response_id": data.get("id"), "finish_reason": data["choices"][0].get("finish_reason"),
                "reserved_cny": reserved, "duration_seconds": time.monotonic() - started, "timestamp": datetime.now(timezone.utc).isoformat()}
