# -*- coding: utf-8 -*-
"""可复用的 Markdown -> PDF 渲染器（A4 中文，供作品说明书导出接口使用）"""
import datetime
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
from reportlab.platypus import (SimpleDocTemplate, BaseDocTemplate, PageTemplate,
                                Frame, Paragraph, Spacer, Table, TableStyle,
                                HRFlowable, KeepTogether, PageBreak, Image)
from reportlab.platypus.tableofcontents import TableOfContents


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
_DATE = _S("d", fontSize=12, leading=18, alignment=TA_CENTER,
           textColor=colors.HexColor("#3B4A6B"), spaceBefore=6)
# 封面信息行（按赛事规则显示单位信息，团队名称和负责人始终保留）：居中
_COVER_INFO = _S("ci", fontSize=12, leading=18, alignment=TA_CENTER,
                textColor=colors.HexColor("#3B4A6B"))
# 富表格单元格：必须 wordWrap='CJK'。中文没有词边界，默认 wordWrap 会在任意字符处
# 断行，配上被压窄的列就会变成逐字竖排（实测「水银 / 体温 / 计」断成三行）。
_CELL_H = _S("cell_h", fontSize=9.5, leading=13, wordWrap='CJK',
             textColor=colors.HexColor("#0F1535"))
_CELL = _S("cell", fontSize=9.5, leading=13, wordWrap='CJK',
           textColor=colors.HexColor("#20263B"))
# 图表/表格标题：视觉与 _H2 一致，但样式名不能叫 h2 —— afterFlowable 是按样式名
# 判定目录条目的，用 _H2 会把 8 张图 + 4 张表的 title 全部塞进目录。
_MEDIA_H = _S("media_h", fontSize=13.5, leading=19,
              textColor=colors.HexColor("#1F2A4D"),
              spaceBefore=10, spaceAfter=6)
# 「目录」二字自己也是个标题，用 _H1 会被 afterFlowable 收进目录，出现「目录 … 2」
# 这种自指条目。视觉与 _H1 一致，样式名改掉即可。
_TOC_H = _S("toc_h", fontSize=16, leading=24,
            textColor=colors.HexColor("#0F1535"),
            spaceBefore=14, spaceAfter=8)


_CELL_FS = 9.5        # 单元格字号：量宽与渲染必须用同一个值
_CELL_PAD = 6.0       # 单元格左右 padding 各 3pt，与下方 TableStyle 保持一致


def _rich_col_widths(rows, total=15.5 * cm, min_w=1.3 * cm):
    """按「每列最宽单元格」的视觉宽度分配 15.5cm 总宽。

    不给 Table 显式 colWidths 时，ReportLab 会按内容最小可行宽度压列，中文长文本
    于是被切成一个字一列宽的竖条。这里显式分配：先按各列实测需求给足，装得下就把
    余量均摊让表格撑满版心；装不下则先保底（防止多列表格出现超窄列）再做一轮
    「多退少补」，尽量不让任何一列被压到需求以下。
    """
    col_count = max((len(r) for r in rows), default=0)
    if not col_count:
        return None
    need = [0.0] * col_count
    for row in rows:
        for ci, cell in enumerate(row[:col_count]):
            w = pdfmetrics.stringWidth(_clean(str(cell)), _FONT, _CELL_FS) + _CELL_PAD
            if w > need[ci]:
                need[ci] = w
    need = [max(min_w, n) for n in need]
    if min_w * col_count >= total:
        # 列数太多、连最小宽都放不下：均分，至少不溢出页面
        return [total / col_count] * col_count
    if sum(need) <= total:
        slack = (total - sum(need)) / col_count
        return [n + slack for n in need]
    free = total - min_w * col_count
    over_min = [n - min_w for n in need]
    w = [min_w + (x / sum(over_min)) * free for x in over_min]
    for _ in range(col_count):
        over = [(i, w[i] - need[i]) for i in range(col_count) if w[i] > need[i]]
        under = [i for i in range(col_count) if w[i] < need[i]]
        if not over or not under:
            break
        so = sum(x for _, x in over)
        give = min(so, sum(need[i] - w[i] for i in under))
        su = sum(need[i] - w[i] for i in under)
        for i, x in over:
            w[i] -= give * x / so
        for i in under:
            w[i] += give * (need[i] - w[i]) / su
    return w


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

