# -*- coding: utf-8 -*-
"""SQLite 数据库自动备份：把 competition.db 复制到 backups/，保留最近 7 份。

用法：
    .venv/bin/python backup_db.py

配合 crontab（每天凌晨 4 点）：
    0 4 * * * cd /opt/comp-agent && .venv/bin/python backup_db.py >> backups/backup.log 2>&1
"""
import os
import sqlite3
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "competition.db")
BACKUP_DIR = os.path.join(BASE, "backups")
KEEP = 7


def backup():
    if not os.path.exists(DB):
        print("无数据库文件，跳过备份")
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, "competition-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
    # 用 SQLite 在线备份 API，比直接 copy 文件更安全（避免备份到写了一半的数据）
    src = sqlite3.connect(DB)
    try:
        with sqlite3.connect(dst) as dest:
            src.backup(dest)
    finally:
        src.close()
    print("已备份到:", dst)
    # 只保留最近 KEEP 份
    files = sorted(f for f in os.listdir(BACKUP_DIR)
                   if f.startswith("competition-") and f.endswith(".db"))
    for f in files[:-KEEP]:
        os.remove(os.path.join(BACKUP_DIR, f))
        print("已删除旧备份:", f)


if __name__ == "__main__":
    backup()
