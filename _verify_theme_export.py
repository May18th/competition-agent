# -*- coding: utf-8 -*-
"""验证 export_zip 里手动 theme 是否覆盖 deck 内置 theme"""
import json, io, zipfile, urllib.request, re
from collections import Counter

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
DECK = {"theme":"tech","variant":"v1","project":"测试",
        "slides":[{"type":"cover","title":"封面","kicker":"TEST","bullets":[]},
                  {"type":"bullets","title":"要点","bullets":["第一条","第二条"]}]}

def run(label, extra):
    p = {"rich_deck": json.loads(json.dumps(DECK))}          # deck 内置 theme=tech
    p.update(extra)
    req = urllib.request.Request('http://127.0.0.1:8080/api/export_zip',
        data=json.dumps(p, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json'}, method='POST')
    raw = opener.open(req, timeout=180).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    ppt = [n for n in names if n.endswith('.pptx')]
    if not ppt:
        print("%-34s zip 内无 pptx（只有 %d 个 docx）" % (label, len(names))); return None
    inner = zipfile.ZipFile(io.BytesIO(z.read(ppt[0])))
    s1 = inner.read('ppt/slides/slide1.xml').decode('utf-8')
    colors = Counter(re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', s1))
    top = ', '.join('%s×%d' % (c, n) for c, n in colors.most_common(4))
    print("%-34s 封面主色 -> %s" % (label, top))
    return set(colors)

a = run("①不传 theme（deck=tech）", {})
b = run("②传 theme=ink（deck=tech）", {"theme":"ink","variant":"v4"})
print()
if a and b:
    print("两次配色不同           :", "YES ✅ 覆盖生效" if a != b else "NO ❌ 覆盖没生效")
    print("ink 特征色 1B1B1B 出现  :", "YES ✅" if '1B1B1B' in b else "NO ❌")
    print("ink 特征色 4A4A4A 出现  :", "YES ✅" if '4A4A4A' in b else "NO ❌")
    print("tech 特征色 0F1535 残留 :", "残留 ❌" if '0F1535' in b else "已清除 ✅")
