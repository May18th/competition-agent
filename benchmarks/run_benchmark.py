# -*- coding: utf-8 -*-
"""评测基准：同一批题目跑三组对照，产出可复现的对比数据。

三组（arms）：
  baseline  通用大模型裸写——只给赛事名和那一句创意，要求写一份申报书
  fast      本系统简洁版（走真实生产接口 /api/generate_async，mode=fast）
  deep      本系统深度版（同一接口，mode=deep）

用法：
    # 三组各跑前 3 题（服务需已在 8080 运行，且 QUOTA_DAILY_LIMIT 放宽）
    python benchmarks/run_benchmark.py --limit 3

    # 只跑指定题目 / 指定组
    python benchmarks/run_benchmark.py --ids c01,c02 --arms fast,deep

    # 对已有结果重新打分（不重新生成）
    python benchmarks/run_benchmark.py --score-only benchmarks/runs/20261124-2100

产物（benchmarks/runs/<时间戳>/）：
    <case>_<arm>.md         正文
    <case>_<arm>.meta.json  耗时、token、机器评分与理由
    summary.csv             三组逐题对照表
    report.md               汇总报告
    blind/                  人工盲评包（A/B/C 匿名 + 打分表模板）
"""
import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "backend"))

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.json")
BASE_URL = os.getenv("BENCH_BASE_URL", "http://127.0.0.1:8080")
ARMS = ("baseline", "fast", "deep")

BASELINE_PROMPT = """你是{competition}的参赛大学生。请根据下面这一句项目创意，写一份可以直接提交的参赛项目申报书。

项目创意：{idea}

要求：
1. 结构完整，含项目背景、痛点、方案、创新点、市场与商业模式、团队；
2. 有具体数字、具体场景、具体技术名词；
3. 中文全角标点；不要出现任何【】占位符。
"""


