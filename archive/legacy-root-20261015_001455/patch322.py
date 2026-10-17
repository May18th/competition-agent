# -*- coding: utf-8 -*-
"""322 轮 P0：移动端点「开始生成」卡在「已用 0 秒」且无任何提示。
根因（app.js startWork）：
    const _poll = () => {
        if (document.hidden) return;                       // ← 静默 return
        if (Date.now() - t0 > WATCHDOG_MS) { ...reject... }// ← 在 return 之后，永不触发
        fetch('/api/status/' + task_id ...)
移动端页面被判后台（微信/夸克内核切回来常不触发 visibilitychange）时：
  ① 「已用 X 秒」只在 _setBar 里更新，而 _setBar 只在轮询回调里调 → 永远 0 秒
  ② 看门狗在 return 之后 → 永不超时报错
  ③ 既不 resolve 也不 reject → 无任何提示，点「重新生成」同样卡死（wbRetry 也走 startWork）
修复：① 看门狗抽成 _wdCheck，hidden 时也推进；② 加墙钟兜底（t0 会被 visibilitychange 顺延）
      ③ 「已用 X 秒」改独立 1s 心跳，不再依赖轮询；④ 补 pageshow / focus 两路恢复轮询。
"""
import io, sys

P = '/opt/comp-agent/static/app.js'
s = io.open(P, encoding='utf-8').read()
orig = s
log = []


def must(old, new, tag):
    global s
    if s.count(old) != 1:
        print('FAIL[%s] count=%d' % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new, 1)
    log.append('OK  ' + tag)


# ---- 1) 看门狗抽成独立函数 + 墙钟兜底，插在 _poll 之前 ----
A_OLD = "                let _queuedSeen = false;\n"
A_NEW = (
    "                let _queuedSeen = false;\n"
    "                // 322 轮 P0：看门狗抽成独立函数。原来它写在 `if (document.hidden) return;` 之后——\n"
    "                // 移动端页面被判后台时（微信/夸克内核从后台切回常不触发 visibilitychange），\n"
    "                // 轮询每轮都在这里静默 return：已用时间永远 0 秒、看门狗永不响、既不 resolve\n"
    "                // 也不 reject，用户看到的就是「卡死且无任何提示」，点「重新生成」也一样。\n"
    "                // 现在：不可见时仍然不发请求（保留省电初衷），但看门狗照常推进。\n"
    "                var _wallT0 = Date.now();   // 墙钟：不做「不可见顺延」，超时必定报错\n"
    "                var _wdFired = false;\n"
    "                var _wdCheck = function () {\n"
    "                    if (_wdFired) return true;\n"
    "                    var _wdMs = (_queuedSeen ? 15 : (mode === 'deep' ? 12 : 5)) * 60 * 1000;\n"
    "                    // t0 会被 visibilitychange 按「不可见时长」顺延；页面若长期被判后台，\n"
    "                    // t0 会被无限顺延、看门狗永远不响。墙钟 +3 分钟兜底，保证一定会报错。\n"
    "                    var _over = (Date.now() - t0 > _wdMs) || (Date.now() - _wallT0 > _wdMs + 3 * 60 * 1000);\n"
    "                    if (_over) {\n"
    "                        _wdFired = true;\n"
    "                        try { clearInterval(tick); } catch (e) {}\n"
    "                        reject(new Error('等待超时（' + (_wdMs / 60000) + ' 分钟未完成）。可能是服务重启过或任务被中断，请重新生成'));\n"
    "                        return true;\n"
    "                    }\n"
    "                    return false;\n"
    "                };\n"
)
must(A_OLD, A_NEW, '1 看门狗独立化')

# ---- 2) _poll 开头：hidden 时也推进看门狗 ----
B_OLD = (
    "                        // 切后台/锁屏时彻底停手：省电、省流量，也不给后端添无意义负载\n"
    "                        if (document.hidden) return;\n"
    "                        if (Date.now() - t0 > (_queuedSeen ? 15 * 60 * 1000 : WATCHDOG_MS)) {\n"
    "                            clearInterval(tick);\n"
    "                            reject(new Error('等待超时（' + (WATCHDOG_MS / 60000) + ' 分钟未完成）。可能是服务重启过或任务被中断，请重新生成'));\n"
    "                            return;\n"
    "                        }\n"
)
B_NEW = (
    "                        // 切后台/锁屏时不发请求：省电、省流量，也不给后端添无意义负载。\n"
    "                        // 322 轮 P0：但不能「静默 return」——看门狗必须照常推进，否则移动端\n"
    "                        // 一旦被判后台就永久停在「已用 0 秒」且没有任何报错。\n"
    "                        if (document.hidden) { try { _wdCheck(); } catch (e) {} return; }\n"
    "                        if (_wdCheck()) return;\n"
)
must(B_OLD, B_NEW, '2 hidden 时推进看门狗')

