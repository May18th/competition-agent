# -*- coding: utf-8 -*-
"""SQLite 数据库 + 知识库/敏感词库自动备份（第二百一十二轮）：复制到 backups/，保留最近 7 份。

用法：
    .venv/bin/python backup_db.py

配合 crontab（每天凌晨 4 点）：
    0 4 * * * cd /opt/comp-agent && .venv/bin/python backup_db.py >> backups/backup.log 2>&1
"""
import os
import sqlite3
import shutil
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "backend", ".data", "competition.db")
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
    # 第二百一十二轮：知识库（knowledge_base/*.json）与敏感词库（data/*.txt）一起打包备份
    _stamp = time.strftime("%Y%m%d-%H%M%S")
    _kb_dst = os.path.join(BACKUP_DIR, "knowledge_base-%s" % _stamp)
    _data_dst = os.path.join(BACKUP_DIR, "data-%s" % _stamp)
    for _src_dir, _dst in (("knowledge_base", _kb_dst), ("data", _data_dst)):
        _src = os.path.join(BASE, _src_dir)
        if os.path.isdir(_src):
            try:
                if os.path.exists(_dst):
                    shutil.rmtree(_dst)
                shutil.copytree(_src, _dst)
                print("已备份目录:", _dst)
            except Exception as _e:
                print("备份目录失败 %s: %s" % (_src_dir, _e))
    # 清理旧的 KB/data 目录备份（各保留最近 KEEP 份）
    for _prefix in ("knowledge_base-", "data-"):
        _old = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(_prefix))
        for f in _old[:-KEEP]:
            try:
                shutil.rmtree(os.path.join(BACKUP_DIR, f))
                print("已删除旧目录备份:", f)
            except Exception as _e:
                print("删除旧目录备份失败 %s: %s" % (f, _e))


if __name__ == "__main__":
    backup()
