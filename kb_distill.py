# -*- coding: utf-8 -*-
"""范文「写作范式蒸馏」：把范文库共性规律提炼成一段紧凑参考，注入生成 prompt。

与 kb_retrieve 的区别：
  - kb_retrieve：按关键词/模块检索具体范文原文，给「对标写法」；
  - kb_distill：给全体范文提炼出的「共性规律」，让主笔先对齐获奖范式再动笔。
读不到种子文件时静默返回空串，绝不阻断生成。
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "writing_paradigm.json")


def _load():
    try:
        with open(PARADIGM_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def paradigm_ref(module_tag=None, max_global=6):
    """返回一段可注入的「写作范式」文本；module_tag 给定则附带该模块的专门要点。"""
    p = _load()
    if not p:
        return ""
    parts = []
    g = p.get("global") or []
    if g:
        lines = ["（%d）%s" % (i + 1, s) for i, s in enumerate(g[:max_global])]
        parts.append("【写作范式（从真实获奖范文蒸馏，务必内化到写作里，不要照抄）】\n" + "\n".join(lines))
    if module_tag:
        mod = (p.get("modules") or {}).get(module_tag)
        if mod:
            parts.append("【本章写法要点】" + mod)
    return "\n\n".join(parts)


_MODULE_KEYS = ["项目简介", "创新点", "商业模式", "社会价值", "实践过程", "风险分析"]


def _pick_diverse(samples, max_samples):
    """按分数降序 + 贪心覆盖模块标签，取一批有代表性的范文做蒸馏素材。"""
    ordered = sorted(samples, key=lambda s: -(s.get("score") or 0))
    picked, seen_modules, seen_tags = [], set(), set()
    for s in ordered:
        if len(picked) >= max_samples:
            break
        tags = set(s.get("tags") or [])
        module_hit = (tags & set(_MODULE_KEYS)) - seen_modules
        new_tag = tags - seen_tags
        # 优先要「带来新模块」或「带来新标签」的样本，否则也按分数收
        if module_hit or new_tag or not picked:
            picked.append(s)
            seen_modules |= (tags & set(_MODULE_KEYS))
            seen_tags |= tags
    return picked


def _build_distill_prompt(corpus):
    return f"""你是科创赛事申报书写作教练。下面是范文库里的若干真实获奖项目/范文（已脱敏，均非完整原文，是公开报道归纳）。
请通读后，提炼这些获奖作品共同的「写作范式」，直接输出 JSON。

硬性要求：
1. global 数组给 6 条全局规律，每条一句话，聚焦「怎么写才对」，不要空洞口号；
2. modules 对象覆盖这 6 个模块：项目简介 / 创新点 / 商业模式 / 社会价值 / 实践过程 / 风险分析，每模块给一句具体写作要点；
3. 只提炼共性规律，不要复述某个具体项目；严禁出现院校名称、指导老师姓名、作者姓名；
4. 不编造数据，不引用样本里没有的数字；
5. 只输出 JSON 本身，不要任何解释，不要 markdown 代码块围栏。

输出格式（严格）：
{{"global": ["规则1", "规则2", "规则3", "规则4", "规则5", "规则6"], "modules": {{"项目简介": "...", "创新点": "...", "商业模式": "...", "社会价值": "...", "实践过程": "...", "风险分析": "..."}}}}

