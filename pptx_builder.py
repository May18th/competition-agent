"""
路演 PPT 生成模块（python-pptx）
设计目标：不是"能用"，而是"拿得出手"——
- 16:9 宽屏，统一视觉系统（深蓝 #0F1535 / 主紫 #4A55B8 / 青强调 #22B8CF）
- 封面 / 章节页 / 要点页 / 图表页 / 表格页 / 数据页 / 结尾页 7 种版式
- 每页统一页眉强调条 + 页脚（项目名 + 页码）
- 微软雅黑全套（含中文 east-asian 字体设置）
输入：deck = {"project":..., "one_liner":..., "competition":..., "slides":[...]}
"""
import os
import re
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

# ============ 主题系统（按项目内容自适应）============
# 每套主题 = 一套完整配色 + 字体 + 装饰色，deep/deep2 决定封面渐变，
# chapter 是章节色轮（内容页顶条、kicker、标题下划线都从它取色）。
THEMES = {
    "tech": {
        "label": "科技蓝（AI/算法/硬件/数据类）",
        "chapter": ["4A55B8", "0E9AA7", "EF8C2C", "DB3F72", "7C5CE0", "2E9E5B", "D94E2A"],
        "deep": "0F1535", "deep2": "3B2170",
        "ink": "1A2347", "body": "3A4468", "muted": "8A93B5",
        "primary": "4A55B8", "accent": "22B8CF",
        "card": "F7F8FD", "soft": "F2F4FB",
        "cover_deco": ["22B8CF", "F59E0B", "DB3F72"],
        "section_rule": "F5D96B", "font": "微软雅黑",
        "chart": ["#4A55B8", "#22B8CF", "#F59E0B", "#34C78A", "#F0637C", "#8B7BE8", "#5B93F5"],
    },
    "ink": {
        "label": "水墨丹青（文化/非遗/文创/古籍/书法类）",
        "chapter": ["5A6B7A", "8B2E2E", "B98A3C", "4A5D4E", "6B5B73", "2F4858", "A65628"],
        "deep": "1B1B1B", "deep2": "4A4A4A",
        "ink": "232323", "body": "4A4A4A", "muted": "8C8579",
        "primary": "8B2E2E", "accent": "B98A3C",
        "card": "F7F4ED", "soft": "F2EDE3",
        "cover_deco": ["8B2E2E", "B98A3C", "4A5D4E"],
        "section_rule": "D9C7A3", "font": "楷体",
        "chart": ["#5A6B7A", "#8B2E2E", "#B98A3C", "#4A5D4E", "#6B5B73", "#2F4858", "#A65628"],
    },
    "medical": {
        "label": "生命青绿（医疗/健康/护理/康复类）",
        "chapter": ["0E9E8C", "2E86C1", "45B39D", "1F7A6B", "D68910", "5DADE2", "27AE60"],
        "deep": "09332F", "deep2": "0E6B60",
        "ink": "123B37", "body": "33605B", "muted": "83A9A4",
        "primary": "0E9E8C", "accent": "34D3B5",
        "card": "F2FAF8", "soft": "E7F5F2",
        "cover_deco": ["34D3B5", "F5C86B", "2E86C1"],
        "section_rule": "A8E6D9", "font": "微软雅黑",
        "chart": ["#0E9E8C", "#2E86C1", "#45B39D", "#F0B429", "#27AE60", "#5DADE2", "#16A085"],
    },
    "edu": {
        "label": "暖橙活力（教育/教学/校园/培训类）",
        "chapter": ["E2803A", "C0563A", "F0B429", "5B8C5A", "4A7FB5", "A463C8", "D45B5B"],
        "deep": "4A2410", "deep2": "8A4B1F",
        "ink": "3B2418", "body": "5B4436", "muted": "A08A78",
        "primary": "E2803A", "accent": "F0B429",
        "card": "FFF8F0", "soft": "FBEEDD",
        "cover_deco": ["F0B429", "E2803A", "D45B5B"],
        "section_rule": "FFD98A", "font": "微软雅黑",
        "chart": ["#E2803A", "#F0B429", "#C0563A", "#5B8C5A", "#4A7FB5", "#A463C8", "#D45B5B"],
    },
    "agri": {
        "label": "大地丰绿（农业/种植/养殖/乡村/生态类）",
        "chapter": ["4E8C3A", "7BA05B", "C9A227", "6B8E23", "3E7C59", "A0703A", "2E6B4F"],
        "deep": "1E3D1A", "deep2": "3E6B2A",
        "ink": "243A1E", "body": "46603A", "muted": "8CA07E",
        "primary": "4E8C3A", "accent": "C9A227",
        "card": "F6FAF2", "soft": "EFF7E8",
        "cover_deco": ["C9A227", "7BA05B", "E08A3C"],
        "section_rule": "DCE9A8", "font": "微软雅黑",
        "chart": ["#4E8C3A", "#C9A227", "#7BA05B", "#6B8E23", "#3E7C59", "#A0703A", "#2E6B4F"],
    },
    "finance": {
        "label": "商务藏金（金融/支付/供应链/商业服务类）",
        "chapter": ["1F3864", "B8860B", "2E5C8A", "8B6914", "40607A", "C99700", "33475B"],
        "deep": "0C1A33", "deep2": "1F3864",
        "ink": "16233D", "body": "3C4A63", "muted": "8894AE",
        "primary": "1F3864", "accent": "B8860B",
        "card": "F7F8FA", "soft": "EFF1F6",
        "cover_deco": ["B8860B", "C99700", "40607A"],
        "section_rule": "E0C068", "font": "微软雅黑",
        "chart": ["#1F3864", "#B8860B", "#2E5C8A", "#C99700", "#40607A", "#8B6914", "#5B7A99"],
    },
    "craft": {
        "label": "匠心工业（智能制造/机械/材料/建筑类）",
        "chapter": ["5C6B73", "E08A38", "3D5A6C", "A63A2F", "7A8B5A", "C77B3E", "4A5D63"],
        "deep": "1F2A30", "deep2": "3D4C55",
        "ink": "232E33", "body": "48575E", "muted": "8B979D",
        "primary": "5C6B73", "accent": "E08A38",
        "card": "F5F6F7", "soft": "EAEDEF",
        "cover_deco": ["E08A38", "A63A2F", "7A8B5A"],
        "section_rule": "E8B87A", "font": "微软雅黑",
        "chart": ["#5C6B73", "#E08A38", "#3D5A6C", "#A63A2F", "#7A8B5A", "#C77B3E", "#4A5D63"],
    },
    "social": {
        "label": "公益暖阳（公益/助老/无障碍/社区服务类）",
        "chapter": ["D46A5C", "E4A03C", "5E8C7E", "C2564F", "7B6DA8", "3E8C86", "B5713C"],
        "deep": "4A2320", "deep2": "8A3F33",
        "ink": "3A2422", "body": "57433F", "muted": "A2897F",
        "primary": "D46A5C", "accent": "E4A03C",
        "card": "FFF7F5", "soft": "FBEDE8",
        "cover_deco": ["E4A03C", "D46A5C", "5E8C7E"],
        "section_rule": "F3C9A0", "font": "微软雅黑",
        "chart": ["#D46A5C", "#E4A03C", "#5E8C7E", "#C2564F", "#7B6DA8", "#3E8C86", "#B5713C"],
    },
    "academic": {
        "label": "学术答辩（论文/开题/结题/科研类）",
        "chapter": ["002FA7", "2E75B6", "4A7FB5", "1F4E78", "5B8C5A", "8B6914", "6B5B73"],
        "deep": "00254D", "deep2": "003F88",
        "ink": "002B5C", "body": "33506E", "muted": "7E93AB",
        "primary": "002FA7", "accent": "2E75B6",
        "card": "F5F7FA", "soft": "EDF1F6",
        "cover_deco": ["2E75B6", "5B8C5A", "8B6914"],
        "section_rule": "B8D4F0", "font": "微软雅黑",
        "chart": ["#002FA7", "#2E75B6", "#4A7FB5", "#5B8C5A", "#8B6914", "#6B5B73", "#7E93AB"],
    },
    "ican": {
        # iCAN 大赛专用：蓝白科技风。全色轮只走蓝色系，封面深蓝渐变 + 亮蓝强调，
        # 不用撞色不用花哨装饰，答辩/路演大屏投影也稳（深底白字，对比度够）。
        "label": "iCAN 蓝白科技（iCAN 大赛 · 正式路演场合）",
        "chapter": ["0E5EA8", "2AA9E0", "124C86", "4E93CE", "1E7FB8", "2F5E9E", "6FB3E0"],
        "deep": "072C55", "deep2": "0F5C9E",
        "ink": "0B2E52", "body": "3A5B7E", "muted": "93A8C2",
        "primary": "0E5EA8", "accent": "2AA9E0",
        "card": "F4F8FE", "soft": "EAF2FB",
        "cover_deco": ["2AA9E0", "7FC4EE", "0E5EA8"],
        "section_rule": "C4DEF5", "font": "微软雅黑",
        "chart": ["#0E5EA8", "#2AA9E0", "#124C86", "#4E93CE", "#6FB3E0", "#1E7FB8", "#9CCBEF"],
    },
    "cyber": {
        "label": "科技紫·AI（人工智能/大数据/赛博未来类）",
        "chapter": ["6D28D9", "7C3AED", "A855F7", "4B0082", "22D3EE", "F472B6", "8B5CF6"],
        "deep": "160826", "deep2": "3B2170",
        "ink": "2A1A4A", "body": "5B4A7A", "muted": "9A8BB8",
        "primary": "7C3AED", "accent": "22D3EE",
        "card": "F7F4FD", "soft": "F1EAFB",
        "cover_deco": ["22D3EE", "A855F7", "F472B6"],
        "section_rule": "C4B5FD", "font": "微软雅黑",
        "chart": ["#7C3AED", "#22D3EE", "#A855F7", "#F472B6", "#8B5CF6", "#4B0082", "#F59E0B"],
    },
}
THEME_ORDER = ["tech", "ink", "medical", "edu", "agri", "finance", "craft", "social", "academic", "cyber", "ican"]

