# -*- coding: utf-8 -*-
"""记忆库数据层：sqlite 存储与 CRUD（与 history 同库 competition.db）。

统一收「范文 / 模板 / 材料」三类参考内容，按内容哈希去重，不重复记忆。
"""
import hashlib
import os
import re
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competition.db")

# 三类标签词表（可持续扩充）
MODULE_TAGS = ["项目简介", "社会价值", "实践过程", "商业模式", "创新点", "风险分析"]
TRACK_TAGS = ["文化文旅", "非遗", "人工智能", "web网站", "校园服务", "乡村振兴"]
FEATURE_TAGS = ["初创阶段", "有软著", "学生团队", "4人团队", "已试点", "用户量小"]

# 记忆类型
MEMORY_TYPES = ["范文", "模板", "材料"]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init():
    conn = _conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS kb_samples
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content TEXT NOT NULL,
                  tags TEXT NOT NULL,
                  source TEXT DEFAULT '',
                  score INTEGER DEFAULT 0,
                  created_time TEXT,
                  type TEXT DEFAULT '材料',
                  summary TEXT DEFAULT '',
                  content_hash TEXT DEFAULT '')''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_kb_tags ON kb_samples(tags)")
    conn.commit()
    conn.close()


_init()


def _ensure_column(column, ddl):
    """旧库迁移：表已存在但缺列时补列，避免 ALTER 报错。"""
    conn = _conn()
    c = conn.cursor()
    c.execute("PRAGMA table_info(kb_samples)")
    cols = [r[1] for r in c.fetchall()]
    if column not in cols:
        c.execute(ddl)
        conn.commit()
    conn.close()


_ensure_column("type", "ALTER TABLE kb_samples ADD COLUMN type TEXT DEFAULT '材料'")
_ensure_column("content_hash", "ALTER TABLE kb_samples ADD COLUMN content_hash TEXT DEFAULT ''")
_ensure_column("summary", "ALTER TABLE kb_samples ADD COLUMN summary TEXT DEFAULT ''")


def _normalize(text):
    """去空白做归一化，用于去重哈希。"""
    return re.sub(r"\s+", "", (text or "").strip())


def find_by_content(content):
    """按内容哈希查重，返回已存在的 id 或 None。"""
    if not content or not content.strip():
        return None
    h = hashlib.md5(_normalize(content).encode("utf-8")).hexdigest()
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id FROM kb_samples WHERE content_hash=?", (h,))
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None


def add_sample(content, tags, source="", score=0, type="材料", summary=""):
    """新增一条记忆，返回 (id, is_new)。

    content 哈希已存在时返回 (已有 id, False)，不重复插入。
    """
    if not content or not content.strip():
        raise ValueError("内容不能为空")
    h = hashlib.md5(_normalize(content).encode("utf-8")).hexdigest()
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT id FROM kb_samples WHERE content_hash=?", (h,))
    row = c.fetchone()
    if row:
        conn.close()
        return row["id"], False
    tag_text = ",".join([str(t).strip() for t in (tags or []) if str(t).strip()])
    c.execute(
        "INSERT INTO kb_samples(content, tags, source, score, created_time, type, summary, content_hash) VALUES(?,?,?,?,?,?,?,?)",
        (content.strip(), tag_text, source or "", int(score or 0),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), type or "材料", summary or "", h),
    )
    conn.commit()
    sid = c.lastrowid
    conn.close()
    # 新增范文后触发「写作范式」自动蒸馏检查（阈值 + 冷却，后台线程，失败静默）
    if (type or "材料") == "范文":
        try:
            from distill_scheduler import maybe_auto_distill
            maybe_auto_distill("writing")
        except Exception:
            pass
    return sid, True


def _row_to_dict(row):
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": [t for t in (row["tags"] or "").split(",") if t],
        "source": row["source"] or "",
        "score": row["score"] or 0,
        "type": row["type"] or "材料",
        "summary": row["summary"] or "",
        "created_time": row["created_time"] or "",
    }


def list_samples(tag=None, limit=100):
    """列出范文；可按 tag 过滤。每项含 id/content/tags/source/score/created_time。"""
    conn = _conn()
    c = conn.cursor()
    if tag:
        # tags 是逗号分隔，用 LIKE 匹配单个标签（前后加逗号避免误匹配）
        c.execute(
            "SELECT * FROM kb_samples WHERE (','||tags||',') LIKE ? ORDER BY score DESC, id DESC LIMIT ?",
            (f"%,{tag},%", int(limit)),
        )
    else:
        c.execute("SELECT * FROM kb_samples ORDER BY score DESC, id DESC LIMIT ?", (int(limit),))
    rows = c.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def delete_sample(sample_id):
    """删除一条范文，返回是否成功。"""
    conn = _conn()
    c = conn.cursor()
    c.execute("DELETE FROM kb_samples WHERE id=?", (int(sample_id),))
    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok


def get_all_tags():
    """返回三类标签词表，并合并库里已用过的标签。"""
    conn = _conn()
    c = conn.cursor()
    c.execute("SELECT tags FROM kb_samples")
    used = set()
    for r in c.fetchall():
        used.update(t for t in (r["tags"] or "").split(",") if t)
    conn.close()
    return {
        "module": sorted(set(MODULE_TAGS) | used),
        "track": sorted(set(TRACK_TAGS) | used),
        "feature": sorted(set(FEATURE_TAGS) | used),
    }