# ---------------- 取题 ----------------
def load_cases(ids=None, limit=None):
    with open(CASES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"]
    if ids:
        want = {x.strip() for x in ids.split(",") if x.strip()}
        cases = [c for c in cases if c["id"] in want]
    if limit:
        cases = cases[:limit]
    return cases


# ---------------- 三组生成 ----------------
def run_baseline(case):
    """通用模型裸写：不注入赛事规则、不给范文、不做质检。"""
    from backend import stage_reporter as sr
    from backend.competition_agents import llm
    from langchain_core.messages import HumanMessage

    prompt = BASELINE_PROMPT.format(competition=case["competition"], idea=case["idea"])
    started = time.time()
    # 用独立 task_id 包裹：用量能单独统计，也不会和真实用户的数据混在一起
    sr.set_current_task("bench-%s-baseline" % case["id"], "benchmark", "baseline")
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = (resp.content or "").strip()
    finally:
        sr.clear_current_task()
    return text, {"duration_ms": int((time.time() - started) * 1000)}


def _http_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _post_json(opener, path, payload):
    req = urllib.request.Request(
        BASE_URL + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(opener, path):
    with opener.open(BASE_URL + path, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def run_system(case, arm, poll_timeout=900):
    """走真实生产接口；返回 (正文, meta)。"""
    opener = _http_opener()
    with opener.open(BASE_URL + "/", timeout=60) as resp:
        resp.read()  # 拿匿名 uid cookie
    started = time.time()
    r = _post_json(opener, "/api/generate_async", {
        "idea": case["idea"],
        "competition_name": case["competition"],
        "mode": arm,
    })
    if not r.get("success"):
        raise RuntimeError("提交失败：%s" % r)
    task_id = r["task_id"]
    status = {}
    while time.time() - started < poll_timeout:
        time.sleep(2)
        status = _get_json(opener, "/api/status/" + task_id)
        if status.get("status") in ("done", "error", "cancelled"):
            break
    if status.get("status") != "done":
        raise RuntimeError("生成失败：%s %s" % (status.get("status"), status.get("error")))
    data = status.get("data") or {}
    return data.get("proposal") or "", {
        "duration_ms": int((time.time() - started) * 1000),
        "task_id": task_id,
        "proposal_chars": data.get("proposal_chars"),
        "reasons_gate": (data.get("completeness") or {}).get("missing") or [],
    }


# ---------------- 机器打分 ----------------
def machine_score(text, arm, case):
    """用系统自己的导出质检规则算分，记录 5 维度与否决项。"""
    from backend.quality_gate import score_export

    mode = "deep" if arm == "deep" else "fast"
    rec = {"proposal": text, "completeness": {"missing": []}}
    out = score_export(rec, mode)
    score, dims, reasons = out[0], out[1], out[2]
    return {"score": score, "dims": dims, "reasons": reasons}


def official_dims(case):
    """取该赛事的官方评分维度与权重（供人工盲评按项打分）。"""
    path = os.path.join(_ROOT, "backend", "assets", "data", "competition_profiles.json")
    try:
        with open(path, encoding="utf-8") as f:
            prof = json.load(f)
    except Exception:
        return []
    key = case["competition"]
    for c in prof.get("competitions", []):
        if c.get("name") == key or key in (c.get("aliases") or []):
            return c.get("scoring") or []
    return []


# ---------------- 盲评包 ----------------
def _shuffle_key(case_id, arm):
    return hashlib.md5(("%s|%s|blind" % (case_id, arm)).encode()).hexdigest()


def build_blind(run_dir, cases):
    """把三组正文按题匿名成 A/B/C，避免评分者被「哪个是系统出的」影响。"""
    blind_dir = os.path.join(run_dir, "blind")
    os.makedirs(blind_dir, exist_ok=True)
    rows = []
    for case in cases:
        texts = {}
        for arm in ARMS:
            p = os.path.join(run_dir, "%s_%s.md" % (case["id"], arm))
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    texts[arm] = f.read()
        if not texts:
            continue
        ordered = sorted(texts.items(), key=lambda kv: _shuffle_key(case["id"], kv[0]))
        labels = "ABC"
        mapping = {}
        for i, (arm, text) in enumerate(ordered):
            label = labels[i]
            mapping[label] = arm
            with open(os.path.join(blind_dir, "%s_%s.md" % (case["id"], label)), "w",
                      encoding="utf-8") as f:
                f.write(text)
        dims = official_dims(case)
        rows.append({
            "case": case["id"], "competition": case["competition"],
            "dims": "/".join("%s(%s)" % (d[0], d[1]) for d in dims),
        })
        with open(os.path.join(blind_dir, "%s_map.json" % case["id"]), "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
    # 打分表模板：每题三份，按官方维度各打 1-10 分
    csv_path = os.path.join(blind_dir, "blind_scores.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "competition", "version", "官方维度(权重)",
                    "各项分数(用 / 分隔，顺序同官方维度)", "总分(0-100)", "备注"])
        for r in rows:
            for label in "ABC":
                w.writerow([r["case"], r["competition"], label, r["dims"], "", "", ""])
    return csv_path


# ---------------- 汇总 ----------------
def write_summary(run_dir, cases):
    rows = []
    for case in cases:
        for arm in ARMS:
            p = os.path.join(run_dir, "%s_%s.meta.json" % (case["id"], arm))
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                meta = json.load(f)
            rows.append({
                "case": case["id"], "competition": case["competition"], "arm": arm,
                "机器分": meta.get("score"),
                "字数": meta.get("chars"),
                "耗时秒": round((meta.get("duration_ms") or 0) / 1000, 1),
                "警告项": "；".join((meta.get("reasons") or [])[:3]),
            })
    if not rows:
        return None
    csv_path = os.path.join(run_dir, "summary.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 分组均值
    agg = {}
    for r in rows:
        a = agg.setdefault(r["arm"], {"n": 0, "score": 0, "chars": 0, "sec": 0.0})
        a["n"] += 1
        a["score"] += r["机器分"] or 0
        a["chars"] += r["字数"] or 0
        a["sec"] += r["耗时秒"] or 0
    lines = ["# 评测基准报告", "",
             "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
             "题目数：%d，组别：%s" % (len(cases), "、".join(ARMS)), "",
             "## 分组均值（机器分 = 系统导出质检规则，仅作参考）", "",
             "| 组 | 题数 | 平均机器分 | 平均字数 | 平均耗时(秒) |", "|---|---|---|---|---|"]
    for arm in ARMS:
        a = agg.get(arm)
        if not a:
            continue
        lines.append("| %s | %d | %.1f | %d | %.0f |" % (
            arm, a["n"], a["score"] / a["n"], a["chars"] / a["n"], a["sec"] / a["n"]))
    lines += ["", "## 逐题明细", "",
              "| 题号 | 赛事 | 组 | 机器分 | 字数 | 耗时(秒) | 警告项 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["case"], r["competition"][:12], r["arm"], r["机器分"], r["字数"],
            r["耗时秒"], r["警告项"][:40]))
    lines += ["", "## 口径说明", "",
              "- **机器分**用本系统导出质检规则计算，三组同规则，可横向比；但它衡量的是"
              "「有没有硬伤」，不衡量「写得好不好」，不能单独当结论。",
              "- **主证据是人工盲评**：`blind/` 下每题有 A/B/C 三份匿名正文与 `blind_scores.csv` "
              "打分表，按该赛事官方评分维度逐项 1-10 分填写；填完用 `--score-only` 或直接汇总。",
              "- 盲评映射在 `blind/<case>_map.json`，评分前不要打开。"]
    report = os.path.join(run_dir, "report.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return csv_path, report


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="逗号分隔的题号，默认全部")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default="", help="输出目录，默认 benchmarks/runs/<时间戳>")
    ap.add_argument("--score-only", default="", help="只对已有结果重新打分")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip() in ARMS]
    cases = load_cases(args.ids or None, args.limit or None)

    if args.score_only:
        run_dir = args.score_only.rstrip("/\\")
        cases = load_cases()
        print("[bench] 重新打分：%s" % run_dir)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", stamp)
        os.makedirs(run_dir, exist_ok=True)
        print("[bench] 输出目录：%s" % run_dir)
        print("[bench] 题目 %d 个，组别 %s" % (len(cases), ",".join(arms)))

        for case in cases:
            for arm in arms:
                md_path = os.path.join(run_dir, "%s_%s.md" % (case["id"], arm))
                meta_path = os.path.join(run_dir, "%s_%s.meta.json" % (case["id"], arm))
                if os.path.exists(md_path) and os.path.exists(meta_path):
                    print("  跳过（已存在）：%s %s" % (case["id"], arm))
                    continue
                print("  跑 %s / %s ..." % (case["id"], arm), flush=True)
                try:
                    if arm == "baseline":
                        text, meta = run_baseline(case)
                    else:
                        text, meta = run_system(case, arm)
                except Exception as exc:
                    print("   失败：%s" % exc)
                    continue
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(text)
                meta.update(machine_score(text, arm, case))
                meta["chars"] = len(text)
                meta["arm"] = arm
                meta["case"] = case["id"]
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                print("   完成：%d 字，机器分 %s" % (len(text), meta.get("score")))

    blind = build_blind(run_dir, cases)
    out = write_summary(run_dir, cases)
    if out:
        print("\n[bench] 汇总：%s\n[bench] 报告：%s\n[bench] 盲评包：%s" % (out[0], out[1], blind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