# ============ 版式模板库：每个主题都可套 4 套模板 ============
# cover  封面样式：gradient 流光大块 / split 左色块 / band 顶部色带 / center 居中留白
# body   正文样式：cards 卡片式 / minimal 极简条目 / numbered 大号序号
# deco   是否渲染角落几何装饰
# section 章节页：dark 深色 / light 浅色
VARIANTS = [
    {"key": "v1", "name": "流光 · 卡片", "cover": "gradient", "body": "cards", "deco": True, "section": "dark"},
    {"key": "v2", "name": "左色块 · 极简", "cover": "split", "body": "minimal", "deco": False, "section": "light"},
    {"key": "v3", "name": "色带 · 序号", "cover": "band", "body": "numbered", "deco": True, "section": "dark"},
    {"key": "v4", "name": "居中 · 留白", "cover": "center", "body": "cards", "deco": False, "section": "light"},
]
V = dict(VARIANTS[0])   # 当前生效版式（默认 v1）
THEME_NAME = "tech"


def list_themes():
    """给前端用的主题/模板清单。

    顺带把配色回传（deep/deep2/primary/accent/deco），前端画缩略图就不用再维护一份
    和 THEMES 重复的对照表——以后新增主题，前端自动就能画出来。
    """
    return {
        "themes": [
            {"key": k, "label": THEMES[k]["label"],
             "colors": {
                 "deep": THEMES[k]["deep"], "deep2": THEMES[k]["deep2"],
                 "primary": THEMES[k]["primary"], "accent": THEMES[k]["accent"],
                 "deco": list(THEMES[k].get("cover_deco", [])),
             },
             "variants": [{"key": v["key"], "name": v["name"]} for v in VARIANTS]}
            for k in THEME_ORDER
        ]
    }


def _apply_variant(key):
    """切换版式模板"""
    global V
    for v in VARIANTS:
        if v["key"] == str(key or "v1").lower():
            V = dict(v)
            return V
    V = dict(VARIANTS[0])
    return V


def _apply_theme(name):
    """切换整套视觉系统：只改模块级常量，页面函数不用动"""
    global THEME_NAME, CHAPTER, DEEP, DEEP2, INK, BODY, MUTED, PRIMARY, ACCENT, CARD, SOFT, FONT, COVER_DECO, SECTION_RULE
    t = THEMES.get(str(name or "").lower()) or THEMES["tech"]
    THEME_NAME = str(name or "tech").lower()
    CHAPTER = t["chapter"]; DEEP = t["deep"]; DEEP2 = t["deep2"]
    INK = t["ink"]; BODY = t["body"]; MUTED = t["muted"]
    PRIMARY = t["primary"]; ACCENT = t["accent"]
    CARD = t["card"]; SOFT = t["soft"]; FONT = t["font"]
    COVER_DECO = t["cover_deco"]; SECTION_RULE = t["section_rule"]
    return THEME_NAME


