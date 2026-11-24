# -*- coding: utf-8 -*-
"""诊断驱动的定向补写：把评分缺口变成「改哪一章、补什么」，改完复检。

为什么不是继续往 prompt 里加约束
--------------------------------
实测：深度版 prompt 已经长到 160k tokens/次生成，再往里加「必须写创新点」，
4 条记录仍然全缺。约束埋在长 prompt 里会被稀释。改成生成后按诊断结果定向补，
每次只动一章、只补一个点，可验证、可回滚。

三道保险
--------
1. 只动目标章节：原文其它章节逐字保留，不整篇重写
2. 补写后重跑清理链与篇幅闸门：防止补出占位符、套话或超字数
3. 补完必须复检：分数没升或缺口没消，就回退到原文——绝不接受「改完更差」
"""

import importlib
import re


def peer(name):
    """按部署布局取同级模块：本地是 backend/ 子目录，线上是扁平目录。"""
    try:
        return importlib.import_module("backend." + name)
    except ImportError:
        return importlib.import_module(name)

# 缺口标签 → 优先落点章节（按顺序取第一个命中的章节标题）
_GAP_TARGET = {
    "创新点可数": ("技术方案", "执行摘要", "产品"),
    "差异化对比陈述": ("技术方案", "市场分析", "竞品"),
    "新颖性有外部支撑": ("技术方案", "附录"),
    "技术构成": ("技术方案",),
    "性能指标": ("技术方案",),
    "结构说明": ("技术方案",),
    "测试与对比": ("技术方案", "风险"),
    "成本与定价": ("商业模式", "财务"),
    "收入模型": ("商业模式", "财务"),
    "市场与客户规模": ("市场分析",),
    "推广路径": ("营销", "商业模式"),
    "角色分工": ("团队",),
    "协作机制": ("团队",),
    "成长与收获": ("团队",),
    "阶段计划": ("发展规划", "实施", "技术方案"),
    "资源投入": ("财务", "发展规划"),
    "风险与应对": ("风险",),
    "验证数据": ("技术方案", "风险"),
    "受益群体": ("社会价值",),
    "社会效益量化": ("社会价值",),
    "可持续性": ("社会价值", "发展规划"),
    "使用场景": ("背景", "执行摘要", "产品"),
    "价值量化": ("社会价值", "商业模式"),
    "与现有方案对比": ("技术方案", "市场分析"),
    "落地进展": ("营销", "发展规划"),
    "章节结构": ("执行摘要",),
    "版面合规": ("执行摘要",),
}

# 事实类缺口一律跳过，不代补、也不提醒：专利/查新/实测/试点订单这些本来就该
# 项目团队自己提供，系统不替用户操心。这里排除它们只有技术目的——让模型不碰，
# 碰了就会编（实测：让它补「新颖性」，它写出「已申请专利并经查新确认」）。
_FACT_GAPS = {
    "新颖性有外部支撑",   # 专利 / 软著 / 查新报告
    "测试与对比",         # 实测数据集、对比实验
    "验证数据",           # 实测 / 试点数据
    "落地进展",           # 试点部署、意向订单、合作单位
    "测试与对比数据",
}

# 补写任务的字数预算（按档位）。fast 版全文上限 1800，缺口补太狠会触发压缩。
_BUDGET = {"fast": 110, "deep": 260}


def _chapter_spans(proposal):
    """切出 [(标题, 起始行号, 结束行号)]，按 `## ` 二级标题切块。"""
    lines = (proposal or "").split("\n")
    idx = [i for i, ln in enumerate(lines) if re.match(r"^##\s+\S", ln.strip())]
    spans = []
    for n, start in enumerate(idx):
        end = idx[n + 1] if n + 1 < len(idx) else len(lines)
        spans.append((lines[start].strip(), start, end))
    return spans, lines


def locate_chapter(proposal, gap_label, dim_name=""):
    """为一条缺口找到该补在哪一章。找不到返回 None。"""
    spans, _ = _chapter_spans(proposal)
    if not spans:
        return None
    keys = _GAP_TARGET.get(gap_label, ())
    for key in keys:
        for title, start, end in spans:
            if key in title:
                return {"title": title, "start": start, "end": end}
    # 兜底：找不到对口章节就补在正文最后一章之前（避免污染「附录」）
    body = [s for s in spans if "附录" not in s[0]] or spans
    title, start, end = body[-1]
    return {"title": title, "start": start, "end": end, "fallback": True}