范文样本：
{corpus}
"""


def _extract_json(text):
    """从 LLM 输出里稳健地抠出 JSON 对象（容忍 markdown 围栏 / 前后杂散文字）。"""
    t = (text or "").strip()
    # 去 ```json ... ``` 围栏
    t = t.replace("```json", "").replace("```", "")
    # 取第一个 { 到最后一个 } 之间
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("LLM 未输出 JSON")
    return json.loads(t[a:b + 1])


def _validate_paradigm(data):
    """校验并规整蒸馏结果，确保 schema 完整；缺失模块用空串补齐。"""
    if not isinstance(data, dict):
        raise ValueError("蒸馏结果不是对象")
    g = data.get("global")
    if not isinstance(g, list) or not g:
        raise ValueError("global 规则缺失")
    data["global"] = [str(x).strip() for x in g if str(x).strip()][:6]
    mods = data.get("modules")
    if not isinstance(mods, dict):
        mods = {}
    data["modules"] = {k: str(mods.get(k, "")).strip() for k in _MODULE_KEYS}
    return data


def distill_from_samples(max_samples=40, max_chars=16000):
    """用 LLM 从当前范文库重新提炼写作范式，写回 writing_paradigm.json。

    返回 dict：{ok, samples_used, global_count, module_count}；失败抛异常且不覆盖原文件。
    """
    from kb_samples import list_samples
    samples = [s for s in list_samples()
               if s.get("type") == "范文" and (s.get("content") or "").strip()]
    if not samples:
        raise ValueError("范文库为空，无法蒸馏")

    picked = _pick_diverse(samples, max_samples)
    corpus = "\n\n---\n\n".join((s.get("content") or "").strip()[:600] for s in picked)
    corpus = corpus[:max_chars]

    from competition_agents import llm
    from langchain_core.messages import HumanMessage
    resp = llm.invoke([HumanMessage(content=_build_distill_prompt(corpus))])
    data = _validate_paradigm(_extract_json(resp.content))

    # 校验通过才覆盖，避免把现有范式写坏
    with open(PARADIGM_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "samples_used": len(picked),
        "global_count": len(data["global"]),
        "module_count": len([v for v in data["modules"].values() if v]),
        "paradigm": data,
    }


# ============ 答辩范式 / 评委评分范式 蒸馏 ============
DEFENSE_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "defense_paradigm.json")
JUDGE_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "judge_paradigm.json")
DEFENSE_QUESTIONS_PATH = os.path.join(BASE, "knowledge_base", "defense_questions.json")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def defense_paradigm_ref():
    """注入答辩生成 prompt 的「答辩范式」；无则空串。"""
    p = _load_json(DEFENSE_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【答辩范式（从高频答辩题库蒸馏，务必内化）】"]
    pats = [str(x).strip() for x in (p.get("question_patterns") or []) if str(x).strip()]
    if pats:
        parts.append("评委必问套路：\n" + "\n".join("（%d）%s" % (i + 1, s) for i, s in enumerate(pats[:8])))
    fw = str(p.get("answer_framework") or "").strip()
    if fw:
        parts.append("回答框架：" + fw)
    return "\n".join(parts) + "\n"


def judge_paradigm_ref():
    """注入评委/多专家评审 prompt 的「评委评分范式」；无则空串。"""
    p = _load_json(JUDGE_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【评委评分范式（从历史评审蒸馏，务必内化）】"]
    crits = [str(x).strip() for x in (p.get("common_criticisms") or []) if str(x).strip()]
    if crits:
        parts.append("高频扣分点：\n" + "\n".join("（%d）%s" % (i + 1, s) for i, s in enumerate(crits[:8])))
    byp = p.get("by_perspective") or {}
    for k, v in byp.items():
        if v and str(v).strip():
            parts.append("%s视角常挑的毛病：%s" % (k, str(v).strip()))
    return "\n".join(parts) + "\n"


def _llm_json(prompt):
    """调 LLM 并稳健抠出 JSON（复用全局 llm 与配额保护）。"""
    from competition_agents import llm
    from langchain_core.messages import HumanMessage
    resp = llm.invoke([HumanMessage(content=prompt)])
    return _extract_json(resp.content)


def distill_defense(max_questions=40, max_chars=16000):
    """从 defense_questions.json 蒸馏答辩范式，写回 defense_paradigm.json。"""
    qd = _load_json(DEFENSE_QUESTIONS_PATH)
    if not qd:
        raise ValueError("未找到答辩题库 defense_questions.json")
    qs = qd.get("questions") or []
    if not qs:
        raise ValueError("答辩题库为空")

    # 按 type 均衡采样
    from collections import defaultdict
    by_type = defaultdict(list)
    for q in qs:
        by_type[str(q.get("type") or "other")].append(q)
    picked, idx = [], 0
    types = list(by_type.keys())
    while len(picked) < max_questions and any(by_type[t] for t in types):
        t = types[idx % len(types)]
        lst = by_type[t]
        if lst:
            picked.append(lst.pop(0))
        idx += 1
    corpus = "\n".join(
        "【%s｜%s】%s\n要点：%s" % (q.get("type"), q.get("topic"), q.get("question"), q.get("hint"))
        for q in picked)
    corpus = corpus[:max_chars]

    prompt = f"""你是科创赛事答辩教练。下面是答辩高频题库里的一批真实评委问法（按工程/商业/建模/学术分类）。请通读后提炼「答辩范式」，直接输出 JSON。

硬性要求：
1. question_patterns 数组给 8 条「评委必问套路」，每条一句，聚焦「评委最爱从哪个角度戳穿项目的真伪/数据/落地」；
2. answer_framework 给一段回答框架（先摆结论 → 再给证据 → 最后堵质疑），200 字内；
3. 不出现院校名称、指导老师姓名、作者姓名，不编造数据；
4. 只输出 JSON 本身，不要解释、不要 markdown 围栏。