# 章节色轮：按 kicker 序号轮换，整份 PPT 从"一片蓝"变成有节奏的多色叙事
CHAPTER = ["4A55B8", "0E9AA7", "EF8C2C", "DB3F72", "7C5CE0", "2E9E5B", "D94E2A"]
DEEP = "0F1535"      # 封面深蓝
DEEP2 = "3B2170"     # 封面渐变尾（蓝紫）
INK = "1A2347"       # 标题深色
BODY = "3A4468"      # 正文
MUTED = "8A93B5"     # 页脚/辅助
PRIMARY = "4A55B8"   # 主色（兜底）
ACCENT = "22B8CF"    # 强调青（兜底）
SOFT = "F2F4FB"      # 浅底（表格斑马纹，会被章节色覆盖）
CARD = "F7F8FD"      # 卡片底
WHITE = "FFFFFF"
FONT = "微软雅黑"
COVER_DECO = ["22B8CF", "F59E0B", "DB3F72"]
SECTION_RULE = "F5D96B"


def _chapter_color(kicker, idx=0):
    """按 kicker 里的序号取章节色：'03 / 市场' -> CHAPTER[2]"""
    m = re.match(r"\D*(\d+)", str(kicker or ""))
    if m:
        try:
            return CHAPTER[(int(m.group(1)) - 1) % len(CHAPTER)]
        except Exception:
            pass
    return CHAPTER[idx % len(CHAPTER)]


def _darken(hexstr, amount=0.15):
    """把颜色往黑色方向压（用于表头逐列递深）"""
    try:
        r = int(hexstr[0:2], 16); g = int(hexstr[2:4], 16); b = int(hexstr[4:6], 16)
        f = lambda v: max(int(v * (1 - amount)), 0)
        return "%02X%02X%02X" % (f(r), f(g), f(b))
    except Exception:
        return "3A44A0"


def _lighten(hexstr, amount=0.55):
    """把颜色往白色方向调（用于渐变尾、浅底色块）"""
    try:
        r = int(hexstr[0:2], 16); g = int(hexstr[2:4], 16); b = int(hexstr[4:6], 16)
        f = lambda v: int(v + (255 - v) * amount)
        return "%02X%02X%02X" % (f(r), f(g), f(b))
    except Exception:
        return "EEF1FA"

SLIDE_W = 13.333
SLIDE_H = 7.5

# ===== 要点断行控制（豆包约定，2026-09-25）=====
# 每条要点最多占 MAX_LINES_PER_BULLET 行，每行不超过 MAX_CHARS_PER_LINE 个中文字符。
# 超出部分末尾补 "…"，保证版面不被长句撑爆。
# 注意：实际每行字数还会按栏宽动态收紧（见 _bullets_body），这两个值是**上限**。
MAX_CHARS_PER_LINE = 40
MAX_LINES_PER_BULLET = 2

# 断行优先落在这类标点之后，避免把词从中间劈开
_BREAK_CHARS = "，。；、！？：）】」》”’,.;!?:)]}"

# ===== 自动分页常量（豆包约定，2026-09-25）=====
# 一页最多放几张要点卡片。实测：双栏 8 张时最后一张底边 6.19in，
# 距页脚（6.98in）仍有余量，所以上限取 8。
MAX_BLOCKS_PER_SLIDE = 8
# 有图表 / 有数据卡片时版面被占掉一半，要点相应减半
MAX_BLOCKS_WITH_CHART = 4
MAX_BLOCKS_WITH_METRICS = 4
# 表格每页最多数据行（不含表头）
MAX_TABLE_ROWS_PER_SLIDE = 7
# 单条要点超过这个字数就先按标点拆成多条，避免长段落被 "…" 截断
SPLIT_BULLET_CHARS = 58

# 14pt 中文字符约占 0.194 inch 宽，留一点余量
_PT_PER_CN_CHAR = 14.0
_INCH_PER_CN_CHAR = _PT_PER_CN_CHAR / 72.0 * 1.03


def _wrap_line(s, per_line):
    """在不超过 per_line 的前提下尽量在标点后断，返回 (本行, 剩余)"""
    s = str(s or "")
    if len(s) <= per_line:
        return s, ""
    window = s[:per_line]
    lo = max(int(per_line * 0.55), 0)
    for i in range(len(window) - 1, lo, -1):
        if window[i] in _BREAK_CHARS:
            return window[: i + 1], s[i + 1:]
    return window, s[per_line:]


def _fit_per_line(col_w):
    """按栏宽反推每行能放多少个中文字，再受 MAX_CHARS_PER_LINE 封顶"""
    usable = max(col_w - 0.62, 1.0)     # 减去卡片内左边距和色条占位
    est = int(usable / _INCH_PER_CN_CHAR)
    return max(min(est, MAX_CHARS_PER_LINE), 10)


def _split_bullets(bullets, max_chars=SPLIT_BULLET_CHARS):
    """把超长段落拆成多条要点（豆包要求：长段落拆分，而不是截断丢弃）

    拆分顺序：句末标点（。；！？）→ 逗号顿号 → 兜底按字数硬切。
    "**标题**：说明" 结构只在第一条保留标题，后续条继承语境。
    """
    out = []
    for b in bullets or []:
        txt = re.sub(r"\s+", " ", str(b)).strip()
        if not txt:
            continue
        if len(txt) <= max_chars:
            out.append(txt)
            continue
        m = re.match(r"^\*\*(.+?)\*\*[：:]\s*(.*)$", txt)
        head = (m.group(1) or "").strip() if m else ""
        body = (m.group(2) or "").strip() if m else txt

        parts = [p for p in re.split(r"(?<=[。；;！？!?])", body) if p.strip()]
        if len(parts) == 1:
            parts = [p for p in re.split(r"(?<=[，,、])", body) if p.strip()]
        if len(parts) == 1:
            parts = [body[i:i + max_chars] for i in range(0, len(body), max_chars)]

        chunks, cur = [], ""
        for p in parts:
            p = p.strip()
            if cur and len(cur) + len(p) > max_chars:
                chunks.append(cur)
                cur = p
            else:
                cur = (cur + p).strip()
        if cur:
            chunks.append(cur)

        for i, c in enumerate(chunks):
            out.append("**%s**：%s" % (head, c) if (i == 0 and head) else c)
    return out


def _chunk(seq, size):
    """按 size 切片；空列表也返回一页，保证至少渲染一页"""
    if not seq:
        return [[]]
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _rgb(hexstr):
    return RGBColor.from_string(hexstr)


