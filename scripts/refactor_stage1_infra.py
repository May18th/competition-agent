#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 1 阶段重构：把基础设施符号从 app.py 抽到 infra.py。

用法
----
    python scripts/refactor_stage1_infra.py                  # 只看计划，不写文件
    python scripts/refactor_stage1_infra.py --apply          # 真正写（先自动备份）
    python scripts/refactor_stage1_infra.py --apply --layout flat   # 线上扁平结构

搬迁内容（20 个符号）
--------------------
    数据库    get_db, DB_PATH
    用户标识  _load_uid_secret, _current_uid, _require_uid
    限流      _client_ip, _rate_hit, _rate_limited,
              _RATE_LIMIT, _RATE_WINDOW_SEC, _rate_hits, _rate_lock
    后台鉴权  ADMIN_TOKEN, _ADMIN_COOKIE_NAME, _ADMIN_SESSION_SIGNER,
              _admin_session_valid, _admin_session_role, _require_admin
    错误归类  _friendly_error, _error_code

为什么先做这一步
----------------
这些符号被 100 多处调用（get_db 50 处、_current_uid 36 处、_friendly_error 20 处…），
是 app.py 里唯一的横切耦合。路由函数之间几乎不互相调用（跨域调用实测仅 3 处），
所以只要把这层剥出去，后续拆 blueprint 时一律 `from infra import ...`，不必碰 app。

安全性
------
infra.py 与 app.py 同目录，因此 `os.path.dirname(__file__)` 的结果不变，
DB_PATH 的定位和 .uid_secret 的存放位置完全一致，不需要改任何路径逻辑。

验收（改完必须全过，缺一不可）
------------------------------
    1. 两边语法：  python -c "import ast;ast.parse(open('backend/app.py').read())"
    2. 独立导入：  python -c "import backend.infra"
    3. 全量测试：  154 项全绿（含 tests/probes 下的探针）
    4. 冒烟四连：  /api/health 200、/admin 401、/api/history 401、/api/chat 缺参数 400
    5. diff 体检： 应只有 app.py 变短 + infra.py 新增，不能出现行为改动
    6. 回滚预案：  git checkout -- backend/app.py && rm backend/infra.py

注意
----
本脚本只搬定义、不改函数体一个字符。如果发现某个函数被改动，说明脚本被改坏了，
不要 --apply。`_rate_hit` 等本地新增符号在线上不存在时会跳过并告警，不算失败。
"""
import argparse
import ast
import io
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOVE_FUNCS = [
    '_load_uid_secret',
    '_current_uid',
    '_require_uid',
    '_client_ip',
    '_rate_hit',
    '_rate_limited',
    '_admin_session_valid',
    '_admin_session_role',
    '_require_admin',
    'get_db',
    '_friendly_error',
    '_error_code',
]

MOVE_ASSIGNS = [
    'DB_PATH',
    '_RATE_LIMIT',
    '_RATE_WINDOW_SEC',
    '_rate_hits',
    '_rate_lock',
    'ADMIN_TOKEN',
    '_ADMIN_COOKIE_NAME',
    '_ADMIN_SESSION_SIGNER',
]

INFRA_HEADER = '''# -*- coding: utf-8 -*-
"""基础设施层：数据库连接、匿名用户标识、限流、后台鉴权、错误归类。

从 app.py 抽出（第 1 阶段重构）。这些符号被 100 多处调用，是 app.py 里唯一的
横切耦合；独立成模块后，后续拆出的 blueprint 只需 `from infra import ...`，
不必依赖 app 本身。