_RE_HEADING_PREFIX = re.compile(
    r'^(?:第[一二三四五六七八九十百0-9]+[章节篇部讲]\s*'
    r'|[一二三四五六七八九十百]+[、.．]\s*'
    r'|[（(][一二三四五六七八九十百0-9]+[）)]\s*'
    r'|\d{1,2}(?:\.\d{1,2})*(?:[、.．)]|\s+)\s*)'
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

    - 无论上游是否已经编号，都先去掉旧前缀再按层级重排，避免目录和正文出现重复编号。
    - 代码围栏（``` … ```）内的行一律不动
    - `# `（文档主标题，本渲染器用作题头）与 `#### ` 不编号
    """
    lines = (text or '').split('\n')
    out, cn1, cn2, cn3, in_code = [], 0, 0, 0, False
    for line in lines:
        if line.strip().startswith('```'):
            in_code = not in_code
            out.append(line)
            continue
        if not in_code:
            m = re.match(r'^(#{2,4})\s+(.*)$', line)
            if m:
                title = m.group(2).strip()
                if m.group(1) == '##':
                    cn1 += 1
                    cn2 = 0
                    cn3 = 0
                    line = '## %s、%s' % (_cn_num(cn1), _RE_HEADING_PREFIX.sub('', title).strip())
                elif m.group(1) == '###':
                    cn2 += 1
                    cn3 = 0
                    line = '### （%s）%s' % (_cn_num(cn2), _RE_HEADING_PREFIX.sub('', title).strip())
                else:
                    cn3 += 1
                    line = '#### %d、%s' % (cn3, _RE_HEADING_PREFIX.sub('', title).strip())
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


def _chart_path(chart):
    """Resolve a chart URL to the local generated asset without trusting a path."""
    if not isinstance(chart, dict):
        return ''
    name = os.path.basename(str(chart.get('url') or '').split('?', 1)[0])
    if not name:
        return ''
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generated')
    path = os.path.join(base, name)
    return path if os.path.isfile(path) else ''


def _chart_story(charts, tables, page_break=False, heading=None):
    """Build semantic chart/table flow; unmatched media may use an appendix heading."""
    story = []
    charts = charts if isinstance(charts, list) else []
    tables = tables if isinstance(tables, list) else []
    usable_charts = [(c, _chart_path(c)) for c in charts if _chart_path(c)]
    usable_tables = [t for t in tables if isinstance(t, dict) and t.get('header') and t.get('rows')]
    if not usable_charts and not usable_tables:
        return story
    if page_break:
        story.append(PageBreak())
    if heading:
        story.append(Paragraph(_clean(heading), _MEDIA_H))
    for chart, path in usable_charts:
        story.append(Paragraph(_clean(chart.get('title') or '数据图表'), _MEDIA_H))
        try:
            img = Image(path)
            img._restrictSize(15.5 * cm, 8.8 * cm)
            img.hAlign = 'CENTER'
            story.append(img)
        except Exception:
            continue
        caption = str(chart.get('caption') or '').strip()
        source = str(chart.get('source') or '').strip()
        note = '；'.join(x for x in (caption, '来源：' + source if source else '') if x)
        if note:
            story.append(Paragraph(_clean(note), _NOTE))
        story.append(Spacer(1, 8))
    for table in usable_tables:
        story.append(Paragraph(_clean(table.get('title') or '结构化附表'), _MEDIA_H))
        # rows[:9]（表头 + 8 行）是防溢出的有意截断，保持不动
        raw_rows = ([list(table.get('header') or [])]
                    + [list(r) for r in (table.get('rows') or [])])[:9]
        if not raw_rows:
            continue
        col_count = max(len(r) for r in raw_rows)
        rows = [[Paragraph(_clean(str(cell)), _CELL if ri else _CELL_H) for cell in row]
                for ri, row in enumerate(raw_rows)]
        rows = [r + [Paragraph('', _CELL)] * (col_count - len(r)) for r in rows]
        if rows:
            tbl = Table(rows, colWidths=_rich_col_widths(raw_rows),
                        repeatRows=1, hAlign='LEFT')
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8ECF7')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#C9D0E4')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 8))
    return story


# Keep these semantic anchors aligned with docx_charts._ANCHORS so Word and PDF
# place the same charts and tables under the same proposal sections.
_MEDIA_ANCHORS = [
    (('预算', '成本', '经费', '资金', '投入', '收入', '盈利', '收费', '单价', '毛利', '成本结构', '费用'),
     ('商业模式', '市场空间', '经费', '预算', '财务')),
    (('市场', '规模', '增长', '用户量', '渗透', '赛道', '份额', '趋势', '预测', '需求'),
     ('商业模式', '市场空间', '市场', '前景', '背景')),
    (('时间', '里程碑', '进度', '计划', '路线', '阶段', '周期', '排期', '季度', '年度', '节点'),
     ('执行计划', '实施', '里程碑', '计划', '进度')),
    (('技术', '架构', '准确率', '性能', '算法', '识别率', '响应', '延迟', '召回', '精度', '系统', '模块'),
     ('技术方案', '系统架构', '技术', '架构', '产品形态')),
    (('风险', '失败', '威胁', '挑战', '不确定', '隐患', '应对', '概率'),
     ('风险分析', '风险', '应对')),
    (('竞品', '对比', '差异', '友商', '同类', '对手', '对标', '优势'),
     ('竞品对比', '竞品', '差异化', '创新点')),
    (('团队', '分工', '人员', '组织', '职责', '角色'),
     ('团队分工', '团队', '执行计划')),
    (('社会', '价值', '公益', '影响', '可持续', '普惠', '就业', '环保'),
     ('社会价值', '应用前景', '社会', '价值')),
    (('用户', '画像', '场景', '人群', '客户', '受众'),
     ('目标用户', '应用场景', '用户', '场景')),
    (('痛点', '问题', '现状', '缺口', '需求'),
     ('背景与痛点', '痛点', '背景', '项目概述')),
]


def _media_norm(text):
    text = re.sub(r'^[一二三四五六七八九十百]+[、.．]', '', str(text or '').strip())
    text = re.sub(r'^[（(][一二三四五六七八九十百]+[）)]', '', text)
    return re.sub(r'^\d+(?:\.\d+)*[、.．]?\s*', '', text)


def _media_text(item, chart=False):
    parts = [item.get('title', ''), item.get('caption', '')]
    if chart:
        parts.append(item.get('source', ''))
        spec = item.get('spec') or {}
        parts.append(spec.get('type', ''))
        data = spec.get('data') or {}
        if isinstance(data, dict):
            for key in ('xAxis', 'x', 'categories', 'labels', 'names', 'name'):
                value = data.get(key)
                if isinstance(value, list):
                    parts.extend(str(x) for x in value[:12])
                elif value:
                    parts.append(str(value))
            parts.extend(str(s.get('name')) for s in (data.get('series') or [])
                         if isinstance(s, dict) and s.get('name'))
    return ' '.join(str(part) for part in parts)


def _pick_media_section(title, section_titles):
    best_i, best_score = -1, 0
    for index, section_title in enumerate(section_titles):
        for media_words, section_words in _MEDIA_ANCHORS:
            media_hits = sum(1 for word in media_words if word in title)
            section_hits = sum(1 for word in section_words if word in section_title)
            score = media_hits * section_hits
            if score > best_score:
                best_i, best_score = index, score
    return best_i


def _split_markdown_sections(body_text):
    prefix, sections, current = [], [], None
    for line in body_text.split('\n'):
        match = re.match(r'^##\s+(.*)$', line)
        if match:
            current = {'title': _media_norm(match.group(1)), 'lines': [line]}
            sections.append(current)
        elif current is None:
            prefix.append(line)
        else:
            current['lines'].append(line)
    return prefix, sections


def _body_with_media_story(body_text, charts, tables):
    prefix, sections = _split_markdown_sections(body_text)
    if not sections:
        return _flow(body_text) + _chart_story(charts, tables, page_break=True,
                                               heading='数据图表与结构化附表')

    chart_items = [(chart, _chart_path(chart)) for chart in (charts or [])
                   if isinstance(chart, dict) and _chart_path(chart)]
    table_items = [table for table in (tables or [])
                   if isinstance(table, dict) and table.get('header') and table.get('rows')]
    titles = [section['title'] for section in sections]
    section_charts = [[] for _ in sections]
    section_tables = [[] for _ in sections]
    fallback_charts, fallback_tables = [], []
    chart_counts, table_counts = {}, {}

    for chart, path in chart_items:
        target = _pick_media_section(_media_text(chart, chart=True), titles)
        if target >= 0 and chart_counts.get(target, 0) < 2:
            section_charts[target].append(chart)
            chart_counts[target] = chart_counts.get(target, 0) + 1
        else:
            fallback_charts.append(chart)
    for table in table_items:
        target = _pick_media_section(_media_text(table), titles)
        if target >= 0 and table_counts.get(target, 0) < 1:
            section_tables[target].append(table)
            table_counts[target] = table_counts.get(target, 0) + 1
        else:
            fallback_tables.append(table)

    story = _flow('\n'.join(prefix)) if any(x.strip() for x in prefix) else []
    for index, section in enumerate(sections):
        story.extend(_flow('\n'.join(section['lines'])))
        story.extend(_chart_story(section_charts[index], section_tables[index]))
    story.extend(_chart_story(fallback_charts, fallback_tables, page_break=True,
                              heading='补充图表与结构化附表'))
    return story


class _PdfDocTemplate(BaseDocTemplate):
    """Small TOC-aware template; page numbers come from ReportLab, not estimates."""
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin,
                      self.width, self.height, id='normal')
        self.addPageTemplates([PageTemplate(id='main', frames=[frame],
                                            onPage=_footer)])

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style = getattr(flowable, 'style', None)
        name = getattr(style, 'name', '') if style else ''
        level = 0 if name == 'h1' else (1 if name == 'h2' else -1)
        if level >= 0:
            self.notify('TOCEntry', (level, flowable.getPlainText(), self.page))


def _footer(canvas, docobj):
    canvas.saveState()
    canvas.setFont(_FONT, 8.5)
    canvas.setFillColor(colors.HexColor('#8A93A8'))
    canvas.drawCentredString(A4[0] / 2.0, 0.85 * cm, '%d' % docobj.page)
    canvas.restoreState()


def render_markdown_to_pdf(markdown_text, out_path, title="申报书", subtitle=None,
                          charts=None, tables=None, include_toc=True,
                          project=None, date_str=None,
                          school=None, team=None, advisor=None,
                          show_school_advisor=True, team_name=None,
                          leader=None, members=None, contact=None):
    """把 Markdown 文本渲染成带封面/目录/媒体的 A4 PDF。

    project  : 项目名，由调用方传入（双盲赛事正文里未必有项目名，这里不做猜测），
               有值时作封面主标题，title 退为副标题位。
    date_str : 封面日期，缺省取当前年月（%Y 年 %m 月）。
    """
    markdown_text = markdown_text or ""
    # 若正文没有以一级标题（# 标题）开头，补一个文档主标题，避免 PDF 上来就是「## 项目简介」没有题头
    stripped = markdown_text.lstrip()
    if not re.match(r"^#\s+", stripped):
        markdown_text = ("# %s\n\n" % (title or "申报书")) + markdown_text
    # 章节编号注入：#（题头）不动，## → 一、二、…，### → （一）（二）…
    markdown_text = _number_headings(markdown_text)

    # 封面标题不再在目录后的正文重复出现；正文其余层级完整保留。
    body_lines = markdown_text.splitlines()
    if body_lines and re.match(r'^#\s+', body_lines[0].strip()):
        body_lines = body_lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
    body_text = '\n'.join(body_lines)
    has_headings = any(re.match(r'^##\s+', x.strip()) for x in body_lines)
    toc = TableOfContents()
    # rightIndent 给右侧页码留位；dotsMinLevel=0 让一级条目也带点引线
    toc.dotsMinLevel = 0
    toc.levelStyles = [
        ParagraphStyle('toc1', fontName=_FONT, fontSize=11, leading=18,
                       leftIndent=0, rightIndent=1.2 * cm,
                       firstLineIndent=0, spaceAfter=3),
        ParagraphStyle('toc2', fontName=_FONT, fontSize=10, leading=16,
                       leftIndent=18, rightIndent=1.2 * cm,
                       firstLineIndent=0, spaceAfter=2),
    ]
    # 封面：主标题优先用项目名，赛事名（subtitle）保留作副标题
    cover_sub = subtitle or (title if project else None)
    # 学校/指导老师双盲赛事要隐藏，只保留团队；非双盲全部展示
    if show_school_advisor:
        info_lines = [("学校", school)] if school else []
    else:
        info_lines = []
    from cover_fields import cover_team_lines
    info_lines.extend(cover_team_lines(team=team, team_name=team_name,
                                       leader=leader, members=members,
                                       contact=contact))
    if show_school_advisor and advisor:
        info_lines.append(("指导教师", advisor))
    story = [Spacer(1, 5.0 * cm),
             Paragraph(_clean(project or title or '申报书'), _TITLE)]
    if cover_sub:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(_clean(cover_sub), _SUB))
    for label, line in info_lines:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(_clean("%s：%s" % (label, line)), _COVER_INFO))
    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph('协作草稿 · 提交前请核对数据来源、署名与赛事要求', _NOTE))
    story.append(Paragraph(
        date_str or datetime.date.today().strftime('%Y 年 %m 月'), _DATE))
    story.append(PageBreak())
    if include_toc and has_headings:
        story.extend([Paragraph('目录', _TOC_H), toc, PageBreak()])
    story.extend(_body_with_media_story(body_text, charts, tables))
    doc = _PdfDocTemplate(
        out_path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title=title,
    )
    doc.multiBuild(story)
    return out_path
