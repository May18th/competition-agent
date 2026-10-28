# -*- coding: utf-8 -*-
"""
docx_render.py —— 把 Markdown 渲染成符合《全国大学生竞赛申报书统一字体格式标准》的 Word 文档。

执行的标准（用户 2026-09-25 提供，优先级最高）：
  页面   A4；上下 2.54cm、左右 3.17cm；全文 1.5 倍行距
  封面   主标题黑体小初加粗居中 / 副标题黑体二号居中 / 日期等黑体小三居中；无页码
  一级   黑体二号加粗左对齐无缩进      （一、二、三、）
  二级   黑体小三加粗左对齐            （（一）（二））
  三级   黑体四号加粗左对齐            （1. 2. 3.）
  四级   宋体小四加粗                  （（1）（2））
  正文   宋体小四，1.5 倍行距，首行缩进 2 字符，段前段后 0
  西文   数字/英文统一 Times New Roman
  图表   表题/图题宋体五号加粗居中；注释宋体五号；表内文字宋体小四
  红线   无底色、无阴影、无特效；不自动编号；图片不拉伸；禁通篇加粗；中文全角标点

早期版本走过的弯路（保留在此以警醒）：
  曾按「好看」优先做成微软雅黑 + 蓝底表头 + 斑马纹 + 引用灰底 + 封面背景图，
  全部违反上面的红线。现在默认走合规路线，花哨效果一律默认关闭。

对外主入口：
    from docx_render import build_docx
    doc = build_docx('项目申报书', md_text, subtitle='iCAN大学生创新创业大赛')
    doc.save('申报书.docx')
"""
import datetime
import os
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ---- 字体：只允许宋体 / 黑体，西文统一 Times New Roman ----
CN_SONG = '宋体'
CN_HEI = '黑体'
EN = 'Times New Roman'

# ---- 中文字号 → 磅 ----
SZ_XIAOCHU = 36      # 小初
SZ_ER = 22           # 二号
SZ_XIAOSAN = 15      # 小三
SZ_SI = 14           # 四号
SZ_XIAOSI = 12       # 小四
SZ_WU = 10.5         # 五号

BLACK = RGBColor(0, 0, 0)

# ---- 文档类型样式档位（用户 2026-09-25 补充）----
# outline  大纲：最轻最简。一级黑体四号加粗 / 二级宋体小四加粗 / 三级宋体小四常规，
#                不要首行缩进、靠左对齐，不要封面和目录
# analysis 分析：标准一二三级 + 正文小四宋体 1.5 倍 + 首行缩进
# report   报告：最正式，标准一二三级 + 正文小四宋体
# default  申报书：同标准层级
_STD_HEADINGS = {
    1: (SZ_ER, CN_HEI, True),        # 黑体二号加粗
    2: (SZ_XIAOSAN, CN_HEI, True),   # 黑体小三加粗
    3: (SZ_SI, CN_HEI, True),        # 黑体四号加粗
    4: (SZ_XIAOSI, CN_SONG, True),   # 宋体小四加粗
}
PROFILES = {
    'outline': {
        'headings': {
            1: (SZ_SI, CN_HEI, True),          # 黑体四号加粗
            2: (SZ_XIAOSI, CN_SONG, True),     # 宋体小四加粗
            3: (SZ_XIAOSI, CN_SONG, False),    # 宋体小四常规
            4: (SZ_XIAOSI, CN_SONG, False),
        },
        'body_indent': False,                   # 不首行缩进，靠左对齐
        'body_align': WD_ALIGN_PARAGRAPH.LEFT,
        'cover': False, 'toc': False,
    },
    'analysis': {'headings': _STD_HEADINGS, 'body_indent': True,
                 'body_align': WD_ALIGN_PARAGRAPH.JUSTIFY,
                 'cover': True, 'toc': False},
    'report': {'headings': _STD_HEADINGS, 'body_indent': True,
               'body_align': WD_ALIGN_PARAGRAPH.JUSTIFY,
               'cover': True, 'toc': True},
    'default': {'headings': _STD_HEADINGS, 'body_indent': True,
                'body_align': WD_ALIGN_PARAGRAPH.JUSTIFY,
                'cover': True, 'toc': True},
}


# ============ 底层工具 ============

def _font(run, size, cn=CN_SONG, bold=False, color=None):
    """设置字体：西文 Times New Roman + 中文宋体/黑体。
    规范：数字、英文统一 Times New Roman；中文只允许宋体/黑体。"""
    run.font.name = EN                 # w:ascii / w:hAnsi
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:ascii'), EN)
    rFonts.set(qn('w:hAnsi'), EN)
    rFonts.set(qn('w:eastAsia'), cn)
    return run


def _indent_chars(p, chars=200):
    """首行缩进 N 个字符（按字符单位，任何字号都是精确 2 字符）。"""
    pPr = p._p.get_or_add_pPr()
    ind = pPr.find(qn('w:ind'))
    if ind is None:
        ind = OxmlElement('w:ind')
        pPr.append(ind)
    ind.set(qn('w:firstLineChars'), str(chars))


def _hanging_indent(p, chars=200):
    """悬挂缩进：首行顶格，换行后缩进 N 字符（列表项用）。"""
    pPr = p._p.get_or_add_pPr()
    ind = pPr.find(qn('w:ind'))
    if ind is None:
        ind = OxmlElement('w:ind')
        pPr.append(ind)
    ind.set(qn('w:firstLineChars'), '-%d' % chars)
    ind.set(qn('w:leftChars'), str(chars))


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader')
    el.set(qn('w:val'), 'true')
    trPr.append(el)


def _set_cell_margins(table, top=40, bottom=40, left=80, right=80):
    tblPr = table._tbl.tblPr
    mar = OxmlElement('w:tblCellMar')
    for tag, val in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
        node = OxmlElement('w:' + tag)
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        mar.append(node)
    tblPr.append(mar)