# ---- 3) 「已用 X 秒」改独立 1s 心跳，不再依赖轮询回调 ----
C_OLD = "            _setBar(2, '正在提交任务…');\n"
C_NEW = (
    "            _setBar(2, '正在提交任务…');\n"
    "            // 322 轮 P0：「已用 X 秒」原先只挂在 _setBar 里更新，而 _setBar 只在轮询回调里调。\n"
    "            // 轮询一旦没跑（页面被判后台 / 请求挂住），时间就永远停在「已用 0 秒」，\n"
    "            // 用户分不清是「还在等」还是「已经死了」。这里起独立心跳，只管把时间走起来。\n"
    "            window._wbGenT0 = Date.now();\n"
    "            (function () {\n"
    "                try { clearInterval(window.__wbElapsedTimer); } catch (e) {}\n"
    "                window.__wbElapsedTimer = setInterval(function () {\n"
    "                    try {\n"
    "                        var _eb = document.getElementById('elapsedBadge');\n"
    "                        if (!_eb || !window._wbGenT0) return;\n"
    "                        var _es = Math.round((Date.now() - window._wbGenT0) / 1000);\n"
    "                        _eb.style.display = 'inline-block';\n"
    "                        _eb.innerText = _es >= 60\n"
    "                            ? ('已用 ' + Math.floor(_es / 60) + ' 分 ' + (_es % 60) + ' 秒')\n"
    "                            : ('已用 ' + _es + ' 秒');\n"
    "                    } catch (e) {}\n"
    "                }, 1000);\n"
    "            })();\n"
)
must(C_OLD, C_NEW, '3 已用时间独立心跳')

# ---- 4) 补 pageshow / focus 两路恢复轮询（移动端 visibilitychange 不可靠） ----
D_OLD = (
    "                    document.addEventListener('visibilitychange', function () {\n"
    "                        if (!document.hidden) { try { _poll(); } catch (e) {} }\n"
    "                    });\n"
)
D_NEW = (
    "                    document.addEventListener('visibilitychange', function () {\n"
    "                        if (!document.hidden) { try { _poll(); } catch (e) {} }\n"
    "                    });\n"
    "                    // 322 轮：移动端（微信 / 夸克 / iOS Safari）从后台或 bfcache 回来时，\n"
    "                    // visibilitychange 常常不触发，页面一直被当成 hidden、轮询一直空转。\n"
    "                    // 补 pageshow 与 focus 两路：只要用户真的在看页面，就立刻把轮询拉起来。\n"
    "                    window.addEventListener('pageshow', function () { try { _poll(); } catch (e) {} });\n"
    "                    window.addEventListener('focus', function () { try { _poll(); } catch (e) {} });\n"
)
must(D_OLD, D_NEW, '4 pageshow/focus 补拉')

# ---- 5) 收尾必须清心跳（成功路径） ----
E_OLD = (
    "                streamFinish();   // 撤掉流式光标与脉冲点，交由最终渲染统一覆盖\n"
    "                try { wbAgentFinish(true); } catch (e) {}\n"
    "                window._wbGenerating = false;\n"
)
E_NEW = (
    "                streamFinish();   // 撤掉流式光标与脉冲点，交由最终渲染统一覆盖\n"
    "                try { wbAgentFinish(true); } catch (e) {}\n"
    "                // 322 轮：生成结束就撤掉「已用时间」心跳，别让它一直跑\n"
    "                try { clearInterval(window.__wbElapsedTimer); window.__wbElapsedTimer = 0; } catch (e) {}\n"
    "                window._wbGenerating = false;\n"
)
must(E_OLD, E_NEW, '5a 成功路径清心跳')

# ---- 6) 收尾必须清心跳（失败路径） ----
F_OLD = (
    "            .catch(err => {\n"
    "                // 注意：这里的 timer 变量已随真实进度改造移除，别再清 interval\n"
    "                streamFinish();   // 失败/取消也要撤掉流式光标和「生成中」占位\n"
)
F_NEW = (
    "            .catch(err => {\n"
    "                // 注意：这里的 timer 变量已随真实进度改造移除，别再清 interval\n"
    "                // 322 轮：「已用时间」心跳必须在这里撤掉，否则失败后它还在后台一直跑\n"
    "                try { clearInterval(window.__wbElapsedTimer); window.__wbElapsedTimer = 0; } catch (e) {}\n"
    "                streamFinish();   // 失败/取消也要撤掉流式光标和「生成中」占位\n"
)
must(F_OLD, F_NEW, '5b 失败路径清心跳')

if s == orig:
    print('NO_CHANGE')
    sys.exit(1)

io.open(P, 'w', encoding='utf-8').write(s)
print('=== 322 补丁 ===')
for l in log:
    print(l)
print('bytes %d -> %d' % (len(orig), len(s)))
