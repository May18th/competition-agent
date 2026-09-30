# -*- coding: utf-8 -*-
"""417轮探针：复现「导出 Word 无封面无目录」"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from docx_render import build_docx

md = []
for i, ch in enumerate(['项目背景与痛点', '解决方案', '技术路线', '市场与商业模式',
                        '团队与分工', '财务测算', '风险控制', '社会价值', '实施计划', '总结展望'], 1):
    md.append('## %d. %s' % (i, ch))
    md.append('本项目针对' + ('该环节存在的效率与准确性问题，结合现场实测数据与文献调研，提出可落地的改进方案。' * 12))
text = '\n\n'.join(md)
print('chars=', len(text.replace('\n', '').replace(' ', '')))

doc = build_docx('智能试剂柜', text, subtitle='iCAN大学生创新创业大赛',
                 doc_type='report', school='某某大学', team='启航团队',
                 advisor='张老师', header_title='项目作品说明书')
doc.save('_probe_417.docx')

d = __import__('docx').Document('_probe_417.docx')
print('paras=', len(d.paragraphs), 'sections=', len(d.sections))
for p in d.paragraphs[:14]:
    print(repr(p.style.name), repr(p.text[:40]))
print('--- 是否含目录两字 ---')
print(any('目' in p.text and '录' in p.text for p in d.paragraphs))
import zipfile
xml = zipfile.ZipFile('_probe_417.docx').read('word/document.xml').decode('utf-8', 'ignore')
print('bookmark _toc_ count=', xml.count('_toc_'))
print('fldSimple=', xml.count('w:fldSimple'), 'instrText=', xml.count('w:instrText'))