# ============ 全角标点 ============

def _is_cn(ch):
    return '\u4e00' <= ch <= '\u9fff'


_PUNCT_MAP = {',': '，', ';': '；', ':': '：', '!': '！', '?': '？'}


def _fullwidth(text):
    """把中文语境里的半角标点转成全角（英文句子、小数、URL 不动）。"""
    if not text:
        return text
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        prev = text[i - 1] if i > 0 else ''
        nxt = text[i + 1] if i + 1 < n else ''
        cn_near = _is_cn(prev) or _is_cn(nxt)
        if ch in _PUNCT_MAP and cn_near:
            out.append(_PUNCT_MAP[ch])
        elif ch == '.' and _is_cn(prev) and not nxt.isdigit():
            out.append('。')
        elif ch == '.' and _is_cn(nxt):
            out.append('。')
        elif ch == '(' and _is_cn(nxt):
            out.append('（')
        elif ch == ')' and _is_cn(prev):
            out.append('）')
        else:
            out.append(ch)
    return ''.join(out)


# ============ Markdown 块解析 ============

_RE_CODE = re.compile(r'^```')
_RE_HR = re.compile(r'^(-{3,}|\*{3,}|_{3,})$')
_RE_HEAD = re.compile(r'^(#{1,6})\s+(.*)$')
_RE_OL = re.compile(r'^(\d+)[.、)]\s+(.*)$')
_RE_UL = re.compile(r'^[-*•·＋]\s+(.*)$')
_RE_SEP = re.compile(r'^\|[\s:\-|]+\|$')
_RE_CAPTION = re.compile(r'^[表图]\s*[\d\-—.]')
# 裸标题（LLM 偶尔不输出 # 号，章节标题是纯文本行）：
# 一级「一、xxx / 第X章」、二级「（一）xxx」、多级「1.1 xxx / 10.2.1 xxx」
_RE_HEAD_CN1 = re.compile(r'^(?:第[一二三四五六七八九十百\d]+[章节篇部]|[一二三四五六七八九十]+、)\s*\S')
_RE_HEAD_CN2 = re.compile(r'^（[一二三四五六七八九十]+）\s*\S')
_RE_HEAD_NUM = re.compile(r'^(\d+(?:\.\d+)+)[、.\s]\s*\S')


def _plain_head_level(line):
    """识别没带 # 的「裸标题」行，返回层级（0 = 不是标题）。

    fast 模式的 LLM 有时整篇申报书章节都是「一、项目背景」这种纯文本行，
    不识别的话导出 Word 的目录只剩「## 待替换数据清单」一条。
    防误伤：超过 40 字、以句读结尾、或行内含句号的，按正文处理。
    """
    s = line.strip()
    if not s or len(s) > 40:
        return 0
    if s.endswith(('。', '，', '；', '：', ',', ';', ':', '.')) or '。' in s:
        return 0
    if _RE_HEAD_CN1.match(s):
        return 1
    if _RE_HEAD_CN2.match(s):
        return 2
    m = _RE_HEAD_NUM.match(s)
    if m:
        return min(m.group(1).count('.') + 1, 4)
    return 0


def _is_sep(line):
    return bool(_RE_SEP.match(line)) and '-' in line