输出格式（严格）：
{{"question_patterns": ["套路1", "套路2", "套路3", "套路4", "套路5", "套路6", "套路7", "套路8"], "answer_framework": "..."}}

题库样本：
{corpus}
"""
    data = _llm_json(prompt)
    pats = data.get("question_patterns")
    if not isinstance(pats, list) or not pats:
        raise ValueError("question_patterns 缺失")
    out = {
        "question_patterns": [str(x).strip() for x in pats if str(x).strip()][:8],
        "answer_framework": str(data.get("answer_framework") or "").strip(),
    }
    _save_json(DEFENSE_PARADIGM_PATH, out)
    return {"ok": True, "questions_used": len(picked),
            "pattern_count": len(out["question_patterns"]), "paradigm": out}


def _history_judge_corpus(limit=60):
    """从 history 抽取评委评分 + 多专家批注，拼成蒸馏素材；无数据返回空串。"""
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE, "competition.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT result_data FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    parts = []
    for r in rows:
        try:
            d = json.loads(r["result_data"])
        except Exception:
            continue
        judge = d.get("judge_scores") or []
        if isinstance(judge, list) and judge:
            dims = "、".join(
                "%s=%s" % (x.get("name"), x.get("score"))
                for x in judge if isinstance(x, dict))
            if dims:
                parts.append("单评委评分维度：" + dims)
        er = d.get("expert_review") or ""
        if isinstance(er, str):
            try:
                erj = json.loads(er)
            except Exception:
                erj = None
        elif isinstance(er, dict):
            erj = er
        else:
            erj = None
        if erj:
            for e in erj.get("experts") or []:
                if not isinstance(e, dict):
                    continue
                role = e.get("role") or ""
                for it in e.get("issues") or []:
                    if isinstance(it, dict) and it.get("problem"):
                        parts.append("%s扣分：%s" % (role, it.get("problem")))
    return "\n".join(parts)[:16000]


def distill_judge(limit=60):
    """从历史评审记录蒸馏评委评分范式，写回 judge_paradigm.json。"""
    corpus = _history_judge_corpus(limit)
    if not corpus:
        raise ValueError("历史里没有评委评分/批注数据，请先生成几轮深度版再蒸馏")
    prompt = f"""你是科创赛事评审主委。下面是历史生成中对多份申报书给出的评委评分维度与批注（已脱敏）。请通读后提炼「评委评分范式」，直接输出 JSON。

硬性要求：
1. common_criticisms 数组给 8 条「高频扣分点」，每条一句，具体到问题，禁止空话；
2. by_perspective 对象给「技术/商业/落地」三个视角各自最常挑的毛病（各一句话）；
3. 不出现院校名称、指导老师姓名、作者姓名，不编造数据；
4. 只输出 JSON 本身，不要解释、不要 markdown 围栏。

输出格式（严格）：
{{"common_criticisms": ["扣分点1", "扣分点2", "扣分点3", "扣分点4", "扣分点5", "扣分点6", "扣分点7", "扣分点8"], "by_perspective": {{"技术": "...", "商业": "...", "落地": "..."}}}}

