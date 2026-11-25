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

        return req.then(function (res) {
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
    }

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

    global.WB = global.WB || {};
    global.WB.api = api;
})(window);