def _split_row(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _is_block_start(line):
    if not line:
        return True
    return bool(_RE_CODE.match(line) or _RE_HR.match(line) or _RE_HEAD.match(line)
                or _RE_OL.match(line) or _RE_UL.match(line)
                or _plain_head_level(line)
                or line.startswith(('>', '|')))


def _blocks(text):
    """切块：('h',level,text) / ('p',[lines]) / ('ul',[items]) / ('ol',[items])
       / ('quote',[lines]) / ('code',[lines],lang) / ('table',header,rows) / ('hr',)"""
    lines = text.replace('\r\n', '\n').split('\n')
    out, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if _RE_CODE.match(s):
            i += 1
            buf = []
            while i < n and not _RE_CODE.match(lines[i].strip()):
                buf.append(lines[i].rstrip())
                i += 1
            i += 1
            out.append(('code', buf))
            continue
        if _RE_HR.match(s):
            out.append(('hr',))
            i += 1
            continue
        m = _RE_HEAD.match(s)
        if m:
            out.append(('h', min(len(m.group(1)), 4), m.group(2).strip()))
            i += 1
            continue
        # 裸标题：LLM 偶尔不输出 # 号，直接是「一、项目背景」「（一）xxx」纯文本行
        hl = _plain_head_level(s)
        if hl:
            out.append(('h', hl, s))
            i += 1
            continue
        if s.startswith('|') and i + 1 < n and _is_sep(lines[i + 1].strip()):
            header = _split_row(s)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append(_split_row(lines[i].strip()))
                i += 1
            out.append(('table', header, rows))
            continue
        if s.startswith('>'):
            buf = []
            while i < n and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append(('quote', buf))
            continue
        if _RE_OL.match(s):
            buf = []
            while i < n:
                mm = _RE_OL.match(lines[i].strip())
                if not mm:
                    break
                buf.append(mm.group(2).strip())
                i += 1
            out.append(('ol', buf))
            continue
        if _RE_UL.match(s):
            buf = []
            while i < n:
                mm = _RE_UL.match(lines[i].strip())
                if not mm:
                    break
                buf.append(mm.group(1).strip())       # _RE_UL 只有 1 个捕获组
                i += 1
            out.append(('ul', buf))
            continue
        buf = []
        while i < n:
            t = lines[i].strip()
            if not t or _is_block_start(t):
                break
            buf.append(t)
            i += 1
        if buf:
            out.append(('p', buf))
    return out


def _plain(text):
    """去掉行内标记（表格单元格用）。"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()


# ============ 页面 ============

def _setup_heading_styles(doc, prof):
    """把 Word 的 Heading 1~4 样式改成符合规范的字体字号。

    关键：目录（TOC 域）只认「标题样式」的段落，认不出普通段落加粗。
    所以标题必须挂上 Heading 样式，再改样式本身的外观，
    这样目录才能自动对应到正文并生成正确页码。
    """
    for level in (1, 2, 3, 4):
        try:
            st = doc.styles['Heading %d' % level]
        except KeyError:
            continue
        size, cn, bold = prof['headings'][level]
        st.font.name = EN
        st.font.size = Pt(size)
        st.font.bold = bold
        st.font.color.rgb = BLACK          # 去掉 Word 标题默认的主题蓝
        st.font.italic = False
        st.font.underline = False
        rPr = st.element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn('w:ascii'), EN)
        rFonts.set(qn('w:hAnsi'), EN)
        rFonts.set(qn('w:eastAsia'), cn)
        pf = st.paragraph_format
        pf.space_before = Pt(10 if level == 1 else 6)
        pf.space_after = Pt(4)
        pf.line_spacing = 1.5
        pf.keep_with_next = (level >= 2)
        pf.left_indent = Cm(0)
        pf.first_line_indent = Cm(0)


def _setup_page(doc, prof=None):
    """A4 + 规范页边距 + 默认正文样式 + 标题样式（供目录域抓取）；封面页无页码。"""
    prof = prof or PROFILES['default']
    doc.sections[0].different_first_page_header_footer = True

    style = doc.styles['Normal']
    style.font.name = EN
    style.font.size = Pt(SZ_XIAOSI)
    rFonts = style.element.rPr.rFonts
    rFonts.set(qn('w:eastAsia'), CN_SONG)
    rFonts.set(qn('w:ascii'), EN)
    rFonts.set(qn('w:hAnsi'), EN)
    pf = style.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)

    for sec in doc.sections:
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(2.54)
        sec.bottom_margin = Cm(2.54)
        sec.left_margin = Cm(3.17)
        sec.right_margin = Cm(3.17)
        sec.header_distance = Cm(1.5)
        sec.footer_distance = Cm(1.5)

    _setup_heading_styles(doc, prof)
    _force_update_fields_on_open(doc)


def _force_update_fields_on_open(doc):
    """让 Word 打开文档时自动刷新 PAGE/PAGEREF 域，避免目录页码显示占位「1」。"""
    try:
        settings = doc.settings.element
        existing = settings.find(qn('w:updateFields'))
        if existing is None:
            el = OxmlElement('w:updateFields')
            el.set(qn('w:val'), 'true')
            settings.append(el)
    except Exception:
        pass


def _page_number_footer(doc):
    """页码：底部居中（封面因 different_first_page 自动无页码）。"""
    p = doc.sections[0].footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(p.add_run('— '), SZ_WU, CN_SONG)
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE  \\* MERGEFORMAT')
    r = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), str(int(SZ_WU * 2)))
    rPr.append(sz)
    r.append(rPr)
    t = OxmlElement('w:t')
    t.text = '1'
    r.append(t)
    fld.append(r)
    p._p.append(fld)
    _font(p.add_run(' —'), SZ_WU, CN_SONG)


# ============ 封面 ============

# ---- 第三百零二轮：封面左上角 Logo ----
# 等比缩放不拉伸；图本身是白底，docx 内不做任何反色/描边处理（夜间模式同样不处理）。
_LOGO_HEIGHT_CM = 1.6      # 封面 Logo 显示高度
_LOGO_X_CM = 1.5           # 相对页面左上角的水平偏移
_LOGO_Y_CM = 1.2           # 相对页面左上角的垂直偏移
_LOGO_REL_PATH = ('static', 'logo.png')


def _logo_path():
    """Logo 绝对路径：以本文件位置为基准定位 static/logo.png，不依赖进程工作目录。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *_LOGO_REL_PATH)