def plan_patches(diag, proposal, limit=2):
    """把诊断缺口转成补写任务。只取丢分最大的几章，避免无限加长。

    同一章的多条缺口合并成一次补写：连补两次同一章会重复调用模型，
    第二次还得在第一次的改写结果上再改，容易把第一次补好的内容覆盖掉。
    """
    if not diag.get("available"):
        return []
    by_chapter, order = {}, []
    for gap in diag.get("top_gaps") or []:
        label = gap["gap"].split("：")[0]
        if label in _FACT_GAPS:
            continue                      # 事实缺口不代补，也不提醒
        target = locate_chapter(proposal, label, gap.get("dim", ""))
        if not target:
            continue
        key = target["title"]
        slot = by_chapter.get(key)
        if slot is None:
            slot = by_chapter[key] = {
                "chapter": key, "start": target["start"], "end": target["end"],
                "fallback": bool(target.get("fallback")),
                "labels": [], "instructions": [], "lost": 0.0, "dims": [],
            }
            order.append(key)
        if label in slot["labels"]:
            continue
        slot["labels"].append(label)
        slot["instructions"].append(gap["gap"].split("：", 1)[-1])
        slot["lost"] += float(gap.get("lost") or 0)
        for dn in str(gap.get("dim", "")).split("、"):
            if dn and dn not in slot["dims"]:
                slot["dims"].append(dn)
    plan = [by_chapter[k] for k in order]
    plan.sort(key=lambda s: -s["lost"])
    for p in plan:
        p["label"] = " + ".join(p["labels"])
        p["dim"] = "、".join(p["dims"])
        p["instruction"] = (
            p["instructions"][0] if len(p["instructions"]) == 1
            else "\n".join("%d. %s" % (i, t) for i, t in enumerate(p["instructions"], 1)))
    return plan[:limit]


_RETRY_HINT = """
【上一次改写没写到位】必须落到具体的人与具体的收获：谁掌握了哪种方法、谁积累了哪类经验、
谁熟悉了什么流程。不能只写「团队获得成长」「成员得到锻炼」这类空话，那等于没写。
"""

_PATCH_PROMPT = """你是申报书编辑。下面是申报书的某一章，需要补齐一个评审关注点。

【本章原文】
{chapter}

【必须补齐的内容】
{instruction}

【硬性要求】
1. 原文里已有的具体数字、场景、技术名词、机构名，全部逐字保留，不要删改事实
2. 只在合适位置增补，改动幅度不超过原文的三成，不要整章换一种写法
3. 新增内容不超过 {budget} 字，宁短勿长
4. 不要出现【】占位符、不要写「待补充」「测算值待定」，拿不准的数字用「约 X（测算值）」直接写
5. 不要出现「赋能」「闭环」「抓手」这类套话，也不要出现「本项得分」「该维度」这类自评话术
6. **绝对不能声称任何未能确认的外部事实**：不许写「已申请专利」「已通过查新」「已实测」
   「已签约」「已在 N 家单位试点」「已有订单」「获 XX 奖」。这些只能由项目团队自己提供，
   你写了就是编造，会被评委当场问穿。缺这类内容时，改用可验证的设计目标或方法描述
   （例：不写「已申请专利」，写「该结构差异可作为专利与查新材料的申报基础」）
7. 直接输出修改后的完整章节（从原标题那一行开始），不要任何解释、前言或后记
"""


def rewrite_chapter(proposal, patch, llm=None, budget=None):
    """让模型只重写目标章节，其余章节原样拼回。失败返回原文。

    每次都按标题重新定位，不能用 patch 里缓存的行号：前一次补写会改变行数，
    按旧行号切片会把别的章节切一半，表现为「上一处补好的内容被覆盖」。
    """
    if llm is None:
        llm = peer("competition_agents").llm
    spans, lines = _chapter_spans(proposal)
    match = next(((t, s, e) for t, s, e in spans if t == patch["chapter"]), None)
    if not match:
        print("[scorecard-patch] 找不到章节「%s」，跳过" % patch["chapter"])
        return proposal, False
    _, start, end = match
    chapter = "\n".join(lines[start:end]).strip()
    prompt = _PATCH_PROMPT.format(chapter=chapter, instruction=patch["instruction"],
                                  budget=budget or _BUDGET["fast"])
    try:
        resp = llm.invoke(prompt)
        new_chapter = (getattr(resp, "content", "") or "").strip()
    except Exception as e:
        print("[scorecard-patch] 补写失败，保留原文：%s" % e)
        return proposal, False
    if not new_chapter or len(new_chapter) < len(chapter) * 0.6:
        # 章节被写短了，多半是模型只回了增量片段，不能拿来替换
        print("[scorecard-patch] 补写结果过短（%d < %d*0.6），保留原文"
              % (len(new_chapter), len(chapter)))
        return proposal, False
    if not new_chapter.lstrip().startswith("#"):
        new_chapter = patch["chapter"] + "\n" + new_chapter
    merged = lines[:start] + new_chapter.split("\n") + lines[end:]
    return "\n".join(merged), True