def _set_run_font(run, size, color, bold=False, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    # 设置中文（east-asian）字体，否则中文回退宋体
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        latin = rPr.find(qn("a:latin"))
        ea = rPr.makeelement(qn("a:ea"), {})
        if latin is not None:
            latin.addnext(ea)
        else:
            rPr.append(ea)
    ea.set("typeface", name)


def _add_box(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return tb, tf


def _add_rect(slide, x, y, w, h, color, round_=False, alpha=None, line=None, line_w=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE
    sp = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if round_:
        try:
            sp.adjustments[0] = 0.08
        except Exception:
            pass
    if color is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = _rgb(color)
        if alpha is not None:
            # 透明度：往 srgbClr 里塞 alpha 子元素（OOXML 单位是千分比百分比：100000=100%）
            srgb = sp.fill.fore_color._xFill.find(".//" + qn("a:srgbClr"))
            if srgb is not None:
                a = srgb.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
                srgb.append(a)
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = _rgb(line)
        sp.line.width = Pt(line_w or 1)
    sp.shadow.inherit = False
    return sp


def _gradient_cover(slide):
    """整页渐变背景（深蓝）"""
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                                Inches(SLIDE_W), Inches(SLIDE_H))
    bg.line.fill.background()
    bg.shadow.inherit = False
    spPr = bg._element.spPr
    old = spPr.find(qn("a:solidFill"))
    if old is not None:
        spPr.remove(old)
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls
    grad = parse_xml(
        '<a:gradFill %s rotWithShape="1">'
        '<a:gsLst>'
        '<a:gs pos="0"><a:srgbClr val="%s"/></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="%s"/></a:gs>'
        '</a:gsLst>'
        '<a:lin ang="2700000" scaled="0"/>'
        '</a:gradFill>' % (nsdecls("a"), DEEP, DEEP2))
    ln = spPr.find(qn("a:ln"))
    if ln is not None:
        spPr.insert(list(spPr).index(ln), grad)
    else:
        spPr.append(grad)
    return bg


def _clean(slide):
    """去掉默认占位符"""
    for ph in list(slide.placeholders):
        ph._element.getparent().remove(ph._element)


def _footer(slide, project, page_no):
    tb, tf = _add_box(slide, 0.7, SLIDE_H - 0.5, 7, 0.3)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = project
    _set_run_font(r, 10, MUTED)
    tb2, tf2 = _add_box(slide, SLIDE_W - 1.4, SLIDE_H - 0.5, 0.9, 0.3)
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.RIGHT
    r2 = p2.add_run()
    r2.text = str(page_no)
    _set_run_font(r2, 10, MUTED)


def _page_header(slide, title, kicker=None, accent=PRIMARY):
    """内容页统一页眉：渐变顶条 + 章节色 kicker + 标题 + 短下划线 + 右上几何装饰"""
    top = _add_rect(slide, 0, 0, SLIDE_W, 0.11, accent)
    _grad(top, accent, _lighten(accent, 0.45), 0)   # 横向渐变，顶条不再是死板纯色
    # 右上角两个低透明度装饰块，打破方版面的呆板
    d1 = _add_rect(slide, SLIDE_W - 1.15, 0.14, 0.5, 0.5, accent, round_=True)
    _set_alpha(d1, 0.28)
    d2 = _add_rect(slide, SLIDE_W - 0.62, 0.22, 0.28, 0.28, accent, round_=True)
    _set_alpha(d2, 0.18)
    y = 0.55
    if kicker:
        tb, tf = _add_box(slide, 0.72, 0.42, 11.5, 0.35)
        r = tf.paragraphs[0].add_run()
        r.text = kicker
        _set_run_font(r, 12.5, accent, bold=True)
        y = 0.85
    tb, tf = _add_box(slide, 0.72, y, 11.9, 0.75)
    r = tf.paragraphs[0].add_run()
    r.text = title
    _set_run_font(r, 27, INK, bold=True)
    _add_rect(slide, 0.74, y + 0.82, 1.15, 0.055, accent)


def _bullets_body(slide, bullets, top=2.15, left=0.72, width=11.9,
                  per_col=None, max_blocks=None, accent=PRIMARY):
    bullets = [b for b in (bullets or []) if str(b).strip()]
    if max_blocks:
        bullets = bullets[:max_blocks]
    # 窄栏（左文右图版式）不再强行分两栏：5.3in 分两栏后每行只剩 10 个字，
    # 内容全被 "…" 吃掉。宽度不足 7in 时一律单栏。
    # 另外：起点越靠下可用高度越小，单栏排不下就自动切双栏，避免压到页脚。
    avail_h = 6.85 - top
    need_single = len(bullets) * 0.92
    two_col = ((per_col is not None or len(bullets) > 4 or need_single > avail_h)
               and width >= 7.0)
    if two_col and per_col is None:
        per_col = math_ceil(len(bullets) / 2)
    if two_col:
        per_col = max(per_col or 1, 1)
        col_w = (width - 0.6) / 2
        cols = [bullets[:per_col], bullets[per_col:]]
    else:
        col_w = width
        cols = [bullets]
    per_line = _fit_per_line(col_w)
    row_h = 0.92 if not two_col else 1.05
    if V.get("body") == "minimal":
        row_h = 0.86 if not two_col else 0.96
    elif V.get("body") == "numbered":
        row_h = 0.95 if not two_col else 1.08
    for ci, col in enumerate(cols):
        x = left + ci * (col_w + 0.6)
        for bi, b in enumerate(col):
            y = top + bi * row_h
            txt = re.sub(r"\s+", " ", str(b)).strip()
            # 支持和 "**标题**：说明" 的结构
            m = re.match(r"^\*\*(.+?)\*\*[：:]\s*(.*)$", txt)
            # 卡片左侧竖条按条目轮换色彩，同一页内也有色彩节奏
            bar_color = CHAPTER[(bi + ci * per_col if two_col else bi) % len(CHAPTER)]
            style = V.get("body")
            if style == "cards":
                card = _add_rect(slide, x, y, col_w, row_h - 0.16, CARD, round_=True)
                card.line.fill.background()
                _add_rect(slide, x + 0.18, y + row_h / 2 - 0.155, 0.075, 0.31, bar_color, round_=True)
                tx, tw = x + 0.45, col_w - 0.62
            elif style == "minimal":
                # 极简：无卡片，左侧圆点 + 底部细分割线
                dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.12),
                                             Inches(y + row_h / 2 - 0.09), Inches(0.17), Inches(0.17))
                dot.fill.solid(); dot.fill.fore_color.rgb = _rgb(bar_color)
                dot.line.fill.background(); dot.shadow.inherit = False
                if bi < len(col) - 1:
                    line = _add_rect(slide, x + 0.38, y + row_h - 0.06, col_w - 0.4, 0.012, None)
                    line.fill.solid(); line.fill.fore_color.rgb = _rgb(_lighten(bar_color, 0.78))
                    line.line.fill.background()
                tx, tw = x + 0.42, col_w - 0.55
            else:
                # numbered：大号序号方块
                box = _add_rect(slide, x + 0.1, y + 0.1, 0.62, row_h - 0.32, bar_color, round_=True)
                tb_n, tf_n = _add_box(slide, x + 0.1, y + 0.1, 0.62, row_h - 0.32)
                tf_n.vertical_anchor = MSO_ANCHOR.MIDDLE
                pn = tf_n.paragraphs[0]; pn.alignment = PP_ALIGN.CENTER
                rn = pn.add_run(); rn.text = "%02d" % (bi + 1 + (ci * per_col if two_col else 0))
                _set_run_font(rn, 15, WHITE, bold=True)
                tx, tw = x + 0.86, col_w - 0.98
            tb, tf = _add_box(slide, tx, y + 0.09, tw, row_h - 0.2)
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE

            head = (m.group(1) or "").strip() if m else ""
            body = (m.group(2) or "").strip() if m else txt

            # 逐行排布：第一行让标题和正文共用，其余行放正文剩余部分
            lines = []
            rest = body
            first = True
            for _ in range(MAX_LINES_PER_BULLET):
                room = per_line - (len(head) + 2) if (first and head) else per_line
                seg, rest = _wrap_line(rest, max(room, 8))
                lines.append((head if first else "", seg))
                head = ""
                first = False
                if not rest:
                    break
            if rest and lines:                       # 还有没排下的内容，末尾补省略号
                h, s = lines[-1]
                lines[-1] = (h, s.rstrip() + "…")

            for li, (pfx, seg) in enumerate(lines):
                if not (pfx or seg):
                    continue
                p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
                p.space_after = Pt(1)
                p.line_spacing = 1.05
                if pfx:
                    r1 = p.add_run(); r1.text = pfx + "  "
                    _set_run_font(r1, 14.5, bar_color, bold=True)
                if seg:
                    r = p.add_run(); r.text = seg
                    _set_run_font(r, 13.5 if pfx else 14, BODY)


