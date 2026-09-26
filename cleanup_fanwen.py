# -*- coding: utf-8 -*-
"""版权整改清理脚本：删除库内全部非官方「范文」，清空范文种子文件。

用法：.venv/bin/python cleanup_fanwen.py
幂等：可重复执行；只删 type='范文'，保留「材料/模板」。
"""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "competition.db")

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS kb_samples "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, tags TEXT, source TEXT, "
            "score INTEGER, created_time TEXT, type TEXT, summary TEXT, content_hash TEXT)")
before = cur.execute("SELECT COUNT(*) FROM kb_samples WHERE type='范文'").fetchone()[0]
cur.execute("DELETE FROM kb_samples WHERE type='范文'")
conn.commit()
left = cur.execute("SELECT type, COUNT(*) FROM kb_samples GROUP BY type").fetchall()
conn.close()
print("删除范文 %d 条" % before)
print("剩余分类:", left)

for rel in ("knowledge_base/real_winning_samples.json", "knowledge_base/seed_samples.json"):
    p = os.path.join(BASE, rel)
    if os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print("已清空:", rel)
