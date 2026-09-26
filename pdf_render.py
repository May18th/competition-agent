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
                                TableStyle, HRFlowable)


def _register_cjk():
    candidates = [
        ("C:/Windows/Fonts/msyh.ttc", "MSYH"),
        ("C:/Windows/Fonts/simhei.ttf", "SIMHEI"),
        ("C:/Windows/Fonts/simsun.ttc", "SIMSUN"),
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


_TITLE = _S("t", fontSize=19, leading=26, alignment=TA_CENTER,
            textColor=colors.HexColor("#0F1535"), spaceAfter=4)
_SUB = _S("s", fontSize=13, leading=19, alignment=TA_CENTER,
          textColor=colors.HexColor("#3B4A6B"), spaceAfter=14)
_H1 = _S("h1", fontSize=14, leading=20, textColor=colors.HexColor("#0F1535"),
         spaceBefore=12, spaceAfter=6)
_H2 = _S("h2", fontSize=11.5, leading=16, textColor=colors.HexColor("#1F2A4D"),
         spaceBefore=8, spaceAfter=4)
_BODY = _S("b", fontSize=10.5, leading=17, firstLineIndent=21, spaceAfter=5)
_BULLET = _S("bl", fontSize=10.5, leading=17, leftIndent=18, bulletIndent=6,
             spaceAfter=3)
_NOTE = _S("n", fontSize=9, leading=14, textColor=colors.HexColor("#5A657F"),
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
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped).strip()


def _flow(text):
    flow, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            flow.append(Paragraph(_clean(line[4:]), _H2))
        elif line.startswith("## "):
            flow.append(Paragraph(_clean(line[3:]), _H1))
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
                t = Table(rows, hAlign="LEFT")
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


def render_markdown_to_pdf(markdown_text, out_path, title="作品说明书"):
    """把 Markdown 文本渲染成 A4 PDF。成功返回 out_path，失败抛异常。"""
    def _watermark(canvas, doc):
        """每页居中加浅灰斜向水印「可创无限团队」。"""
        canvas.saveState()
        canvas.setFont(_FONT, 44)
        try:
            canvas.setFillAlpha(0.18)
        except Exception:
            pass
        canvas.setFillColor(colors.HexColor("#B9C0D4"))
        canvas.translate(doc.pagesize[0] / 2, doc.pagesize[1] / 2)
        canvas.rotate(42)
        canvas.drawCentredString(0, 0, "可创无限团队")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title=title,
    )
    doc.build(_flow(markdown_text or ""), onFirstPage=_watermark, onLaterPages=_watermark)
    return out_path
