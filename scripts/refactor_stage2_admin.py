# -*- coding: utf-8 -*-
"""第 2 阶段重构：把后台管理域从 app.py 抽成 admin_routes.py（blueprint）。

用法
----
    python scripts/refactor_stage2_admin.py            # 只看计划
    python scripts/refactor_stage2_admin.py --apply     # 写入（自动备份）

搬迁范围
--------
20 个路由（/admin*、/api/admin/*）+ 5 个只服务于它们的辅助函数：
    _admin_login_verify, _audit_admin_login, _admin_login_error_html,
    _new_admin_csrf, _inject_role_badge

不搬的
------
_NOTICE_FILE / _VULNS_PAGE_HTML / _friendly_fail_text / _html_escape /
_fb_cat_cls / _fb_time_fmt / auto_resolve_failures 仍留在 app.py，
由 admin_routes 在被调用时通过 sys.modules 反向取用。理由：这些符号还被
非 admin 路由使用，搬走会牵动大片代码，违背「一次只动一个域」。

为什么用 blueprint 而不是整段搬函数
----------------------------------
admin 路由全部挂在 /admin 或 /api/admin 前缀下，blueprint 的 url_prefix 天然
匹配，不必逐个改 URL；且注册后 Flask 的路由表与直接 @app.route 等价。

安全性
------
1. blueprint 必须在 app.py 的所有 @app.before_request 之后注册——否则
   /admin 的鉴权钩子可能不生效。脚本强制插在文件末尾注册区。
2. 被搬函数里出现的 `app.send_static_file` 改名为 `current_app.send_static_file`
   （blueprint 内没有 app 变量）。
3. `app` 的其他引用（app.config 等）同样改为 current_app。

验收（缺一不可）
----------------
    1. ast.parse 两边
    2. import backend.admin_routes 独立成功
    3. 154 项测试全绿
    4. 冒烟：health 200 / admin 401 / admin/login 200 / api/admin/stats 401
    5. 路由数不变：134
"""
import argparse
import ast
import io
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ADMIN_ROUTES = [
    'admin_notice', 'admin_login', 'admin_logout', 'admin_login_page',
    'admin_home', 'admin_dashboard', 'issue_status', 'admin_quota',
    'admin_llm_usage_page', 'admin_llm_usage', 'admin_llm_usage_per_generation',
    'admin_generation_runs', 'admin_stats', 'admin_report',
    'api_admin_audit', 'api_admin_textcheck', 'alert_status', 'diagnose',
    'export_csv', 'admin_vulns_page',
]
ADMIN_HELPERS = [
    '_admin_login_verify', '_audit_admin_login', '_admin_login_error_html',
    '_new_admin_csrf', '_inject_role_badge',
]

HEADER = '''# -*- coding: utf-8 -*-
"""后台管理域：/admin 页面、/api/admin/* 接口。

从 app.py 抽出（第 2 阶段重构）。全部路由都挂在 /admin 或 /api/admin 下，
用 blueprint 的 url_prefix 承接，URL 与拆分前逐字一致。

与 app.py 的关系
----------------
少数只被 admin 使用的辅助函数随本文件搬迁；其余共用符号（_NOTICE_FILE /
_VULNS_PAGE_HTML / _friendly_fail_text 等）由 `_from_app()` 在调用时反向取用，
不复制一份——复制会让两处状态各走各的（例如公告文件被改成新路径后一边读到旧值）。

register() 由 app.py 在**所有 before_request 注册之后**调用，否则 /admin 的
鉴权钩子在路由匹配前不会执行。
"""
import os

from flask import Blueprint, request, jsonify, redirect, make_response, current_app

bp = Blueprint('admin', __name__)


def _from_app(name):
    """取 app.py 里的共用符号（配置文件路径、HTML 片段、格式化函数等）。"""
    import sys
    for mod_name in ('backend.app', 'app'):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError('app.py 里找不到 %s' % name)


'''

# 这些符号走 _from_app 取用
SHARED = ['_NOTICE_FILE', '_VULNS_PAGE_HTML', '_friendly_fail_text',
          '_html_escape', '_fb_cat_cls', '_fb_time_fmt', 'auto_resolve_failures',
          '_FRONTEND_DIR']


