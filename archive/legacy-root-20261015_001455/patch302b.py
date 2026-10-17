# -*- coding: utf-8 -*-
"""302 轮：后台 Logo 统一应用 + 补回 283 轮被回滚的后台按钮样式 link
   说明：本脚本只做「纯新增式字符串替换」，不动任何业务逻辑；幂等，可重复执行。
   改动对象 app.py（后台登录页 _ADMIN_LOGIN_HTML + 4 个后台页顶栏 nav + 283 link）
"""
import io, os

BASE = '/opt/comp-agent'
APP = os.path.join(BASE, 'app.py')
VER = '20260929ah'
report = []


def read(p):
    with io.open(p, 'r', encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(s)


s = read(APP)
orig = s

# ---------------- 1. 后台登录页：Logo 居中（用户要求「登录页居中」）----------------
LOGIN_LOGO = (
    '<div style="text-align:center;margin:0 0 12px">'
    '<img src="/static/logo.png" alt="科创赛事助手" '
    'style="height:56px;width:auto;display:block;margin:0 auto"></div>'
)
old_login = '<h1>科创赛事助手 · 管理后台</h1>\n<p class="sub">请输入账号密码进入管理后台</p>'
if 'height:56px' not in s and old_login in s:
    s = s.replace(old_login, LOGIN_LOGO + old_login, 1)
    report.append('app-1 登录页居中 Logo(56px) 已插入 OK')
elif 'height:56px' in s:
    report.append('app-1 登录页 Logo 已存在，跳过')
else:
    report.append('app-1 !! 登录页锚点未匹配，需人工看')

# ---------------- 2. 后台页顶栏 nav 最左侧放 Logo（26px）----------------
NAV_LOGO = (
    '<img src="/static/logo.png" alt="科创赛事助手" '
    'style="height:26px;width:auto;vertical-align:middle;margin-right:10px">'
)
old_nav = '<nav class="nav">'
n_nav = s.count(old_nav)
if n_nav and 'height:26px' not in s:
    s = s.replace(old_nav, old_nav + NAV_LOGO)
    report.append('app-2 顶栏 nav Logo(26px) ×%d 已插入 OK' % n_nav)
elif 'height:26px' in s:
    report.append('app-2 顶栏 Logo 已存在，跳过')
else:
    report.append('app-2 !! 未找到 nav')

# ---------------- 3. 补回 283 轮后台按钮样式 link（被 reset 回滚掉了）----------------
old_head = '</style></head><body><div class="wrap">'
new_head = ('</style><link rel="stylesheet" href="/static/wbbtn-admin.css?v=%s">'
            '</head><body><div class="wrap">' % VER)
if 'wbbtn-admin.css' not in s:
    n_head = s.count(old_head)
    if n_head:
        s = s.replace(old_head, new_head)
        report.append('app-3 283 后台按钮样式 link ×%d 已补回 OK' % n_head)
    else:
        report.append('app-3 !! 未找到 </style></head><body><div class="wrap"> 锚点')
else:
    report.append('app-3 已存在 wbbtn-admin.css，跳过')

if s != orig:
    write(APP, s)
    report.append('app.py 写入完成')
else:
    report.append('app.py 无变化')

print('\n'.join(report))
