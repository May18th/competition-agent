# -*- coding: utf-8 -*-
"""临时测试：导出 Word / PDF 的章节编号注入（docx_render + pdf_render）。

用「裸标题 + 已编号标题」混合的 markdown 走两条渲染链路，断言：
1. 裸 H2 按序拿到 一、二、…（中文数字）
2. 裸 H3 拿到 （一）（二）…，每进新 H2 章重新起算
3. 上游已有编号统一重排，不重复、不乱序
4. H1 不编号，H4 使用 1、2、3…
5. 生成真实 docx 读回 Heading 段落验证编号写进文档；生成 PDF 读回文本验证
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

from docx_render import _blocks, _number_heading_blocks, build_docx
import pdf_render
from pdf_render import (_media_norm, _number_headings, _pick_media_section,
                        _split_markdown_sections, render_markdown_to_pdf)

MD = """## 摘要

这是摘要内容，用来撑段落。

## 研究目的

正文段落。

### 子节甲

内容。

### 3.1 已编号小节

内容。

## 一、已编号章节

内容。

### 裸小节

内容。

## 项目背景与意义

内容。

#### 四级标题不编号

内容。

# 文档主标题

正文。

第一章 手写章标题

正文。

## 5G 创新应用

正文。
"""


def check(cond, msg):
    if not cond:
        print('FAIL: %s' % msg)
        sys.exit(1)
    print('PASS: %s' % msg)


# ---------- 1. docx 链路：blocks 级断言 ----------
blocks = _number_heading_blocks(_blocks(MD))
heads = [(b[1], b[2]) for b in blocks if b[0] == 'h']
print('---- docx blocks 标题序列 ----')
for lvl, t in heads:
    print('  H%d  %s' % (lvl, t))

expect = [
    (2, '一、摘要'),
    (2, '二、研究目的'),
    (3, '（一）子节甲'),
    (3, '（二）已编号小节'),       # 已编号 → 统一重排
    (2, '三、已编号章节'),         # 已编号 → 统一重排
    (3, '（一）裸小节'),          # 新章后 H3 重新起算
    (2, '四、项目背景与意义'),    # 前面已有 3 个 H2 → 四
    (4, '1、四级标题不编号'),      # H4 使用阿拉伯数字序号
    (1, '文档主标题'),            # H1 不编号
    (1, '第一章 手写章标题'),     # 裸「第X章」→ 已编号，原样
    (2, '五、5G 创新应用'),       # 「5G」不是编号，照常编号
]
check(heads == expect, 'docx 标题序列与预期完全一致（%d 条）' % len(heads))

# ---------- 2. docx 链路：生成真实文档读回 ----------
doc = build_docx('测试项目申报书', MD, doc_type='report',
                 subtitle='测试赛事', team='测试团队')
paras = [(p.style.name, p.text.strip()) for p in doc.paragraphs
         if (p.style.name or '').startswith('Heading') and p.text.strip()]
print('---- docx Heading 段落 ----')
for st, t in paras:
    print('  %-9s %s' % (st, t))

texts = [t for _st, t in paras]
for want in ('一、摘要', '二、研究目的', '（一）子节甲', '四、项目背景与意义',
             '五、5G 创新应用'):
    check(want in texts, 'docx Heading 段落含「%s」' % want)
for banned in ('一、一、已编号章节', '（3.1）', '一、3.1', '一、5G'):
    check(banned not in ' '.join(texts), 'docx 无重复编号「%s」' % banned)
# 目录条目应与正文标题一致（同用一份 blocks）
toc_zone = [p.text.strip() for p in doc.paragraphs]
joined = ' '.join(toc_zone)
check('一、摘要' in joined and '四、项目背景与意义' in joined,
      'docx 目录/正文均携带编号标题')

# ---------- 3. pdf 链路：纯文本预处理断言 ----------
numbered = _number_headings(MD)
lines = [l for l in numbered.split('\n') if l.startswith('#')]
print('---- pdf 编号后标题行 ----')
for l in lines:
    print('  ' + l)

pdf_expect = [
    '## 一、摘要',
    '## 二、研究目的',
    '### （一）子节甲',
    '### （二）已编号小节',
    '## 三、已编号章节',
    '### （一）裸小节',
    '## 四、项目背景与意义',
    '#### 1、四级标题不编号',
    '# 文档主标题',
    '## 五、5G 创新应用',
]
check(lines == pdf_expect, 'pdf 编号后标题行与预期完全一致（%d 条）' % len(lines))
# 裸「第X章」行不是 markdown 标题，pdf 链路原样保留、不加号
check('第一章 手写章标题' in numbered and '一、第一章' not in numbered,
      'pdf 裸「第X章」行原样保留不重复加号')

# 代码围栏内的 ## 不编号
fenced = _number_headings('```\n## 围栏内不是标题\n```\n## 真标题\n')
check('## 围栏内不是标题' in fenced and '## 一、真标题' in fenced,
      'pdf 代码围栏内的 ## 不编号，围栏外正常编号')

# ---------- 3b. 语义媒体落位：与 Word 使用同类章节锚点 ----------
media_sections = [
    '一、项目背景与痛点',
    '二、技术方案与系统架构',
    '三、竞品分析与差异化',
    '四、商业模式与财务预测',
    '五、实施计划与里程碑',
]
for media_title, section_index in (
        ('预算与成本结构', 3),
        ('系统准确率与响应延迟', 1),
        ('竞品功能与差异化对比', 2),
        ('实施进度与里程碑', 4),
        ('无关材料', -1)):
    check(_pick_media_section(media_title, media_sections) == section_index,
          'PDF 媒体「%s」语义落位正确' % media_title)
prefix, parsed_sections = _split_markdown_sections(
    '前置摘要\n\n## 一、技术方案\n正文\n\n## 二、实施计划\n进度')
check('前置摘要' in prefix and
      [_media_norm(item['title']) for item in parsed_sections] == ['技术方案', '实施计划'],
      'PDF 正文章节切分保留前置内容并去除编号用于匹配')

_original_chart_path = pdf_render._chart_path
_original_chart_story = pdf_render._chart_story
_placements = []
try:
    pdf_render._chart_path = lambda _chart: 'mock-image.png'
    def _capture_media(charts, tables, page_break=False, heading=None):
        _placements.append({
            'charts': [x.get('title') for x in charts or []],
            'tables': [x.get('title') for x in tables or []],
            'page_break': page_break,
        })
        return []
    pdf_render._chart_story = _capture_media
    _body = ('## 一、技术方案与系统架构\n技术正文\n\n'
             '## 二、竞品分析与差异化\n竞品正文\n\n'
             '## 三、商业模式与财务预测\\n商业正文')
    _charts = [
        {'title': '系统准确率与响应延迟', 'url': '/generated/mock.png'},
        {'title': '无关材料', 'url': '/generated/mock.png'},
    ]
    _tables = [{'title': '竞品功能与差异化对比', 'header': ['维度'], 'rows': [['效果']]}]
    pdf_render._body_with_media_story(_body, _charts, _tables)
finally:
    pdf_render._chart_path = _original_chart_path
    pdf_render._chart_story = _original_chart_story

check(_placements[0]['charts'] == ['系统准确率与响应延迟'] and
      _placements[1]['tables'] == ['竞品功能与差异化对比'] and
      _placements[-1]['charts'] == ['无关材料'] and _placements[-1]['page_break'],
      'PDF 图表/表格随语义章节落位，未匹配媒体才进入补充附表')

# ---------- 4. pdf 链路：生成真实 PDF 读回 ----------
try:
    from pypdf import PdfReader
except Exception:
    from PyPDF2 import PdfReader

_fd, pdf_path = tempfile.mkstemp(prefix='competition-agent-num-', suffix='.pdf')
os.close(_fd)
render_markdown_to_pdf(MD, pdf_path, title='测试申报书')
reader = PdfReader(pdf_path)
pdf_text = ''.join((pg.extract_text() or '') for pg in reader.pages)
pdf_text_cmp = pdf_text.replace(' ', '').replace('\n', '')
print('---- pdf 抽取文本（前 400 字）----')
print('  ' + pdf_text[:400].replace('\n', ' '))
for want in ('一、摘要', '二、研究目的', '（一）子节甲', '四、项目背景与意义'):
    check(want in pdf_text_cmp, 'pdf 文本含「%s」' % want)
os.unlink(pdf_path)

print('\nALL TESTS PASSED')
