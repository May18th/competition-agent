/* 科创赛事助手 · 统一请求层（第二百九十一轮渐进改造 1/3）
   ------------------------------------------------------------------
   背景：app.js 里 _wbFetch 只包了 9 处，其余 31 处仍是裸 fetch。
   后果不是「不能用」，而是三类故障不可控：
     1. 无超时 —— 隧道抖动时按钮永久转圈，用户只能刷新；
     2. 无统一错误语义 —— 每处各写一套 r.ok ? r.json() : null，
        422 被业务拒绝（质量门拦截）和 500 崩了长得一模一样；
     3. 提示各写各的 —— demo-panel / sync-panel 各自实现了一个 toast。

   本文件是纯新增的零依赖请求层，加载顺序最早（先于 wbchat.js / app.js），
   任何模块都能用，不改变任何现有调用点的行为。迁移按调用点逐个进行。

   用法：
     WB.api('/api/stats')                        GET，自动解析 JSON
     WB.api('/api/kb/add', { body: {...} })      POST JSON，自动序列化
     WB.api('/api/upload_file', { form: fd })    FormData 上传，超时放宽
     WB.api(url, { raw: true })                  要自己判断状态码时用
     WB.api(url, { silent: true })               失败不弹提示（后台轮询类）
     WB.api.onError(fn)                          注册全局错误提示（app.js 接 wbToast）

   失败一律抛 Error，带 httpStatus / body / aborted，调用方 catch 里照旧处理。
*/
(function (global) {
    'use strict';

    var DEFAULT_TIMEOUT = 30000;   // 普通接口
    var UPLOAD_TIMEOUT = 120000;   // 上传 / 导出，大文件放宽

    var handlers = [];             // 全局错误提示订阅者
    var lastTip = { key: '', at: 0 };
    // 同参 GET 合并：url -> Promise。老内核没有 Map 时退化成普通对象（key 前缀防原型污染）
    var inflight = (typeof Map === 'function') ? new Map() : null;
    function _iget(k) { return inflight ? inflight.get(k) : _objGet(k); }
    function _iset(k, v) { if (inflight) inflight.set(k, v); else _objSet(k, v); }
    function _idel(k) { if (inflight) inflight.delete(k); else _objSet(k, undefined); }
    var _obj = {};
    function _objGet(k) { return _obj['$' + k]; }
    function _objSet(k, v) { _obj['$' + k] = v; }

    function isFormData(v) {
        return typeof FormData !== 'undefined' && v instanceof FormData;
    }

    function makeError(msg, status, body) {
        var e = new Error(msg || ('请求失败' + (status ? '（' + status + '）' : '')));
        e.isApiError = true;
        e.httpStatus = status || 0;
        e.body = body;
        return e;
    }

    /* 全局提示节流：同一路径 3 秒内只提示一次。
       生成失败时前端常有连环请求（status 轮询、history 刷新），不节流会连弹五个框。
       401/403 不弹：登录态失效有专门的引导流程，这里再弹一次只会盖住它。 */
    function emit(err, url) {
        if (!err || err.httpStatus === 401 || err.httpStatus === 403) return;
        var key = String(url || '').split('?')[0];
        var now = Date.now();
        if (key === lastTip.key && now - lastTip.at < 3000) return;
        lastTip.key = key;
        lastTip.at = now;
        for (var i = 0; i < handlers.length; i++) {
            try { handlers[i](err, url); } catch (e) { /* 提示失败不能影响请求链路 */ }
        }
    }

    function api(url, opt) {
        opt = opt || {};
        var upload = isFormData(opt.form) || isFormData(opt.body);
        var ms = opt.timeout !== undefined ? opt.timeout : (upload ? UPLOAD_TIMEOUT : DEFAULT_TIMEOUT);

        var headers = {};
        var k;
        if (opt.headers) for (k in opt.headers) headers[k] = opt.headers[k];

        var init = {
            method: String(opt.method || 'GET').toUpperCase(),
            headers: headers,
            credentials: opt.credentials || 'same-origin'
        };
        if (opt.cache) init.cache = opt.cache;

        if (opt.form !== undefined && opt.form !== null) {
            init.body = opt.form;                       // FormData 不能设 Content-Type
        } else if (opt.body !== undefined && opt.body !== null) {
            if (isFormData(opt.body) || typeof opt.body === 'string') {
                init.body = opt.body;
            } else {
                init.body = JSON.stringify(opt.body);
                if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
            }
        }

        /* ---------- 同参 GET 合并（2026-11-25） ----------
           动机：历史列表 / 统计 / 状态这类只读接口会被多处同时触发（切页签、
           滚到可视区、面板各自 init），同一个 URL 在 200ms 内并发三四次很常见。
           合并后只发一个请求，其余调用方共享同一个 Promise。
           只对「无 body 的 GET」生效：POST 有副作用不能合并；带 form 的更不能。 */
        var dedupeKey = '';
        if (init.method === 'GET' && !init.body && !opt.noDedupe) {
            dedupeKey = url;
            var hit = _iget(dedupeKey);
            if (hit) return hit;
        }

        // 老内核（iOS Safari / 微信 X5 早期版）没有 AbortController，退化为普通 fetch
        var ctl = null;
        if (typeof AbortController === 'function' && ms > 0) {
            ctl = new AbortController();
            init.signal = ctl.signal;
        }

        var timer = null;
        var req;
        try {
            req = global.fetch(url, init);
        } catch (e) {
            var syncErr = makeError('请求未能发出', 0, null);
            syncErr.cause = e;
            if (!opt.silent) emit(syncErr, url);
            return Promise.reject(syncErr);
        }
        if (ctl) {
            timer = setTimeout(function () { try { ctl.abort(); } catch (e) {} }, ms);
        }

        var p = req.then(function (res) {
            if (timer) { clearTimeout(timer); timer = null; }
            if (opt.raw) return res;

            var ct = (res.headers && res.headers.get && res.headers.get('content-type')) || '';
            var parse = ct.indexOf('json') >= 0
                ? res.json().catch(function () { return null; })
                : res.text().catch(function () { return ''; });

            return parse.then(function (body) {
                if (!res.ok) {
                    var msg = (body && (body.error || body.message)) || ('服务返回 ' + res.status);
                    var err = makeError(msg, res.status, body);
                    if (!opt.silent) emit(err, url);
                    throw err;
                }
                return body;
            });
        }, function (e) {
            if (timer) { clearTimeout(timer); timer = null; }
            var aborted = !!(e && (e.name === 'AbortError' || e.code === 20));
            var err = makeError(aborted ? '网络超时，请重试' : '网络异常，请检查连接', 0, null);
            err.aborted = aborted;
            err.cause = e;
            if (!opt.silent) emit(err, url);
            throw err;
        });

        if (dedupeKey) {
            _iset(dedupeKey, p);
            // 无论成败都要摘钩子：失败的 Promise 留在表里会让后续同 URL 请求永久失败
            var _clear = function () { if (_iget(dedupeKey) === p) _idel(dedupeKey); };
            p.then(_clear, _clear);
        }
        return p;
    }

    /* ---------- 竞态守卫（2026-11-25） ----------
       场景：连点两条历史记录，或快速切比赛筛选。请求 A 先发后到、B 后发先到，
       结果 A 的响应把 B 的渲染覆盖掉 —— 列表和详情对不上，用户以为点错了。
       用法：
         var seq = WB.api.seq('history');
         WB.api.get('/api/history').then(function (d) {
             if (!WB.api.isLatest('history', seq)) return;   // 有更新的请求在路上，丢弃本次
             render(d);
         });
       命名空间隔离，不同列表各用各的 key。 */
    var _seq = {};
    api.seq = function (ns) {
        ns = String(ns || 'default');
        _seq[ns] = (_seq[ns] || 0) + 1;
        return _seq[ns];
    };
    api.isLatest = function (ns, n) {
        ns = String(ns || 'default');
        return _seq[ns] === n;
    };
    // 显式作废：放弃某命名空间所有在途请求的结果
    api.cancelSeq = function (ns) {
        ns = String(ns || 'default');
        _seq[ns] = (_seq[ns] || 0) + 1;
    };

    api.get = function (url, opt) {
        var o = {};
        if (opt) for (var k in opt) o[k] = opt[k];
        o.method = 'GET';
        return api(url, o);
    };
    api.post = function (url, body, opt) {
        var o = {};
        if (opt) for (var k in opt) o[k] = opt[k];
        o.method = 'POST';
        if (body !== undefined) o.body = body;
        return api(url, o);
    };
    // 注册全局错误提示；返回取消函数，便于面板卸载时摘钩子
    api.onError = function (fn) {
        if (typeof fn !== 'function') return function () {};
        handlers.push(fn);
        return function () {
            var i = handlers.indexOf(fn);
            if (i >= 0) handlers.splice(i, 1);
        };
    };
    api.timeout = DEFAULT_TIMEOUT;
    api.uploadTimeout = UPLOAD_TIMEOUT;

    /* ---------- 前端错误上报（2026-11-25） ----------
       在此之前 window.onerror / unhandledrejection 一处都没挂：
       前端脚本炸了、Promise 没 catch，只有用户自己知道 "点了没反应"，
       开发侧拿不到任何现场。后端 /api/log_error 早就有了（按 type+message 5 分钟去重合并），
       这里只是把客户端现场送过去。

       刻意做的取舍：
         ① 只报「真错误」—— 静态资源 404、用户取消、网络中断不报（噪音大、无信息量）；
         ② 同一 (message + 首行栈) 每页只发一次，避免某个循环里抛错把接口打爆；
         ③ 上限 10 条：报够就停，宁可少报也不给用户添流量；
         ④ 全部走 sendBeacon（失败退回 fetch keepalive），页面即将卸载也送得出去；
         ⑤ 上报本身不能抛错 —— 整个函数体包 try，宁可丢一条日志。
       用法：WB.reportError('frontend', err, { path: location.pathname }); */
    var _reported = {};           // 指纹 -> 1，去重
    var _reportCount = 0;
    var _REPORT_MAX = 10;

    function _errFingerprint(type, msg, stack) {
        var first = String(stack || '').split('\n')[1] || '';
        return String(type) + '|' + String(msg).slice(0, 80) + '|' + first.slice(0, 80);
    }

    api.reportError = function (type, err, extra) {
        try {
            if (_reportCount >= _REPORT_MAX) return;
            var msg = '';
            var stack = '';
            if (err && typeof err === 'object') {
                msg = err.message || String(err);
                stack = err.stack || '';
            } else {
                msg = String(err || '');
            }
            // 用户主动取消、网络断开这类不是缺陷，不进错误库
            if (/cancel|取消|abort|AbortError|网络异常|网络超时|Failed to fetch|NetworkError/i.test(msg)) return;
            var fp = _errFingerprint(type, msg, stack);
            if (_reported[fp]) return;
            _reported[fp] = 1;
            _reportCount++;

            var payload = {
                type: String(type || 'frontend').slice(0, 20),
                path: String((extra && extra.path) || location.pathname + location.hash).slice(0, 200),
                message: String(msg).slice(0, 200),
                detail: String(stack || (extra && extra.detail) || '').slice(0, 500)
            };
            var body = JSON.stringify(payload);
            // sendBeacon 优先：卸载/崩溃边缘也送得出去，且不占用连接的 promise 链
            if (global.navigator && typeof navigator.sendBeacon === 'function') {
                try {
                    var blob = new Blob([body], { type: 'application/json' });
                    if (navigator.sendBeacon('/api/log_error', blob)) return;
                } catch (e) {}
            }
            // 兜底：keepalive 允许请求在页面关闭后继续完成
            try {
                global.fetch('/api/log_error', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: body,
                    keepalive: true,
                    credentials: 'same-origin'
                }).catch(function () {});
            } catch (e) {}
        } catch (e) { /* 上报失败绝不能影响业务 */ }
    };

    // 全局钩子：脚本异常 + 未处理的 Promise 拒绝。只挂一次。
    if (global.addEventListener && !global.__wbErrBound) {
        global.__wbErrBound = true;
        global.addEventListener('error', function (ev) {
            try {
                // 资源加载失败（img/script）也走 error，但 target 不是 window，没有 message
                var t = ev && ev.target;
                if (t && t !== global && t.tagName) {
                    var url = t.src || t.href || '';
                    // 静态资源 404 不上报：部署缓存失配很常见，报上来只是噪音
                    if (/\.(js|css|png|jpe?g|gif|svg|ico|woff2?)(\?|$)/i.test(url)) return;
                    api.reportError('resource', '资源加载失败: ' + url, { path: url });
                    return;
                }
                api.reportError('script', ev && (ev.error || ev.message), {
                    detail: ev && ev.filename ? (ev.filename + ':' + ev.lineno + ':' + ev.colno) : ''
                });
            } catch (e) {}
        }, true);
        global.addEventListener('unhandledrejection', function (ev) {
            try {
                var r = ev && ev.reason;
                api.reportError('promise', (r && (r.message || r)) || 'Unhandled rejection', {
                    detail: (r && r.stack) || ''
                });
            } catch (e) {}
        });
    }

    global.WB = global.WB || {};
    global.WB.api = api;
})(window);