def _chart_body(slide, bullets, image_path, accent=PRIMARY):
    """左文右图。要点区 5.3in 单栏，图片等比缩到 6.2×4.5in 内居中。"""
    _bullets_body(slide, bullets, top=2.2, left=0.72, width=5.3,
                  max_blocks=MAX_BLOCKS_WITH_CHART, accent=accent)
    if not (image_path and os.path.exists(image_path)):
        return
    BX, BY, BW, BH = 6.35, 2.0, 6.2, 4.5
    # 图底下垫一层极淡的章节色块，让图片和页面底色有层次
    pad = _add_rect(slide, BX - 0.12, BY - 0.12, BW + 0.24, BH + 0.24,
                    _lighten(accent, 0.9), round_=True)
    pad.line.color.rgb = _rgb(_lighten(accent, 0.7))
    pad.line.width = Pt(1)
    pic = slide.shapes.add_picture(image_path, Inches(BX), Inches(BY),
                                   width=Inches(BW))
    if pic.height > Inches(BH):                      # 太高就等比压回框内
        ratio = float(Inches(BH)) / float(pic.height)
        pic.height = Inches(BH)
        pic.width = Emu(int(pic.width * ratio))
    pic.left = Inches(BX + (BW - pic.width / 914400.0) / 2)
    pic.top = Inches(BY + (BH - pic.height / 914400.0) / 2)


def _table_body(slide, table, accent=PRIMARY):
    header = table.get("header", [])
    rows = table.get("rows", [])
    n_rows = min(len(rows) + 1, 9)
    n_cols = min(len(header), 7)          # 列数上限放宽到 7，宽表不再被砍列
    if not header or not rows:
        return
    left, top = 0.72, 2.1
    width = 11.9
    row_h = min(0.62, 4.4 / n_rows)
    gt = slide.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top),
                                Inches(width), Inches(row_h * n_rows)).table
    # 列宽：第一列稍宽
    first = width * (0.34 if n_cols <= 3 else 0.24)
    rest = (width - first) / (n_cols - 1) if n_cols > 1 else 0
    gt.columns[0].width = Inches(first)
    for ci in range(1, n_cols):
        gt.columns[ci].width = Inches(rest)
    # 表头：先看 WithBlocks 是否为纯色（powerpoint 表格 cell 不支持渐变 XML hack 的风险较高，
    # 改用"章节色 + 逐列递深"的做法制造层次
    for ci, htext in enumerate(header[:n_cols]):
        cell = gt.cell(0, ci)
        cell.fill.solid()
        shade = accent if ci == 0 else _darken(accent, ci * 0.06)
        cell.fill.fore_color.rgb = _rgb(shade)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = str(htext)
        _set_run_font(r, 13 if n_cols <= 6 else 11, WHITE, bold=True)
    softener = _lighten(accent, 0.93)
    for ri, row in enumerate(rows[:n_rows - 1]):
        for ci in range(n_cols):
            cell = gt.cell(ri + 1, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(softener if ri % 2 == 0 else WHITE)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            val = str(row[ci]) if ci < len(row) else ""
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if ci > 0 else PP_ALIGN.LEFT
            r = p.add_run(); r.text = val
            _set_run_font(r, 12 if n_cols <= 6 else 10.5, BODY, bold=(ci == 0))


def _metrics_body(slide, metrics, top=2.35, height=2.5, accent=PRIMARY):
    """2-4 个数据卡片：每张卡取色轮中不同颜色做渐变底，数字用白字"""
    metrics = [m for m in (metrics or []) if str(m).strip()][:4]
    n = len(metrics)
    if n == 0:
        return
    gap = 0.45
    card_w = (11.9 - gap * (n - 1)) / n
    num_size = 34 if height >= 2.0 else 28
    for i, m in enumerate(metrics):
        m = str(m)
        num, label = m, ""
        # 单位放宽到 人/家/台/项/次 等：申报书里挖出来的数字带这些单位时，
        # 不会整串被当成"大号数字"排版（原来只认 %万亿倍年个天元周亿）
        mm = re.match(r"^\s*([\d.]+\s*[%万亿倍年个天元周亿人家台套项次所校]?)\s*[：:、\s]\s*(.+)$", m)
        if mm:
            num, label = mm.group(1).strip(), mm.group(2).strip()
        x = 0.72 + i * (card_w + gap)
        c1 = CHAPTER[i % len(CHAPTER)]
        card = _add_rect(slide, x, top, card_w, height, c1, round_=True)
        _grad(card, c1, _darken(c1, 0.28), 5400000)
        card.line.fill.background()
        tb, tf = _add_box(slide, x + 0.2, top + height * 0.16,
                          card_w - 0.4, height * 0.36)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = num
        _set_run_font(r, num_size, WHITE, bold=True)
        tb2, tf2 = _add_box(slide, x + 0.25, top + height * 0.55,
                            card_w - 0.5, height * 0.36)
        p2 = tf2.paragraphs[0]; p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run(); r2.text = label or m
        _set_run_font(r2, 13.5 if height >= 2.0 else 12, WHITE)


def _add_notes(slide, text):
    """把 LLM 给的 note 写进 PPT 备注栏（演示时双击可见）"""
    if not text:
        return
    try:
        tf = slide.notes_slide.notes_text_frame
        tf.text = str(text)[:500]
    except Exception:
        pass


def math_ceil(x):
    import math as _m
    return _m.ceil(x)


# ============ 各版式 ============
def _cover_gradient(slide, meta, s):
    """v1 流光：整页渐变 + 三色装饰圆 + 三段式彩色竖条"""
    _bg_grad(slide, DEEP, DEEP2, 3150000)
    for (cx, cy, cw, ch, col, al) in ((10.2, -1.5, 5.0, 5.0, COVER_DECO[0], 0.42),
                                      (11.8, 5.4, 3.4, 3.4, COVER_DECO[1], 0.38),
                                      (-1.4, 5.6, 3.0, 3.0, COVER_DECO[2], 0.30)):
        d = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx), Inches(cy), Inches(cw), Inches(ch))
        d.fill.solid(); d.fill.fore_color.rgb = _rgb(col)
        d.line.fill.background(); d.shadow.inherit = False
        _set_alpha(d, al)
    for i, col in enumerate(COVER_DECO):
        _add_rect(slide, 0.9, 2.02 + i * 0.78, 0.14, 0.62, col, round_=True)
    tb, tf = _add_box(slide, 1.35, 2.0, 10.3, 1.5)
    r = tf.paragraphs[0].add_run(); r.text = meta.get("project", "项目路演")
    _set_run_font(r, 40, WHITE, bold=True)
    if meta.get("one_liner"):
        tb2, tf2 = _add_box(slide, 1.37, 3.35, 10, 0.7)
        r2 = tf2.paragraphs[0].add_run(); r2.text = meta["one_liner"]
        _set_run_font(r2, 17, "A9B6E8")


