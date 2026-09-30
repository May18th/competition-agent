# -*- coding: utf-8 -*-
"""实测两档生成耗时（走真实 HTTP 链路：generate_async + status 轮询）。
用法：python _time_bench.py [fast|deep|all]
输出：每种组合的墙钟耗时，供前端卡片文案对齐。
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"

IDEA = "面向高校实验室的智能试剂柜管理系统：用 RFID + 称重传感实现试剂全生命周期追溯，"
IDEA += "解决危化品领用登记靠纸质台账、过期试剂难清理、安全责任难追溯三个痛点。"

DRAFT = (
    "一、项目背景\n"
    "高校实验室危化品管理长期依赖纸质台账，领用登记不及时、过期试剂难清理，"
    "安全责任难以追溯。本团队面向这一问题设计智能试剂柜管理系统。\n\n"
    "二、解决方案\n"
    "采用 RFID 标签 + 高精度称重传感器，实现试剂入库、领用、归还、报废全流程自动记录；"
    "配套微信小程序，支持扫码领用与到期预警。\n\n"
    "三、创新点\n"
    "称重与 RFID 双模校验，避免误领；试剂到期自动推送；数据可导出为安全台账。\n\n"
    "四、预期成果\n"
    "在 3 个校内实验室试点，形成可复制的管理规范与数据报表。"
)


# 本机回环请求不走代理（环境里可能设了 HTTP_PROXY，会导致 127.0.0.1 请求 502）
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({}))
)


def post_json(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_json(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def bench(mode, with_draft):
    payload = {
        "competition_name": "iCAN大学生创新创业大赛",
        "competition": "iCAN大学生创新创业大赛",
        "idea": IDEA,
        "rules": "",
        "proposal_draft": DRAFT if with_draft else "",
        "mode": mode,
    }
    t0 = time.time()
    r = post_json("/api/generate_async", payload)
    task_id = r.get("task_id") or r.get("id")
    if not task_id:
        raise RuntimeError("未拿到 task_id: %s" % r)
    stages = []
    while True:
        time.sleep(0.6)
        s = get_json("/api/status/%s" % task_id)
        st = s.get("status")
        stage = s.get("stage") or ""
        if stage and (not stages or stages[-1][0] != stage):
            stages.append((stage, round(time.time() - t0, 1)))
        if st in ("done", "error", "cancelled"):
            break
        if time.time() - t0 > 900:
            raise RuntimeError("超时 900s")
    el = round(time.time() - t0, 1)
    n = len(s.get("data") or {}) if st == "done" else 0
    return {
        "mode": mode,
        "draft": bool(with_draft),
        "status": st,
        "seconds": el,
        "fields": n,
        "stages": stages,
    }


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    plan = []
    if which in ("fast", "all"):
        plan += [("fast", False), ("fast", True)]
    if which in ("deep", "all"):
        plan += [("deep", False), ("deep", True)]
    out = []
    for mode, draft in plan:
        try:
            res = bench(mode, draft)
        except Exception as e:
            res = {"mode": mode, "draft": draft, "status": "EXC", "error": str(e)}
        out.append(res)
        print("RESULT " + json.dumps(res, ensure_ascii=False), flush=True)
    print("\n=== 汇总 ===")
    for r in out:
        if r.get("status") == "done":
            print("%-5s %-8s %6ss  (字段 %s)" % (
                r["mode"], "有草稿" if r["draft"] else "仅创意", r["seconds"], r.get("fields")))
        else:
            print("%-5s %-8s FAILED %s" % (r["mode"], "有草稿" if r["draft"] else "仅创意", r.get("error") or r.get("status")))
