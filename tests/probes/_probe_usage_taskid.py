# -*- coding: utf-8 -*-
"""一次性探针：真跑一次简洁版生成，验证 LLM 用量记录带上了 task_id / 用户 / 版本。

跑法（本地服务须已在 8080 起好）：
    python tests/probes/_probe_usage_taskid.py

判定通过：usage 库里该 task_id 的记录数 > 0，且 user_key 不是 anonymous。
跑完把结果贴回对话即可，脚本本身不进交付物。
"""
import http.cookiejar
import json
import sqlite3
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"
DB = "backend/.data/llm_usage.sqlite"

PAYLOAD = {
    "idea": "面向高校实验室的试剂耗材智能盘点柜，用称重+视觉识别自动记录领用，解决耗材台账靠手抄、月底对不上账的问题",
    "competition_name": "互联网+",
    "mode": "fast",
}

# 用法：python tests/probes/_probe_usage_taskid.py [fast|deep]
if len(sys.argv) > 1 and sys.argv[1] in ("fast", "deep"):
    PAYLOAD["mode"] = sys.argv[1]


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def _post(opener, path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(opener, path):
    with opener.open(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    opener, jar = _opener()
    with opener.open(BASE + "/", timeout=30) as resp:  # 拿匿名 uid cookie（HTML，不解析）
        resp.read()
    uid = next((c.value for c in jar if c.name == "comp_uid"), "")
    print("uid cookie:", (uid[:24] + "...") if uid else "(无)")

    started = time.time()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started))
    resp = _post(opener, "/api/generate_async", PAYLOAD)
    if not resp.get("success"):
        print("提交失败:", resp)
        return 1
    task_id = resp["task_id"]
    print("task_id:", task_id)

    status = {}
    for _ in range(300):
        time.sleep(2)
        status = _get(opener, "/api/status/" + task_id)
        st = status.get("status")
        stage = status.get("stage") or status.get("stage_label") or ""
        print("  [%3ds] %s / %s" % (int(time.time() - started), st, stage))
        if st in ("done", "error", "cancelled", "failed"):
            break
    print("最终状态:", status.get("status"), "耗时 %ds" % int(time.time() - started))
    if status.get("error"):
        print("错误:", status.get("error"))

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT task_id, user_key, mode, stage, total_tokens, duration_ms "
        "FROM llm_usage WHERE task_id = ? ORDER BY id", (task_id,))]
    # 有阶段名却没有 task_id = 上下文丢失（并行节点没拿到任务归属）；
    # 阶段名也为空的多半是 health 的探活请求，不属于本次生成。
    orphan = conn.execute(
        "SELECT COUNT(*) FROM llm_usage WHERE task_id = '' AND stage != '' AND created_at >= ?",
        (started_at,)).fetchone()[0]
    noise = conn.execute(
        "SELECT COUNT(*) FROM llm_usage WHERE task_id = '' AND stage = '' AND created_at >= ?",
        (started_at,)).fetchone()[0]
    print("\n=== 该任务的用量记录 %d 条 ===" % len(rows))
    for r in rows:
        print("  stage=%-14s tokens=%-7s %sms key=%s" % (
            r["stage"] or "-", r["total_tokens"], r["duration_ms"], r["user_key"]))
    stages = {r["stage"] for r in rows if r["stage"]}
    if rows:
        print("汇总: 调用 %d 次 / token %d / 耗时 %dms / mode=%s" % (
            len(rows), sum(r["total_tokens"] for r in rows),
            sum(r["duration_ms"] for r in rows), rows[0]["mode"] or "-"))
    print("覆盖环节 %d 个: %s" % (len(stages), " ".join(sorted(stages))))
    print("上下文丢失记录（有阶段无任务）: %d 条；探活噪声（无阶段无任务）: %d 条" % (orphan, noise))

    ok = bool(rows) and orphan == 0 and len(stages) >= 6 and rows[0]["user_key"] != "anonymous"
    print("\n判定:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
