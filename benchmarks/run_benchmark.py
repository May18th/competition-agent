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


def peer(name):
    """按部署布局取模块：本地是 backend/ 子目录，线上是扁平目录。"""
    import importlib
    try:
        return importlib.import_module("backend." + name)
    except ImportError:
        return importlib.import_module(name)

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.json")
BASE_URL = os.getenv("BENCH_BASE_URL", "http://127.0.0.1:8080")
ARMS = ("baseline", "fast", "deep")
# 补充对照：简洁版的产物是 1800 字摘要稿，拿它跟「裸写全文」比是错配——
# 官方维度自查看的是覆盖面，长文天然占优。所以要有一条「裸写也写 1800 字摘要」的
# 对照臂，才能回答「简洁版到底比裸写强在哪」。它不进盲评包（盲评只放三个可比稿）。
EXTRA_ARMS = ("baseline_slim",)
ALL_ARMS = ARMS + EXTRA_ARMS

BASELINE_PROMPT = """你是{competition}的参赛大学生。请根据下面这一句项目创意，写一份可以直接提交的参赛项目申报书。

项目创意：{idea}

要求：
1. 结构完整，含项目背景、痛点、方案、创新点、市场与商业模式、团队；
2. 有具体数字、具体场景、具体技术名词；
3. 中文全角标点；不要出现任何【】占位符。
"""

