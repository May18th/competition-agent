# -*- coding: utf-8 -*-
"""302 修：_NS_DRAW 漏声明 xmlns:w，导致 <w:drawing> 解析失败（封面 Logo 看似成功实则没插进去）"""
import io, os, sys, zipfile, re

BASE = '/opt/comp-agent'
F = os.path.join(BASE, 'docx_render.py')
out = []

s = io.open(F, 'r', encoding='utf-8').read()

OLD = "_NS_DRAW = (\n    'xmlns:wp="
NEW = ("_NS_DRAW = (\n"
       "    'xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" '\n"
       "    'xmlns:wp=")

if 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"' in s and '_NS_DRAW' in s:
    out.append('已存在 xmlns:w，跳过')
elif OLD in s:
    s = s.replace(OLD, NEW, 1)
    io.open(F, 'w', encoding='utf-8').write(s)
    out.append('NS 修复已写入')
else:
    out.append('!! 未匹配 _NS_DRAW，需人工看')

# 复验：真的把 Logo 插进段落了吗（不只看 media 里有图）
sys.path.insert(0, BASE)
import docx
import docx_render as dr
d = docx.Document()
p = d.add_paragraph()
dr._cover_logo(d, p)
path = '/tmp/wb302_cover_test2.docx'
d.save(path)
z = zipfile.ZipFile(path)
imgs = [n for n in z.namelist() if n.startswith('word/media/')]
xml = d.element.xml
out.append('docx bytes=%d  IMG_COUNT=%d' % (os.path.getsize(path), len(imgs)))
out.append('段落内含 drawing: %s' % ('<w:drawing' in xml))
out.append('段落内含 blip(图片引用): %s' % ('<a:blip' in xml))
out.append('文件大小 %s' % os.path.getsize(path))
print('\n'.join(out))
