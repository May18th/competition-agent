# -*- coding: utf-8 -*-
"""
docx_inplace.py —— 「优化申报表」专用：保留原表格的一切格式排版，只替换文字。

【为什么单独一个模块】
用户的原则很清楚：
    申报表规则仅限于「创意生成」的文档；
    优化已有申报表时，**不改变原表格的格式和排版，只修改内容**。

所以这条链路绝对不能用 docx_render.py 重新渲染 —— 那会把用户原来的
表格结构、字体、合并单元格、页边距全部冲掉。这里做的是「原位换字」：
    - 段落样式、字体、字号、颜色、缩进：不动
    - 表格结构、列宽、合并单元格、边框底纹：不动
    - 页眉页脚、页码、页边距、目录域：不动
    - 只把 run 里的文字换成优化后的文字

【槽位收集】
按文档真实顺序遍历 body 里的 w:p 和 w:tbl，保证替换顺序和阅读顺序一致。
表格按「行优先」展开单元格，每个非空单元格算一个槽位。

【数量不匹配的处理】
优化后内容变多/变少是常态。策略：
    - 一一对应替换；
    - 优化文本有多余 → 追加到文档末尾（绝不丢内容）；
    - 优化文本不够 → 剩余槽位保持原文不动。
并返回一份报告，方便排查哪一段没对上。

用法：
    from docx_inplace import apply_content_keep_style
    buf, report = apply_content_keep_style(original_bytes, optimized_text)
"""
import io
import re

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# 需要剥掉的 Markdown 痕迹（优化文本里常见）
_RE_HEAD = re.compile(r'^#{1,6}\s*')
_RE_QUOTE = re.compile(r'^>\s*')
_RE_BULLET = re.compile(r'^[-*•·＋]\s*')
_RE_OL = re.compile(r'^\d+[.、)]\s*')
_RE_BOLD = re.compile(r'\*\*(.+?)\*\*')
_RE_CODE = re.compile(r'`([^`]+)`')
_RE_PIPE = re.compile(r'^\||\|$')


def _clean(line):
    """把一行优化文本洗成纯文字（不留 Markdown 符号）。"""
    s = line.strip()
    if not s:
        return ''
    s = _RE_HEAD.sub('', s)
    s = _RE_QUOTE.sub('', s)
    s = _RE_BULLET.sub('', s)
    s = _RE_OL.sub('', s)
    s = _RE_BOLD.sub(r'\1', s)
    s = _RE_CODE.sub(r'\1', s)
    s = _RE_PIPE.sub('', s)
    s = re.sub(r'\s*\|\s*', ' ', s)      # 表格行里的竖线转空格
    return s.strip()


def _set_text(container, text):
    """只换文字，保留第一个 run 的全部格式（字体/字号/颜色/加粗都不动）。"""
    runs = container.runs
    if not runs:
        container.add_run(text)          # 原段落没 run，只能新增（样式用默认）
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ''                      # 清掉多余 run 的文字，避免残留旧内容


def _collect_slots(doc):
    """按文档真实顺序收集可替换的文本槽位（段落 + 表格单元格）。"""
    slots = []
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            para = Paragraph(child, doc)
            if para.text.strip():
                slots.append(('para', para, para.text.strip()))
        elif child.tag == qn('w:tbl'):
            table = Table(child, doc)
            for row in table.rows:
                for cell in row.cells:
                    txt = cell.text.strip()
                    if not txt:
                        continue
                    # 取该单元格第一个非空段落来换字
                    target = None
                    for cp in cell.paragraphs:
                        if cp.text.strip():
                            target = cp
                            break
                    if target is None:
                        target = cell.paragraphs[0] if cell.paragraphs else None
                    if target is not None:
                        slots.append(('cell', target, txt))
    return slots


def apply_content_keep_style(original_bytes, optimized_text, append_extra=True):
    """在原文档上原地换字，格式排版一律不动。

    :param original_bytes: 原申报表的 .docx 二进制
    :param optimized_text: AI 优化后的文本（可含 Markdown）
    :param append_extra:   优化文本比原文长时，是否把多出来的追加到末尾（默认 True，绝不丢内容）
    :return: (BytesIO 新文档, dict 报告)
    """
    if hasattr(original_bytes, 'read'):
        original_bytes = original_bytes.read()
    doc = Document(io.BytesIO(original_bytes))

    slots = _collect_slots(doc)

    items = []
    for line in str(optimized_text or '').split('\n'):
        c = _clean(line)
        if c:
            items.append(c)

    replaced = 0
    n = min(len(items), len(slots))
    for i in range(n):
        _kind, target, _old = slots[i]
        _set_text(target, items[i])
        replaced += 1

    extra = items[n:]
    appended = 0
    if extra and append_extra:
        doc.add_page_break()
        hp = doc.add_paragraph()
        hp.add_run('补充内容')
        for t in extra:
            p = doc.add_paragraph()
            p.add_run(t)
            appended += 1

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    report = {
        'slots': len(slots),          # 原文档可替换位置数（段落+表格单元格）
        'items': len(items),          # 优化文本条目数
        'replaced': replaced,         # 实际替换数
        'appended': appended,         # 追加到末尾的条数
        'untouched': max(0, len(slots) - replaced),   # 保持原文没动的位置数
    }
    return buf, report