def _sanitize(text):
    """补写后重跑清理链，防止补出占位符、套话、内部待办。"""
    try:
        ca = peer("competition_agents")
        return ca._strip_cliches(ca._strip_ai_artifacts(ca._fix_mislabeled_measured(
            ca._strip_fabricated_times(ca._downgrade_fabrication(ca._strip_placeholders(
                ca._dedupe_consecutive(ca._strip_pending_sections(
                    ca._strip_revision_note(text)))))))))
    except Exception:
        return text


def patch_until_clean(result, competition_name, track=None, mode="fast",
                      limit=2, llm=None, min_gain=0.5):
    """诊断 → 补写 → 复检。分数没涨就回退，只保留真正改好的那几处。

    返回 {"before", "after", "applied": [...], "reverted": [...], "proposal"}
    """
    diagnose = peer("scorecard").diagnose

    mode = "deep" if str(mode).strip().lower() == "deep" else "fast"
    result = dict(result or {})
    proposal = result.get("proposal") or ""
    before = diagnose(result, competition_name, track, mode)
    plan = plan_patches(before, proposal, limit=limit)
    report = {"before": before.get("total"), "after": before.get("total"),
              "applied": [], "reverted": [], "proposal": proposal}
    if not plan:
        return report

    cur_proposal, cur_total = proposal, before.get("total")
    budget = _BUDGET["deep" if mode == "deep" else "fast"]
    for patch in plan:
        accepted, last_reason = False, "补写失败"
        # 模型单次输出不稳定：写不出具体收获就会被复检拒掉，这时换更明确的指令再试一次。
        # 复检已经把「改坏」挡住了，重试只增加一次调用成本，不会增加污染风险。
        for attempt in range(2):
            instr = patch["instruction"] + (_RETRY_HINT if attempt else "")
            nxt, ok = rewrite_chapter(cur_proposal, dict(patch, instruction=instr),
                                      llm=llm, budget=budget)
            if not ok:
                last_reason = "补写失败"
                continue
            nxt = _sanitize(nxt)
            diag_trial = diagnose(dict(result, proposal=nxt), competition_name, track, mode)
            gain = (diag_trial.get("total") or 0) - (cur_total or 0)
            if gain >= min_gain:
                cur_proposal, cur_total = nxt, diag_trial.get("total")
                report["applied"].append({"label": patch["label"], "chapter": patch["chapter"],
                                          "gain": round(gain, 1), "attempts": attempt + 1})
                accepted = True
                break
            last_reason = "复检未升分（%+.1f）" % gain
        if not accepted:
            report["reverted"].append({"label": patch["label"], "reason": last_reason})
    report["proposal"] = cur_proposal
    report["after"] = cur_total
    return report


if __name__ == "__main__":
    import json
    import os
    import sys

    db = (os.environ.get("COMPETITION_DB_PATH")
          or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "backend", ".data", "competition.db"))
    if len(sys.argv) < 2:
        print("用法: python -m backend.scorecard_patch <history_id> [--apply]")
        sys.exit(1)
    hid = int(sys.argv[1])
    apply_it = "--apply" in sys.argv

    import sqlite3
    with sqlite3.connect(db) as c:
        row = c.execute("SELECT result_data, mode, competition_name FROM history WHERE id=?",
                        (hid,)).fetchone()
    rec = json.loads(row[0] or "{}")
    _sc = peer("scorecard")
    diagnose, render_text = _sc.diagnose, _sc.render_text
    if not apply_it:
        plan = plan_patches(diagnose(rec, row[2], None, row[1]), rec.get("proposal") or "")
        print("补写计划（%d 章）：" % len(plan))
        for p in plan:
            print("  [%s] → %s\n     补：%s" % (p["label"], p["chapter"],
                                             p["instruction"].replace("\n", "\n         ")))
        print("\n加 --apply 实际执行（会调用模型，fast 约 10 秒/条）")
        sys.exit(0)

    rep = patch_until_clean(rec, row[2], None, row[1])
    print("自查分：%s → %s" % (rep["before"], rep["after"]))
    for a in rep["applied"]:
        print("  ✓ %s（%s）+%s" % (a["label"], a["chapter"], a["gain"]))
    for r in rep["reverted"]:
        print("  ✗ %s：%s" % (r["label"], r["reason"]))
    out = os.path.join(os.path.dirname(db), "patched_%d.md" % hid)
    with open(out, "w", encoding="utf-8") as f:
        f.write(rep["proposal"])
    print("\n补写后正文：%s" % out)
    print(render_text(diagnose(dict(rec, proposal=rep["proposal"]), row[2], None, row[1])))