def _logo_aspect(path):
    """读图片真实像素宽高比 w/h；读不出来返回 None（调用方按 1:1 兜底，绝不拉伸）。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            if w and h:
                return float(w) / float(h)
    except Exception:
        pass
    try:
        import struct
        with open(path, 'rb') as f:
            head = f.read(32)
        if head[:8] == b'\x89PNG\r\n\x1a\n':
            w, h = struct.unpack('>II', head[16:24])
            if w and h:
                return float(w) / float(h)
    except Exception:
        pass
    return None


def _cover_logo(doc, anchor_paragraph):
    """封面左上角 Logo（第三百〇二轮）。

    用 python-docx 原生 add_picture 插成行内图，挂在封面第一个段落上并左对齐，
    视觉位置就是封面版心左上角；宽高按图片真实宽高比算，绝不拉伸。

    为什么不用浮动图（_add_float_picture 那套 parse_xml 拼 <w:drawing>）：
    手写 drawing XML 依赖完整的 xmlns 声明，漏一个 w 前缀就整段解析失败，
    而且失败得很隐蔽 —— 图片进了 word/media/，drawing 节点却没插进去，
    自检只看 media 里有图就会误判成功。原生 API 没有这个坑。

    任何异常（文件缺失 / 图片损坏 / 依赖缺失）一律静默跳过：
    封面 Logo 是锦上添花，绝不能让导出这条核心链路失败。
    """
    try:
        path = _logo_path()
        if not os.path.exists(path):
            return
        ratio = _logo_aspect(path) or 1.0
        height = Cm(_LOGO_HEIGHT_CM)
        width = Cm(_LOGO_HEIGHT_CM * ratio)     # 按真实宽高比算，不拉伸
        run = anchor_paragraph.add_run()
        run.add_picture(path, width=width, height=height)
        try:
            anchor_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        except Exception:
            pass
        return True
    except Exception as e:
        print('[docx_render] 封面 Logo 插入失败，忽略：%r' % (e,))
        return False


def _header(doc, title):
    """页眉：文档标题，宋体五号居中（无装饰线，符合「无特效」要求）。"""
    header = doc.sections[0].header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0
    _font(p.add_run(title or ''), SZ_WU, CN_SONG)


def _cover(doc, title, subtitle=None, org=None, school=None, team=None, advisor=None,
           show_school_advisor=True):
    """封面：主标题黑体小初 / 副标题黑体二号 / 学校·团队·指导老师·日期黑体小三，全部居中。"""
    # 封面文字压到纵向约 1/6 处（之前 150pt 把标题推太低，顶部留一大块空白）
    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(34)
    sp.paragraph_format.space_after = Pt(0)
    sp.paragraph_format.line_spacing = 1.0
    _font(sp.add_run(''), 1)

    # 第三百零二轮：封面左上角 Logo（挂在上面这个段落上，不额外占位；失败自动跳过）
    _cover_logo(doc, sp)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    p.paragraph_format.line_spacing = 1.3
    _font(p.add_run(title or ''), SZ_XIAOCHU, CN_HEI, bold=True)

    if subtitle:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(10)
        p.paragraph_format.line_spacing = 1.3
        _font(p.add_run(subtitle), SZ_ER, CN_HEI)

    # 学校 / 团队 / 指导老师：黑体小三居中（申报书封面必备信息）
    # iCAN 等双盲赛事不允许出现学校与指导老师，此时只保留团队（学生）信息
    if show_school_advisor:
        info_lines = [x for x in (org, school, team, advisor) if x]
    else:
        # org 通常也是「XX大学/单位」，双盲时一并隐藏
        info_lines = [x for x in (team,) if x]
    for line in info_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(10)
        p.paragraph_format.line_spacing = 1.5
        _font(p.add_run(line), SZ_XIAOSAN, CN_HEI)

    if info_lines:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(18)
        p.paragraph_format.line_spacing = 1.0
        _font(p.add_run(''), SZ_XIAOSAN)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = 1.5
    _font(p.add_run(datetime.datetime.now().strftime('%Y 年 %m 月 %d 日')),
          SZ_XIAOSAN, CN_HEI)


def _add_bookmark(p, name, bid):
    """给段落加书签，供目录的 PAGEREF 域取页码。"""
    start = OxmlElement('w:bookmarkStart')
    start.set(qn('w:id'), str(bid))
    start.set(qn('w:name'), name)
    end = OxmlElement('w:bookmarkEnd')
    end.set(qn('w:id'), str(bid))
    p._p.insert(0, start)
    p._p.append(end)


def _paginate_headings(doc, headings):
    """用 LibreOffice 渲染到 PDF，反查每个标题的真实页码（mark -> 页码）。

    失败（服务器没装 soffice / 解析异常）返回 None，由调用方退化为「目录不写页码」。
    """
    try:
        import os
        import subprocess
        import tempfile
        try:
            from pypdf import PdfReader
        except Exception:
            from PyPDF2 import PdfReader

        fd, docx_path = tempfile.mkstemp(suffix='.docx')
        os.close(fd)
        doc.save(docx_path)
        outdir = tempfile.mkdtemp()
        try:
            _soffice = None
            for _cand in ('soffice', 'libreoffice'):
                try:
                    subprocess.run(
                        [_cand, '--headless', '--convert-to', 'pdf',
                         '--outdir', outdir, docx_path],
                        check=True, timeout=180,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    _soffice = _cand
                    break
                except FileNotFoundError:
                    continue
            if _soffice is None:
                return None
            pdf_path = os.path.join(outdir, os.path.basename(docx_path).replace('.docx', '.pdf'))
            if not os.path.exists(pdf_path):
                return None
            reader = PdfReader(pdf_path)
            pages = [re.sub(r'\s+', '', (pg.extract_text() or '')) for pg in reader.pages]
        finally:
            try:
                os.unlink(docx_path)
            except Exception:
                pass
            try:
                for f in os.listdir(outdir):
                    os.unlink(os.path.join(outdir, f))
                os.rmdir(outdir)
            except Exception:
                pass

        result = {}
        for _level, text, mark in headings:
            key = re.sub(r'\s+', '', text or '')
            if len(key) < 2:
                continue
            # PDF 抽取可能把标题断行/加空格，取前 10 字做前缀匹配；
            # 从最后一页往前找，命中正文里的标题（避开目录页里同文字）。
            probe = key[:10]
            for idx in range(len(pages) - 1, -1, -1):
                if probe and probe in pages[idx]:
                    result[mark] = idx + 1
                    break
        return result if result else None
    except Exception:
        return None


def _toc_field_begin(doc):
    """开一个 TOC 域（begin + instrText + separate），之后写入的段落即「域结果缓存」。

    这样做一次满足两端：Word 打开可按 F9 刷新成自动目录；WPS / 手机不刷新域时
    直接显示下面的静态缓存（含真实页码），不会出现空目录或占位「1」。
    """
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run()
    fc = OxmlElement('w:fldChar')
    fc.set(qn('w:fldCharType'), 'begin')
    r._r.append(fc)
    r = p.add_run()
    it = OxmlElement('w:instrText')
    it.set(qn('xml:space'), 'preserve')
    it.text = r'TOC \o "1-2" \h \z \u'
    r._r.append(it)
    r = p.add_run()
    fs = OxmlElement('w:fldChar')
    fs.set(qn('w:fldCharType'), 'separate')
    r._r.append(fs)
    return p


def _toc_field_end(doc):
    """闭合上面开的 TOC 域。"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run()
    fe = OxmlElement('w:fldChar')
    fe.set(qn('w:fldCharType'), 'end')
    r._r.append(fe)
    return p


