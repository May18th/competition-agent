# -*- coding: utf-8 -*-
"""302 修（第二版）：封面 Logo 改用 python-docx 原生 add_picture，彻底避开手写 drawing XML
   的命名空间坑。上一版 _add_float_picture 用 parse_xml 拼 <w:drawing>，
   因 _NS_DRAW 缺 xmlns:w（后补上又报属性未转义）两次失败 —— 图片进了 media，
   但 drawing 节点没插进段落，封面根本不显示。原生 API 零风险。"""
import io, os, sys, zipfile

BASE = '/opt/comp-agent'
F = os.path.join(BASE, 'docx_render.py')
out = []
s = io.open(F, 'r', encoding='utf-8').read()

start = s.find('def _cover_logo(doc, anchor_paragraph):')
end = s.find('def _header(doc, title):')
if start < 0 or end < 0 or end < start:
    print('!! 定位失败 _cover_logo=%d _header=%d' % (start, end))
    sys.exit(1)

NEW = '''def _cover_logo(doc, anchor_paragraph):
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


'''

s = s[:start] + NEW + s[end:]
io.open(F, 'w', encoding='utf-8').write(s)
out.append('_cover_logo 已改写为原生 add_picture')

# 复验：必须同时满足 media 有图 + 段落里有 drawing/blip
sys.path.insert(0, BASE)
import importlib, docx
import docx_render as dr
importlib.reload(dr)
d = docx.Document()
p = d.add_paragraph()
ok = dr._cover_logo(d, p)
path = '/tmp/wb302_cover_test3.docx'
d.save(path)
z = zipfile.ZipFile(path)
imgs = [n for n in z.namelist() if n.startswith('word/media/')]
xml = d.element.xml
out.append('返回值=%r' % (ok,))
out.append('docx bytes=%d IMG_COUNT=%d' % (os.path.getsize(path), len(imgs)))
out.append('段落含 drawing=%s 段落含 blip=%s' % ('<w:drawing' in xml, '<a:blip' in xml))
print('\n'.join(out))
