# -*- coding: utf-8 -*-
"""修接线 bug（wbchat.js 的 script 标签被拆坏）+ 补做 313①（移除前台管理入口）+ bump aj"""
import io, os

BASE = '/opt/comp-agent'
HTML = os.path.join(BASE, 'index.html')
out = []
s = io.open(HTML, 'r', encoding='utf-8').read()
orig = s

# ---------- 1. 修 script 闭合（接线时把 wbchat.js 的 '>' 当结尾插，导致标签拆坏）----------
BAD = ('<script src="/static/wbchat.js?v=20260929ai">\n'
       '<script src="/static/wbsync.js?v=20260929ai"></script>\n'
       '<script src="/static/wbsmart.js?v=20260929ai"></script></script>')
GOOD = ('<script src="/static/wbchat.js?v=20260929ai"></script>\n'
        '<script src="/static/wbsync.js?v=20260929ai"></script>\n'
        '<script src="/static/wbsmart.js?v=20260929ai"></script>')
if BAD in s:
    s = s.replace(BAD, GOOD, 1)
    out.append('script 闭合已修 OK')
else:
    out.append('script 块未匹配（可能已修）')

# ---------- 2. 313①：移除前台「管理入口」链接 ----------
OLD_ENTRY = '''    <div style="opacity: .45; margin-top: 4px;">
        <a href="/admin/login" style="color: inherit; text-decoration: none;"
           title="管理后台（需登录）">管理入口</a>
    </div>'''
NEW_ENTRY = '''    <!-- 第三百一十三轮：前台移除「管理入口」链接。
         原来这里给了一个小字入口（204 轮的拍板是「不撤入口、安全靠登录门」），
         但实测评委/用户会误点进后台登录页，观感像后台暴露。现在撤掉前台入口，
         后台仍可通过直接访问 /admin/login 进入 —— 少一个入口不等于少一道门。 -->'''
if OLD_ENTRY in s:
    s = s.replace(OLD_ENTRY, NEW_ENTRY, 1)
    out.append('313 前台管理入口已移除 OK')
elif '管理入口' not in s:
    out.append('313 入口已是移除状态')
else:
    out.append('313 !! 入口锚点未匹配，需人工看')

# ---------- 3. bump ai -> aj ----------
n = s.count('v=20260929ai')
if n:
    s = s.replace('v=20260929ai', 'v=20260929aj')
    out.append('版本 ai -> aj ×%d' % n)

if s != orig:
    io.open(HTML, 'w', encoding='utf-8').write(s)
    out.append('index.html 写入完成')

# 复查
s2 = io.open(HTML, 'r', encoding='utf-8').read()
out.append('复查 管理入口残留=%d' % s2.count('管理入口'))
out.append('复查 wbchat 闭合正常=%s' % ('<script src="/static/wbchat.js?v=20260929aj"></script>' in s2))
out.append('复查 版本=%s' % (sorted(set(__import__('re').findall(r'v=(20260929[a-z]+)', s2)))))
print('\n'.join(out))
