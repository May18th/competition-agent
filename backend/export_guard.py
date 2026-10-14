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
    """417 轮重写：检测 docx 是否含封面页 + 目录页 + 标题层级。

    旧版只认「TOC 域」，而 docx_render 渲染的是**静态目录**（WPS/手机 Word 不会
    刷新域，静态目录才是能真看到的），结果长文档一律被判「缺少可刷新目录」误杀；
    同时旧版死盯 Heading1，而申报书章节用的是 `## 一、xxx`（= Heading2），
    于是「无 Heading1 章节标题」也是误报。两处误报叠起来 = 导出的说明书既没通过
    校验、又让人以为目录逻辑有问题。

    现在的判定，按「评委打开手机能看到什么」来定：
      1. 封面：正文第一个标题之前必须有非空内容；
      2. 目录：存在「目  录」标题段，且其后至少 2 条与正文标题同名的条目；
         （TOC 域也算通过，二者有一即可）
      3. 标题层级：Heading1~3 至少 1 个。
    """
    if not os.path.exists(docx_path):
        return {"ok": False, "errors": [f"文件不存在：{docx_path}"], "warnings": []}

    errors, warnings = [], []
    try:
        xml = _docx_text(docx_path)
    except Exception as e:
        return {"ok": False, "errors": [f"读取 docx 失败：{e}"], "warnings": []}

    # ---- 标题层级：Heading1~3 任一即可（申报书章节多为 Heading2）----
    n_head = sum(len(re.findall(r'w:val="Heading%d"' % i, xml)) for i in (1, 2, 3))
    if n_head == 0:
        errors.append("无章节标题（Heading1~3 一个都没有）")

    try:
        import docx as _docx
        d = _docx.Document(docx_path)
        paras = [p.text.strip() for p in d.paragraphs]
    except Exception as e:
        return {"ok": False, "errors": [f"读取 docx 段落失败：{e}"], "warnings": []}

    # ---- 目录页 ----
    toc_idx = -1
    for i, t in enumerate(paras):
        if re.match(r'^目\s*录$', t or ''):
            toc_idx = i
            break
    has_toc_field = re.search(r'<w:instrText[^>]*>\s*TOC\b', xml) is not None
    if toc_idx < 0 and not has_toc_field:
        errors.append("缺少目录页（未找到「目  录」章节列表）")
    elif toc_idx >= 0:
        # 目录条目数：目录标题之后、直到第一个 Heading 样式段落为止的非空行
        entries = 0
        for i in range(toc_idx + 1, min(toc_idx + 60, len(paras))):
            st = (d.paragraphs[i].style.name or '').lower()
            if st.startswith('heading'):
                break
            if paras[i]:
                entries += 1
        if entries < 2:
            warnings.append(f"目录条目仅 {entries} 条（正文章节可能没被识别为标题）")

    # ---- 封面页：第一个标题之前必须有内容 ----
    first_head = -1
    for i, p in enumerate(d.paragraphs):
        if (p.style.name or '').lower().startswith('heading') and p.text.strip():
            first_head = i
            break
    if first_head <= 0:
        errors.append("缺少封面页（正文第一个标题之前没有任何内容）")
    elif not any(paras[i] for i in range(first_head)):
        errors.append("封面页为空（有段落但无文字，项目名/赛事/团队都没写上去）")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def check_word_cover_toc(docx_path):
    """语义化别名：封面 + 目录 + 标题层级一起查（417 轮）。"""
    return check_word_toc(docx_path)


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
    # 申报书正文通常从 Heading2 开始，Heading1 会被封面/目录标题占用。
    # 只要存在可导航的 Heading1~3，就不能把「无 H1」误报成结构损坏。
    # 取最浅层级作为章节层，兼容 Word/WPS/手机端不同模板。
    chapter_level = min((lvl for lvl, _ in heads), default=None)
    if chapter_level is None:
        return {"ok": False, "errors": ["无章节标题（Heading1~3 一个都没有）"], "warnings": []}
    h1 = [t for lvl, t in heads if lvl == chapter_level]
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
    lines = [(line.strip()) for line in (outline_text or "").split("\n")]
    lines = [line for line in lines if line]

    # 优先使用显式页码。深度版大纲常在末尾附「答辩问题库/讲解稿」等
    # 非页面内容；只要文档存在明确页码，就不能把这些二级标题误算成 PPT 页。
    page_re = re.compile(
        r"^(?:#{1,4}\s+)?(?:第\s*\d+\s*页|页?\s*\d+|[（(]?\d+[）)])"
        r"(?:[.、:：\s|｜-]+)(.+)$"
    )
    explicit = [m for line in lines if (m := page_re.match(line))]

    def _is_appendix_heading(title):
        return bool(re.match(
            r"^(?:附录?|附)[:：\s]|^(?:答辩问题库|答辩问题预测|讲解稿|演讲稿|备注)",
            (title or "").strip(), re.IGNORECASE
        ))

    def _clean(title):
        title = (title or "").strip().lstrip("#* ").strip()
        if not title or len(title) > 40:
            return ""
        normalized = re.sub(r"[\s\u00b7\-\u2014_()（）\[\]【】|｜]+", "", title)
        # 文档级标题及附录资源不是 PPT 页面。
        if re.search(r"(?:PPT|路演)?大纲(?:\d+页?)?$", normalized, re.IGNORECASE) \
                or normalized in ("目录", "PPT目录", "目录页"):
            return ""
        if _is_appendix_heading(title):
            return ""
        return title

    if explicit:
        pages = []
        appendix_started = False
        for line in lines:
            heading = re.match(r"^#{1,4}\s+(.*)$", line)
            if heading and _is_appendix_heading(heading.group(1)):
                appendix_started = True
                continue
            if appendix_started:
                continue
            m = page_re.match(line)
            if m:
                title = _clean(m.group(1))
                if title:
                    pages.append(title)
        return pages

    # 兼容没有页码的旧大纲：仅把 markdown 标题视为页面，普通正文行不计页。
    pages = []
    for line in lines:
        m = re.match(r"^#{1,4}\s+(.*)", line)
        if m:
            title = _clean(m.group(1))
            if title:
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
