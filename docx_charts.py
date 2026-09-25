# -*- coding: utf-8 -*-
"""申报书 Word 自动插图（深度版专用）。

职责：把 rich_pipeline 生成的 AI 图表 PNG，按语义插到申报书对应章节末尾。
刻意做成独立模块、不碰 docx_render.py —— 排版层已验收，本模块只做「插入」这一件事，
走 python-docx 在 build_docx() 产出的 Document 上做后处理。

用法：
    from docx_render import build_docx
    from docx_charts import inject_charts
    doc = build_docx(title, text, doc_type='default', ...)
    inject_charts(doc, charts)          # charts 来自 result["rich_charts"]
"""
import os
import re

from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

GEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generated')

# 每张图 → 目标章节的语义匹配表
# 结构：(图表侧关键字, 章节侧关键字)
# 匹配时取「图表侧命中数 × 章节侧命中数」，得分最高者胜出；全 0 分则落到文末附录。
_ANCHORS = [
    (('预算', '成本', '经费', '资金', '投入', '收入', '盈利', '收费', '单价',
      '毛利', '成本结构', '费用'),
     ('商业模式', '市场空间', '经费', '预算', '财务')),
    (('市场', '规模', '增长', '用户量', '渗透', '赛道', '份额', '趋势',
      '预测', '需求'),
     ('商业模式', '市场空间', '市场', '前景', '背景')),
    (('时间', '里程碑', '进度', '计划', '路线', '阶段', '周期', '排期',
      '季度', '年度', '节点'),
     ('执行计划', '实施', '里程碑', '计划', '进度')),
    (('技术', '架构', '准确率', '性能', '算法', '识别率', '响应', '延迟',
      '召回', '精度', '系统', '模块'),
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


def _norm(s):
    """去掉章节编号和空白，便于关键字匹配。"""
    s = re.sub(r'^[一二三四五六七八九十百]+[、.．]', '', str(s or '').strip())
    s = re.sub(r'^（[一二三四五六七八九十]+）', '', s)
    s = re.sub(r'^\d+(\.\d+)*[、.．]?', '', s)
    return s


def _is_heading(p):
    name = (p.style.name or '') if p.style is not None else ''
    return ('Heading' in name) or ('标题' in name) or name in ('1', '2', '3')


def _heading_level(p):
    m = re.search(r'(\d+)', (p.style.name or ''))
    return int(m.group(1)) if m else 1


def _chart_text(c):
    """图表侧用于匹配的文本：标题 + 题注 + 原始 spec 里的关键字段。"""
    parts = [c.get('title', ''), c.get('caption', '')]
    spec = c.get('spec') or {}
    parts.append(spec.get('type', ''))
    data = spec.get('data') or {}
    if isinstance(data, dict):
        for k in ('xAxis', 'x', 'categories', 'labels', 'names', 'name'):
            v = data.get(k)
            if isinstance(v, list):
                parts += [str(x) for x in v[:12]]
            elif v:
                parts.append(str(v))
        for s in (data.get('series') or []):
            if isinstance(s, dict) and s.get('name'):
                parts.append(str(s['name']))
    return ' '.join(str(x) for x in parts)


def _local_path(c):
    """chart.url 形如 /generated/chart_c1.png → 本地绝对路径。"""
    url = str(c.get('url') or '')
    name = os.path.basename(url)
    if not name:
        return ''
    p = os.path.join(GEN_DIR, name)
    return p if os.path.exists(p) else ''


def _sections(doc):
    """扫出章节区间：[(标题文本, 起始段落下标, 结束段落下标)]。"""
    paras = doc.paragraphs
    heads = [(i, _norm(p.text)) for i, p in enumerate(paras) if _is_heading(p) and p.text.strip()]
    if not heads:
        return []
    out = []
    for n, (i, title) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(paras)
        out.append((title, i, end))
    return out


def _pick_section(title, sections):
    """给一张图挑最合适的章节，返回下标；-1 表示没匹配上。"""
    best_i, best_score = -1, 0
    for si, (sec_title, _s, _e) in enumerate(sections):
        for chart_kw, sec_kw in _ANCHORS:
            c_hit = sum(1 for k in chart_kw if k in title)
            if not c_hit:
                continue
            s_hit = sum(1 for k in sec_kw if k in sec_title)
            if not s_hit:
                continue
            score = c_hit * s_hit
            if score > best_score:
                best_score, best_i = score, si
    return best_i


def _new_after(doc, anchor_p):
    """在 anchor_p 之后插入一个新段落（python-docx 没公开 insert_after，挪 XML 节点）。"""
    new_p = doc.add_paragraph()
    anchor_p._p.addnext(new_p._p)
    return new_p


def _add_image(doc, anchor_p, img_path, title, caption, width_in):
    p_img = _new_after(doc, anchor_p)
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(2)
    try:
        p_img.add_run().add_picture(img_path, width=Inches(width_in))
    except Exception:
        return anchor_p
    # 题注：「图1 xxx —— 一句话洞察」
    cap = '图：%s' % (title or '数据分析')
    if caption:
        cap += '　—— %s' % caption
    p_cap = _new_after(doc, p_img)
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_after = Pt(8)
    r = p_cap.add_run(cap)
    r.font.size = Pt(9)
    r.italic = True
    r.font.color.rgb = RGBColor(0x6b, 0x78, 0x99)
    return p_cap


def inject_charts(doc, charts, width_in=5.4, per_section=2):
    """把图表插进申报书对应章节末尾。

    :param doc:     build_docx() 产出的 python-docx Document
    :param charts:  [{"id","title","caption","url","spec"}, ...]
    :param width_in:    图片宽度（英寸），A4 版心约 6.5，5.4 留边距
    :param per_section: 同一章节最多插几张，防止堆砌
    :return: 实际插入的图数量
    """
    charts = charts or []
    if not charts:
        return 0

    usable = []
    for c in charts:
        p = _local_path(c)
        if p:
            usable.append((c, p))
    if not usable:
        return 0

    sections = _sections(doc)
    paras = doc.paragraphs

    # 先按语义分派，同章节超过 per_section 的挤到文末
    placed, fallback = [], []
    counts = {}
    for c, path in usable:
        title = _chart_text(c)
        si = _pick_section(title, sections) if sections else -1
        if si >= 0 and counts.get(si, 0) < per_section:
            counts[si] = counts.get(si, 0) + 1
            placed.append((si, c, path))
        else:
            fallback.append((c, path))
    placed.sort(key=lambda x: x[0])     # 按章节顺序插入，避免后面章节下标错位

    done = 0
    for si, c, path in placed:
        _s, _e = sections[si][1], sections[si][2]
        # 插到该章节最后一个非空段落之后（跳过表格之间等特殊情况）
        anchor_i = _e - 1
        while anchor_i > _s and not paras[anchor_i].text.strip():
            anchor_i -= 1
        anchor = paras[anchor_i]
        _add_image(doc, anchor, path, c.get('title', ''), c.get('caption', ''), width_in)
        done += 1

    if fallback:
        anchor = doc.paragraphs[-1] if doc.paragraphs else None
        if anchor is None:
            return done
        # 兜底区加个小标题
        p_t = _new_after(doc, anchor)
        p_t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p_t.add_run('附：项目数据分析图表')
        r.font.size = Pt(10.5)
        r.bold = True
        r.font.color.rgb = RGBColor(0x93, 0xa0, 0xc4)
        cur = p_t
        for c, path in fallback:
            cur = _add_image(doc, cur, path, c.get('title', ''), c.get('caption', ''), width_in)
            done += 1
    return done
