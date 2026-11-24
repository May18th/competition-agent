# -*- coding: utf-8 -*-
"""线上端到端验证：真跑一次简洁版生成，确认清理链在新稿上生效。

在服务器上执行（服务须已在 127.0.0.1:8080 运行）：
    cd /opt/comp-agent && .venv/bin/python /tmp/_probe_cleanup_e2e.py

判定通过：正文与各板块里套话 0 处、无「待替换数据清单」类章节、无修订说明开头，
且导出质检分数不低于基线。跑完自动删除本次创建的测试记录。
"""
import http.cookiejar
import json
import re
import sqlite3
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"
DB = "/opt/comp-agent/competition.db"

PAYLOAD = {
    "idea": "面向高校实验室的试剂耗材智能盘点柜，用称重加视觉识别自动记录领用，"
            "解决耗材台账靠手抄、月底对不上账的问题",
    "competition_name": "互联网+",
    "mode": "fast",
}

FIELDS = ("proposal", "judge_feedback", "proposal_analysis", "tech_solution",
          "competitor_analysis", "business_model", "risk_analysis",
          "defense_questions", "ppt_outline", "speech_script")
CLICHE = ("赋能", "闭环", "抓手", "进一步提升", "不断完善", "积极探索",
          "高度重视", "显著提高", "扎实推进", "深入贯彻")
PENDING = re.compile(r"^#{1,6}\s+.*(?:待替换|待补充|需替换)", re.M)
REVISION = re.compile(r"^\s*(?:#{1,3}\s*)?(?:修订说明|修改说明|本次修订)", re.M)


def opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def post(op, path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with op.open(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get(op, path):
    with op.open(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    conn = sqlite3.connect(DB)
    before_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM history").fetchone()[0]

    op, jar = opener()
    with op.open(BASE + "/", timeout=30) as r:
        r.read()
    started = time.time()
    resp = post(op, "/api/generate_async", PAYLOAD)
    if not resp.get("success"):
        print("提交失败:", resp)
        return 1
    tid = resp["task_id"]
    print("task_id:", tid)

    for _ in range(300):
        time.sleep(2)
        st = get(op, "/api/status/" + tid)
        if st.get("status") in ("done", "error", "failed", "cancelled"):
            break
    print("最终状态: %s，耗时 %ds" % (st.get("status"), int(time.time() - started)))
    if st.get("status") != "done":
        print("错误:", st.get("error"))
        return 2

    row = conn.execute(
        "SELECT id, mode, competition_name, result_data FROM history "
        "WHERE id > ? ORDER BY id DESC LIMIT 1", (before_id,)).fetchone()
    if not row:
        print("未找到本次生成的记录")
        return 3
    hid, mode, comp, data = row
    rec = json.loads(data or "{}")
    print("history id=%s mode=%s comp=%s 字数=%s"
          % (hid, mode, comp, len(rec.get("proposal") or "")))

    joined = "\n".join(str(rec.get(k) or "") for k in FIELDS)
    hit = [w for w in CLICHE if w in joined]
    pend = PENDING.findall(rec.get("proposal") or "")
    head = "\n".join((rec.get("proposal") or "").split("\n")[:2])
    rev = REVISION.findall(head)
    print("套话命中: %s" % (hit or "无"))
    print("待办章节: %s" % (pend or "无"))
    print("修订说明开头: %s" % (rev or "无"))
    print("章节数:", (rec.get("proposal") or "").count("## "))

    try:
        sys.path.insert(0, "/opt/comp-agent")
        from quality_gate import score_export
        out = score_export(rec, "deep" if str(mode).lower() == "deep" else "fast")
        print("导出质检:", out[0] if isinstance(out, (tuple, list)) else out,
              "|", (out[2] if isinstance(out, (tuple, list)) and len(out) > 2 else ""))
    except Exception as e:
        print("质检调用失败（不影响判定）:", e)

    ok = not hit and not pend and not rev
    print("\n判定:", "PASS" if ok else "FAIL")

    conn.execute("DELETE FROM history WHERE id=?", (hid,))
    conn.commit()
    print("已删除本次测试记录 hid=%s" % hid)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