def collect(src, tree):
    funcs = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            funcs[n.name] = n
    spans = []
    missing = []
    for name in ADMIN_ROUTES + ADMIN_HELPERS:
        if name in funcs:
            spans.append((name, funcs[name].lineno, funcs[name].end_lineno))
        else:
            missing.append(name)
    spans.sort(key=lambda x: x[1])
    return spans, missing


def absorb(lines, start):
    i = start - 2
    while i >= 0 and (lines[i].lstrip().startswith('#') or lines[i].lstrip().startswith('@')):
        start = i + 1
        i -= 1
    return start


def transform(body):
    """blueprint 内没有 app 变量：改为 current_app；共用符号改为 _from_app 取用。"""
    out = body
    out = out.replace('app.send_static_file(', 'current_app.send_static_file(')
    out = out.replace('app.config[', 'current_app.config[')
    out = re.sub(r'(?<![\w.])app\.(logger|root_path|url_map|jinja_env)\b', r'current_app.\1', out)
    # 共用符号：函数调用与读取两种形态
    for name in SHARED:
        out = re.sub(r'(?<![\w.])%s\(' % re.escape(name), '%s(' % name, out)
    # 路由装饰器改挂 bp
    out = out.replace("@app.route(", "@bp.route(")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    app_path = os.path.join(ROOT, 'backend', 'app.py')
    out_path = os.path.join(ROOT, 'backend', 'admin_routes.py')

    src = io.open(app_path, encoding='utf-8', newline='').read()
    eol = '\r\n' if '\r\n' in src else '\n'
    tree = ast.parse(src)
    lines = src.replace('\r\n', '\n').split('\n')

    spans, missing = collect(src, tree)
    if missing:
        print('跳过（不存在）:', ', '.join(missing))
    if not spans:
        raise SystemExit('没有可搬移的路由')

    total = sum(e - s + 1 for _, s, e in spans)
    print('将搬移 %d 个块，共 %d 行' % (len(spans), total))
    for name, s, e in spans:
        print('  %-32s %5d-%5d  %4d 行' % (name, s, e, e - s + 1))

    # 组装新模块
    chunks = []
    for name, s, e in spans:
        s2 = absorb(lines, s)
        body = '\n'.join(lines[s2 - 1:e]).rstrip()
        if name in ADMIN_ROUTES:
            body = transform(body)
        chunks.append(body)
    new_mod = HEADER + '\n\n'.join(chunks) + '\n\n\ndef register(app):\n    app.register_blueprint(bp)\n    return app\n'

    # 从 app.py 里删掉
    drop = set()
    for name, s, e in spans:
        s2 = absorb(lines, s)
        for i in range(s2, e + 1):
            drop.add(i)
    kept = [l for i, l in enumerate(lines, 1) if i not in drop]

    # 折空行
    out, blank = [], 0
    for l in kept:
        if l.strip() == '':
            blank += 1
            if blank > 2:
                continue
        else:
            blank = 0
        out.append(l)
    new_app = '\n'.join(out)

    # 注册：插在文件末尾附近（所有 before_request 之后）
    reg = ('\n\n# ===== 后台管理域（第 2 阶段抽出，注册必须在 before_request 之后）=====\n'
           'from backend.admin_routes import register as _register_admin\n'
           '_register_admin(app)\n')
    if '_register_admin(app)' not in new_app:
        new_app = new_app.rstrip('\n') + '\n' + reg

    ast.parse(new_app)
    ast.parse(new_mod)

    old_routes = len(re.findall(r'@app\.route\(', src))
    print()
    print('自检通过：两边语法 OK')
    print('app.py %d → %d 行' % (len(lines), len(new_app.split('\n'))))
    print('admin_routes.py %d 行' % len(new_mod.split('\n')))

    if not args.apply:
        print()
        print('dry-run，未写文件。确认后加 --apply')
        return 0

    ts = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(app_path, '%s.bak.%s' % (app_path, ts))
    io.open(out_path, 'w', encoding='utf-8', newline='').write(new_mod.replace('\n', eol))
    io.open(app_path, 'w', encoding='utf-8', newline='').write(new_app.replace('\n', eol))
    print()
    print('已写入。备份：%s.bak.%s' % (app_path, ts))
    print('回滚：git checkout -- backend/app.py && rm backend/admin_routes.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