路径注意：本文件与 app.py 同目录，所以 `os.path.dirname(__file__)` 的结果不变，
DB_PATH 与 .uid_secret 的定位和重构前完全一致。
"""
import os
import sqlite3
import threading
import time
import secrets as _secrets

from flask import request, jsonify, g
from itsdangerous import URLSafeSerializer


'''


def load_targets(path, layout):
    src = io.open(path, encoding='utf-8', newline='').read()
    lines = src.split('\n')
    tree = ast.parse(src)
    return src, lines, tree


def index_symbols(tree):
    funcs, assigns = {}, {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[n.name] = (n.lineno, n.end_lineno)
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            assigns[n.targets[0].id] = (n.lineno, n.end_lineno)
    return funcs, assigns


def absorb_comments(lines, start):
    """把紧贴在上方的连续注释行并入块（遇到空行或非注释即停）。"""
    i = start - 2
    while i >= 0 and lines[i].lstrip().startswith('#'):
        start = i + 1
        i -= 1
    return start


def build_blocks(lines, funcs, assigns, missing):
    spans = []
    for name in MOVE_FUNCS:
        if name in funcs:
            spans.append((name, funcs[name][0], funcs[name][1]))
        else:
            missing.append(name)
    for name in MOVE_ASSIGNS:
        if name in assigns:
            spans.append((name, assigns[name][0], assigns[name][1]))
        else:
            missing.append(name)

    spans.sort(key=lambda x: x[1])

    # 合并相邻块：中间只隔空行且相距 <= 3 行就并为一块，避免留下碎片
    merged = []
    for name, s, e in spans:
        if merged and s - merged[-1][2] <= 3:
            merged[-1][2] = max(merged[-1][2], e)
            merged[-1][3].append(name)
        else:
            merged.append([s, s, e, [name]])

    blocks = []
    for _, s, e, names in merged:
        s2 = absorb_comments(lines, s)
        blocks.append({'start': s2, 'end': e, 'names': names})
    return blocks


def render_infra(lines, blocks):
    chunks = []
    for b in blocks:
        body = '\n'.join(lines[b['start'] - 1:b['end']]).rstrip()
        chunks.append(body)
    return INFRA_HEADER + '\n\n\n'.join(chunks) + '\n'


def render_app(lines, blocks, layout):
    drop = set()
    for b in blocks:
        for i in range(b['start'], b['end'] + 1):
            drop.add(i)
        # 顺带吃掉块后紧邻的空行，避免留下连续 4 个空行
        j = b['end'] + 1
        while j <= len(lines) and j not in drop and lines[j - 1].strip() == '':
            drop.add(j)
            j += 1

    kept = [l for i, l in enumerate(lines, 1) if i not in drop]

    prefix = '' if layout == 'flat' else 'backend.'
    names = []
    for b in blocks:
        for n in b['names']:
            if n not in names:
                names.append(n)
    # 保持稳定顺序：先函数后常量，便于阅读
    ordered = [n for n in MOVE_FUNCS if n in names] + [n for n in MOVE_ASSIGNS if n in names]
    if not ordered:
        return '\n'.join(kept)
    if len(ordered) <= 4:
        imp = '%sfrom %sinfra import %s' % ('', prefix, ', '.join(ordered))
    else:
        body = ',\n'.join('    ' + ', '.join(ordered[i:i + 4]) for i in range(0, len(ordered), 4))
        imp = '%sfrom %sinfra import (\n%s,\n)' % ('', prefix, body)

    # 插在 Flask 实例化之前（此时所有顶层函数尚未定义，import 必须在最上方区域）
    anchor = None
    for i, l in enumerate(kept):
        if l.startswith('app = Flask('):
            anchor = i
            break
    if anchor is None:
        raise SystemExit('找不到 `app = Flask(` 锚点，无法确定 import 插入位置')

    kept.insert(anchor, imp)
    kept.insert(anchor + 1, '')

    # 压缩连续空行到最多 2 行
    out, blank = [], 0
    for l in kept:
        if l.strip() == '':
            blank += 1
            if blank > 2:
                continue
        else:
            blank = 0
        out.append(l)
    return '\n'.join(out)


def verify(app_src, infra_src, names):
    ast.parse(app_src)
    tree = ast.parse(infra_src)

    defined = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            defined.add(n.targets[0].id)

    problems = []
    for n in names:
        if n not in defined:
            problems.append('infra.py 缺少 %s' % n)
    # app.py 里不应再有这些定义
    app_tree = ast.parse(app_src)
    still = set()
    for n in app_tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            still.add(n.name)
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            still.add(n.targets[0].id)
    for n in names:
        if n in still:
            problems.append('app.py 里仍残留 %s 的定义' % n)
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真正写文件（默认只打印计划）')
    ap.add_argument('--layout', choices=['local', 'flat'], default='local',
                    help='local=backend/app.py（默认）；flat=线上扁平目录')
    ap.add_argument('--root', default=ROOT, help='项目根目录')
    args = ap.parse_args()

    app_path = os.path.join(args.root, 'backend', 'app.py') if args.layout == 'local' \
        else os.path.join(args.root, 'app.py')
    infra_path = os.path.join(os.path.dirname(app_path), 'infra.py')

    if not os.path.isfile(app_path):
        raise SystemExit('找不到 %s' % app_path)

    src, lines, tree = load_targets(app_path, args.layout)
    funcs, assigns = index_symbols(tree)
    missing = []
    blocks = build_blocks(lines, funcs, assigns, missing)

    print('目标文件     %s（%d 行）' % (app_path, len(lines)))
    print('生成文件     %s' % infra_path)
    print('布局         %s（import 前缀 %s）' % (args.layout, '' if args.layout == 'flat' else 'backend.'))
    print()
    print('将搬移 %d 块：' % len(blocks))
    for b in blocks:
        print('  行 %5d-%5d  %2d 行  %s' % (b['start'], b['end'], b['end'] - b['start'] + 1,
                                            ', '.join(b['names'])))
    if missing:
        print()
        print('跳过（本文件里没有，可能是线上/本地差异）：%s' % ', '.join(missing))

    all_names = [n for b in blocks for n in b['names']]
    if not all_names:
        raise SystemExit('没有可搬移的符号，脚本可能已经执行过')

    infra_src = render_infra(lines, blocks)
    new_app = render_app(lines, blocks, args.layout)

    problems = verify(new_app, infra_src, all_names)
    if problems:
        print()
        print('自检失败：')
        for p in problems:
            print('  - ' + p)
        raise SystemExit(1)

    moved_lines = sum(b['end'] - b['start'] + 1 for b in blocks)
    print()
    print('自检通过：两边语法 OK，无残留定义，符号齐全')
    print('预计 app.py  %d → %d 行（-%.0f%%）' % (
        len(lines), len(new_app.split('\n')), moved_lines * 100.0 / len(lines)))
    print('预计 infra.py %d 行' % len(infra_src.split('\n')))

    if not args.apply:
        print()
        print('这是 dry-run，未写任何文件。确认无误后加 --apply。')
        return 0

    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = '%s.bak.%s' % (app_path, ts)
    shutil.copy2(app_path, backup)
    io.open(infra_path, 'w', encoding='utf-8', newline='').write(infra_src)
    io.open(app_path, 'w', encoding='utf-8', newline='').write(new_app)

    print()
    print('已写入。备份：%s' % backup)
    print()
    print('接着按这个顺序验收：')
    print('  1. python -c "import ast;ast.parse(open(%r).read())"' % app_path)
    print('  2. python -c "import %sinfra"' % ('' if args.layout == 'flat' else 'backend.'))
    print('  3. 跑全量测试（应为 154 项全绿）')
    print('  4. 冒烟：health 200 / admin 401 / history 401 / chat 缺参数 400')
    print('  5. 回滚：git checkout -- %s && rm %s' % (
        os.path.relpath(app_path, args.root), os.path.relpath(infra_path, args.root)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
