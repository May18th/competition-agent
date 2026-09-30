# -*- coding: utf-8 -*-
"""302 轮 P0：右下角悬浮控件统一垂直堆叠 —— 精确替换补丁（可重复执行，幂等）"""
import io, os, sys

BASE = '/opt/comp-agent'
JS = os.path.join(BASE, 'static', 'wbchat.js')
HTML = os.path.join(BASE, 'index.html')

report = []


def read(p):
    with io.open(p, 'r', encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(s)


# ---------------- 1. wbchat.js ----------------
s = read(JS)
orig = s

# 1-a 气泡默认 bottom：140 -> 196（带 289 轮旧注释的那一行）
old_a = "st.bottom = '140px';                 // 与 #wbFabMain(16)/#wbTop(78) 同列，互不遮挡"
new_a = "st.bottom = '196px';                 // 302 队形：fab16 / ↑76 / ↓136 / 聊196，间距 12px"
if old_a in s:
    s = s.replace(old_a, new_a)
    report.append('js-1a 气泡默认bottom(带注释) 140->196 OK')
elif "'196px'" in s:
    report.append('js-1a 已是196，跳过')
else:
    report.append('js-1a !! 未匹配，需人工看')

# 1-b 其余两处裸的 st.bottom = '140px';（面板创建 + resize 回调）
cnt = s.count("st.bottom = '140px';")
if cnt:
    s = s.replace("st.bottom = '140px';", "st.bottom = '196px';")
    report.append('js-1b 裸bottom 140->196 ×%d OK' % cnt)
else:
    report.append('js-1b 无剩余140（可能已替换）')

# 1-c 风格菜单 bottom：196 -> 252（气泡 196~244，菜单要再往上 8px）
cnt2 = s.count("bottom:196px; width:210px;")
if cnt2:
    s = s.replace("bottom:196px; width:210px;", "bottom:252px; width:210px;")
    report.append('js-1c 风格菜单 196->252 ×%d OK' % cnt2)
else:
    report.append('js-1c 风格菜单未匹配（检查是否已被改）')

# 1-d 面板展开时给 body 挂 class，让 ↑/↓ 让位（wbfab302.css 消费）
old_d = "        panel.style.display = opened ? 'flex' : 'none';"
new_d = ("        panel.style.display = opened ? 'flex' : 'none';\n"
         "        // 302：面板展开时 ↑/↓ 淡出并停止接收点击，避免与面板边缘互相干扰\n"
         "        try { document.body.classList.toggle('wbchat-open', opened); } catch (e) {}")
if old_d in s and 'wbchat-open' not in s:
    s = s.replace(old_d, new_d, 1)
    report.append('js-1d body.wbchat-open 联动 OK')
elif 'wbchat-open' in s:
    report.append('js-1d 已存在，跳过')
else:
    report.append('js-1d !! 未匹配 setOpen 行')

if s != orig:
    write(JS, s)
    report.append('js 写入完成')
else:
    report.append('js 无变化')

# ---------------- 2. index.html：引入 wbfab302.css + bump 版本 ----------------
h = read(HTML)
orig_h = h

# 2-a 引入：必须排在 wbfix295.css 之后
old_ver = '20260929ad'
new_ver = '20260929ah'
if 'wbfab302.css' not in h:
    idx = h.find('/static/wbfix295.css')
    if idx > 0:
        # 找到该 link 标签的结束位置
        end = h.find('>', idx)
        if end > 0:
            tag = h[idx:end + 1]
            add = '\n    <link rel="stylesheet" href="/static/wbfab302.css?v=%s">' % new_ver
            h = h[:end + 1] + add + h[end + 1:]
            report.append('html-2a wbfab302.css 已插入到 wbfix295.css 之后 OK')
        else:
            report.append('html-2a !! 找不到 wbfix295 link 结束符')
    else:
        report.append('html-2a !! 找不到 wbfix295.css 引用')
else:
    report.append('html-2a 已引入，跳过')

# 2-b 版本号 bump（ad -> ah），这是绕过 Cloudflare CDN 唯一可靠手段
n = h.count(old_ver)
if n:
    h = h.replace(old_ver, new_ver)
    report.append('html-2b 版本号 %s->%s ×%d OK' % (old_ver, new_ver, n))
else:
    report.append('html-2b 版本号无 %s（可能已 bump）' % old_ver)

if h != orig_h:
    write(HTML, h)
    report.append('html 写入完成')
else:
    report.append('html 无变化')

print('\n'.join(report))
