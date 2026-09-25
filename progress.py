# -*- coding: utf-8 -*-
"""生成进度上报 / 任务取消 / 并发数（零依赖）。

为什么单独拆一个文件：app.py 里有 `from competition_agents import ...`，
如果 competition_agents 反过来 `from app import _report_stage` 就是**循环导入**，
运行时要么 ImportError，要么拿到半初始化的对象。本模块不 import 本项目的任何代码，两边都能安全引用。

Codex 侧接入（competition_agents.py 的节点里）：

    from progress import report, _workers_for, is_cancelled

    def deep_competitor_agent(state):
        report("four_analysis")
        ...

三者都可以独立使用：只用 report() 也能让真实进度跑到前端。
"""

import os
import threading
import time

# ---------------- 阶段表 ----------------
# 前端不要再自己写中文映射，直接用这份数据里的 label。
STAGES = [
    ("parsing_rules", "解析评分规则", 5),
    ("similarity",    "查重查新",     15),
    ("idea_eval",     "评估创意",     24),
    ("oneliner",      "提炼一句话方案", 32),
    ("four_analysis", "并行四维分析",  40),
    ("writing",       "撰写申报书",    58),
    ("judging",       "模拟评委打分",  74),
    ("revising",      "按意见定向改写", 80),
    ("analysis",      "生成诊断建议",  88),
    ("rich_media",    "生成图表与PPT", 93),
    ("materials",     "生成答辩材料",  97),
]
STAGE_MAP = {k: {"label": l, "pct": p} for k, l, p in STAGES}

# 前端顶部那排胶囊点，按模式给不同集合
FAST_FLOW = ["parsing_rules", "similarity", "idea_eval", "oneliner",
             "analysis", "writing", "judging", "materials"]
DEEP_FLOW = ["parsing_rules", "similarity", "idea_eval", "oneliner", "four_analysis",
             "analysis", "writing", "judging", "revising", "analysis", "rich_media", "materials"]


def stage_flow(mode="fast"):
    """返回该模式的阶段顺序（给前端画胶囊点用）。"""
    return DEEP_FLOW if mode == "deep" else FAST_FLOW


def stage_meta(name):
    return STAGE_MAP.get(name, {})


# ---------------- 订阅 ----------------
_lock = threading.Lock()
_handlers = []
_task_id = None
_stage = None
_t0 = None


def subscribe(fn):
    """注册回调 fn(stage_name)。app.py 用它把 stage 写进 tasks 字典。"""
    with _lock:
        _handlers.append(fn)


def bind(task_id):
    """任务开始时绑定，之后 report() 才知道往哪个任务写。"""
    global _task_id, _stage, _t0
    with _lock:
        _task_id = task_id
        _stage = "queued"
        _t0 = time.time()
    report("queued")


def release():
    global _task_id
    with _lock:
        _task_id = None


def report(stage):
    """上报当前阶段。重复上报同一个阶段会被去重（每阶段只触发一次）。"""
    global _stage
    with _lock:
        if _stage == stage:
            return
        _stage = stage
        hs = list(_handlers)
    for fn in hs:
        try:
            fn(stage)
        except Exception as e:
            print("progress handler error:", e)


def snapshot():
    """给 /api/status 用的一次性取值，避免路由里到处加锁。"""
    with _lock:
        return _task_id, _stage, _t0


# ---------------- 任务取消 ----------------
CANCELLED = set()


def cancel(task_id):
    with _lock:
        CANCELLED.add(task_id)
    return True


def is_cancelled(task_id=None):
    tid = task_id or _task_id
    return bool(tid) and tid in CANCELLED


def clear_cancel(task_id):
    CANCELLED.discard(task_id)


# ---------------- 并发数（用户可在界面上调，不要写死） ----------------
_WORKERS = {"n": None}


def set_workers(n):
    """app.py 在启动任务时写入本次任务期望的并发数。"""
    try:
        _WORKERS["n"] = int(n) if n else None
    except (TypeError, ValueError):
        _WORKERS["n"] = None


def _workers_for(default=0):
    """供 competition_agents 里 ThreadPoolExecutor(max_workers=...) 使用。

    取值优先级：本次任务设定值 > 环境变量 > 调用方给的默认。
    """
    n = _WORKERS.get("n")
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
