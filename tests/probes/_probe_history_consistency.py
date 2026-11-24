# -*- coding: utf-8 -*-
"""一次性探针：验证「前端拿到的正文」与「历史库里存的正文」是同一份。

修复前：最终篇幅闸门（压缩）跑在 save_history_item 之后，历史里是压缩前的长稿，
前端是压缩后的短稿，导出回源 history_id 时取到长稿 → 导出件与预览字数不一致。

跑法（本地服务须已在 8080 起好）：
    python tests/probes/_probe_history_consistency.py
判定通过：status.data 里的正文有效字数 == history 表里存的正文有效字数。
"""
import http.cookiejar
import json
import sqlite3
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"
DB = "backend/.data/competition.db"

PAYLOAD = {
    "idea": "面向高校实验室的试剂耗材智能盘点柜，用称重+视觉识别自动记录领用，解决耗材台账靠手抄、月底对不上账的问题",
    "competition_name": "互联网+",
    "mode": "fast",
}


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _post(opener, path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(opener, path):
    with opener.open(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def main():
    sys.path.insert(0, ".")
    from backend.competition_agents import _cjk_len

    opener = _opener()
    with opener.open(BASE + "/", timeout=30) as resp:
        resp.read()

    started = time.time()
    r = _post(opener, "/api/generate_async", PAYLOAD)
    if not r.get("success"):
        print("提交失败:", r)
        return 1
    task_id = r["task_id"]
    print("task_id:", task_id)

    status = {}
    for _ in range(300):
        time.sleep(2)
        status = _get(opener, "/api/status/" + task_id)
        if status.get("status") in ("done", "error", "cancelled"):
            break
    print("状态: %s，耗时 %ds" % (status.get("status"), int(time.time() - started)))
    if status.get("status") != "done":
        print("错误:", status.get("error"))
        return 2

    data = status.get("data") or {}
    api_proposal = data.get("proposal") or ""
    api_chars = data.get("proposal_chars")
    api_len = _cjk_len(api_proposal)

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, result_data FROM history ORDER BY id DESC LIMIT 1").fetchone()
    hist_proposal = ""
    if row:
        try:
            hist_proposal = (json.loads(row["result_data"]) or {}).get("proposal", "")
        except Exception as exc:
            print("历史解析失败:", exc)
    hist_len = _cjk_len(hist_proposal)

    print("\n前端（status.data）正文 %d 字，payload 自报 %s 字" % (api_len, api_chars))
    print("历史库（history id=%s）正文 %d 字" % (row["id"] if row else "-", hist_len))
    print("差值: %d 字" % (api_len - hist_len))

    ok = bool(hist_proposal) and api_len == hist_len
    print("\n判定:", "PASS 两份正文一致" if ok else "FAIL 两份正文不一致")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
