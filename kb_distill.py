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
