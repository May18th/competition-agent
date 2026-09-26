# -*- coding: utf-8 -*-
"""触发式自动蒸馏：范文/评审数据攒够量后，后台自动重跑对应范式蒸馏。

设计目标：既「自主学习」又不烧 LLM 配额——
  - 有阈值（新增数据达到 N 条才触发）
  - 有冷却（同一种范式最短间隔 COOLDOWN_SEC，防止刷爆）
  - 后台线程执行，不阻塞上传/生成请求
  - 失败静默记录，不重试风暴；手动后台按钮仍是兜底

可用环境变量 AUTO_DISTILL=off 关闭自动蒸馏。
"""
import json
import os
import sqlite3
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "competition.db")

THRESHOLDS = {
    "writing": 10,   # 范文库新增 10 条范文
    "judge": 15,     # 历史新增 15 条带多专家评审的记录
}
COOLDOWN_SEC = 3600  # 同一种范式 1 小时内最多自动蒸馏一次

_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _ensure_meta():
    c = _conn()
    c.execute("CREATE TABLE IF NOT EXISTS kb_meta (k TEXT PRIMARY KEY, v TEXT)")
    c.commit()
    c.close()


def _load_state():
    try:
        _ensure_meta()
        c = _conn()
        row = c.execute("SELECT v FROM kb_meta WHERE k='distill_state'").fetchone()
        c.close()
        if row:
            return json.loads(row["v"])
    except Exception:
        pass
    return {}


def _save_state(s):
    try:
        _ensure_meta()
        c = _conn()
        c.execute("INSERT OR REPLACE INTO kb_meta (k, v) VALUES ('distill_state', ?)",
                  (json.dumps(s, ensure_ascii=False),))
        c.commit()
        c.close()
    except Exception:
        pass


def _count(kind):
    c = _conn()
    try:
        if kind == "writing":
            n = c.execute("SELECT COUNT(*) FROM kb_samples WHERE type='范文'").fetchone()[0]
        elif kind == "judge":
            n = c.execute(
                "SELECT COUNT(*) FROM history WHERE COALESCE(json_extract(result_data,'$.expert_review'),'') != ''"
            ).fetchone()[0]
        else:
            n = 0
    finally:
        c.close()
    return int(n)


def _run(kind):
    """后台实际执行蒸馏（在子线程里跑，失败只记录不抛出）。"""
    try:
        from kb_distill import distill_from_samples, distill_judge
        if kind == "writing":
            distill_from_samples()
        elif kind == "judge":
            distill_judge()
    except Exception as e:
        try:
            import app_log
            app_log.warn("distill", "自动蒸馏 %s 失败：%s" % (kind, e))
        except Exception:
            pass


def maybe_auto_distill(kind):
    """新增数据后调用；达到阈值且过了冷却，则后台线程自动蒸馏一次。"""
    if os.getenv("AUTO_DISTILL", "").lower() in ("off", "0", "false"):
        return
    if kind not in THRESHOLDS:
        return
    try:
        with _lock:
            state = _load_state()
            cur = _count(kind)
            if kind not in state:
                # 首次运行：把当前数量记为水位，避免把服务里已有的历史数据误判成「新增」
                state[kind] = {"count": cur, "ts": 0}
                _save_state(state)
                return
            prev = int((state.get(kind) or {}).get("count") or 0)
            last = float((state.get(kind) or {}).get("ts") or 0)
            now = time.time()
            if cur - prev < THRESHOLDS[kind] or (now - last) < COOLDOWN_SEC:
                return
            # 先落水位，避免并发/连续触发重复蒸馏；失败也不回滚，手动按钮兜底
            state[kind] = {"count": cur, "ts": now}
            _save_state(state)
        threading.Thread(target=_run, args=(kind,), daemon=True).start()
    except Exception:
        pass