历史评审样本：
{corpus}
"""
    data = _llm_json(prompt)
    crits = data.get("common_criticisms")
    if not isinstance(crits, list) or not crits:
        raise ValueError("common_criticisms 缺失")
    byp = data.get("by_perspective") or {}
    out = {
        "common_criticisms": [str(x).strip() for x in crits if str(x).strip()][:8],
        "by_perspective": {k: str(byp.get(k, "")).strip() for k in ("技术", "商业", "落地")},
    }
    _save_json(JUDGE_PARADIGM_PATH, out)
    return {"ok": True, "criticism_count": len(out["common_criticisms"]), "paradigm": out}


# ============ 分析模块 / PPT·演讲稿 / 同质化 范式 ============
ANALYSIS_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "analysis_paradigm.json")
DECK_SPEECH_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "deck_speech_paradigm.json")
SIMILARITY_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "similarity_paradigm.json")


def _history_corpus(fields, limit=60, max_chars=16000):
    """从历史 result_data 抽取若干字段拼成蒸馏素材；无数据返回空串。"""
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE, "competition.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT result_data FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    parts = []
    for r in rows:
        try:
            d = json.loads(r["result_data"])
        except Exception:
            continue
        for f in fields:
            v = d.get(f)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip()[:800])
    return "\n\n---\n\n".join(parts)[:max_chars]


def analysis_paradigm_ref(module_tag=None):
    """注入竞品/商业/风险/技术分析 prompt 的「分析范式」；无则空串。"""
    p = _load_json(ANALYSIS_PARADIGM_PATH)
    if not p:
        return ""
    if module_tag and p.get(module_tag):
        return "【分析模块写法要点】" + str(p[module_tag]) + "\n"
    parts = ["【分析模块写法范式（从历史分析蒸馏）】"]
    for k in ("competitor", "business", "risk", "tech"):
        if p.get(k):
            parts.append("- %s" % str(p[k]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def deck_speech_paradigm_ref():
    """注入 PPT 大纲/演讲稿 prompt 的范式；无则空串。"""
    p = _load_json(DECK_SPEECH_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【PPT·演讲稿范式（从历史产出蒸馏）】"]
    for k in ("ppt_structure", "speech_opening", "speech_closing"):
        if p.get(k):
            parts.append("- %s" % str(p[k]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def similarity_paradigm_ref():
    """注入同质化检测 prompt 的范式；无则空串。"""
    p = _load_json(SIMILARITY_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【同质化检测范式（从历史检索蒸馏）】"]
    angles = p.get("common_angles") or []
    if angles:
        parts.append("常见撞车角度：" + "、".join(str(a) for a in angles[:10]))
    if p.get("differentiation_check"):
        parts.append("差异化检查：" + str(p["differentiation_check"]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def distill_analysis(limit=60):
    corpus = _history_corpus(["competitor_analysis", "business_model", "risk_analysis", "tech_solution"], limit)
    if not corpus:
        raise ValueError("历史里没有分析类内容，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事申报书的分析模块教练。下面是历史生成中的竞品分析/商业模式/风险分析/技术方案（已脱敏）。请提炼这四个模块各自的写法要点，输出 JSON。
硬性要求：competitor/business/risk/tech 各给一句话具体要点；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"competitor":"...","business":"...","risk":"...","tech":"..."}}
历史分析样本：
{corpus}
"""
    data = _llm_json(prompt)
    out = {k: str(data.get(k, "")).strip() for k in ("competitor", "business", "risk", "tech")}
    if not any(out.values()):
        raise ValueError("蒸馏结果为空")
    _save_json(ANALYSIS_PARADIGM_PATH, out)
    return {"ok": True, "paradigm": out}


def distill_deck_speech(limit=60):
    corpus = _history_corpus(["ppt_outline", "speech_script"], limit)
    if not corpus:
        raise ValueError("历史里没有 PPT 大纲/演讲稿，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事路演教练。下面是历史生成中的 PPT 大纲和路演演讲稿（已脱敏）。请提炼 PPT 结构与演讲稿的开场/收尾套路，输出 JSON。
硬性要求：ppt_structure 给 PPT 章节顺序；speech_opening 给开场套路；speech_closing 给收尾套路；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"ppt_structure":"...","speech_opening":"...","speech_closing":"..."}}
历史样本：
{corpus}
"""
    data = _llm_json(prompt)
    out = {k: str(data.get(k, "")).strip() for k in ("ppt_structure", "speech_opening", "speech_closing")}
    if not any(out.values()):
        raise ValueError("蒸馏结果为空")
    _save_json(DECK_SPEECH_PARADIGM_PATH, out)
    return {"ok": True, "paradigm": out}


def distill_similarity(limit=60):
    corpus = _history_corpus(["similarity_report"], limit)
    if not corpus:
        raise ValueError("历史里没有同质化检测报告，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事同质化检测教练。下面是历史生成中的同质化检测报告（已脱敏）。请提炼「项目之间最容易撞车的角度」和「差异化检查要点」，输出 JSON。
硬性要求：common_angles 给 6~10 个常见撞车角度；differentiation_check 给一句检查要点；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"common_angles":["角度1","角度2","角度3","角度4","角度5","角度6"],"differentiation_check":"..."}}
历史报告样本：
{corpus}
"""
    data = _llm_json(prompt)
    angles = data.get("common_angles")
    if not isinstance(angles, list) or not angles:
        raise ValueError("common_angles 缺失")
    out = {
        "common_angles": [str(a).strip() for a in angles if str(a).strip()][:10],
        "differentiation_check": str(data.get("differentiation_check") or "").strip(),
    }
    _save_json(SIMILARITY_PARADIGM_PATH, out)
    return {"ok": True, "angle_count": len(out["common_angles"]), "paradigm": out}
