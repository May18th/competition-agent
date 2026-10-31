# -*- coding: utf-8 -*-
"""把「选赛道不显眼」这一处改动逐项移植到线上分支（/tmp/live 是线上原始文件）。

只做加法式替换，不整文件覆盖：
  index.html  → 标题栏加 #evTrackBadge；evTrackBox 换成新结构
  app.js      → chip 渲染改 class/aria-pressed；回执徽章逻辑；evTrackBadgeClick；来源徽章走主题变量
  style.css   → 追加 #evTrackBox/.ev-track-chip/#evTrackBadge 样式块
另外同步 ?v= 与 sw BUILD（sw 对 /static 是 cache-first，不换等于没改）。

线上文件是 CRLF，这里统一用 newline='' 读、写回 '\\r\\n'，不改变行尾风格。
"""
import io
import os
import re
import sys

import os as _os
LIVE = _os.environ.get("LIVE_DIR", "/tmp/live")
LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend")


# 行尾必须按每个文件的**原样**保留：线上 index.html / app.js 是 LF，
# style.css 是 CRLF（实测 CR 字节 0 / 0 / 2153）。统一转 CRLF 会让整文件每行都变，
# 事后 diff 全是噪音、也没法判断到底改了什么。
_EOL = {}


def read(p):
    with io.open(p, "rb") as f:
        raw = f.read()
    _EOL[p] = b"\r\n" if b"\r\n" in raw else b"\n"
    return raw.decode("utf-8").replace("\r\n", "\n")


def write(p, s):
    with io.open(p, "wb") as f:
        f.write(s.replace("\n", "\r\n" if _EOL.get(p) == b"\r\n" else "\n").encode("utf-8"))


def must(cond, msg):
    if not cond:
        print("FAIL: " + msg)
        sys.exit(1)


# ---------------- index.html ----------------
src = read(os.path.join(LOCAL, "index.html"))
dst = read(os.path.join(LIVE, "index.html"))

# 1) 标题栏：整段换成新版（含回执徽章）
m = re.search(r'<div onclick="evToggleBody\(\)".*?id="evBodyArrow".*?</div>', src, re.S)
must(m, "本地找不到 evToggleBody 标题块")
new_head = m.group(0)

m2 = re.search(r'<div onclick="evToggleBody\(\)".*?id="evBodyArrow".*?</div>', dst, re.S)
must(m2, "线上找不到 evToggleBody 标题块")
dst = dst[:m2.start()] + new_head + dst[m2.end():]
print("✔ index.html 标题栏已加 #evTrackBadge")

# 2) 赛区块：整块换成新版
m3 = re.search(r'( *)<!-- 赛道选择.*?(?=\n\1<div id="evSections")', src, re.S)
must(m3, "本地找不到赛区块")
new_box = m3.group(0)

m4 = re.search(r'( *)<!-- 赛道选择.*?(?=\n\1<div id="evSections")', dst, re.S)
must(m4, "线上找不到赛区块")
dst = dst[:m4.start()] + new_box + dst[m4.end():]
print("✔ index.html 赛区块已换新结构")

# 3) 版本号
before = dst
dst = dst.replace("style.css?v=20261031b", "style.css?v=20261031e")
dst = dst.replace("app.js?v=20261018a", "app.js?v=20261031f")
must(dst != before, "index.html 里没找到预期的 ?v= 值，请人工确认")
write(os.path.join(LIVE, "index.html"), dst)
print("✔ index.html ?v= → 20261031c")

# ---------------- app.js ----------------
srcj = read(os.path.join(LOCAL, "static", "app.js"))
dstj = read(os.path.join(LIVE, "app.js"))

# 1) 赛道渲染头：回执徽章 + chip 模板
a = srcj.index("            // 赛道选择：无赛道数据的赛事整块隐藏，不留空壳")
b = srcj.index("                    // 赛道细则：禁忌用红色")
new_render = srcj[a:b]

a2 = dstj.index("            // 赛道选择：无赛道数据的赛事整块隐藏，不留空壳")
b2 = dstj.index("                    // 赛道细则：禁忌用红色")
dstj = dstj[:a2] + new_render + dstj[b2:]
print("✔ app.js 赛道渲染头已替换")

# 2) 「当前按 XX 生成」回执行
old_h = "                    if (ti && c._track) {\n                        var t = c._track, h = '';\n"
new_h = ("                    if (ti && c._track) {\n"
         "                        var t = c._track, h = '';\n"
         "                        // 明确回执：告诉他现在是按哪个赛道在生成\n"
         "                        h += '<div style=\"margin-bottom: 6px; font-size: 13px; font-weight: 700; color: var(--text);\">' +\n"
         "                             '当前按「' + _esc(t.name) + '」生成</div>';\n")