def _add_toc(doc, headings, toc_pages=None):
    """目录页：TOC 域 + 静态页码结果缓存。

    WPS / 手机预览不会像 Word 那样自动更新域，所以静态目录（真实页码）作为
    TOC 域的结果缓存写进去 —— 不刷新时照常可读，Word 里按 F9 即刷新为自动目录。
    toc_pages 拿不到某条页码时，该条只写标题、不写页码（绝不出现「1」）。
    """
    toc_pages = toc_pages or {}
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(16)
    _font(p.add_run('目  录'), SZ_ER, CN_HEI, bold=True)

    # 第二百三十五轮：导出门禁要「可刷新目录（TOC 域）」，此前只有静态段落 → 一律判缺。
    _toc_field_begin(doc)

    for level, text, mark in headings:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.0 if level == 1 else (0.6 if level == 2 else 1.2))
        pf.space_after = Pt(3)
        pf.line_spacing = 1.4

        # 右对齐制表位 + 省略号前导符，页码落在行尾
        pPr = p._p.get_or_add_pPr()
        tabs = OxmlElement('w:tabs')
        tab = OxmlElement('w:tab')
        tab.set(qn('w:val'), 'right')
        tab.set(qn('w:leader'), 'dot')
        tab.set(qn('w:pos'), '9060')      # 可编辑区右边界 ≈16cm
        tabs.append(tab)
        pPr.append(tabs)

        _font(p.add_run(_fullwidth(text)), SZ_XIAOSI,
              CN_HEI if level == 1 else CN_SONG, bold=(level == 1))

        page = toc_pages.get(mark)
        if page:
            # 制表符（右对齐 + 省略号前导符）+ 静态页码
            tr = p.add_run()
            tr._r.append(OxmlElement('w:tab'))
            _font(p.add_run(str(page)), SZ_XIAOSI, CN_SONG)

    _toc_field_end(doc)


# ============ 各类块渲染 ============

def _render_heading(doc, level, text, prof=None, mark=None, bid=0):
    """标题：按文档类型档位取字号/字体（申报书=标准层级，大纲=小字号轻层级）。"""
    prof = prof or PROFILES['default']
    size, cn, bold = prof['headings'].get(level, prof['headings'][4])
    # 必须挂 Heading 样式，否则目录域抓不到这一行
    try:
        p = doc.add_paragraph(style='Heading %d' % level)
    except KeyError:
        p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(10 if level == 1 else 6)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.5
    # 只让二级以下标题与正文「同页不分离」；一级章标题允许落页底，
    # 避免「keep_with_next」把整章推到下一页、在页底留大片空白
    pf.keep_with_next = (level >= 2)
    _font(p.add_run(_fullwidth(text)), size, cn, bold=bold)
    if mark:
        _add_bookmark(p, mark, bid)


def _render_para(doc, lines, prof=None):
    """正文：宋体小四，1.5 倍行距，段前段后 0。
    申报书/分析/报告 → 首行缩进 2 字符；大纲 → 不缩进、靠左对齐。
    行内的 **加粗** 保留（仅关键词，不通篇加粗）。"""
    prof = prof or PROFILES['default']
    _INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`)')
    for line in lines:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.alignment = prof['body_align']
        if prof['body_indent']:
            _indent_chars(p, 200)
        for seg in _INLINE.split(line):
            if not seg:
                continue
            if len(seg) > 4 and seg.startswith('**') and seg.endswith('**'):
                _font(p.add_run(_fullwidth(seg[2:-2])), SZ_XIAOSI, CN_SONG, bold=True)
            elif len(seg) > 2 and seg.startswith('`') and seg.endswith('`'):
                _font(p.add_run(seg[1:-1]), SZ_XIAOSI, EN)
            else:
                _font(p.add_run(_fullwidth(seg)), SZ_XIAOSI, CN_SONG)


def _render_list(doc, items, ordered, prof=None):
    """手动编号，不使用 Word 自动编号（规范要求）。"""
    prof = prof or PROFILES['default']
    for idx, item in enumerate(items, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = 1.5
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.alignment = prof['body_align']
        _hanging_indent(p, 200)
        if ordered:
            _font(p.add_run('%d. ' % idx), SZ_XIAOSI, CN_SONG, bold=True)
        else:
            _font(p.add_run('● '), SZ_XIAOSI, CN_SONG)
        _render_inline_into(p, item)


def _render_inline_into(p, text):
    _INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`)')
    for seg in _INLINE.split(text):
        if not seg:
            continue
        if len(seg) > 4 and seg.startswith('**') and seg.endswith('**'):
            _font(p.add_run(_fullwidth(seg[2:-2])), SZ_XIAOSI, CN_SONG, bold=True)
        elif len(seg) > 2 and seg.startswith('`') and seg.endswith('`'):
            _font(p.add_run(seg[1:-1]), SZ_XIAOSI, EN)
        else:
            _font(p.add_run(_fullwidth(seg)), SZ_XIAOSI, CN_SONG)


def _render_quote(doc, lines):
    """引用/注释：宋体五号，左右缩进，无底色无边框。"""
    for line in lines:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.8)
        pf.right_indent = Cm(0.4)
        pf.line_spacing = 1.5
        pf.space_before = Pt(3)
        pf.space_after = Pt(3)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _font(p.add_run(_fullwidth(line)), SZ_WU, CN_SONG)


def _render_code(doc, lines):
    """代码/公式块：Times New Roman 五号，缩进，无底色。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.8)
    pf.line_spacing = 1.25
    pf.space_before = Pt(4)
    pf.space_after = Pt(8)
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        _font(p.add_run(line if line else ' '), SZ_WU, EN)


def _render_caption(doc, text):
    """表题/图题：宋体五号加粗居中。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(8)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.5
    _font(p.add_run(_fullwidth(text)), SZ_WU, CN_SONG, bold=True)


def _tbl_borders(tblPr, spec):
    """给表格（或单元格）写边框。spec: {边: (val, sz, color)}，sz 单位是 1/8 pt。"""
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement('w:' + edge)
        v = spec.get(edge)
        if v:
            el.set(qn('w:val'), v[0])
            el.set(qn('w:sz'), str(v[1]))
            el.set(qn('w:color'), v[2])
        else:
            el.set(qn('w:val'), 'nil')
        borders.append(el)
    tblPr.append(borders)