BASELINE_SLIM_PROMPT = """你是{competition}的参赛大学生。请根据下面这一句项目创意，写一份**精简版**申报书（摘要稿）。

项目创意：{idea}

要求：
1. 全文不超过 1800 字，章节按背景、痛点、方案、创新点、市场与商业模式、团队组织，每章一个自然段；
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
def run_baseline(case, slim=False):
    """通用模型裸写：不注入赛事规则、不给范文、不做质检。

    slim=True 时只要求 1800 字摘要稿，与简洁版同体量——用来做同体量对照。
    """
    sr = peer("stage_reporter")
    llm = peer("competition_agents").llm
    from langchain_core.messages import HumanMessage

    tpl = BASELINE_SLIM_PROMPT if slim else BASELINE_PROMPT
    prompt = tpl.format(competition=case["competition"], idea=case["idea"])
    started = time.time()
    # 用独立 task_id 包裹：用量能单独统计，也不会和真实用户的数据混在一起
    sr.set_current_task("bench-%s-%s" % (case["id"], "baseline_slim" if slim else "baseline"),
                        "benchmark", "baseline_slim" if slim else "baseline")
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
        # 富媒体是否产出：深度版会生成图表/表格/路演PPT，但正文里没有。
        # 不记下来的话，自查会把「没图表」扣分算到深度版头上（实测 c11/c14 因此反被判低），
        # 那是评测口径问题，不是内容问题。
        "rich_charts": bool(data.get("rich_charts")),
        "rich_tables": bool(data.get("rich_tables")),
        "rich_deck": bool(data.get("rich_deck")),
    }


# ---------------- 机器打分 ----------------
def _rec(text, media=None):
    """组装打分用的记录。media 里带 rich_charts/tables/deck，缺省就是没有。"""
    rec = {"proposal": text, "completeness": {"missing": []}}
    for k in ("rich_charts", "rich_tables", "rich_deck"):
        if media and media.get(k):
            rec[k] = media[k]
    return rec


def diagnose_score(text, arm, case, media=None):
    """按赛事官方评分维度自查（与产品内「评分项自查」同一套判据）。

    这是第三把尺子：机器分只看硬伤、区分不出好坏（实测三组都 92），
    官方维度自查才看得出「创新点有没有、有没有量化、有没有对标」。
    同样有同源偏向（判据出自本系统），所以仍不能单独当结论。
    """
    scorecard = peer("scorecard")
    mode = "deep" if arm == "deep" else "fast"
    try:
        diag = scorecard.diagnose(_rec(text, media), case["competition"], None, mode)
    except Exception as exc:
        return {"diag_total": None, "diag_note": "自查失败：%s" % str(exc)[:80]}
    gaps = [g.get("gap", "").split("：")[0] for g in (diag.get("top_gaps") or [])]
    return {"diag_total": diag.get("total"),
            "diag_available": diag.get("available"),
            "diag_top_gaps": gaps}


def machine_score(text, arm, case, media=None):
    """用系统自己的导出质检规则算分，记录 5 维度与否决项。

    记两列：
      score      生产口径（命中一票否决即 0 分）——用来体现「能不能交付」
      score_soft 评测口径（否决原因照记，但仍按维度算分）——用来做横向对照，
                 否则裸写组因为没人要求它规避双盲信息，一律 0 分，对照列没有区分度
    """
    score_export = peer("quality_gate").score_export

    mode = "deep" if arm == "deep" else "fast"
    rec = _rec(text, media)
    strict_out = score_export(rec, mode)
    soft_score, dims, reasons = score_export(rec, mode, strict=False)
    return {"score": strict_out[0], "score_soft": soft_score,
            "dims": dims, "reasons": strict_out[2] or reasons}


def official_dims(case):
    """取该赛事的官方评分维度与权重（供人工盲评按项打分）。"""
    candidates = [os.path.join(_ROOT, "backend", "assets", "data", "competition_profiles.json"),
                  os.path.join(_ROOT, "assets", "data", "competition_profiles.json")]
    path = next((p for p in candidates if os.path.exists(p)), candidates[0])
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
        for arm in ALL_ARMS:
            p = os.path.join(run_dir, "%s_%s.meta.json" % (case["id"], arm))
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                meta = json.load(f)
            rows.append({
                "case": case["id"], "competition": case["competition"], "arm": arm,
                "机器分": meta.get("score"),
                "机器分软": meta.get("score_soft"),
                "自查分": meta.get("diag_total"),
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
        a = agg.setdefault(r["arm"], {"n": 0, "score": 0, "soft": 0, "diag": 0, "dn": 0,
                                      "chars": 0, "sec": 0.0})
        a["n"] += 1
        a["score"] += r["机器分"] or 0
        a["soft"] += r["机器分软"] if r["机器分软"] is not None else (r["机器分"] or 0)
        if r["自查分"] is not None:
            a["diag"] += r["自查分"]; a["dn"] += 1
        a["chars"] += r["字数"] or 0
        a["sec"] += r["耗时秒"] or 0
    lines = ["# 评测基准报告", "",
             "生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
             "题目数：%d，组别：%s" % (len(cases), "、".join(ALL_ARMS)), "",
             "## 分组均值（三把尺子都只看相对差异，主证据仍是人工盲评）", "",
             "> 注意：各组题数不等时（例如中途配额/余额中断），这张表的均值不可直接横比。"
             "先看下方逐题明细里「三组都齐」的题号，再下结论。", "",
             "| 组 | 题数 | 机器分(生产口径) | 机器分(评测口径) | 官方维度自查 | 平均字数 | 平均耗时(秒) |",
             "|---|---|---|---|---|---|---|"]
    for arm in ALL_ARMS:
        a = agg.get(arm)
        if not a:
            continue
        lines.append("| %s | %d | %.1f | %.1f | %s | %d | %.0f |" % (
            arm, a["n"], a["score"] / a["n"], a["soft"] / a["n"],
            ("%.1f" % (a["diag"] / a["dn"])) if a["dn"] else "—",
            a["chars"] / a["n"], a["sec"] / a["n"]))
    lines += ["", "## 逐题明细", "",
              "| 题号 | 赛事 | 组 | 机器分 | 机器分(评测口径) | 自查分 | 字数 | 耗时(秒) | 警告项 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["case"], r["competition"][:12], r["arm"], r["机器分"], r["机器分软"],
            r["自查分"], r["字数"], r["耗时秒"], r["警告项"][:40]))
    lines += ["", "## 口径说明", "",
              "- **机器分**用本系统导出质检规则计算，三组同规则，可横向比；但它衡量的是"
              "「有没有硬伤」，不衡量「写得好不好」，不能单独当结论。",
              "- **生产口径**命中一票否决（空文档/乱码/占位符/编造引用/双盲泄露）即 0 分，"
              "代表「能不能直接交付」；**评测口径**照记否决原因但不归零，用于横向对照——"
              "裸写组从未被要求规避双盲信息，只报生产口径会全为 0，失去区分度。",
              "- **自查分**按该赛事官方评分维度逐项核对，判据与本产品「评分项自查」同源，"
              "能区分「创新点有没有集中列出 / 数字有没有 / 有没有对标」，但同样带系统侧偏向。",
              "- **主证据是人工盲评**：`blind/` 下每题有 A/B/C 三份匿名正文与 `blind_scores.csv` "
              "打分表，按该赛事官方评分维度逐项 1-10 分填写；填完用 `--score-only` 或直接汇总。",
              "- 盲评映射在 `blind/<case>_map.json`，评分前不要打开。",
              "- **`baseline_slim` 是同体量对照**：要求裸写也只出 1800 字摘要稿。"
              "简洁版的产物本来就是摘要稿，拿它跟「裸写全文」比是错配（官方自查看覆盖面，"
              "长文天然占优）；要判断简洁版有没有价值，看 `fast` vs `baseline_slim`。"
              "它不进盲评包，避免四份混评时被卷长差异带偏。"]
    report = os.path.join(run_dir, "report.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return csv_path, report


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="逗号分隔的题号，默认全部")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--arms", default=",".join(ALL_ARMS))
    ap.add_argument("--out", default="", help="输出目录，默认 benchmarks/runs/<时间戳>")
    ap.add_argument("--score-only", default="", help="只对已有结果重新打分")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip() in ALL_ARMS]
    cases = load_cases(args.ids or None, args.limit or None)

    if args.score_only:
        run_dir = args.score_only.rstrip("/\\")
        cases = load_cases()
        print("[bench] 重新打分：%s" % run_dir)
        by_id = {c["id"]: c for c in cases}
        for fn in sorted(os.listdir(run_dir)):
            if not fn.endswith(".meta.json"):
                continue
            meta_path = os.path.join(run_dir, fn)
            case_id, _, arm = fn[:-len(".meta.json")].partition("_")
            md_path = os.path.join(run_dir, fn[:-len(".meta.json")] + ".md")
            if arm not in ALL_ARMS or case_id not in by_id or not os.path.exists(md_path):
                continue
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            with open(md_path, encoding="utf-8") as f:
                text = f.read()
            meta.update(machine_score(text, arm, by_id[case_id], meta))
            meta.update(diagnose_score(text, arm, by_id[case_id], meta))
            meta["chars"] = len(text)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            print("  重算 %s %s → 机器分 %s / 评测口径 %s / 自查分 %s"
                  % (case_id, arm, meta.get("score"), meta.get("score_soft"),
                     meta.get("diag_total")))
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
                    if arm in ("baseline", "baseline_slim"):
                        text, meta = run_baseline(case, slim=(arm == "baseline_slim"))
                    else:
                        text, meta = run_system(case, arm)
                except Exception as exc:
                    print("   失败：%s" % exc)
                    continue
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(text)
                meta.update(machine_score(text, arm, case, meta))
                meta.update(diagnose_score(text, arm, case, meta))
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
