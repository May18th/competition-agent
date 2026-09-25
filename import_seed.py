# -*- coding: utf-8 -*-
"""导入种子范文到范文库。

用法：
    python import_seed.py

行为：
- 优先调用 kb_samples.add_sample（任务 1 的正式接口）
- 若 kb_samples 尚未交付，自动降级为直连 competition.db 建表插入（表结构与分工文档一致）
- 幂等：已存在相同 content 的记录会跳过，可重复执行
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(BASE, "knowledge_base", "seed_samples.json")
DB = os.path.join(BASE, "competition.db")

CREATE_SQL = """CREATE TABLE IF NOT EXISTS kb_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT NOT NULL,
  tags TEXT NOT NULL,
  source TEXT DEFAULT '',
  score INTEGER DEFAULT 0,
  created_time TEXT
)"""


def load_seed():
    with open(SEED, encoding="utf-8") as f:
        return json.load(f)


def fallback_add(content, tags, source, score):
    """kb_samples 未就绪时的降级写入。返回 True 表示新插入，False 表示已存在跳过。"""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(CREATE_SQL)
    c.execute("SELECT COUNT(*) FROM kb_samples WHERE content = ?", (content,))
    if c.fetchone()[0] > 0:
        conn.close()
        return False
    c.execute(
        "INSERT INTO kb_samples (content, tags, source, score, created_time) "
        "VALUES (?, ?, ?, ?, ?)",
        (content, ",".join(tags), source, score,
         datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()
    return True


def main():
    if not os.path.exists(SEED):
        print("未找到种子文件：%s" % SEED)
        return 1

    items = load_seed()
    print("种子文件共 %d 段范文" % len(items))

    use_kb = False
    try:
        import kb_samples  # noqa: F401
        use_kb = True
        print("导入方式：kb_samples.add_sample（正式接口）")
    except Exception:
        print("导入方式：降级直连 competition.db（kb_samples 尚未交付）")

    added, skipped, failed = 0, 0, 0
    for it in items:
        content = it.get("content", "").strip()
        tags = it.get("tags", [])
        if not content or not tags:
            failed += 1
            continue
        try:
            if use_kb:
                import kb_samples as k
                exists = any(x.get("content") == content
                             for x in k.list_samples(limit=500))
                if exists:
                    skipped += 1
                    continue
                k.add_sample(content, tags,
                             it.get("source", ""), it.get("score", 0))
                added += 1
            else:
                ok = fallback_add(content, tags,
                                  it.get("source", ""), it.get("score", 0))
                added += 1 if ok else 0
                skipped += 0 if ok else 1
        except Exception as e:
            print("  [失败] %s -> %s" % (it.get("id"), e))
            failed += 1

    print("\n导入结果：新增 %d / 跳过 %d / 失败 %d" % (added, skipped, failed))

    conn = sqlite3.connect(DB)
    try:
        total = conn.execute("SELECT COUNT(*) FROM kb_samples").fetchone()[0]
        print("范文库当前总数：%d 条" % total)
    except Exception:
        print("范文库表尚未创建")
    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