must(old_h in dstj, "app.js 里找不到 ti 块锚点")
dstj = dstj.replace(old_h, new_h, 1)

# 3) 来源徽章改主题变量
old_sm = """                        var sm = { official: ['官方原文', '#0E9F6E', '#E7F7F1'],
                                   kb: ['知识库整理', '#6B7280', '#F3F4F6'],
                                   derived: ['建议', '#B45309', '#FEF3C7'] }[t.src || 'kb'];"""
new_sm = """                        // 用主题变量而不是写死浅色：原来 #E7F7F1/#F3F4F6 的浅底在夜间是白噪声
                        var sm = { official: ['官方原文', 'var(--c-b)', 'var(--surface-2)'],
                                   kb: ['知识库整理', 'var(--text-dim)', 'var(--surface-2)'],
                                   derived: ['建议', 'var(--warn-text)', 'var(--warn-bg)'] }[t.src || 'kb'];"""
must(old_sm in dstj, "app.js 里找不到来源徽章色值")
dstj = dstj.replace(old_sm, new_sm, 1)

# 4) 徽章点击函数：插在 evTrackRule 之前
ia = srcj.index("        // 标题栏的「待选赛道 / 赛道 · XX」徽章：点它 = 展开卡并滚到赛区块")
ib = srcj.index("        // 赛道规则拼成给 AI 看的约束文本（走 rule_content 链路，后端不用改）")
new_fn = srcj[ia:ib]
anchor = "        // 赛道规则拼成给 AI 看的约束文本（走 rule_content 链路，后端不用改）"
must(anchor in dstj, "app.js 里找不到 evTrackRule 注释锚点")
dstj = dstj.replace(anchor, new_fn + anchor, 1)
print("✔ app.js 已加 evTrackBadgeClick / 回执行 / 徽章色值")


# 5) 线上已有「请先选择参赛赛道」拦截（toast + scrollIntoView），但只弹一句就走了，
#    用户反馈「没提醒到」。不新建第二道，直接把这一道加厚：换成更具体的文案 + 抖动高亮。
old_gate = """                wbToast('请先选择参赛赛道', { type: 'warn', sub: '不同赛道的评审重点不同，确认后再开始生成' });
                var _trackBox = document.getElementById('evTrackBox');
                if (_trackBox && _trackBox.scrollIntoView) {
                    try { _trackBox.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
                }
                return;"""
new_gate = """                wbToast('先选一条赛道再生成', { type: 'warn',
                    sub: '这个赛事分了 ' + _eventChoice._tracks.length + ' 条赛道，评分侧重和禁忌都不一样' });
                // 展开卡片 + 滚到中间 + 抖一下 + 聚焦第一个 chip：光弹一句话用户会漏掉
                evNudgeTrack();
                return;"""
must(old_gate in dstj, "线上 app.js 里找不到既有赛道拦截块")
dstj = dstj.replace(old_gate, new_gate, 1)
print("✔ app.js 既有赛道拦截已加厚（提示文案 + 抖动定位）")

write(os.path.join(LIVE, "app.js"), dstj)

# ---------------- style.css ----------------
srcc = read(os.path.join(LOCAL, "static", "style.css"))
dstc = read(os.path.join(LIVE, "style.css"))
mark = "/* ===== 选赛道（2026-10-31 用户反馈「选赛道」"
i = srcc.index("/* ===== 选赛道（2026-10-31")
css_block = srcc[i:]
must("ev-track-chip" in css_block and "#evTrackBadge" in css_block, "本地样式块内容不完整")
must("ev-track-chip" not in dstc, "线上 style.css 已存在同名类，需人工核对")
dstc = dstc.rstrip("\n") + "\n\n" + css_block
write(os.path.join(LIVE, "style.css"), dstc)
print("✔ style.css 已追加赛区块样式块（%d 行）" % css_block.count("\n"))

# ---------------- sw.js ----------------
dsts = read(os.path.join(LIVE, "sw.js"))
must("var BUILD = '20261031b';" in dsts, "sw.js BUILD 不是预期值")
write(os.path.join(LIVE, "sw.js"), dsts.replace("var BUILD = '20261031b';", "var BUILD = '20261031f';"))
print("✔ sw.js BUILD → 20261031c")
print("\n全部补丁完成")
