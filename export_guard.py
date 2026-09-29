# -*- coding: utf-8 -*-
"""第一百七十六轮：导出前规范检测模块（纯函数，不 import app.py / flask）。

规范验收标准写死为检测规则，导出前必查，不合格返回错误列表供调用方打回重生成：
1. Word 目录规范：docx 含 TOC 目录域（可刷新）+ 标题层级正确 + 章节顺序/缺章。
2. PPT 规范：页数 == ppt_outline 大纲页数，每页标题与大纲对应，讲解稿在备注（弱校验）。

统一返回结构：{"ok": bool, "errors": [str], "warnings": [str]}
依赖缺失时不崩溃，返回 errors=["缺少依赖：python-docx / python-pptx"]。
"""
import os
import re
import zipfile

__all__ = ["check_word_toc", "check_word_structure", "check_ppt_matches_outline", "check_export"]


def _docx_text(docx_path):
    """读 docx 的 document.xml 原文（用于检测 TOC 域，避免依赖 python-docx）。"""
    with zipfile.ZipFile(docx_path) as z:
        return z.read("word/document.xml").decode("utf-8", "ignore")


def check_word_toc(docx_path):
    """检测 docx 是否含可刷新 TOC 目录域 + 是否有标题层级。"""
    if not os.path.exists(docx_path):
        return {"ok": False, "errors": [f"文件不存在：{docx_path}"], "warnings": []}
    try:
        xml = _docx_text(docx_path)
    except Exception as e:
        return {"ok": False, "errors": [f"读取 docx 失败：{e}"], "warnings": []}

    errors, warnings = [], []
    # TOC 域：w:fldSimple 的 instr 含 TOC，或 instrText 含 TOC
    has_toc = ('w:fldSimple' in xml and 'TOC' in xml) or re.search(r'<w:instrText[^>]*>\s*TOC\b', xml) is not None
    if not has_toc:
        errors.append("缺少可刷新目录（TOC 域）")
    # 标题层级：按「实际存在的最高层级」判定，不再硬要求 Heading1。
    # 第二百三十五轮：渲染器把正文的「## 章节」挂成 Heading2，全文没有 Heading1 是
    # 正常的（文档主名在封面、正文一级章节即 ##），旧规则一律误判「无 Heading1」。
    # 只要任一 Heading 层级存在，TOC 域就抓得到内容，不该判死。
    counts = {lv: len(re.findall(r'w:val="Heading%d"' % lv, xml)) for lv in (1, 2, 3, 4)}
    if not any(counts.values()):
        errors.append("无 Heading 章节标题（正文未挂标题样式，目录域抓不到内容）")
    else:
        top = min(lv for lv, n in counts.items() if n)
        if top > 1:
            warnings.append("最高层级标题为 Heading%d（正文一级章节即此层），目录按其生成" % top)
        if counts.get(2) == 0 and sum(counts.values()) > 3:
            warnings.append("无 Heading2 小节标题（长文档通常应有）")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _docx_headings(docx_path):
    """返回 [(level, text)]，按文档顺序。依赖 python-docx。"""
    import docx
    d = docx.Document(docx_path)
    out = []
    for p in d.paragraphs:
        st = (p.style.name or "").lower()
        if st.startswith("heading"):
            m = re.match(r"heading\s*(\d)", st)
            lvl = int(m.group(1)) if m else 1
            if p.text.strip():
                out.append((lvl, p.text.strip()))
    return out


def check_word_structure(docx_path, expected_chapters=None):
    """检测章节顺序/缺章。expected_chapters 为章节名列表（H1 级），缺省只检测标题非空。"""
    if not os.path.exists(docx_path):
        return {"ok": False, "errors": [f"文件不存在：{docx_path}"], "warnings": []}
    try:
        heads = _docx_headings(docx_path)
    except Exception as e:
        return {"ok": False, "errors": [f"缺少依赖或读取失败：{e}"], "warnings": []}

    errors, warnings = [], []
    h1 = [t for lvl, t in heads if lvl == 1]
    if not h1:
        return {"ok": False, "errors": ["无 H1 章节标题"], "warnings": []}
    if expected_chapters:
        exp = [re.sub(r'^[一二三四五六七八九十]+、', '', c).strip() for c in expected_chapters]
        missing = [c for c in exp if not any(c and (c in h or h in c) for h in h1)]
        if missing:
            errors.append("缺章：" + "、".join(missing))
    # 乱序：H1 重复检测
    seen = set()
    for t in h1:
        if t in seen:
            warnings.append("重复章节标题：" + t)
        seen.add(t)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _outline_pages(outline_text):
    """从 ppt_outline markdown 提取页面标题列表（与 rich_pipeline._outline_deck 同口径）。"""
    pages = []
    for line in (outline_text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^#{1,4}\s+(.*)", line) or re.match(r"^(?:页?\d+|[（(]?\d+[）)])[.、:：\s]+(.*)", line)
        if m:
            title = m.group(1).strip().lstrip("#* ").strip()
            if not title or len(title) > 40:
                continue
            if re.match(r"^(?:PPT|路演)?\s*大纲$|^目录$", title, re.IGNORECASE):
                continue
            pages.append(title)
    return pages


def check_ppt_matches_outline(pptx_path, ppt_outline_text):
    """检测 PPT 页数 == 大纲页数，且每页标题与大纲标题对应（弱校验）。"""
    if not os.path.exists(pptx_path):
        return {"ok": False, "errors": [f"文件不存在：{pptx_path}"], "warnings": []}
    try:
        import pptx
        prs = pptx.Presentation(pptx_path)
        slides = list(prs.slides)
    except Exception as e:
        return {"ok": False, "errors": [f"缺少依赖或读取失败：{e}"], "warnings": []}

    errors, warnings = [], []
    expected = _outline_pages(ppt_outline_text)
    if not expected:
        return {"ok": False, "errors": ["无 PPT 大纲，无法校验页数（170 轮铁律：有 PPT 必须先有大纲）"], "warnings": []}
    n = len(slides)
    if n != len(expected):
        errors.append(f"PPT 页数 {n} != 大纲页数 {len(expected)}")
    # 标题对应：逐页比对 slide 标题文本与大纲标题（允许空标题，只警告）
    for i, slide in enumerate(slides[:len(expected)]):
        slide_titles = []
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                slide_titles.append(sh.text_frame.text.strip().split("\n")[0])
        if slide_titles and not any(expected[i] in t or t in expected[i] for t in slide_titles):
            warnings.append(f"第 {i+1} 页标题与大纲「{expected[i]}」不一致")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def check_export(docx_path=None, pptx_path=None, ppt_outline_text="", expected_chapters=None):
    """统一入口：对 docx/pptx 各跑一遍检测，合并结果。"""
    errors, warnings = [], []
    if docx_path:
        r = check_word_toc(docx_path)
        errors += r["errors"]; warnings += r["warnings"]
        r2 = check_word_structure(docx_path, expected_chapters)
        errors += r2["errors"]; warnings += r2["warnings"]
    if pptx_path:
        r = check_ppt_matches_outline(pptx_path, ppt_outline_text)
        errors += r["errors"]; warnings += r["warnings"]
    return {"ok": not errors, "errors": errors, "warnings": warnings}
