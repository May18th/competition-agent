# -*- coding: utf-8 -*-
"""可复用的 Markdown -> PDF 渲染器（A4 中文，供作品说明书导出接口使用）"""
import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)


def _register_cjk():
    candidates = [
        ("C:/Windows/Fonts/msyh.ttc", "MSYH"),
        ("C:/Windows/Fonts/simhei.ttf", "SIMHEI"),
        ("C:/Windows/Fonts/simsun.ttc", "SIMSUN"),
        ("/System/Library/Fonts/PingFang.ttc", "PINGFANG"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NOTOCJK"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf", "NOTOCJK"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "NOTOCJK"),
        ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "NOTOCJK"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WQY"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WQY"),
    ]
    for path, name in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            # 粗体：优先微软雅黑粗体，退回黑体（simhei 本身就是黑体，作粗体兜底可用）
            bold_name = None
            for bpath, bname in (
                ("C:/Windows/Fonts/msyhbd.ttc", name + "B"),
                ("C:/Windows/Fonts/simhei.ttf", name + "B"),
            ):
                try:
                    if os.path.exists(bpath) and bname != name:
                        pdfmetrics.registerFont(TTFont(bname, bpath))
                        bold_name = bname
                        break
                except Exception:
                    continue
            if bold_name:
                try:
                    pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name,
                                                  italic=name, boldItalic=bold_name)
                except Exception:
                    pass
            return name
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


_FONT = _register_cjk()
_styles = {}


def _S(name, **kw):
    if name not in _styles:
        _styles[name] = ParagraphStyle(name, fontName=_FONT, **kw)
    return _styles[name]


_TITLE = _S("t", fontSize=22, leading=30, alignment=TA_CENTER,
            textColor=colors.HexColor("#0F1535"), spaceAfter=6)
_SUB = _S("s", fontSize=14, leading=20, alignment=TA_CENTER,
          textColor=colors.HexColor("#3B4A6B"), spaceAfter=16)
_H1 = _S("h1", fontSize=16, leading=24, textColor=colors.HexColor("#0F1535"),
         spaceBefore=14, spaceAfter=8)
_H2 = _S("h2", fontSize=13.5, leading=19, textColor=colors.HexColor("#1F2A4D"),
         spaceBefore=10, spaceAfter=6)
_BODY = _S("b", fontSize=12, leading=20, firstLineIndent=24, spaceAfter=6)
_BULLET = _S("bl", fontSize=12, leading=20, leftIndent=20, bulletIndent=6,
             spaceAfter=3)
_NOTE = _S("n", fontSize=10.5, leading=16, textColor=colors.HexColor("#5A657F"),
           spaceBefore=10, spaceAfter=4)


_HTML_ESCAPE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
}


def _escape_html(t):
    return "".join(_HTML_ESCAPE.get(ch, ch) for ch in (t or ""))


def _clean(t):
    # 先把用户/模型文本里的 HTML 特殊字符转义，防止被 reportlab 当标签吞掉内容；
    # 再仅针对 Markdown **加粗** 还原成 <b> 标签。
    escaped = _escape_html(t)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    # 行内反引号 `xxx`：去掉反引号保留内容（不原样输出反引号）
    out = re.sub(r"`([^`]+)`", r"\1", out)
    return out.strip()


def _is_body_line(s):
    """判断一行是否是可当作「标题的下一段」的普通正文段落。"""
    s = (s or '').strip()
    if not s:
        return False
    if re.match(r'^#{1,6}\s', s):      # 标题
        return False
    if s.startswith('> ') or s == '---':  # 引用 / 分隔线
        return False
    if s.startswith('|'):               # 表格
        return False
    if re.match(r'^[-*]\s', s):         # 无序列表
        return False
    if re.match(r'^\d+\.\s', s):        # 有序列表
        return False
    return True


def _next_nonempty(lines, start):
    for j in range(start, len(lines)):
        if lines[j].strip():
            return j
    return None


# ============ 章节编号注入（导出件是正式材料，章节必须带编号） ============
# 与 docx_render._number_heading_blocks 保持同一套规则（两链路各自实现，规则必须一致）：
#   ##  → 一、二、三、…（一级章节，中文数字）
#   ### → （一）（二）…（二级小节，每章重新起算）
#   已带编号的标题原样保留不重复加；#（文档主标题）与 #### 及以下不编号。

_RE_NUM_HEAD = re.compile(
    r'^(?:'
    r'第[一二三四五六七八九十百0-9]+[章节篇部讲]'      # 第一章 / 第2章
    r'|[一二三四五六七八九十百]+[、.．]'               # 一、 二.
    r'|[（(][一二三四五六七八九十百]+[）)]'             # （一） (二)
    r'|\d{1,2}(?:\.\d{1,2}){0,3}[、.．]'              # 1. / 2、 / 1.2.
    r'|\d{1,2}(?:\.\d{1,2})+\s'                      # 1.1 / 10.2.1（多级+空格）
    r'|[①②③④⑤⑥⑦⑧⑨⑩]'
    r')'
)


def _cn_num(n):
    """阿拉伯数字 → 中文数字（一、二、… 十一、… 二十一、…）。"""
    digits = '零一二三四五六七八九'
    if n <= 0:
        return ''
    if n >= 100:
        return str(n)
    if n < 10:
        return digits[n]
    if n == 10:
        return '十'
    if n < 20:
        return '十' + digits[n - 10]
    tens, ones = divmod(n, 10)
    return digits[tens] + '十' + (digits[ones] if ones else '')