def _cell_borders(cell, bottom_sz=6):
    """单元格下边框（三线表的表头分隔线）。"""
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for edge in ('top', 'left', 'right'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'nil')
        borders.append(el)
    b = OxmlElement('w:bottom')
    b.set(qn('w:val'), 'single')
    b.set(qn('w:sz'), str(bottom_sz))
    b.set(qn('w:color'), '000000')
    borders.append(b)
    tcPr.append(borders)


def _row_cant_split(row):
    """一行不跨页断开：表格被打断在两页是最难看的一种。"""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement('w:cantSplit'))


def _text_w(s):
    """估算列宽权重：中日韩字符算 2，其余算 1。"""
    s = _plain(s or '')
    w = 0
    for ch in s:
        w += 2 if _is_cn(ch) else 1
    return w


def _col_widths(header, rows, total_cm=14.66):
    """按各列最长内容分配版心宽度（A4 左右 3.17cm 后剩 14.66cm）。
    首列一般是「维度 / 指标」这类短标签，给点加成，别被长正文挤成窄条。"""
    cols = len(header)
    w = []
    for j in range(cols):
        m = _text_w(header[j])
        for r in rows:
            m = max(m, _text_w(r[j]))
        w.append(min(m, 30))
    if w:
        w[0] = w[0] * 1.2 + 2
    tot = sum(w) or 1
    # 单列最窄 1.6cm（放得下 4 个汉字），最宽不超过版心一半
    return [max(1.6, min(total_cm * 0.5, total_cm * x / tot)) for x in w]


def _set_tbl_layout(table, widths_cm):
    """钉死列宽：只设 cell.width 不够，Word 主要看 tblGrid 和 tblW，
    不写死的话打开文档又会弹回自动布局（列宽忽宽忽窄）。"""
    total = int(sum(widths_cm) * 567)          # 1cm = 567 twips
    tblPr = table._tbl.tblPr
    for el in tblPr.findall(qn('w:tblW')):
        tblPr.remove(el)
    tblW = OxmlElement('w:tblW')
    tblW.set(qn('w:w'), str(total))
    tblW.set(qn('w:type'), 'dxa')
    tblPr.append(tblW)
    grid = table._tbl.tblGrid
    for j, col in enumerate(grid.gridCol_lst):
        col.set(qn('w:w'), str(int(widths_cm[j] * 567)))


def _render_table(doc, header, rows):
    """表格：全框线（与 iCAN 官方计划书模板一致，红头文件优先），无底色无阴影；
    表头黑体小四加粗居中，表内宋体小四；列宽按内容自适应；行不跨页断开。

    注：曾试过改三线表（顶线/表头线/底线），但官方模板用的是 Table Grid 全框线，
    与红头文件冲突时以红头文件为准，故保留全框线，只优化列宽与对齐。
    """
    cols = len(header)
    if cols == 0:
        return
    norm = [(r + [''] * cols)[:cols] for r in rows]

    table = doc.add_table(rows=1, cols=cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_cell_margins(table, top=60, bottom=60, left=100, right=100)

    widths = _col_widths(header, norm)
    _set_tbl_layout(table, widths)

    def _align_for(j, txt):
        # 首列左对齐；其余列短内容居中、长内容左对齐（长句居中会读得很累）
        if j == 0:
            return WD_ALIGN_PARAGRAPH.LEFT
        return WD_ALIGN_PARAGRAPH.CENTER if _text_w(txt) <= 16 else WD_ALIGN_PARAGRAPH.LEFT

    hdr = table.rows[0]
    _repeat_header(hdr)
    _row_cant_split(hdr)
    for j, txt in enumerate(header):
        cell = hdr.cells[j]
        cell.width = Cm(widths[j])
        cell.text = ''
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(0)
        _font(p.add_run(_fullwidth(_plain(txt))), SZ_XIAOSI, CN_HEI, bold=True)

    for r in norm:
        row = table.add_row()
        _row_cant_split(row)
        for j, txt in enumerate(r):
            cell = row.cells[j]
            cell.width = Cm(widths[j])
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = _align_for(j, txt)
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(0)
            _font(p.add_run(_fullwidth(_plain(txt))), SZ_XIAOSI, CN_SONG)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)
    sp.paragraph_format.line_spacing = 1.0


def _render_hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.0


# ============ 主入口 ============

# ---------- 245.1：章节编号统一 & 重复章节去重（渲染层兜底） ----------
_CN_DIGITS = '零一二三四五六七八九'
# 紧跟这些字说明是「1.5 万元预算」这类正文，不是编号前缀
_UNIT_CHARS = '万亿亿元秒米克吨%％个人次件套项部章节篇'

# 标题上可能已经带的编号前缀：一、/（一）/（1）/第X章/1.1 / 1.1.2 / 3.
_RE_HEAD_PREFIX = re.compile(
    r'^\s*(?:'
    r'第[0-9一二三四五六七八九十百]+[章篇節节]'
    r'|[（(]\s*[0-9一二三四五六七八九十]+\s*[)）]'
    r'|[0-9]+(?:\.[0-9]+)*[、.．]\s*'
    r'|[一二三四五六七八九十百]+[、．.]'
    r')\s*'
)


