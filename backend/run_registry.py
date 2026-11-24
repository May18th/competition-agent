# -*- coding: utf-8 -*-
"""生成运行清单：为每一次生成落一条可追溯记录。

解决的问题：出了问题时只能回答「大概什么时候生成的」，答不了
「那次跑的是哪版 prompt、用的哪份知识库、模型是哪个、质检过了没有、导出成没成」。
把这些固定成一行，答辩时的说法就从「我们有多智能体」变成「每次运行都可审计」。

只存元数据与指纹，不存创意原文与生成正文（隐私）。
"""
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CODE_FILES = ("backend/app.py", "backend/competition_agents.py", "backend/quality_gate.py")
_KB_DIRS = ("backend/assets/data", "backend/assets/knowledge_base")

_ready_paths = set()
_lock = threading.Lock()
_fingerprint_cache = {}


def _sha(text, n=12):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def code_version():
    """代码版本指纹：三个核心文件内容的哈希。

    不依赖 git（部署环境未必有 .git），改过任何一行 prompt 指纹就会变。
    """
    if "code" in _fingerprint_cache:
        return _fingerprint_cache["code"]
    h = hashlib.sha256()
    for rel in _CODE_FILES:
        path = os.path.join(_ROOT, rel)
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except Exception:
            h.update(rel.encode())
    val = h.hexdigest()[:12]
    _fingerprint_cache["code"] = val
    return val


def kb_snapshot():
    """知识库快照指纹：赛事档案与规则文本的路径+大小+修改时间。

    规则文本更新后指纹会变，历史记录能据此判断「这条是按哪版规则生成的」。
    """
    if "kb" in _fingerprint_cache:
        return _fingerprint_cache["kb"]
    entries = []
    for rel in _KB_DIRS:
        base = os.path.join(_ROOT, rel)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
                entries.append("%s|%d|%d" % (os.path.join(rel, name), st.st_size, int(st.st_mtime)))
            except Exception:
                continue
    val = _sha("\n".join(entries), 12) if entries else ""
    _fingerprint_cache["kb"] = val
    return val


def ensure_schema(db_path):
    path = os.path.abspath(db_path)
    if path in _ready_paths:
        return
    with _lock:
        if path in _ready_paths:
            return
        with closing(sqlite3.connect(path, timeout=5)) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""CREATE TABLE IF NOT EXISTS generation_runs (
                task_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_key TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                competition TEXT NOT NULL DEFAULT '',
                idea_digest TEXT NOT NULL DEFAULT '',
                code_version TEXT NOT NULL DEFAULT '',
                kb_snapshot TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                calls INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                quality_score INTEGER,
                quality_reasons TEXT NOT NULL DEFAULT '',
                quality_missing TEXT NOT NULL DEFAULT '',
                export_state TEXT NOT NULL DEFAULT 'pending',
                export_warnings TEXT NOT NULL DEFAULT '',
                history_id INTEGER
            )""")
            for col, ddl in (
                ("export_state", "ALTER TABLE generation_runs ADD COLUMN export_state TEXT NOT NULL DEFAULT 'pending'"),
                ("export_warnings", "ALTER TABLE generation_runs ADD COLUMN export_warnings TEXT NOT NULL DEFAULT ''"),
                ("history_id", "ALTER TABLE generation_runs ADD COLUMN history_id INTEGER"),
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON generation_runs(created_at)")
            conn.commit()
        _ready_paths.add(path)


def record_run(db_path, usage_db_path, *, task_id, mode="", competition="", idea="",
               user_id="", duration_ms=0, quality_score=None, quality_reasons=None,
               quality_missing=None, history_id=None):
    """生成结束后写一条清单；token 从用量表按 task_id 汇总。失败不影响主流程。"""
    if not task_id:
        return
    ensure_schema(db_path)
    calls = prompt_tokens = completion_tokens = total_tokens = 0
    model = ""
    try:
        with closing(sqlite3.connect(usage_db_path, timeout=5)) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            row = conn.execute("""SELECT COUNT(*), COALESCE(SUM(prompt_tokens),0),
                COALESCE(SUM(completion_tokens),0), COALESCE(SUM(total_tokens),0)
                FROM llm_usage WHERE task_id = ?""", (task_id,)).fetchone()
            if row:
                calls, prompt_tokens, completion_tokens, total_tokens = row
            m = conn.execute("SELECT model FROM llm_usage WHERE task_id = ? AND model != '' LIMIT 1",
                             (task_id,)).fetchone()
            model = m[0] if m else ""
    except Exception:
        pass
    user_key = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16] if user_id else "anonymous"
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""INSERT OR REPLACE INTO generation_runs
            (task_id, created_at, user_key, mode, competition, idea_digest, code_version,
             kb_snapshot, model, calls, prompt_tokens, completion_tokens, total_tokens,
             duration_ms, quality_score, quality_reasons, quality_missing, history_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_key, mode,
             str(competition or "")[:80], _sha(str(idea or ""), 10), code_version(), kb_snapshot(),
             model, int(calls or 0), int(prompt_tokens or 0), int(completion_tokens or 0),
             int(total_tokens or 0), int(duration_ms or 0), quality_score,
             json.dumps(quality_reasons or [], ensure_ascii=False),
             json.dumps(quality_missing or [], ensure_ascii=False), history_id))
        conn.commit()


def update_export(db_path, task_id="", state="ok", warnings=None, history_id=None):
    """导出环节回填结果：ok / warned / blocked，带上当时的警告项。

    导出请求常常只带 history_id 不带 task_id，所以两条路都要能定位到那一行。
    """
    if not task_id and not history_id:
        return
    ensure_schema(db_path)
    payload = (str(state)[:20], json.dumps(warnings or [], ensure_ascii=False))
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        if task_id:
            conn.execute("UPDATE generation_runs SET export_state=?, export_warnings=? WHERE task_id=?",
                         payload + (task_id,))
        else:
            conn.execute("UPDATE generation_runs SET export_state=?, export_warnings=? WHERE history_id=?",
                         payload + (int(history_id),))
        conn.commit()


def recent_runs(db_path, limit=50):
    ensure_schema(db_path)
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute("SELECT * FROM generation_runs ORDER BY created_at DESC LIMIT ?",
                            (max(1, min(500, int(limit or 50))),)).fetchall()
    return [dict(r) for r in rows]
