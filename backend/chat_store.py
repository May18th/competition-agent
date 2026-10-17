"""SQLite persistence for per-user side-chat history."""
import os
import sqlite3
import threading
from datetime import datetime


_LOCK = threading.Lock()
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")


def ensure_schema(db_path=None):
    path = db_path or _DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _LOCK:
        conn = sqlite3.connect(path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chat_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, "
                "role TEXT NOT NULL CHECK(role IN ('user','bot')), content TEXT NOT NULL, "
                "style TEXT NOT NULL DEFAULT 'concise', created_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_uid_created "
                "ON chat_history(uid, created_at, id)"
            )
            conn.commit()
        finally:
            conn.close()


def append_message(db_path, uid, role, content, style="concise"):
    if not uid or role not in ("user", "bot"):
        raise ValueError("uid and a valid chat role are required")
    ensure_schema(db_path)
    created_at = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "INSERT INTO chat_history(uid, role, content, style, created_at) VALUES(?,?,?,?,?)",
                (uid, role, str(content or ""), style or "concise", created_at),
            )
            conn.commit()
        finally:
            conn.close()
    return created_at


def list_recent(db_path, uid, limit=50):
    if not uid:
        return []
    ensure_schema(db_path)
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 50
    with _LOCK:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=5000")
            rows = conn.execute(
                "SELECT role, content, style, created_at FROM chat_history "
                "WHERE uid=? ORDER BY id DESC LIMIT ?", (uid, limit)
            ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in reversed(rows)]


def clear(db_path, uid):
    if not uid:
        return 0
    ensure_schema(db_path)
    with _LOCK:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            cur = conn.execute("DELETE FROM chat_history WHERE uid=?", (uid,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
