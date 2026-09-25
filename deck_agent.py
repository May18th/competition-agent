# -*- coding: utf-8 -*-
"""
deck_agent.py —— 从深度版产物中提取结构化 PPT 素材

两个独立任务（可并发）：
  1. build_visuals(state)  → 图表数据（雷达、竞品矩阵、财务、甘特、预算）
  2. build_deck(state)     → PPT slides 结构（每页标题、要点、配图、演讲备注）

优先调用 LLM（DeepSeek）做结构化提取；当 API 余额不足 / 超时 / 输出为空时，
自动降级到规则提取，保证不依赖模型也能出图、出 PPT。

输出格式统一用 ```json 代码块，解析失败时降级，绝不抛异常。

作者：WorkBuddy（阿渡）  2026-09-25
"""
import os
import re
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage

load_dotenv()

_llm = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0.35,
    max_tokens=4000,
    request_timeout=60,
    max_retries=3,
)


def _to_float(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[，,\s]", "", str(v))
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return 0.0
    val = float(m.group(0))
    if "亿" in str(v):
        val *= 10000
    return val


def _extract_json(text):
    """从模型返回文本里尽量安全地抠出一个 JSON 对象"""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        raw = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        raw = text[start : end + 1]
    try:
        return json.loads(raw)
    except Exception:
        return None


def _state_digest(state):
    key_text = "|".join([
        str(state.get("competition_name", "")),
        str(state.get("idea", ""))[:400],
        str(state.get("one_liner", ""))[:120],
        str(state.get("proposal", ""))[:600],
    ])
    return hashlib.sha256(key_text.encode("utf-8")).hexdigest()[:16]


def _summarize_text(parts, limit=1800):
    out = []
    total = 0
    for label, txt in parts:
        txt = str(txt or "").strip()
        if not txt:
            continue
        chunk = f"【{label}】\n{txt}\n"
        if total + len(chunk) > limit:
            left = max(0, limit - total - 80)
            if left > 40:
                out.append(f"【{label}】\n{txt[:left]}...\n")
            break
        out.append(chunk)
        total += len(chunk)
    return "\n".join(out)


# ------------------------------------------------------------------
# 1. 图表数据
# ------------------------------------------------------------------
def _pick_scores_from_text(text):
    scores = {}
    if not text:
        return scores
    dims = ["创新性", "可行性", "市场价值", "技术壁垒", "社会价值"]
    for dim in dims:
        for pat in [
            dim + r"[：:是为]*\s*(\d{1,3}(?:\.\d+)?)",
            dim + r"[^0-9]{0,8}(\d{1,3}(?:\.\d+)?)",
        ]:
            m = re.search(pat, text)
            if m:
                scores[dim] = _to_float(m.group(1))
                break
    return scores


def _parse_competitor_table(text):
    """从 markdown 表格提取竞品矩阵"""
    try:
        from media_factory import split_blocks
    except Exception:
        return None
    for kind, payload in split_blocks(text or ""):
        if kind != "table" or len(payload) < 3:
            continue
        header = payload[0]
        rows = payload[1:]
        if len(header) < 3:
            continue
        metrics = [str(c).strip() for c in header[1:]]
        items = []
        matrix = []
        for r in rows:
            if not r:
                continue
            items.append(str(r[0]).strip() or f"竞品{len(items) + 1}")
            row_scores = []
            for val in r[1:]:
                val_str = str(val)
                sc = _to_float(val_str)
                if sc == 0:
                    if any(k in val_str for k in ["全自动", "高", "好", "强", "优", "领先", "±", "毫米"]):
                        sc = 8.5
                    elif any(k in val_str for k in ["半自动", "中", "一般", "尚可"]):
                        sc = 6.0
                    elif any(k in val_str for k in ["人工", "无", "低", "差", "弱", "落后"]):
                        sc = 3.5
                if sc > 10:
                    sc = sc / 10
                row_scores.append(sc)
            matrix.append(row_scores)
        if items and matrix:
            return {"items": items, "metrics": metrics, "matrix": matrix}
    return None


def _parse_finance(text):
    """从商业模式/申报书里提取前三年财务"""
    text = text or ""
    aliases = [
        ["第1年", "第一年", "Y1", "首年"],
        ["第2年", "第二年", "Y2"],
        ["第3年", "第三年", "Y3"],
    ]
    years_map = {}
    for i, alias_list in enumerate(aliases, 1):
        for a in alias_list:
            # 严格模式：收入、成本、利润
            m = re.search(
                re.escape(a) + r".{0,60}?收入[^0-9]*(\d+(?:\.\d+)?)[^0-9]{0,30}成本[^0-9]*(\d+(?:\.\d+)?)[^0-9]{0,30}利润[^0-9]*(-?\d+(?:\.\d+)?)",
                text, re.DOTALL,
            )
            if m:
                years_map[i] = (_to_float(m.group(1)), _to_float(m.group(2)), _to_float(m.group(3)))
                break
            # 宽松模式：先找到年份，再在附近 120 字抓收入/成本/利润
            m2 = re.search(re.escape(a) + r"[^。;；\n]{0,80}?收入[^0-9]*(\d+(?:\.\d+)?)", text)
            if m2:
                rev = _to_float(m2.group(1))
                tail = text[m2.end(): m2.end() + 120]
                cost = 0.0
                profit = 0.0
                mc = re.search(r"成本[^0-9]*(\d+(?:\.\d+)?)", tail)
                mp = re.search(r"利润[^0-9]*(-?\d+(?:\.\d+)?)", tail)
                if mc:
                    cost = _to_float(mc.group(1))
                if mp:
                    profit = _to_float(mp.group(1))
                years_map[i] = (rev, cost, profit)
                break
    if not years_map:
        return None
    idxs = sorted(years_map.keys())[:3]
    return {
        "years": [f"第{i}年" for i in idxs],
        "revenue": [years_map[i][0] for i in idxs],
        "cost": [years_map[i][1] for i in idxs],
        "profit": [years_map[i][2] for i in idxs],
        "unit": "万元",
    }


def _parse_timeline(text):
    """从实施计划文本提取阶段和周次"""
    phases = []
    starts = []
    ends = []
    if text:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.search(r"第?(\d+)[\-~～至到](\d+)[周周次]", line)
            if m:
                phase_name = re.sub(r"^[-·*▍\d\.、第周次\-~～至到\s]+", "", line).strip()
                phase_name = phase_name.replace("：", "").replace(":", "")
                if len(phase_name) < 2:
                    phase_name = f"阶段{len(phases) + 1}"
                phases.append(phase_name[:12])
                starts.append(int(_to_float(m.group(1))) - 1)
                ends.append(int(_to_float(m.group(2))))
    if not phases:
        phases = ["需求调研", "原型开发", "小批量试产", "市场推广"]
        starts = [0, 2, 5, 7]
        ends = [2, 5, 7, 8]
    return {"phases": phases[:6], "start_week": starts[:6], "end_week": ends[:6]}


def _parse_budget(text):
    """从商业模式/申报书里提取预算占比"""
    labels = ["研发", "生产", "营销", "运营"]
    values = []
    for label in labels:
        m = re.search(label + r"[^0-9：:]{0,5}[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*[%％]", text or "")
        if m:
            values.append(_to_float(m.group(1)))
        else:
            values.append(0.0)
    if sum(values) > 0:
        return {"labels": labels, "values": values}
    return {"labels": labels, "values": [40, 30, 15, 15]}


def fallback_visuals(state):
    """LLM 不可用时，用规则从文本里抠图表数据"""
    visuals = {"radar": {}, "competitor": {}, "finance": {}, "timeline": {}, "budget": {}}

    scores = {}
    scores.update(_pick_scores_from_text(state.get("idea_feedback", "")))
    scores.update(_pick_scores_from_text(state.get("judge_feedback", "")))
    if len(scores) >= 3:
        labels = ["创新性", "可行性", "市场价值", "技术壁垒", "社会价值"]
        visuals["radar"] = {"labels": labels, "values": [scores.get(k, 70) for k in labels]}

    comp = _parse_competitor_table(state.get("competitor_analysis", ""))
    if comp:
        visuals["competitor"] = comp

    fin = _parse_finance(state.get("business_model", "") or state.get("proposal", ""))
    if fin:
        visuals["finance"] = fin

    visuals["timeline"] = _parse_timeline(state.get("implementation_plan", ""))
    visuals["budget"] = _parse_budget(state.get("business_model", "") or state.get("proposal", ""))
    return visuals


def build_visuals(state):
    """返回 radar/competitor/finance/timeline/budget"""
    parts = [
        ("项目一句话定位", state.get("one_liner", "")),
        ("创意", state.get("idea", "")),
        ("规则解析", state.get("parsed_rules", "")),
        ("同质化分析", state.get("similarity_report", "")),
        ("竞品分析", state.get("competitor_analysis", "")),
        ("商业模式", state.get("business_model", "")),
        ("风险分析", state.get("risk_analysis", "")),
        ("技术方案", state.get("tech_solution", "")),
        ("实施计划", state.get("implementation_plan", "")),
        ("社会价值", state.get("social_value", "")),
        ("评委意见", state.get("judge_feedback", "")),
        ("创意评分反馈", state.get("idea_feedback", "")),
    ]
    context = _summarize_text(parts, limit=2800)

    prompt = f"""你是数据可视化专家。请从下面这份科创项目材料中提取能用于 matplotlib 画图的真实数据，输出一个 ```json 代码块。

要求：
1. 数值必须能在原文里找到依据，禁止凭空编造；找不到的字段就留空数组 / 空对象，不要硬填。
2. 财务数据只提取前三年，统一用“万元”作单位，数值只写纯数字。
3. 实施计划拆成 4-6 个阶段，start_week / end_week 是 0-8 的整数（共 8 周），end_week > start_week。
4. 竞品矩阵只对比“本项目 + 2-3 个竞品”，指标 3-5 个，得分 0-10，第一个条目必须是“本项目”。
5. 雷达图从评委意见/创意评分里提取五个维度得分 0-100；找不到就空对象。
6. 预算构成从商业模式/实施计划里找研发、生产/硬件、营销、运营等类别占比；只写百分比数字。

请严格输出 JSON 代码块，格式如下：
```json
{{
  "radar": {{"labels": ["创新性","可行性","市场价值","技术壁垒","社会价值"], "values": [82,74,68,71,80]}},
  "competitor": {{"items": ["本项目","竞品A","竞品B"], "metrics": ["功能完整度","价格优势","技术壁垒","易用性"], "matrix": [[9,8,9,8],[7,6,5,7],[6,7,4,6]]}},
  "finance": {{"years": ["第1年","第2年","第3年"], "revenue": [120,380,860], "cost": [150,300,560], "profit": [-30,80,300], "unit": "万元"}},
  "timeline": {{"phases": ["需求调研","原型开发","小批量试产","市场推广"], "start_week": [0,2,5,7], "end_week": [2,5,7,8]}},
  "budget": {{"labels": ["研发","生产","营销","运营"], "values": [45,30,15,10]}}
}}
```

材料如下：
{context}
"""
    llm_error = None
    try:
        resp = _llm.invoke([HumanMessage(content=prompt)])
        data = _extract_json(resp.content) or {}
    except Exception as e:
        data = {}
        llm_error = str(e)[:120]

    visuals = {"radar": {}, "competitor": {}, "finance": {}, "timeline": {}, "budget": {}}

    r = data.get("radar") or {}
    if r.get("labels") and r.get("values") and len(r["labels"]) == len(r["values"]):
        visuals["radar"] = r

    c = data.get("competitor") or {}
    if (c.get("items") and c.get("metrics") and c.get("matrix")
            and len(c["items"]) == len(c["matrix"])
            and all(len(row) == len(c["metrics"]) for row in c["matrix"])):
        visuals["competitor"] = c

    f = data.get("finance") or {}
    if f.get("years") and f.get("revenue") and f.get("cost"):
        ln = min(len(f["years"]), len(f["revenue"]), len(f["cost"]))
        profit = f.get("profit") or [f["revenue"][i] - f["cost"][i] for i in range(ln)]
        visuals["finance"] = {
            "years": f["years"][:ln],
            "revenue": [_to_float(x) for x in f["revenue"][:ln]],
            "cost": [_to_float(x) for x in f["cost"][:ln]],
            "profit": [_to_float(x) for x in profit[:ln]],
            "unit": f.get("unit") or "万元",
        }

    t = data.get("timeline") or {}
    if t.get("phases") and t.get("start_week") and t.get("end_week"):
        ln = min(len(t["phases"]), len(t["start_week"]), len(t["end_week"]))
        visuals["timeline"] = {
            "phases": [str(x) for x in t["phases"][:ln]],
            "start_week": [int(_to_float(x)) for x in t["start_week"][:ln]],
            "end_week": [max(int(_to_float(t["start_week"][i])) + 1, int(_to_float(t["end_week"][i]))) for i in range(ln)],
        }

    b = data.get("budget") or {}
    if b.get("labels") and b.get("values") and len(b["labels"]) == len(b["values"]):
        visuals["budget"] = {"labels": b["labels"], "values": [_to_float(x) for x in b["values"]]}

    # 若 LLM 没给出任何有效数据，降级到规则提取
    if not any(visuals.values()):
        visuals = fallback_visuals(state)
        return visuals, (llm_error or "LLM 未返回有效数据，已降级规则提取")
    return visuals, None


# ------------------------------------------------------------------
# 2. PPT 结构
# ------------------------------------------------------------------
def _split_proposal(proposal):
    """按章节标题切分申报书"""
    sections = []
    current = {"title": "项目概述", "body": []}
    for line in (proposal or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(?:[\d一二三四五六七八九十]+[、.．)\s]+|第[一二三四五六七八九十\d]+章)", line) and len(line) < 28:
            if current["body"]:
                sections.append(current)
            current = {"title": re.sub(r"^(?:[\d一二三四五六七八九十]+[、.．)\s]+|第[一二三四五六七八九十\d]+章\s*)", "", line), "body": []}
        else:
            current["body"].append(line)
    if current["body"]:
        sections.append(current)
    return sections


def _sentences(text, n=4):
    sents = re.split(r"[。；!！?？\n]", text or "")
    out = []
    for s in sents:
        s = s.strip()
        if 8 <= len(s) <= 60:
            out.append(s)
        if len(out) >= n:
            break
    return out


def fallback_deck(state):
    """LLM 不可用时，从申报书章节生成 PPT 结构"""
    title = state.get("competition_name", "科创项目") or "科创项目"
    idea_first = str(state.get("idea", "") or state.get("project_summary", "") or "").split("\n")[0][:40]
    default_title = idea_first or "科创项目"
    subtitle = str(state.get("one_liner", "") or "")[:50] or ""
    brand = f"{title} · {default_title}"
    deck = {"title": default_title, "subtitle": subtitle, "brand": brand, "slides": []}

    proposal = state.get("proposal", "") or state.get("idea", "") or ""
    sections = _split_proposal(proposal)
    if len(sections) < 3:
        sections = [
            {"title": "项目简介", "body": [state.get("project_summary", "") or state.get("idea", "")]},
            {"title": "解决方案", "body": [proposal[:300]]},
            {"title": "商业模式", "body": [state.get("business_model", "")[:300]]},
            {"title": "实施计划", "body": [state.get("implementation_plan", "")[:300]]},
            {"title": "社会价值", "body": [state.get("social_value", "")[:300]]},
        ]

    deck["slides"].append({"layout": "cover", "title": default_title})
    kickers = ["01 / 项目简介", "02 / 痛点与方案", "03 / 技术路线", "04 / 商业模式", "05 / 实施计划", "06 / 价值与风险"]
    for i, sec in enumerate(sections[:6]):
        bullets = _sentences("\n".join(sec["body"]), n=5)
        if not bullets:
            bullets = [sec["title"]]
        deck["slides"].append({
            "layout": "bullets",
            "kicker": kickers[i] if i < len(kickers) else f"0{i+1} / {sec['title']}",
            "title": sec["title"][:20],
            "bullets": bullets[:5],
            "note": "本页素材来自申报书自动生成，请按路演节奏取舍。",
        })
    deck["slides"].append({"layout": "end", "title": "感谢聆听", "bullets": ["敬请评委老师指正"]})
    return deck


def build_deck(state):
    """返回 deck 结构，可直接交给 media_factory.build_pptx()"""
    parts = [
        ("赛事", state.get("competition_name", "")),
        ("一句话定位", state.get("one_liner", "")),
        ("创意", state.get("idea", "")),
        ("项目简介", state.get("project_summary", "")),
        ("规则解析", state.get("parsed_rules", "")),
        ("同质化分析", state.get("similarity_report", "")),
        ("竞品分析", state.get("competitor_analysis", "")),
        ("商业模式", state.get("business_model", "")),
        ("风险分析", state.get("risk_analysis", "")),
        ("技术方案", state.get("tech_solution", "")),
        ("实施计划", state.get("implementation_plan", "")),
        ("社会价值", state.get("social_value", "")),
        ("申报书全文", state.get("proposal", "")),
        ("评委意见", state.get("judge_feedback", "")),
    ]
    context = _summarize_text(parts, limit=3200)

    title = state.get("competition_name", "科创项目") or "科创项目"
    idea_first = str(state.get("idea", "") or state.get("project_summary", "") or "").split("\n")[0][:40]
    default_title = idea_first or "科创项目"
    subtitle = str(state.get("one_liner", "") or "")[:50] or ""

    prompt = f"""你是资深路演 PPT 专家。请根据下面这份项目材料，生成 11 页路演 PPT 的结构，输出一个 ```json 代码块。

项目名建议：{default_title}
一句话定位建议：{subtitle}
赛事：{title}

结构必须严格按以下顺序，每页字段如下：
- layout: "cover" / "bullets" / "chart" / "table" / "end"
- kicker: 页码标签，例如 "01 / 痛点"、"05 / 竞品"
- title: 本页大标题（不超过 20 字）
- bullets: 3-5 条要点，每条不超过 24 字，必须具体、有数字/场景优先，禁止空话套话
- note: 演讲者备注，80 字以内，提示这一页怎么讲
- chart: 若 layout="chart"，则必填 "competitor" / "finance" / "timeline" / "radar" / "budget"
- caption: chart 页配图下方的说明文字
- table: 若 layout="table"，填 [["列1","列2"], ["行1","行2"]] 的二维数组

11 页顺序：
1. cover（封面）
2. bullets "01 / 痛点"：讲清项目解决的具体问题，带场景或数字
3. bullets "02 / 解决方案"：产品是什么、核心功能、怎么用
4. bullets "03 / 技术路线"：技术架构 + 2-3 个关键技术点
5. bullets "04 / 核心创新点"：3 条差异化优势，每条写清楚「别人做不到什么」
6. chart "05 / 竞品对比"：chart 用 "competitor"，caption 写清对比维度
7. bullets "06 / 商业模式"：目标客户、盈利模式、定价
8. chart "07 / 财务预测"：chart 用 "finance"，caption 写清单位
9. chart "08 / 实施计划"：chart 用 "timeline"，caption 写清总周期
10. bullets "09 / 风险与应对"：2-3 个主要风险 + 具体应对措施
11. end（结束页）

注意：
- 不要重复申报书全文，只提炼要点。
- 不要出现 "待补充"/"TODO"/"示例" 等占位词。
- 所有观点必须能在材料里找到依据。

输出格式：
```json
{{
  "title": "项目名",
  "subtitle": "一句话定位",
  "brand": "赛事名 · 项目名",
  "slides": [ {{...}}, {{...}} ]
}}
```

材料如下：
{context}
"""
    llm_error = None
    try:
        resp = _llm.invoke([HumanMessage(content=prompt)])
        data = _extract_json(resp.content) or {}
    except Exception as e:
        data = {}
        llm_error = str(e)[:120]

    deck = {
        "title": data.get("title") or default_title,
        "subtitle": data.get("subtitle") or subtitle,
        "brand": data.get("brand") or f"{title} · {default_title}",
        "slides": [],
    }

    slides = data.get("slides") or []
    valid_layouts = {"cover", "bullets", "chart", "table", "end"}
    has_cover = False
    has_end = False

    for s in slides:
        if not isinstance(s, dict):
            continue
        layout = s.get("layout") or "bullets"
        if layout not in valid_layouts:
            layout = "bullets"
        if layout == "cover":
            has_cover = True
        if layout == "end":
            has_end = True

        bullets = []
        for b in (s.get("bullets") or []):
            b = re.sub(r"^[-·*▍]\s*", "", str(b)).strip()
            if b and len(b) <= 80:
                bullets.append(b[:60])
        if len(bullets) > 6:
            bullets = bullets[:6]

        slide = {
            "layout": layout,
            "kicker": str(s.get("kicker") or ""),
            "title": str(s.get("title") or "")[:28],
            "bullets": bullets,
            "note": str(s.get("note") or "")[:180],
            "chart": s.get("chart") if layout == "chart" else None,
            "caption": str(s.get("caption") or "")[:70],
        }
        if layout == "table" and isinstance(s.get("table"), list) and len(s["table"]) >= 2:
            slide["table"] = [[str(c)[:60] for c in row] for row in s["table"][:12]]
        if layout == "end":
            slide["title"] = slide["title"] or "感谢聆听"
            if not slide["bullets"]:
                slide["bullets"] = ["敬请评委老师指正"]
        deck["slides"].append(slide)

    if not has_cover:
        deck["slides"].insert(0, {"layout": "cover", "title": deck["title"]})
    if not has_end:
        deck["slides"].append({"layout": "end", "title": "感谢聆听", "bullets": ["敬请评委老师指正"]})

    # 若 LLM 结果太薄（只有封面+结束），降级到章节切分
    if len(deck["slides"]) <= 2:
        deck = fallback_deck(state)
        return deck, (llm_error or "LLM 未返回有效 slides，已降级规则提取")
    return deck, None


# ------------------------------------------------------------------
# 3. 并发入口
# ------------------------------------------------------------------
def build_media_plan(state):
    """并发提取 visuals + deck，返回 dict（含 fallback 原因）"""
    reasons = []

    def run_visuals():
        v, err = build_visuals(state)
        if err:
            reasons.append(err)
        return v

    def run_deck():
        d, err = build_deck(state)
        if err:
            reasons.append(err)
        return d

    with ThreadPoolExecutor(max_workers=2) as pool:
        v_future = pool.submit(run_visuals)
        d_future = pool.submit(run_deck)
        visuals = v_future.result()
        deck = d_future.result()
    return {
        "visuals": visuals,
        "deck": deck,
        "digest": _state_digest(state),
        "fallback_reason": "；".join(reasons) if reasons else None,
    }


if __name__ == "__main__":
    demo_state = {
        "competition_name": "iCAN 大学生创新创业大赛",
        "one_liner": "让每一瓶危化品试剂的取用都可追溯",
        "idea": "智能危化品试剂管理柜：RFID+称重+三级预警，实现实验室危化品从领用、使用到归还的全流程闭环管理。",
        "parsed_rules": "创新性30%，实用性25%，技术难度20%，团队展示15%，社会价值10%。",
        "competitor_analysis": "## 竞品对比\n| 方案 | 单柜成本 | 识别精度 | 台账自动化 |\n|---|---|---|---|\n| 本项目 | 1.2万元 | ±1g | 全自动 |\n| 传统人工台账 | 0.1万元 | 人工 | 无 |\n| 进口智能柜 | 6.8万元 | ±0.5g | 半自动 |",
        "business_model": "目标客户：高校、科研院所、医药企业实验室。收入来源：智能柜硬件销售（1.2万元/台）、SaaS 年费（3000元/台）、耗材（RFID标签）。三年预测：第1年收入120万元、成本150万元、利润-30万元；第2年收入380万元、成本300万元、利润80万元；第3年收入860万元、成本560万元、利润300万元。预算构成：研发45%、生产30%、营销15%、运营10%。",
        "risk_analysis": "技术风险：称重精度受温湿度影响；市场风险：高校采购周期长；应对：双传感器融合校准、提前布局招投标。",
        "tech_solution": "整体架构：感知层（RFID+称重+摄像头）、平台层（Spring Boot + MySQL）、应用层（微信小程序）。技术难点：危化品混放检测、低功耗连续称重。",
        "implementation_plan": "第1-2周需求调研与用户访谈；第3-5周硬件原型与小程序开发；第6-7周小批量试产与试点部署；第8周市场推广与路演材料准备。",
        "social_value": "降低实验室危化品事故率，提升试剂使用透明度，惠及高校科研人员。",
        "proposal": "项目背景：实验室危化品管理依赖人工台账，500mL 丙酮实际使用 80mL 却无法追踪。解决方案：智能柜通过 RFID 识别试剂、称重记录余量、三级预警防止超期与超量。\n\n1. 项目背景与痛点\n实验室每年因试剂管理不善导致的安全事故超过 200 起。\n\n2. 解决方案\n智能试剂柜集成 RFID、称重、摄像头，实现一物一码一重量。\n\n3. 商业模式\n硬件销售 + SaaS 年费 + 耗材，首年覆盖 20 所高校。\n\n4. 实施计划\n八周完成原型到试点。\n\n5. 社会价值\n降低事故率，提升科研透明度。",
        "judge_feedback": "创新性：85分；可行性：78分；市场价值：72分；技术壁垒：75分；社会价值：80分。",
    }
    plan = build_media_plan(demo_state)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
