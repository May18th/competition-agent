# -*- coding: utf-8 -*-
"""302 收尾：① manifest.json 补 Logo 图标  ② 实测 Word 封面 Logo 真的插进去了"""
import io, json, os, sys, zipfile

BASE = '/opt/comp-agent'
MANI = os.path.join(BASE, 'static', 'manifest.json')
out = []

# ---------- ① manifest 补 Logo 图标（幂等）----------
with io.open(MANI, 'r', encoding='utf-8') as f:
    m = json.load(f)

icons = m.get('icons', [])
has_logo = any('logo.png' in (i.get('src') or '') for i in icons)
if not has_logo:
    icons.append({
        "src": "/static/logo.png",
        "sizes": "512x512",          # 实测所得，非编造
        "type": "image/png",
        "purpose": "any"
    })
    m['icons'] = icons
    with io.open(MANI, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    out.append('manifest: 已追加 logo.png 图标')
else:
    out.append('manifest: 已存在 logo 图标，跳过')
out.append('manifest icons 共 %d 项' % len(m['icons']))

# ---------- ② 实测 Word 封面 Logo ----------
sys.path.insert(0, BASE)
try:
    import docx
    import docx_render as dr
    d = docx.Document()
    p = d.add_paragraph()
    dr._cover_logo(d, p)                       # 302 新增：封面左上角 Logo
    path = '/tmp/wb302_cover_test.docx'
    d.save(path)
    z = zipfile.ZipFile(path)
    imgs = [n for n in z.namelist() if n.startswith('word/media/')]
    out.append('docx 生成成功: %s (%d bytes)' % (path, os.path.getsize(path)))
    out.append('IMG_COUNT=%d  %s' % (len(imgs), imgs[:3]))
except Exception as e:
    out.append('docx 实测失败: %r' % (e,))

print('\n'.join(out))
