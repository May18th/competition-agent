# -*- coding: utf-8 -*-
"""进度 / 取消 / 并发的统一出口（薄封装）。

背景：为了避开 app.py 与 competition_agents.py 的循环导入，任务字典与阶段上报
下沉在 stage_reporter.py（零依赖，Codex 维护）。为避免出现两份互不一致的真相，
本模块**不再自己持有任务字典**，只做三件补充：

1. 并发数：resolve_workers()，优先用本次任务设定值；
2. 取消：cancel / is_cancelled，给前端「终止」按钮用；
3. live 快照：每次上报后原子写 progress_live.json，便于实时监控 /api/status/live。

阶段代号与中文文案以 stage_reporter.STAGE_META 为准（与《协作_进度条stage约定.md》一致），
这里只做转发，不复制。
"""

import os
import json
import threading
import time

from stage_reporter import STAGE_META, tasks, \
    set_current_task, clear_current_task, report_stage, \
    cancel_task as _sr_cancel, is_cancelled as _sr_is_cancelled, clear_cancel as _sr_clear_cancel

# 兼容旧代码里用过的名字
STAGE_MAP = STAGE_META
# 阶段顺序直接由 STAGE_META 的声明顺序派生（dict 保序），不复制一份
STAGE_ORDER = list(STAGE_META.keys())

# 仅在这个被 Frankestein 的模块里存在的派生能力，很多 ^_^
_workers_lock = threading.Lock()
_workers = {"n": None}

_LIVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress_live.json")


# ---------------- 阶段元数据转发 ----------------
def stage_meta(name):
    return STAGE_META.get(name, (name, 0))


# ---------------- 任务生命周期（写进共享 tasks 字典） ----------------
def bind(task_id, mode=None, workers=None, **kw):
    set_current_task(task_id)
    if workers is not None:
        set_workers(workers)
    t = tasks.get(task_id)
    if isinstance(t, dict):
        t["mode"] = mode or t.get("mode")
        t["workers"] = workers if workers is not None else t.get("workers")
        t.setdefault("events", [])
        t.setdefault("t_log_path", None)
    return t


def mark_running(task_id, **kw):
    t = tasks.get(task_id)
    if isinstance(t, dict):
        t["status"] = "running"
        t["updated_at"] = time.time()
    return t


def mark_stage(task_id, stage=None, **kw):
    """更新阶段（登记在 STAGE_META 里的才认）。"""
    t = tasks.get(task_id)
    if not isinstance(t, dict) or stage is None:
        return None
    if stage not in STAGE_META:
        return None
    t["stage"] = stage
    t["updated_at"] = time.time()
    return t


def mark_done(task_id, data=None, **kw):
    t = tasks.get(task_id)
    if isinstance(t, dict):
        t["status"] = "done"
        t["stage"] = "done"
        if data is not None:
            t["data"] = data
        t["updated_at"] = time.time()
    clear_current_task()


def mark_error(task_id, error=None, **kw):
    t = tasks.get(task_id)
    if isinstance(t, dict):
        t["status"] = "error"
        t["stage"] = "error"
        t["error"] = error
        t["updated_at"] = time.time()
    clear_current_task()


def stage_snapshot(task_id):
    """给路由用的统一 stage 视图：代号 / 中文 / 百分比 / 是否结束。"""
    t = tasks.get(task_id)
    if not isinstance(t, dict):
        return None
    stage = t.get("stage", "start")
    label, pct = STAGE_META.get(stage, (stage, 0))
    return {
        "stage": stage,
        "stage_label": label,
        "pct": pct,
        "status": t.get("status", "running"),
        "done": t.get("status") in ("done", "error", "cancelled"),
        "flow": STAGE_ORDER,
        "updated_at": t.get("updated_at", time.time()),
    }


# ---------------- 并发数（可调，不写死） ----------------
def set_workers(n):
    try:
        _workers["n"] = int(n) if n else None
    except (TypeError, ValueError):
        _workers["n"] = None


def resolve_workers(default=8):
    """给 ThreadPoolExecutor 用。优先级：本次设定 > 环境变量 DEEP_WORKERS > default。"""
    with _workers_lock:
        n = _workers["n"]
    if n and n > 0:
        return n
    for key in ("DEEP_WORKERS", "WORKERS"):
        try:
            v = int(os.environ.get(key, "0") or 0)
            if v > 0:
                return v
        except ValueError:
            continue
    return default


# ---------------- 取消 ----------------
def cancel(task_id):
    return _sr_cancel(task_id)


def is_cancelled(task_id=None):
    return _sr_is_cancelled(task_id)


def clear_cancel(task_id):
    _sr_clear_cancel(task_id)


# ---------------- live 快照 ----------------
def write_live(task_id):
    t = tasks.get(task_id)
    if not isinstance(t, dict):
        return None
    snap = {k: v for k, v in t.items() if k != "data"}
    try:
        tmp = _LIVE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _LIVE_PATH)
    except Exception as e:
        print("write_live error:", e)
    return snap