def _cn_numeral(n):
    """1->一  10->十  11->十一  20->二十  42->四十二；>=100 退回阿拉伯数字"""
    n = int(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return '十' + (_CN_DIGITS[n - 10] if n > 10 else '')
    if n < 100:
        return _CN_DIGITS[n // 10] + '十' + (_CN_DIGITS[n % 10] if n % 10 else '')
    return str(n)


def _strip_head_prefix(text):
    """剥掉标题上已有的编号前缀；判定为误匹配时原样返回。"""
    s0 = str(text or '')
    m = _RE_HEAD_PREFIX.match(s0)
    if not m:
        return s0
    rest = s0[m.end():]
    # 前缀吃掉了整行 -> 大概率是误匹配（如「一体化方案」），原样返回
    if not rest:
        return s0
    frag = m.group(0).strip()
    # 下面两道闸门只对阿拉伯数字前缀生效。中文数字（一、二、）和整数编号（1、）一律照剥 ——
    # 否则「一、项目背景」会因为 rest 首字「项」命中单位闸门而剥不掉，重排后变成「一、一、」。
    if re.match(r'^[0-9]', frag):
        # 点分数字 + 紧跟单位字 -> 是正文（1.5 万元预算），不剥
        if re.match(r'^[0-9]+\.[0-9]', frag) and rest[0] in _UNIT_CHARS:
            return s0
        # 首位为 0 -> 是正文（0.8 秒识别），不剥
        if re.match(r'^0', frag):
            return s0
    return rest


def _core_key(text):
    """去重主键：剥编号 + 去空白 + 括号归一"""
    t = _strip_head_prefix(str(text or ''))
    t = t.replace('（', '(').replace('）', ')')
    return re.sub(r'\s+', '', t).lower()


def _head_prefix(depth, n):
    """章层级 一、/ 二级（一）/ 三级 1. / 四级（1）——沿用《统一字体格式标准》"""
    if depth <= 0:
        return _cn_numeral(n) + '、'
    if depth == 1:
        return '（' + _cn_numeral(n) + '）'
    if depth == 2:
        return '%d. ' % n
    return '（%d）' % n


def _chapter_level(blocks):
    """章层级 = 实际存在的、拥有 >=2 个标题的最浅层级。
    不写死 Heading1：申报书正文几乎全是 markdown 的 ##(Heading2)，
    偶发的单个 # 是文档名不是章节，写死 H1 会把文档名编成「一、」。"""
    cnt = {}
    for blk in blocks:
        if blk[0] == 'h':
            cnt[blk[1]] = cnt.get(blk[1], 0) + 1
    if not cnt:
        return None
    for lv in sorted(cnt):
        if cnt[lv] >= 2:
            return lv
    return None


def _append_body(seg, blk):
    """把重复章节的正文并入已保留章节：完全相同的跳过，同类列表合并去重。"""
    if blk[0] == 'p':
        for prev in seg:
            if prev[0] == 'p' and list(prev[1]) == list(blk[1]):
                return
        seg.append(blk)
    elif blk[0] in ('ul', 'ol'):
        for prev in seg:
            if prev[0] == blk[0]:
                for it in blk[1]:
                    if it not in prev[1]:
                        prev[1].append(it)
                return
        seg.append(blk)
    else:
        seg.append(blk)


def _normalize_sections(blocks):
    """重复章节去重 + 按真实层级顺序重排章节编号。"""
    if not blocks:
        return blocks
    cl = _chapter_level(blocks)
    if cl is None:
        return blocks

    # 1) 按章层级切段：章层级标题开启新段，之前的内容（如文档名 H1）作为 prelude
    segs, prelude, cur = [], [], None
    for blk in blocks:
        if blk[0] == 'h' and blk[1] == cl:
            cur = {'title': blk[2], 'body': []}
            segs.append(cur)
        elif cur is not None:
            cur['body'].append(blk)
        else:
            prelude.append(blk)

    # 2) 合并重复章节：一律保留先出现的（保留"更完整的"会把整章搬到文末），
    #    重复项的正文并进来，不丢内容
    merged, index = [], {}
    for seg in segs:
        key = _core_key(seg['title'])
        if key in index:
            for b in seg['body']:
                _append_body(merged[index[key]]['body'], b)
            continue
        index[key] = len(merged)
        merged.append(seg)

    # 3) 重排编号
    out, counters = list(prelude), {}
    for seg in merged:
        counters[cl] = counters.get(cl, 0) + 1
        for k in [k for k in counters if k > cl]:
            del counters[k]
        out.append(('h', cl, _head_prefix(0, counters[cl]) + _strip_head_prefix(seg['title'])))
        for b in seg['body']:
            if b[0] == 'h':
                d = b[1] - cl
                if d > 0:
                    lv = b[1]
                    counters[lv] = counters.get(lv, 0) + 1
                    for k in [k for k in counters if k > lv]:
                        del counters[k]
                    out.append(('h', lv, _head_prefix(d, counters[lv]) + _strip_head_prefix(b[2])))
                else:
                    out.append(b)   # 比章层级更浅的标题不编号
            else:
                out.append(b)
    return out

def build_docx(title, text, subtitle=None, org=None, toc=None,
               cover=None, cover_image=False, topic=None, doc_type='report',
               school=None, team=None, advisor=None, show_school_advisor=True,
               header_title=None, toc_pages=None):
    # _WB_ASSIST_DECL_417 417 轮 P0：所有生成文档底部统一加「智能辅助」声明
    # 措辞温和、禁用「AI」字样（418 轮口径）；幂等，重复执行不会叠加。
    if '本材料由智能助手辅助起草' not in (text or ''):
        text = (text or '') + '\n\n' + '本材料由智能助手辅助起草，已按官方要求排版，请以团队真实情况核对补充后提交。'
    """生成符合格式标准的 Word 文档。

    :param title:       文档主标题（封面黑体小初）
    :param text:        Markdown 正文
    :param subtitle:    封面副标题（黑体二号），如赛事名称 / 项目类别
    :param org:         封面单位行（黑体小三），如「XX大学 · 团队名称」
    :param toc:         是否插入目录页；None = 按 doc_type 档位决定
    :param cover:       是否生成封面页；None = 按 doc_type 档位决定
    :param cover_image: 是否加封面背景图 —— 默认 False，
                        因为申报书标准禁止底色/特效，仅非申报场景可开
    :param topic:       封面背景图风格匹配用文本（cover_image=True 时生效）
    :param doc_type:    'report' 报告（默认）/ 'analysis' 分析 / 'outline' 大纲
                        / 'default' 申报书 —— 决定标题字号、正文缩进、封面目录
    :param show_school_advisor: 封面是否显示学校/指导老师；iCAN 双盲评审时应为 False
    :param header_title:        页眉文字；None 时用 title。申报书封面放项目名、页眉放「XX 申报书」
    :param toc_pages:           目录真实页码 {mark: page}；None 时自动渲染计算，算不出则不写页码
    :return:            python-docx Document
    """
    prof = PROFILES.get(doc_type, PROFILES['default'])
    if cover is None:
        cover = prof['cover']
    if toc is None:
        toc = prof['toc']
    # 短文档（简洁版约 1000-1500 字）不要目录：目录页只有 5 个条目，整页大半空白
    if toc and len((text or '').replace('\n', '').replace(' ', '')) < 2500:
        toc = False

    blocks = _blocks(text or '')
    # 第二百四十五轮：渲染层兜底 —— 重复章节去重 + 按真实层级顺序重排编号
    blocks = _normalize_sections(blocks)
    # 先收集标题，用来生成目录（目录条目必须和正文一一对应）
    headings, _bm_id = [], 0
    for blk in blocks:
        if blk[0] == 'h' and blk[1] <= 3:
            _bm_id += 1
            headings.append((blk[1], blk[2], '_toc_%d' % _bm_id))

    def _assemble(toc_pages_arg):
        doc = Document()
        _setup_page(doc, prof)
        _page_number_footer(doc)     # 页脚：页码居中（封面因首页不同自动无页码）
        _header(doc, header_title or title)  # 页眉：文档标题，宋体五号居中

        if cover:
            if cover_image:
                try:
                    from cover_style import get_cover
                    path, _sk, _ink = get_cover(topic or subtitle or title or '')
                    _cover_background(doc, path)
                except Exception as e:
                    print('[docx_render] 封面背景图失败，忽略：%r' % (e,))
            _cover(doc, title, subtitle, org, school, team, advisor,
                   show_school_advisor=show_school_advisor)
            doc.add_page_break()

        if toc:
            if headings:
                _add_toc(doc, headings, toc_pages_arg)
            doc.add_page_break()

        _bm_i = 0
        for i, blk in enumerate(blocks):
            kind = blk[0]
            if kind == 'h':
                _bm_i += 1
                _render_heading(doc, blk[1], blk[2], prof,
                                mark=('_toc_%d' % _bm_i if blk[1] <= 3 else None),
                                bid=1000 + _bm_i)
            elif kind == 'p':
                # 形如「表 5-1 xxx」「图 3-2 xxx」且后面紧跟表格 → 按表题/图题渲染
                nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                body = ' '.join(blk[1])
                if nxt and nxt[0] == 'table' and _RE_CAPTION.match(body) and len(body) <= 40:
                    _render_caption(doc, body)
                elif _RE_CAPTION.match(body) and len(body) <= 40:
                    _render_caption(doc, body)
                else:
                    _render_para(doc, blk[1], prof)
            elif kind == 'ul':
                _render_list(doc, blk[1], ordered=False, prof=prof)
            elif kind == 'ol':
                _render_list(doc, blk[1], ordered=True, prof=prof)
            elif kind == 'quote':
                _render_quote(doc, blk[1])
            elif kind == 'code':
                _render_code(doc, blk[1])
            elif kind == 'table':
                _render_table(doc, blk[1], blk[2])
            elif kind == 'hr':
                _render_hr(doc)

        cp = doc.core_properties
        cp.title = title
        cp.author = '科创赛事多智能体协同创作助手'
        cp.category = '赛事申报材料'
        return doc

    # 需要目录但没给现成页码：先渲染一版算出真实页码，再重建一版写死页码。
    # LibreOffice 不在 / 解析失败时退回无页码目录（标题仍完整，绝不出现占位「1」）。
    if toc and headings and toc_pages is None:
        probe = _assemble({})
        pages = _paginate_headings(probe, headings)
        if pages:
            return _assemble(pages)
        return probe
    return _assemble(toc_pages or {})


# ---- 封面背景图（默认不启用，保留给非申报场景）----

_NS_DRAW = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


def _add_float_picture(paragraph, img_path, part, width_cm, height_cm,
                       pos_x_cm=0.0, pos_y_cm=0.0):
    from docx.oxml import parse_xml
    _img_part, r_id = part.get_or_add_image(img_path)
    cx = int(width_cm * 360000)
    cy = int(height_cm * 360000)
    xml = (
        '<w:drawing {ns}>'
        '<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"'
        ' relativeHeight="251658240" behindDoc="1" locked="0" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page"><wp:posOffset>{px}</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="page"><wp:posOffset>{py}</wp:posOffset></wp:positionV>'
        '<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:wrapNone/>'
        '<wp:docPr id="{pid}" name="cover"/>'
        '<a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic>'
        '<pic:nvPicPr><pic:cNvPr id="{pid}" name="cover"/><pic:cNvPicPr><a:picLocks/></pic:cNvPicPr></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="{rid}"/><a:srcRect/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr bwMode="auto">'
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:noFill/><a:ln><a:noFill/></a:ln>'
        '</pic:spPr>'
        '</pic:pic>'
        '</a:graphicData>'
        '</a:graphic>'
        '</wp:anchor>'
        '</w:drawing>'
    ).format(ns=_NS_DRAW, px=int(pos_x_cm * 360000), py=int(pos_y_cm * 360000),
             cx=cx, cy=cy, pid=abs(hash(img_path)) % 100000 + 1, rid=r_id)
    run = paragraph.add_run()
    run._r.append(parse_xml(xml))
    return run


def _cover_background(doc, img_path):
    header = doc.sections[0].first_page_header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    _add_float_picture(p, img_path, header.part, 21.0, 29.7, 0, 0)
