# -*- coding: utf-8 -*-
"""确定性校验：按函数名切片，检查各 Agent 的规格注入是否到位。"""
import io, re, sys

SRC = 'competition_agents.py'
src = io.open(SRC, encoding='utf-8').read()
lines = src.splitlines()

# 按函数名切片：从 def name( 到下一个顶层 def 之前
def slice_fn(name):
    start = None
    for i, ln in enumerate(lines):
        if re.match(r'\s*def\s+%s\s*\(' % re.escape(name), ln):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if re.match(r'\s*def\s+\w+\s*\(', lines[j]):
            return '\n'.join(lines[start:j])
    return '\n'.join(lines[start:])

# 期望：函数名 -> [(标签, 必含子串)]
EXPECT = [
    ('rule_parser',        [('报告规格', '_REPORT_SPEC')]),
    ('similarity_checker', [('报告规格', '_REPORT_SPEC')]),
    ('summary_agent',      [('内联段落要求', '文字要求')]),
    ('plan',               [('报告规格', '_REPORT_SPEC')]),
    ('social_value',       [('报告规格', '_REPORT_SPEC')]),
    ('judge_agent',        [('内联点评要求', '点评文字要求')]),
    ('proposal_analysis',  [('分析规格', '_ANALYSIS_SPEC')]),
]

fail = 0
print('%-22s %-14s %-8s %s' % ('函数', '检查项', '结果', '证据'))
print('-' * 76)
for fn, checks in EXPECT:
    body = slice_fn(fn)
    if body is None:
        print('%-22s %-14s %-8s %s' % (fn, '-', 'MISS', '未找到该函数定义'))
        fail += 1
        continue
    for label, needle in checks:
        ok = needle in body
        if not ok:
            fail += 1
        # 取证据行
        ev = ''
        for ln in body.splitlines():
            if needle in ln:
                ev = ln.strip()[:44]
                break
        print('%-22s %-14s %-8s %s' % (fn, label, 'PASS' if ok else 'FAIL', ev))

print('-' * 76)
print('结论：%s' % ('全部通过' if fail == 0 else ('%d 项未通过' % fail)))
sys.exit(1 if fail else 0)
