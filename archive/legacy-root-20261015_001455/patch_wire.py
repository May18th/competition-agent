# -*- coding: utf-8 -*-
"""接线：把 304(wbsync.js) / 308(wbsmart.js+wbsmart.css) 引入 index.html 并 bump 版本号。
   幂等：已引入就跳过。版本号自动从当前串推到下一个（ah -> ai -> aj ...）。"""
import io, os, re

BASE = '/opt/comp-agent'
HTML = os.path.join(BASE, 'index.html')
out = []
s = io.open(HTML, 'r', encoding='utf-8').read()
orig = s

# 当前版本号
m = re.search(r'v=(20260929[a-z]+)', s)
cur = m.group(1) if m else '20260929ah'


def nxt(v):
    pre, suf = v[:8], v[8:]
    # 字母序递增：ah -> ai
    letters = [ord(c) - 97 for c in suf]
    i = len(letters) - 1
    while i >= 0:
        letters[i] += 1
        if letters[i] <= 25:
            break
        letters[i] = 0
        i -= 1
        if i < 0:
            letters = [0] + letters
            break
    return pre + ''.join(chr(97 + c) for c in letters)


new = nxt(cur)
out.append('版本 %s -> %s' % (cur, new))

# 1) CSS：wbsmart.css 放在 wbfab302.css 之后
if 'wbsmart.css' not in s:
    i = s.find('/static/wbfab302.css')
    if i > 0:
        end = s.find('>', i)
        s = s[:end + 1] + '\n    <link rel="stylesheet" href="/static/wbsmart.css?v=%s">' % new + s[end + 1:]
        out.append('wbsmart.css 已引入')
else:
    out.append('wbsmart.css 已存在')

# 2) JS：wbsync.js / wbsmart.js 放在 wbchat.js 之后
i = s.find('/static/wbchat.js')
if i > 0:
    end = s.find('>', i)
    add = ''
    if 'wbsync.js' not in s:
        add += '\n<script src="/static/wbsync.js?v=%s"></script>' % new
        out.append('wbsync.js 已引入')
    if 'wbsmart.js' not in s:
        add += '\n<script src="/static/wbsmart.js?v=%s"></script>' % new
        out.append('wbsmart.js 已引入')
    if add:
        s = s[:end + 1] + add + s[end + 1:]
else:
    out.append('!! 找不到 wbchat.js 锚点')

# 3) bump 全部版本号
n = s.count('v=' + cur)
s = s.replace('v=' + cur, 'v=' + new)
out.append('版本号替换 %d 处' % n)

if s != orig:
    io.open(HTML, 'w', encoding='utf-8').write(s)
    out.append('index.html 写入完成')
print('\n'.join(out))
