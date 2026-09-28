# -*- coding: utf-8 -*-
"""本轮改动的静态校验：DOM 闭合 + 内联脚本语法 + 关键断言。
用 html.parser 走一遍标签栈，栈剩 0 且无错误才算 DOM 平衡（能抓出包错层）。"""
import re, subprocess, os, sys
from html.parser import HTMLParser

NODE = r'C:\Users\34984\.workbuddy\binaries\node\versions\22.22.2-3\node.exe'
html_src = open('index.html', encoding='utf-8').read()
css_src = open('static/style.css', encoding='utf-8').read()
js_src = open('static/app.js', encoding='utf-8').read()

VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class Chk(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errs = [], []
    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))
    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errs.append('多余闭合 </%s> @%s' % (tag, self.getpos())); return
        if self.stack[-1][0] != tag:
            self.errs.append('不匹配：期望 </%s>(开于%s) 实得 </%s> @%s'
                             % (self.stack[-1][0], self.stack[-1][1], tag, self.getpos()))
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]; return
            return
        self.stack.pop()

c = Chk(); c.feed(html_src)
print('--- 1) DOM 闭合 ---')
print('  未闭合残留:', len(c.stack), '| 错误:', len(c.errs))
for e in c.errs[:6]:
    print('   !', e)
if c.stack:
    print('   残留栈(末5):', c.stack[-5:])
dom_ok = (not c.stack and not c.errs)

print('--- 2) 内联 script 块语法 ---')
blocks = re.findall(r'<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>', html_src, re.S)
ok = 0
for i, b in enumerate(blocks):
    p = '_blk%d.js' % i
    open(p, 'w', encoding='utf-8').write(b)
    r = subprocess.run([NODE, '--check', p], capture_output=True, text=True)
    if r.returncode: print('   ! BLOCK %d: %s' % (i, r.stderr[:300]))
    else: ok += 1
    os.remove(p)
print('  inline blocks ok:', ok, '/', len(blocks))

r = subprocess.run([NODE, '--check', 'static/app.js'], capture_output=True, text=True)
print('  static/app.js node --check:', 'OK' if r.returncode == 0 else 'FAIL ' + r.stderr[:300])
js_ok = (r.returncode == 0)

print('--- 3) 本轮断言 ---')
# 注释里会提到这些字符串（本轮就是靠注释写清根因），所以断言必须剔除行注释再统计，
# 否则「校验器把自己的注释当正文」会给出假失败——这个坑本项目已经踩过（探针自污染）。
def code_only(s):
    out = []
    for ln in s.split('\n'):
        t = ln.lstrip()
        if t.startswith('//') or t.startswith('*') or t.startswith('/*'):
            continue
        out.append(ln.split('//')[0] if '//' in ln and '"' not in ln.split('//')[0] else ln)
    return '\n'.join(out)

js_code = code_only(js_src)

def chk(label, cond, extra=''):
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', label, extra))
    return bool(cond)

res = []
# 「注释吞元素」专项：HTML 注释必须以 --> 结尾。若误写成 */（JS 风格），
# 注释会一路吞到下一个 -->，把中间的元素整段变成注释文本——
# 合法注释、DOM 闭合检查也过，但元素在运行时根本不存在（本轮实际踩到）。
_nc = re.sub(r'<!--.*?-->', '', html_src, flags=re.S)
_missing = [i for i in set(re.findall(r'id="([A-Za-z0-9_-]+)"', html_src)) if ('id="%s"' % i) not in _nc]
res.append(chk('无注释吞元素（每个 id 都活在注释外）', not _missing,
               '(被吞: %s)' % _missing[:5] if _missing else ''))
res.append(chk('注释开闭配对', html_src.count('<!--') == html_src.count('-->'),
               '(%d/%d)' % (html_src.count('<!--'), html_src.count('-->'))))
res.append(chk('公告条 DOM 已加', 'id="wbNoticeBar"' in html_src and 'id="wbNoticeText"' in html_src))
res.append(chk('公告条函数挂 window', 'window.wbNoticeClose = function' in js_code))
res.append(chk('公告条双源(api+静态)', "'/api/notice'" in js_code and "'/static/notice.json" in js_code))
res.append(chk('公告条默认不显示', 'bar.style.display = \'flex\'' in js_code))
res.append(chk('notice.json 存在且可解析',
               __import__('json').load(open('static/notice.json', encoding='utf-8')).get('text') == ''))
res.append(chk('下拉 option 改主题变量', 'select option { background: var(--surface-solid)' in css_src))
res.append(chk('骨架屏改 --bg-0', 'background: var(--bg-0, #f5f7fb)' in css_src))
res.append(chk('白底适配段已落仓', '白底柔和主题适配' in css_src))
res.append(chk('白底适配段限定 body.light', 'body.light .card{\n' in css_src
               and '\n.card{\n    background:linear-gradient(158deg' not in css_src,
               '(无条件浅色卡片={})'.format('\n.card{\n    background:linear-gradient(158deg' in css_src)))
res.append(chk('浅色下重阴影已柔化', 'body.light #themeToggle{ box-shadow:0 6px 18px rgba(31,42,68,.12); }' in css_src))
res.append(chk('完成条分享按钮改「分享链接」', '>分享链接</button>' in html_src))
res.append(chk('从材料识别挂 window 3 个',
               all(('window.%s = %s;' % (f, f)) in js_code for f in ('wbMatOpen', 'wbMatClose', 'wbMatGo'))))
res.append(chk('marked 本地优先', '<script src="/static/marked.min.js"></script>' in html_src
               and 'jsdelivr.net/npm/marked' in html_src))
res.append(chk('浅色 .wb-bg 已覆盖', 'body.light .wb-bg {' in css_src))
res.append(chk('--bg-0 已改白', '--bg-0:#ffffff;' in css_src))
res.append(chk('@media print 已存在', '@media print' in css_src))
res.append(chk('CSS 括号平衡', css_src.count('{') == css_src.count('}'),
               '(%d/%d)' % (css_src.count('{'), css_src.count('}'))))
# 第一百零八轮铁律：静态资源版本号必须是时间戳唯一值（v=20xxxxxx[x]），禁止 v=N 递增复用
# （N 复用会让 Cloudflare 捧着旧缓存不放——17:30 全站 JS 不执行那次就是 v=11 被 CF 缓存了坏版）
_refs = re.findall(r'(?:app\.js|style\.css)\?v=([^"\']+)', html_src)
_ts_ok = bool(_refs) and all(re.fullmatch(r'2026\d{4}[a-z]?', v) for v in _refs) and len(set(_refs)) == 1
res.append(chk('版本号为时间戳唯一值(禁 v=N)', _ts_ok, '(refs: %s)' % _refs))

print('--- 汇总 ---')
allok = dom_ok and js_ok and ok == len(blocks) and all(res)
print('ALL OK' if allok else 'HAS FAILURE')
sys.exit(0 if allok else 1)