def _cover_split(slide, meta, s):
    """v2 左色块：左侧 4.6in 渐变块放标题，右侧留白放定位（明暗对比更强）"""
    block = _add_rect(slide, 0, 0, 4.9, SLIDE_H, PRIMARY)
    _grad(block, DEEP, PRIMARY, 3150000)
    accent_bar = _add_rect(slide, 4.9, 0, 0.09, SLIDE_H, ACCENT)
    tb, tf = _add_box(slide, 0.75, 2.55, 3.9, 2.2)
    r = tf.paragraphs[0].add_run(); r.text = meta.get("project", "项目路演")
    _set_run_font(r, 34, WHITE, bold=True)
    _add_rect(slide, 0.75, 4.5, 1.1, 0.06, WHITE)
    tb2, tf2 = _add_box(slide, 5.6, 2.75, 7.0, 1.6)
    r2 = tf2.paragraphs[0].add_run(); r2.text = meta.get("one_liner", "")
    _set_run_font(r2, 20, INK)
    comp = meta.get("competition") or "科创赛事路演"
    tb3, tf3 = _add_box(slide, 5.6, 4.35, 7.0, 0.6)
    r3 = tf3.paragraphs[0].add_run()
    r3.text = f"{comp} · {datetime.now().strftime('%Y-%m')}"
    _set_run_font(r3, 13, MUTED)
    for i, col in enumerate(COVER_DECO[:2]):
        d = _add_rect(slide, 10.4 + i * 0.85, 5.75, 0.62, 0.62, col, round_=True)
        _set_alpha(d, 0.55)


def _cover_band(slide, meta, s):
    """v3 顶部粗色带：白底提案感，标题压在色带上"""
    band = _add_rect(slide, 0, 0, SLIDE_W, 2.85, PRIMARY)
    _grad(band, DEEP, PRIMARY, 0)
    stripe = _add_rect(slide, 0, 2.85, SLIDE_W, 0.075, ACCENT)
    tb, tf = _add_box(slide, 0.9, 0.85, 11.5, 1.4)
    r = tf.paragraphs[0].add_run(); r.text = meta.get("project", "项目路演")
    _set_run_font(r, 38, WHITE, bold=True)
    if meta.get("one_liner"):
        tb2, tf2 = _add_box(slide, 0.9, 3.5, 11.0, 1.1)
        r2 = tf2.paragraphs[0].add_run(); r2.text = meta["one_liner"]
        _set_run_font(r2, 19, INK)
    comp = meta.get("competition") or "科创赛事路演"
    tb3, tf3 = _add_box(slide, 0.9, 4.75, 8.0, 0.6)
    r3 = tf3.paragraphs[0].add_run()
    r3.text = f"{comp} · {datetime.now().strftime('%Y-%m')}"
    _set_run_font(r3, 13, MUTED)
    for i, col in enumerate(COVER_DECO):
        d = _add_rect(slide, 9.3 + i * 1.3, 5.5, 0.95, 0.95, col, round_=True)
        _set_alpha(d, 0.5)


def _cover_center(slide, meta, s):
    """v4 居中留白：对称构图，标题居中，上下细线夹住"""
    _bg_grad(slide, DEEP, DEEP2, 2700000)
    _add_rect(slide, 3.4, 1.95, 6.5, 0.03, WHITE)
    tb, tf = _add_box(slide, 1.6, 2.45, 10.1, 1.6)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = meta.get("project", "项目路演")
    _set_run_font(r, 42, WHITE, bold=True)
    if meta.get("one_liner"):
        tb2, tf2 = _add_box(slide, 2.2, 4.15, 8.9, 0.8)
        p2 = tf2.paragraphs[0]; p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run(); r2.text = meta["one_liner"]
        _set_run_font(r2, 17, "C6CFEF")
    _add_rect(slide, 5.2, 5.15, 2.9, 0.03, WHITE)
    comp = meta.get("competition") or "科创赛事路演"
    tb3, tf3 = _add_box(slide, 1.6, 5.5, 10.1, 0.6)
    p3 = tf3.paragraphs[0]; p3.alignment = PP_ALIGN.CENTER
    r3 = p3.add_run(); r3.text = f"{comp} · {datetime.now().strftime('%Y-%m')}"
    _set_run_font(r3, 13, "8F9DD4")


_COVERS = {"gradient": _cover_gradient, "split": _cover_split,
           "band": _cover_band, "center": _cover_center}


def _slide_cover(prs, s, meta):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    _COVERS.get(V.get("cover"), _cover_gradient)(slide, meta, s)
    # 封面底部信息（split/band 版式已在各自函数里画过，避免重复）
    if V.get("cover") in ("gradient", "center"):
        tb3, tf3 = _add_box(slide, 1.37 if V.get("cover") == "gradient" else 1.6,
                            6.35, 10, 0.5)
        comp = meta.get("competition") or "科创赛事路演"
        r3 = tf3.paragraphs[0].add_run()
        r3.text = f"{comp} · {datetime.now().strftime('%Y-%m')}"
        _set_run_font(r3, 13, "7C88C0")
    if s.get("note"):
        _add_notes(slide, s.get("note"))
    return slide


def _set_alpha(shape, alpha):
    srgb = shape.fill.fore_color._xFill.find(".//" + qn("a:srgbClr"))
    if srgb is not None:
        a = srgb.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
        srgb.append(a)