def _number_headings(text):
    """给 markdown 的 ## / ### 标题行注入中文编号；返回处理后的全文。

    - 已带编号的标题（一、 / 1. / 1.1 / （一） / 第X章…）原样保留、不重复加号，
      但照样推进计数器，保证后面的裸标题拿到与位置对应的号
    - 代码围栏（``` … ```）内的行一律不动
    - `# `（文档主标题，本渲染器用作题头）与 `#### ` 不编号
    """
    lines = (text or '').split('\n')
    out, cn1, cn2, in_code = [], 0, 0, False
    # 2026-10-01 P2 修复（与 docx_render._number_heading_blocks 同步）：
    # 孤立裸标题夹在已编号章节序列中间时，按位置注入的号会与原文自带编号撞车
    # （出现两个「五、」）。注入前只查【后文】的 H2 是否已占该号——查全量会把
    # 编号漂移后的前文标题也算进来误伤（实测「后裸标题」被误判撞五、）。
    _h2_titles = []
    for _l in lines:
        _m = re.match(r'^(#{2,3})\s+(.*)$', _l)
        if _m and _m.group(1) == '##':
            _h2_titles.append(_m.group(2).strip())
    _h2_seen = -1
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            out.append(line)
            continue
        if not in_code:
            m = re.match(r'^(#{2,3})\s+(.*)$', line)
            if m:
                title = m.group(2).strip()
                if m.group(1) == '##':
                    _h2_seen += 1
                    cn1 += 1
                    cn2 = 0
                    if title and not _RE_NUM_HEAD.match(title):
                        _pref = _cn_num(cn1) + '、'
                        # 后文已有该编号（原文自带）→ 裸标题保持不编号，防撞车
                        if not any(t.startswith(_pref) for t in _h2_titles[_h2_seen + 1:]):
                            line = '## %s、%s' % (_cn_num(cn1), title)
                else:
                    cn2 += 1
                    if title and not _RE_NUM_HEAD.match(title):
                        line = '### （%s）%s' % (_cn_num(cn2), title)
        out.append(line)
    return '\n'.join(out)


def _flow(text):
    flow, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            h = Paragraph(_clean(line[4:]), _H2)
            nxt = _next_nonempty(lines, i + 1)
            if nxt is not None and _is_body_line(lines[nxt]):
                flow.append(KeepTogether([h, Paragraph(_clean(lines[nxt].rstrip()), _BODY)]))
                i = nxt
            else:
                flow.append(h)
        elif line.startswith("## "):
            h = Paragraph(_clean(line[3:]), _H1)
            nxt = _next_nonempty(lines, i + 1)
            if nxt is not None and _is_body_line(lines[nxt]):
                flow.append(KeepTogether([h, Paragraph(_clean(lines[nxt].rstrip()), _BODY)]))
                i = nxt
            else:
                flow.append(h)
        elif line.startswith("# "):
            flow.append(Paragraph(_clean(line[2:]), _TITLE))
        elif line.startswith("> "):
            flow.append(Paragraph(_clean(line[2:]), _NOTE))
        elif line.strip() == "---":
            flow.append(HRFlowable(width="100%", thickness=0.7,
                                   color=colors.HexColor("#C9D0E4"),
                                   spaceBefore=6, spaceAfter=8))
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append([_clean(c) for c in cells])
                i += 1
            i -= 1
            if rows:
                t = Table(rows, hAlign="LEFT", repeatRows=1)
                t.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), _FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("LEADING", (0, 0), (-1, -1), 12),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#20263B")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8ECF7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F1535")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9D0E4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                flow.append(t)
                flow.append(Spacer(1, 5))
        elif re.match(r"^\d+\.\s", line):
            flow.append(Paragraph(_clean(re.sub(r"^\d+\.\s*", "", line)), _BULLET,
                                  bulletText="•"))
        elif line.startswith("- "):
            flow.append(Paragraph(_clean(line[2:]), _BULLET, bulletText="•"))
        else:
            flow.append(Paragraph(_clean(line), _BODY))
        i += 1
    return flow


def render_markdown_to_pdf(markdown_text, out_path, title="申报书"):
    """把 Markdown 文本渲染成 A4 PDF。成功返回 out_path，失败抛异常。"""
    markdown_text = markdown_text or ""
    # 若正文没有以一级标题（# 标题）开头，补一个文档主标题，避免 PDF 上来就是「## 项目简介」没有题头
    stripped = markdown_text.lstrip()
    if not re.match(r"^#\s+", stripped):
        markdown_text = ("# %s\n\n" % (title or "申报书")) + markdown_text
    # 章节编号注入：#（题头）不动，## → 一、二、…，### → （一）（二）…
    markdown_text = _number_headings(markdown_text)

    def _footer(canvas, docobj):
        canvas.saveState()
        canvas.setFont(_FONT, 8.5)
        canvas.setFillColor(colors.HexColor("#8A93A8"))
        canvas.drawCentredString(A4[0] / 2.0, 0.85 * cm, "%d" % docobj.page)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title=title,
    )
    doc.build(_flow(markdown_text), onFirstPage=_footer, onLaterPages=_footer)
    return out_path
