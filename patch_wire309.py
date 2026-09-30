# -*- coding: utf-8 -*-
"""309：把 demo picker（wbdemo.js/css）接进 index.html 并 bump 版本号。
注意：index.html 由 team-lead 独家收口，接线脚本做幂等保护（已引入则跳过）。
"""
import io, re, sys

P = '/opt/comp-agent/index.html'
s = io.open(P, encoding='utf-8').read()
orig = s
log = []

# ---------- 1) CSS ----------
css_tag = '<link rel="stylesheet" href="/static/wbdemo.css?v=__V__">'
if '/static/wbdemo.css' in s:
    log.append('SKIP css 已引入')
else:
    anchor = '<link rel="stylesheet" href="/static/wbtools307.css'
    idx = s.find(anchor)
    if idx < 0:
        print('FAIL 找不到 CSS 锚点 wbtools307.css')
        sys.exit(1)
    end = s.find('>', idx)
    s = s[:end + 1] + '\n    ' + css_tag + s[end + 1:]
    log.append('OK  css 已插入（排在 wbtools307.css 之后）')

# ---------- 2) JS ----------
js_tag = '<script src="/static/wbdemo.js?v=__V__"></script>'
if '/static/wbdemo.js' in s:
    log.append('SKIP js 已引入')
else:
    # 必须排在 app.js 之后（它要包 window.wbOpenDemo），且排在 wbsmart.js 之后保持顺序稳定
    anchor = '<script src="/static/wbsmart.js'
    idx = s.find(anchor)
    if idx < 0:
        print('FAIL 找不到 JS 锚点 wbsmart.js')
        sys.exit(1)
    end = s.find('</script>', idx)
    if end < 0:
        print('FAIL wbsmart.js 的 script 标签未闭合')
        sys.exit(1)
    s = s[:end + len('</script>')] + '\n' + js_tag + s[end + len('</script>'):]
    log.append('OK  js 已插入（排在 wbsmart.js 之后）')

# ---------- 3) bump 版本号 ----------
m = re.search(r'v=(20260929[a-z]+)', s)
if not m:
    print('FAIL 找不到版本号')
    sys.exit(1)
cur = m.group(1)


def nxt(v):
    ls = [ord(c) - 97 for c in v[8:]]
    i = len(ls) - 1
    while i >= 0:
        ls[i] += 1
        if ls[i] <= 25:
            break
        ls[i] = 0
        i -= 1
        if i < 0:
            ls = [0] + ls
            break
    return v[:8] + ''.join(chr(97 + c) for c in ls)


new = nxt(cur)
n = s.count('v=' + cur)
s = s.replace('v=' + cur, 'v=' + new)
s = s.replace('__V__', new)
log.append('OK  bump %s -> %s（%d 处）' % (cur, new, n))

io.open(P, 'w', encoding='utf-8').write(s)
print('=== 309 接线 ===')
for l in log:
    print(l)
print('bytes %d -> %d' % (len(orig), len(s)))
print('REST wbdemo refs:', s.count('/static/wbdemo'))