def _set_alpha_text(run, alpha):
    """给文字填充加透明度（用于衬底大数字）"""
    try:
        rPr = run._r.get_or_add_rPr()
        sf = rPr.find(qn("a:solidFill"))
        if sf is None:
            return
        c = sf.find(qn("a:srgbClr"))
        if c is None:
            return
        a = c.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
        c.append(a)
    except Exception:
        pass


def _grad(shape, c1, c2, angle=2700000):
    """给任意 shape 应用双色线性渐变（python-pptx 原生不支持，走 XML）"""
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls
    spPr = shape._element.spPr
    if spPr.find(qn("a:gradFill")) is not None:
        return shape
    try:
        shape.fill.solid()
        old = spPr.find(qn("a:solidFill"))
        if old is not None:
            spPr.remove(old)
    except Exception:
        pass
    grad = parse_xml(
        '<a:gradFill %s rotWithShape="1">'
        '<a:gsLst>'
        '<a:gs pos="0"><a:srgbClr val="%s"/></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="%s"/></a:gs>'
        '</a:gsLst>'
        '<a:lin ang="%d" scaled="0"/>'
        '</a:gradFill>' % (nsdecls("a"), c1, c2, int(angle)))
    ln = spPr.find(qn("a:ln"))
    if ln is not None:
        spPr.insert(list(spPr).index(ln), grad)
    else:
        spPr.append(grad)
    return shape


def _bg_grad(slide, c1, c2, angle=2700000):
    """整页渐变背景"""
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                                Inches(SLIDE_W), Inches(SLIDE_H))
    bg.line.fill.background()
    bg.shadow.inherit = False
    return _grad(bg, c1, c2, angle)


def _slide_section(prs, s, meta, page_no, idx=0):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    # 每个章节一种颜色：不再全篇同一个深蓝
    color = _chapter_color(s.get("num") or s.get("kicker"), idx)
    num = str(s.get("num", "")).zfill(2) or "01"
    if V.get("section") == "light":
        # 浅色章节页：白底 + 巨大浅灰数字 + 深色标题（像杂志分隔页）
        panel = _add_rect(slide, 8.6, 0, SLIDE_W - 8.6, SLIDE_H, _lighten(color, 0.82))
        panel.line.fill.background()
        tb, tf = _add_box(slide, 0.95, 1.75, 5.0, 2.6)
        r = tf.paragraphs[0].add_run(); r.text = num
        _set_run_font(r, 96, _lighten(color, 0.55), bold=True)
        tb2, tf2 = _add_box(slide, 3.5, 3.15, 5.2, 1.2)
        r2 = tf2.paragraphs[0].add_run(); r2.text = s.get("title", "")
        _set_run_font(r2, 32, INK, bold=True)
        _add_rect(slide, 3.56, 4.25, 1.3, 0.06, color)
    else:
        _bg_grad(slide, _darken(color, 0.45), _darken(color, 0.12), 3150000)
        deco = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.6), Inches(1.2),
                                      Inches(5.6), Inches(5.6))
        deco.fill.solid(); deco.fill.fore_color.rgb = _rgb(WHITE)
        deco.line.fill.background(); deco.shadow.inherit = False
        _set_alpha(deco, 0.10)
        tb, tf = _add_box(slide, 0.95, 1.9, 4.2, 2.4)
        r = tf.paragraphs[0].add_run(); r.text = num
        _set_run_font(r, 88, "FFFFFF", bold=True)
        _set_alpha_text(r, 0.35)
        tb2, tf2 = _add_box(slide, 3.6, 3.05, 8.6, 1.2)
        r2 = tf2.paragraphs[0].add_run(); r2.text = s.get("title", "")
        _set_run_font(r2, 32, WHITE, bold=True)
        _add_rect(slide, 3.66, 4.15, 1.3, 0.06, SECTION_RULE)
    if s.get("bullets"):
        line_color = MUTED if V.get("section") == "light" else "A9B6E8"
        tb3, tf3 = _add_box(slide, 3.56 if V.get("section") == "light" else 3.66, 4.5, 8.4, 1.4)
        for line in s["bullets"][:3]:
            p = tf3.add_paragraph()
            rr = p.add_run(); rr.text = "— " + str(line)
            _set_run_font(rr, 14, line_color)
    _add_notes(slide, s.get("note"))
    return slide
    if s.get("bullets"):
        tb3, tf3 = _add_box(slide, 3.66, 4.5, 8.4, 1.4)
        for line in s["bullets"][:3]:
            p = tf3.add_paragraph()
            rr = p.add_run(); rr.text = "— " + str(line)
            _set_run_font(rr, 14, "A9B6E8")
    return slide


def _slide_bullets(prs, s, meta, page_no, chart_path=None, cont=False, idx=0):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    title = s.get("title", "")
    if cont:
        title = "%s（续）" % title
    accent = _chapter_color(s.get("kicker"), idx)
    _page_header(slide, title, s.get("kicker"), accent)
    metrics = s.get("metrics") or []
    bullets = s.get("bullets", [])
    if chart_path:
        _chart_body(slide, bullets, chart_path, accent)
        if metrics:                                  # 图右、要点左，指标压到页脚上方
            _metrics_body(slide, metrics, top=5.15, height=1.6)
    elif metrics:
        _metrics_body(slide, metrics, top=2.05, height=1.9)   # 上半屏
        _bullets_body(slide, bullets, top=4.15,                # 下半屏，不再重叠
                      max_blocks=MAX_BLOCKS_WITH_METRICS, accent=accent)
    else:
        _bullets_body(slide, bullets, max_blocks=MAX_BLOCKS_PER_SLIDE, accent=accent)
    _footer(slide, meta.get("project", ""), page_no)
    return slide


def _slide_table(prs, s, meta, page_no, cont=False, idx=0):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    title = s.get("title", "")
    if cont:
        title = "%s（续）" % title
    accent = _chapter_color(s.get("kicker"), idx)
    _page_header(slide, title, s.get("kicker"), accent)
    _table_body(slide, s.get("table") or {}, accent)
    if s.get("note"):
        tb, tf = _add_box(slide, 0.72, 6.55, 11.9, 0.5)
        r = tf.paragraphs[0].add_run(); r.text = str(s["note"])
        _set_run_font(r, 11.5, MUTED)
    _footer(slide, meta.get("project", ""), page_no)
    return slide


def _slide_metrics(prs, s, meta, page_no, idx=0):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    accent = _chapter_color(s.get("kicker"), idx)
    _page_header(slide, s.get("title", ""), s.get("kicker"), accent)
    _metrics_body(slide, s.get("metrics", []), top=2.15, height=2.35)
    if s.get("bullets"):
        _bullets_body(slide, s["bullets"], top=4.75,
                      max_blocks=MAX_BLOCKS_WITH_METRICS, accent=accent)
    _footer(slide, meta.get("project", ""), page_no)
    return slide


