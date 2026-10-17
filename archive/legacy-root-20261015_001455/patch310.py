# -*- coding: utf-8 -*-
"""310 一键演示为空 + 311 报错提示技术化（都是 app.js，合并成一条线，幂等）"""
import io, os

BASE = '/opt/comp-agent'
JS = os.path.join(BASE, 'static', 'app.js')
out = []
s = io.open(JS, 'r', encoding='utf-8').read()
orig = s

# ---------------- 310：一键演示「样例数据为空」----------------
# 根因：demo_sample.json 顶层是 {success, data, rating, rich_deck, ...}，
#       proposal 在 data 里；而判定写的是 !d.proposal（顶层根本没有）→ 必抛错。
#       且 window.__wbDemoData = d 存的是顶层，openHistory 的演示分支又包一层
#       {success:true, data: __wbDemoData}，两边错了一层，即使判定改对也渲染不出正文。
OLD_DEMO = """                var d = await res.json();
                if (!d || !d.proposal) throw new Error('演示样例数据为空');
                window.__wbDemoData = d;
                try {
                    await openHistory(d.id || 0);"""
NEW_DEMO = """                var d = await res.json();
                // 310 轮修复：样例文件顶层是 {success, data, rating, rich_deck, ...}，
                // proposal 在 data 这一层里。原来直接判 d.proposal（顶层没有这个字段）
                // 必然抛「演示样例数据为空」；同时 openHistory 的演示分支会再包一层
                // {success:true, data: __wbDemoData}，所以这里必须存 data 层，
                // 两边才对得上，否则正文渲染出来是空的。
                var payload = (d && d.data && typeof d.data === 'object') ? d.data : d;
                if (!payload || !payload.proposal) throw new Error('演示样例数据为空');
                window.__wbDemoData = payload;
                try {
                    await openHistory((d && d.id) || (payload && payload.id) || 0);"""
if OLD_DEMO in s:
    s = s.replace(OLD_DEMO, NEW_DEMO, 1)
    out.append('310 演示数据层级 + 判定字段 已修 OK')
elif 'var payload = (d && d.data' in s:
    out.append('310 已修过，跳过')
else:
    out.append('310 !! 未匹配 wbOpenDemo 锚点，需人工看')

# ---------------- 311：报错弹窗不显示 HTTP 状态码 + 修标点连排 ----------------
OLD_ERR = """                    wbToast('生成服务暂不可用：' + (err.message || '未知原因') + '，请重试', {
                        type: 'error',
                        sub: (err.httpStatus ? ('HTTP ' + err.httpStatus + ' · ') : '') + '已填内容都还在，改好后点「开始生成」即可'
                    });"""
NEW_ERR = """                    // 311 轮：① 后端文案有时自带句号，直接拼「，请重试」会出现「。，」连排，
                    // 先清掉尾部标点；② 技术状态码（HTTP 403/500）不出现在界面上，
                    // 只在控制台留痕，方便排查又不吓唬用户。
                    var _raw = String((err && err.message) || '未知原因');
                    var _clean = _raw.replace(/[\\u3002\\uff0c,\\u3001\\uff1b;\\s]+$/, '');
                    if (err && err.httpStatus) {
                        try { console.warn('[生成失败] HTTP ' + err.httpStatus + ' ' + _raw); } catch (e) {}
                    }
                    wbToast('生成服务暂不可用：' + _clean + '，请重试', {
                        type: 'error',
                        sub: '已填内容都还在，改好后点「开始生成」即可'
                    });"""
if OLD_ERR in s:
    s = s.replace(OLD_ERR, NEW_ERR, 1)
    out.append('311 去掉 HTTP 状态码 + 修标点连排 OK')
elif '_clean' in s:
    out.append('311 已修过，跳过')
else:
    out.append('311 !! 未匹配报错锚点，需人工看')

if s != orig:
    io.open(JS, 'w', encoding='utf-8').write(s)
    out.append('app.js 写入完成')
else:
    out.append('app.js 无变化')

# 复查
s2 = io.open(JS, 'r', encoding='utf-8').read()
out.append('复查 HTTP 前缀残留: %d' % s2.count("'HTTP ' + err.httpStatus"))
out.append('复查 payload 修复在: %s' % ('var payload = (d && d.data' in s2))
print('\n'.join(out))
