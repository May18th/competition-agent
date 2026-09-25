# -*- coding: utf-8 -*-
"""范文库数据层：sqlite 存储与 CRUD（与 history 同库 competition.db）。"""
import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competition.db")

# 三类标签词表（可持续扩充）
MODULE_TAGS = ["项目简介", "社会价值", "实践过程", "商业模式", "创新点", "风险分析"]
TRACK_TAGS = ["文化文旅", "非遗", "人工智能", "web网站", "校园服务", "乡村振兴"]
FEATURE_TAGS = ["初创阶段", "有软著", "学生团队", "4人团队", "已试点", "用户量小"]


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
                  created_time TEXT)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_kb_tags ON kb_samples(tags)")
    conn.commit()
    conn.close()


_init()


def add_sample(content, tags, source="", score=0):
    """新增一条范文，返回其 id。tags 为 list。"""
    if not content or not content.strip():
        raise ValueError("范文内容不能为空")
    tag_text = ",".join([str(t).strip() for t in (tags or []) if str(t).strip()])
    conn = _conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO kb_samples(content, tags, source, score, created_time) VALUES(?,?,?,?,?)",
        (content.strip(), tag_text, source or "", int(score or 0),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    sid = c.lastrowid
    conn.close()
    return sid


def _row_to_dict(row):
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": [t for t in (row["tags"] or "").split(",") if t],
        "source": row["source"] or "",
        "score": row["score"] or 0,
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
