#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把「评分维度覆盖清单 + 创新点可数」移植到线上 agents 文件。

线上是另一套血缘：没有 _scoring_cover_block / _innovation_ask，
prompt 片段的位置也与本地不同，所以按本文件里的锚点逐处插入，不做整段覆盖。

用法（在 agents_live3.py 同目录）：python _patch_online_innovation.py
产出 agents_innov.py。行尾沿用源文件（线上是 CRLF）。
"""
import io
import re
import sys

LOCAL = r"D:\competition-agent\backend\competition_agents.py"
SRC = "agents_live3.py"
OUT = "agents_innov.py"


def grab(text, start, end):
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j].rstrip() + "\n"


def main():
    local = io.open(LOCAL, encoding="utf-8").read()
    block = "\n\n".join([
        grab(local, "_SCORING_HINT = {", "def _dim_hint(name, family):"),
        grab(local, "def _dim_hint(name, family):", "def _scoring_cover_block(state: dict) -> str:"),
        grab(local, "def _scoring_cover_block(state: dict) -> str:", "def _innovation_slot(titles):"),
        grab(local, "def _innovation_slot(titles):", "def _defense_focus(state: dict) -> str:"),
    ])
    for fn in ("_SCORING_HINT", "_DIM_SPECIFIC_HINT", "def _dim_hint", "def _scoring_cover_block",
               "def _innovation_slot", "def _innovation_ask"):
        if fn not in block:
            sys.exit("块内缺：%s" % fn)

    raw = io.open(SRC, "rb").read()
    crlf = b"\r\n" in raw
    # 线上是 CRLF：先归一化成 LF 再匹配，写完统一还原。
    # 直接拿带 \r 的文本去匹配 "\n" 结尾的锚点会全部落空（踩过）。
    s = raw.decode("utf-8").replace("\r\n", "\n")
    n0 = len(s)

    for sym in ("_scoring_cover_block", "_innovation_ask"):
        if sym in s:
            sys.exit("线上已含 %s，疑似重复打补丁" % sym)

    # ① 待办节：删节后还要清掉指向它的引用
    old_tail = ("        if skipping:\n"
                "            continue\n"
                "        kept.append(line)\n"
                "    return '\\n'.join(kept).rstrip() + '\\n'")
    new_tail = ("        if skipping:\n"
                "            continue\n"
                "        kept.append(line)\n"
                "    t = '\\n'.join(kept).rstrip()\n"
                "    # 章节删掉后，正文里还留着指向它的引用（实测：「替换口径见待替换数据清单」\n"
                "    # 「（详见待补充清单）」）。留着就是指向不存在的内容，评委一翻就露。\n"
                "    _pending_ref = r'待(?:替换|补充|办)[^。；，\\n）)]{0,8}清单'\n"
                "    t = re.sub(r'[（(]\\s*(?:具体|详细|替换口径|口径|详见|见)?\\s*[^（()）]{0,8}?'\n"
                "               + _pending_ref + r'\\s*[）)]', '', t)\n"
                "    t = re.sub(r'[，,；;]\\s*(?:具体|详细|替换口径|口径)?\\s*(?:详见|见)\\s*'\n"
                "               r'(?:文末|后文|下)?\\s*' + _pending_ref, '', t)\n"
                "    t = re.sub(r'\\s*(?:详见|见)\\s*(?:文末|后文|下)?\\s*' + _pending_ref, '', t)\n"
                "    return t + '\\n'")
    if s.count(old_tail) != 1:
        sys.exit("待办节锚点异常：%d" % s.count(old_tail))
    s = s.replace(old_tail, new_tail, 1)

    # ② 在待办节之后插入新块
    anchor = "\n\n_CLICHE_REPLACE = ("
    if s.count(anchor) != 1:
        sys.exit("插入锚点异常：%d" % s.count(anchor))
    s = s.replace(anchor, "\n\n" + block.rstrip("\n") + anchor, 1)

    # ③ 简洁版：算出章节标题 + 注入创新点要求
    fast_anchor = '    prompt = f"""你是科创赛事申报书写作专家。请写一份**精简版**申报书'
    if s.count(fast_anchor) != 1:
        sys.exit("简洁版锚点异常：%d" % s.count(fast_anchor))
    fast_pre = ("    _quick_titles = [ln.strip()[3:] for ln in _fast_chapter_block(state).split(\"\\n\")\n"
                "                     if ln.strip().startswith(\"## \")]\n")
    s = s.replace(fast_anchor, fast_pre + fast_anchor, 1)

    fast_tail_old = ("6. 全文禁止出现任何【】方括号占位符，段落必须完整写完，需要估算的数字直接用「测算值/示例值/预计约 X」写出。\n"
                     "{_SELF_TECH_HIGHLIGHTS}")
    fast_tail_new = ("6. 全文禁止出现任何【】方括号占位符，段落必须完整写完，需要估算的数字直接用「测算值/示例值/预计约 X」写出。\n"
                     "{_innovation_ask(_quick_titles)}\n"
                     "{_SELF_TECH_HIGHLIGHTS}")
    if s.count(fast_tail_old) != 1:
        sys.exit("简洁版尾部锚点异常：%d" % s.count(fast_tail_old))
    s = s.replace(fast_tail_old, fast_tail_new, 1)

    # ④ 深度版：章节提前算 + 注入两份块
    deep_common = '    common = f"""你是资深科创赛事申报书写作专家。'
    if s.count(deep_common) != 1:
        sys.exit("深度版 common 锚点异常：%d" % s.count(deep_common))
    s = s.replace(deep_common,
                  "    # 章节先算出来：创新点要求要指名落在哪一章\n    chapters = _chapter_list(state)\n\n"
                  + deep_common, 1)

    deep_later = ("    # 并行失败自动退回串行，不牺牲正确性。\n"
                  "    chapters = _chapter_list(state)\n")
    if s.count(deep_later) == 1:
        s = s.replace(deep_later, "    # 并行失败自动退回串行，不牺牲正确性。\n", 1)
    else:
        alt = "    chapters = _chapter_list(state)\n    if len(chapters) >= 4:"
        if s.count(alt) != 1:
            sys.exit("深度版重复赋值锚点异常")
        s = s.replace(alt, "    if len(chapters) >= 4:", 1)

    deep_tail_old = "{_score_diagnosis_ref()}\n\n注意：\n1. 保留用户原来的核心内容和结构"
    deep_tail_new = ("{_score_diagnosis_ref()}\n{_scoring_cover_block(state)}\n"
                     "{_innovation_ask(chapters)}\n\n注意：\n1. 保留用户原来的核心内容和结构")
    if s.count(deep_tail_old) != 1:
        sys.exit("深度版尾部锚点异常：%d" % s.count(deep_tail_old))
    s = s.replace(deep_tail_old, deep_tail_new, 1)

    # ⑤ 简洁版也加评分维度清单（与本地一致：紧邻 _competition_focus 之前）
    fast_cf = "{_humanize_spec(state)}\n{_competition_focus(state)}\n\"\"\""
    if s.count(fast_cf) == 1:
        s = s.replace(fast_cf,
                      "{_humanize_spec(state)}\n{_scoring_cover_block(state)}{_competition_focus(state)}\n\"\"\"", 1)
    else:
        print("提示：简洁版 _competition_focus 锚点不唯一（%d），跳过覆盖清单注入" % s.count(fast_cf))

    out = s.replace("\n", "\r\n") if crlf else s
    io.open(OUT, "w", encoding="utf-8", newline="").write(out)
    print("ok: %d -> %d 字符%s" % (n0, len(s), "（CRLF）" if crlf else ""))
    for sym in ("def _scoring_cover_block", "def _innovation_ask", "_quick_titles",
                "{_innovation_ask(chapters)", "{_scoring_cover_block(state)}"):
        print("  %-32s %d" % (sym, s.count(sym)))


if __name__ == "__main__":
    main()
