"""Persistent, prompt-free LLM usage records and admin aggregates."""
import hashlib
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta


_READY_PATHS = set()
_SCHEMA_LOCK = threading.Lock()


def ensure_schema(db_path):
    path = os.path.abspath(db_path)
    if path in _READY_PATHS:
        return
    with _SCHEMA_LOCK:
        if path in _READY_PATHS:
            return
        with closing(sqlite3.connect(path, timeout=5)) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                task_id TEXT NOT NULL DEFAULT '',
                user_key TEXT NOT NULL DEFAULT 'anonymous',
                stage TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_user ON llm_usage(user_key)")
            conn.commit()
        _READY_PATHS.add(path)


def _int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def record_usage(db_path, *, task_id="", user_id="", stage="", section="", mode="",
                 model="", prompt_tokens=0, completion_tokens=0, total_tokens=None,
                 duration_ms=0, created_at=None):
    """Store only metadata and token counts; never store prompts or generated text."""
    user_key = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16] if user_id else "anonymous"
    prompt_tokens = _int(prompt_tokens)
    completion_tokens = _int(completion_tokens)
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens
    ensure_schema(db_path)
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""INSERT INTO llm_usage
            (created_at, task_id, user_key, stage, section, mode, model,
             prompt_tokens, completion_tokens, total_tokens, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             str(task_id or "")[:80], user_key, str(stage or "")[:80],
             str(section or "")[:160], str(mode or "")[:20], str(model or "")[:80],
             prompt_tokens, completion_tokens, _int(total_tokens), _int(duration_ms)))
        conn.commit()


def aggregate_tasks(db_path, days=30, limit=200):
    """按单次生成（task_id）汇总调用次数与 token，用于核算单次生成成本。

    task_id 为空的行不计入（历史数据里这类行无法归属到某一次生成）。
    """
    days = min(90, max(1, _int(days) or 30))
    limit = min(500, max(1, _int(limit) or 200))
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d 00:00:00")
    ensure_schema(db_path)
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute("""SELECT task_id, MIN(created_at) started_at,
            MAX(mode) mode, MAX(model) model, COUNT(*) calls,
            SUM(prompt_tokens) prompt_tokens, SUM(completion_tokens) completion_tokens,
            SUM(total_tokens) total_tokens, SUM(duration_ms) duration_ms,
            GROUP_CONCAT(DISTINCT NULLIF(stage, '')) stages
            FROM llm_usage WHERE created_at >= ? AND task_id != ''
            GROUP BY task_id ORDER BY started_at DESC LIMIT ?""", (start, limit)).fetchall()
    return [dict(row) for row in rows]


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    idx = int(round((len(sorted_values) - 1) * pct))
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def per_generation_summary(db_path, days=30):
    """单次生成的调用次数 / token / 耗时分布（只统计有 task_id 的记录）。

    这是核算「一次生成要花多少钱」的官方口径：mean 用于成本估算，
    p90 用于最坏情况（深度版长尾任务），task_count 说明样本量够不够。
    """
    tasks = aggregate_tasks(db_path, days=days, limit=500)
    calls = sorted(_int(r["calls"]) for r in tasks)
    tokens = sorted(_int(r["total_tokens"]) for r in tasks)
    durations = sorted(_int(r["duration_ms"]) for r in tasks)
    n = len(tasks)
    if not n:
        return {"days": days, "task_count": 0, "calls": {}, "total_tokens": {},
                "duration_ms": {}, "by_mode": {}}
    by_mode = {}
    for row in tasks:
        key = row.get("mode") or "未标记"
        bucket = by_mode.setdefault(key, {"task_count": 0, "calls": 0, "total_tokens": 0})
        bucket["task_count"] += 1
        bucket["calls"] += _int(row["calls"])
        bucket["total_tokens"] += _int(row["total_tokens"])
    for bucket in by_mode.values():
        bucket["avg_calls"] = round(bucket["calls"] / bucket["task_count"], 1)
        bucket["avg_tokens"] = int(round(bucket["total_tokens"] / bucket["task_count"]))
    return {
        "days": days,
        "task_count": n,
        "calls": {"mean": round(sum(calls) / n, 1), "min": calls[0],
                  "p50": _percentile(calls, 0.5), "p90": _percentile(calls, 0.9),
                  "max": calls[-1], "total": sum(calls)},
        "total_tokens": {"mean": int(round(sum(tokens) / n)), "min": tokens[0],
                         "p50": _percentile(tokens, 0.5), "p90": _percentile(tokens, 0.9),
                         "max": tokens[-1], "total": sum(tokens)},
        "duration_ms": {"mean": int(round(sum(durations) / n)),
                        "p50": _percentile(durations, 0.5),
                        "p90": _percentile(durations, 0.9), "max": durations[-1]},
        "by_mode": by_mode,
    }


def aggregate_usage(db_path, days=30, limit=20, now=None):
    days = min(90, max(1, _int(days) or 30))
    limit = min(100, max(1, _int(limit) or 20))
    end = now or datetime.now()
    start = (end - timedelta(days=days - 1)).strftime("%Y-%m-%d 00:00:00")
    ensure_schema(db_path)
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        totals = conn.execute("""SELECT COUNT(*) calls,
            COALESCE(SUM(prompt_tokens),0) prompt_tokens,
            COALESCE(SUM(completion_tokens),0) completion_tokens,
            COALESCE(SUM(total_tokens),0) total_tokens,
            COALESCE(SUM(duration_ms),0) duration_ms
            FROM llm_usage WHERE created_at >= ?""", (start,)).fetchone()
        daily = conn.execute("""SELECT substr(created_at,1,10) date, COUNT(*) calls,
            SUM(prompt_tokens) prompt_tokens, SUM(completion_tokens) completion_tokens,
            SUM(total_tokens) total_tokens FROM llm_usage WHERE created_at >= ?
            GROUP BY substr(created_at,1,10) ORDER BY date""", (start,)).fetchall()
        users = conn.execute("""SELECT user_key, COUNT(*) calls, SUM(total_tokens) total_tokens
            FROM llm_usage WHERE created_at >= ? GROUP BY user_key
            ORDER BY total_tokens DESC LIMIT ?""", (start, limit)).fetchall()
        sections = conn.execute("""SELECT CASE WHEN section != '' THEN section
            WHEN stage != '' THEN stage ELSE '未标记' END section,
            COUNT(*) calls, SUM(prompt_tokens) prompt_tokens,
            SUM(completion_tokens) completion_tokens, SUM(total_tokens) total_tokens
            FROM llm_usage WHERE created_at >= ?
            GROUP BY CASE WHEN section != '' THEN section
                WHEN stage != '' THEN stage ELSE '未标记' END
            ORDER BY total_tokens DESC LIMIT ?""", (start, limit)).fetchall()
        models = conn.execute("""SELECT CASE WHEN model != '' THEN model ELSE '未知' END model,
            COUNT(*) calls, SUM(total_tokens) total_tokens FROM llm_usage
            WHERE created_at >= ? GROUP BY model ORDER BY total_tokens DESC LIMIT ?""",
            (start, limit)).fetchall()
    return {
        "days": days,
        "totals": dict(totals),
        "daily": [dict(row) for row in daily],
        "users": [dict(row) for row in users],
        "sections": [dict(row) for row in sections],
        "models": [dict(row) for row in models],
    }