def _slide_closing(prs, s, meta, page_no):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _clean(slide)
    _bg_grad(slide, "141C4A", "4A2170", 2700000)
    d1 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(-1.6), Inches(-1.2),
                                Inches(4.4), Inches(4.4))
    d1.fill.solid(); d1.fill.fore_color.rgb = _rgb("22B8CF")
    d1.line.fill.background(); d1.shadow.inherit = False
    _set_alpha(d1, 0.25)
    d2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10.6), Inches(4.9),
                                Inches(4.6), Inches(4.6))
    d2.fill.solid(); d2.fill.fore_color.rgb = _rgb("DB3F72")
    d2.line.fill.background(); d2.shadow.inherit = False
    _set_alpha(d2, 0.28)
    tb, tf = _add_box(slide, 1.2, 2.6, 11, 1.4)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = s.get("title", "谢谢聆听")
    _set_run_font(r, 44, WHITE, bold=True)
    if s.get("bullets"):
        tb2, tf2 = _add_box(slide, 1.7, 4.15, 10, 1.2)
        for b in s["bullets"][:2]:
            p2 = tf2.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run(); r2.text = str(b)
            _set_run_font(r2, 15, "A9B6E8")
    tb3, tf3 = _add_box(slide, 1.2, 5.9, 11, 0.6)
    p3 = tf3.paragraphs[0]; p3.alignment = PP_ALIGN.CENTER
    r3 = p3.add_run(); r3.text = meta.get("one_liner") or meta.get("project", "")
    _set_run_font(r3, 13, "7C88C0")
    return slide


# ============ 主入口 ============
def build_deck(deck, out_path, chart_paths=None):
    """chart_paths: {chart_id: png路径}
    deck 可选 theme（主题 key）与 variant（模板 key v1-v4），不传则用默认。"""
    chart_paths = chart_paths or {}
    # 关键：把主题/模板真正应用到本次渲染（不接这两行，传了 theme 也不会生效）
    _apply_theme(deck.get("theme"))
    _apply_variant(deck.get("variant"))
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    meta = {
        "project": deck.get("project", "科创项目"),
        "one_liner": deck.get("one_liner", ""),
        "competition": deck.get("competition", ""),
    }
    page = 1
    for i, s in enumerate(deck.get("slides", [])):
        stype = str(s.get("type", "bullets")).lower()
        if stype in ("cover", "title"):
            _slide_cover(prs, s, meta)
            page += 1
        elif stype == "section":
            _slide_section(prs, s, meta, page, i)
            page += 1
        elif stype == "table":
            page = _emit_table(prs, s, meta, page, i)
        elif stype == "metrics":
            if s.get("bullets"):
                sub = dict(s)
                sub["bullets"] = _split_bullets(s["bullets"])
                _slide_metrics(prs, sub, meta, page, i)
            else:
                _slide_metrics(prs, s, meta, page, i)
            page += 1
        elif stype in ("closing", "thanks", "end"):
            _slide_closing(prs, s, meta, page)
            page += 1
        else:
            page = _emit_bullets(prs, s, meta, page, chart_paths, i)
    prs.save(out_path)
    return out_path


def _emit_bullets(prs, s, meta, page, chart_paths, idx=0):
    """要点页自动分页：先拆长段落，再按每页容量切片，超出生成"（续）"页"""
    cpath = chart_paths.get(s.get("chart")) if s.get("chart") else None
    metrics = s.get("metrics") or []
    blocks = _split_bullets(s.get("bullets", []))
    # 首页要放图表或指标卡，容量减半；续页是干净版面，按满容量排
    if cpath or metrics:
        cap0 = MAX_BLOCKS_WITH_CHART if cpath else MAX_BLOCKS_WITH_METRICS
        head, tail = blocks[:cap0], blocks[cap0:]
        chunks = [head] + (_chunk(tail, MAX_BLOCKS_PER_SLIDE) if tail else [])
    else:
        chunks = _chunk(blocks, MAX_BLOCKS_PER_SLIDE)
    if not chunks:
        chunks = [[]]
    for pi, chunk in enumerate(chunks):
        sub = dict(s)
        sub["bullets"] = chunk
        sub["metrics"] = metrics if pi == 0 else []   # 指标只在首页出现
        _slide_bullets(prs, sub, meta, page,
                       cpath if pi == 0 else None, cont=(pi > 0), idx=idx)
        page += 1
    return page


def _emit_table(prs, s, meta, page, idx=0):
    """表格页自动分页：每页 MAX_TABLE_ROWS_PER_SLIDE 行，表头每页重复"""
    t = s.get("table") or {}
    header, rows = t.get("header") or [], t.get("rows") or []
    if not header or not rows:
        _slide_table(prs, s, meta, page, idx=idx)
        return page + 1
    for pi, chunk in enumerate(_chunk(rows, MAX_TABLE_ROWS_PER_SLIDE)):
        sub = dict(s)
        sub["table"] = {"header": header, "rows": chunk}
        _slide_table(prs, sub, meta, page, cont=(pi > 0), idx=idx)
        page += 1
    return page


if __name__ == "__main__":
    deck = {
        "project": "护途 CareWay",
        "one_liner": "让每一次住院都有人管、有据可依",
        "competition": "iCAN 大学生创新创业大赛",
        "slides": [
            {"type": "cover", "title": "护途 CareWay"},
            {"type": "bullets", "kicker": "01 / 痛点", "title": "住院陪护市场痛点",
             "bullets": ["**找护工难**：靠熟人介绍，质量无从考证",
                         "**价格不透明**：同类服务差价可达 2 倍",
                         "**纠纷难界定**：出了问题责任说不清"],
             "metrics": ["4.5亿：全国年住院人次", "60%：家属请假陪护比例", "38%：护工无培训上岗"]},
            {"type": "table", "kicker": "02 / 竞品", "title": "竞品对比",
             "table": {"header": ["维度", "我们", "传统中介", "平台A"],
                       "rows": [["资质审核", "三重背调", "无", "证件拍照"],
                                ["价格", "平台统一定价", "口头议价", "抽成20%"]]}},
            {"type": "section", "num": "3", "title": "商业模式",
             "bullets": ["抽佣 + 会员 + 保险分成"]},
            {"type": "bullets", "title": "市场规模", "chart": "demo",
             "bullets": ["目标市场 120 亿", "首年渗透 0.5%"]},
            {"type": "closing", "title": "谢谢聆听", "bullets": ["欢迎评委指导"]},
        ],
    }
    build_deck(deck, "_ppt_test.pptx", chart_paths={"demo": "_chart_test/demo.png"})
    print("ok")
