"""Token budget logging — tracks AI API token usage for cost monitoring.

Logs each AI call as a JSON line to a rolling file.  Supports per-user tracking
for the AI cost circuit breaker.
"""

import json
import logging
import os
import time
from pathlib import Path

from app.middleware.request_context import get_request_id

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "token_usage.jsonl"
TOKEN_LOG_PATH = os.environ.get("TOKEN_LOG_PATH", str(DEFAULT_TOKEN_LOG_PATH))

# DeepSeek pricing (CNY per 1M tokens)
COST_PER_1M: dict[str, float] = {
    "deepseek-v4-pro": 1.0,
    "deepseek-v4-flash": 0.5,
    "qwen-vl-max": 3.0,
    "qwen-max": 2.0,
    "unknown": 1.0,
}


def log_token_usage(
    model: str,
    task: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    skill_name: str = "",
    project_id: str = "",
    user_id: int | None = None,
    duration_ms: float = 0.0,
    success: bool = True,
    error: str = "",
) -> None:
    """Append one token usage record to the JSONL log file."""
    try:
        Path(TOKEN_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "request_id": get_request_id(),
            "model": model,
            "task": task,
            "skill": skill_name,
            "project_id": project_id,
            "user_id": user_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "error": "redacted" if error else "",
        }
        with open(TOKEN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write token usage log")


def get_recent_usage(hours: float = 24.0, limit: int = 500) -> list[dict]:
    """Read recent usage records from the log file."""
    cutoff = time.time() - hours * 3600
    records: list[dict] = []
    try:
        if not os.path.exists(TOKEN_LOG_PATH):
            return []
        with open(TOKEN_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("ts", 0) >= cutoff:
                        records.append(record)
                except json.JSONDecodeError:
                    continue
        records.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return records[:limit]
    except Exception:
        logger.exception("Failed to read token usage log")
        return []


def get_user_usage(user_id: int, hours: float = 24.0) -> dict:
    """Get token usage for a specific user over the last N hours.

    Returns {total_tokens, total_calls, estimated_cost_cny}.
    """
    cutoff = time.time() - hours * 3600
    total_tokens = 0
    total_calls = 0
    estimated_cost = 0.0
    try:
        if not os.path.exists(TOKEN_LOG_PATH):
            return {"total_tokens": 0, "total_calls": 0, "estimated_cost_cny": 0.0}
        with open(TOKEN_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("user_id") != user_id:
                        continue
                    if record.get("ts", 0) < cutoff:
                        continue
                    total_calls += 1
                    tt = record.get("total_tokens", 0)
                    total_tokens += tt
                    rate = COST_PER_1M.get(record.get("model", "unknown"), 1.0)
                    estimated_cost += (tt / 1_000_000) * rate
                except json.JSONDecodeError:
                    continue
    except Exception:
        logger.exception("Failed to read token usage for user %s", user_id)
    return {
        "total_tokens": total_tokens,
        "total_calls": total_calls,
        "estimated_cost_cny": round(estimated_cost, 4),
    }


def get_usage_summary(hours: float = 24.0) -> dict:
    """Aggregate token usage for the last N hours."""
    records = get_recent_usage(hours=hours)
    if not records:
        return {
            "hours": hours,
            "total_calls": 0,
            "by_model": {},
            "by_task": {},
            "total_tokens": 0,
            "estimated_cost_cny": 0.0,
        }

    by_model: dict[str, dict] = {}
    by_task: dict[str, dict] = {}
    total_tokens = 0
    total_calls = 0
    failed_calls = 0

    for r in records:
        total_calls += 1
        model = r.get("model", "unknown")
        task = r.get("task", "unknown")
        pt = r.get("prompt_tokens", 0)
        ct = r.get("completion_tokens", 0)

        if not r.get("success", True):
            failed_calls += 1

        if model not in by_model:
            by_model[model] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        by_model[model]["calls"] += 1
        by_model[model]["prompt_tokens"] += pt
        by_model[model]["completion_tokens"] += ct

        if task not in by_task:
            by_task[task] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        by_task[task]["calls"] += 1
        by_task[task]["prompt_tokens"] += pt
        by_task[task]["completion_tokens"] += ct

        total_tokens += r.get("total_tokens", 0)

    estimated_cost = 0.0
    for model, stats in by_model.items():
        tokens = stats["prompt_tokens"] + stats["completion_tokens"]
        rate = COST_PER_1M.get(model, 1.0)
        estimated_cost += (tokens / 1_000_000) * rate

    return {
        "hours": hours,
        "total_calls": total_calls,
        "failed_calls": failed_calls,
        "total_tokens": total_tokens,
        "estimated_cost_cny": round(estimated_cost, 4),
        "by_model": by_model,
        "by_task": by_task,
    }
