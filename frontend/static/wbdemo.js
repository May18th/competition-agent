/* ============================================================
 * 309 轮：一键演示「样例选择器」前端 —— 独立文件
 * 只新增 static/wbdemo.js + static/wbdemo.css，不碰 index.html / app.js / 其它文件。
 * ------------------------------------------------------------
 * 背景：「一键演示」原来固定加载 /static/demo_sample.json 那一份样例。
 *   后端正在扩到 3~5 份并给列表接口，本文件负责「有多份时先让选一份」。
 *
 * 接口契约（后端尚未生效，实测 /api/demo/list 现在返回 {"samples":[],"success":true}）：
 *   GET /api/demo/list
 *     → {success:true, items:[{key,title,competition,summary,tier,chars,updated}]}
 *   GET /api/demo/sample?key=ican
 *     → {success:true, data:{...proposal...}, rating, rich_deck}
 *   GET /api/demo/sample（不带 key → 第一份）
 *   ⚠️ 坑 1：错误响应 HTTP 也是 200，必须看 success 字段，不能只看 r.ok。
 *   ⚠️ 坑 2：字段名后端可能给 items 也可能给 samples，两个都认。
 *   ⚠️ 坑 3：字段可能缺失 → 按字段有无决定显不显示，不拿默认值凑数。
 *
 * 降级纪律（最重要）：列表拿不到 / 只有 1 条 / 出错 / 超时，一律直接调原来的
 *   wbOpenDemo()，行为与今天完全一致，绝不白屏、绝不弹红字堆栈，只 console.warn。
 *
 * 310 轮层级铁律（必须复用，不另写一套）：
 *   payload = (d && d.data && typeof d.data === 'object') ? d.data : d;
 *   window.__wbDemoData 必须存 data 那一层（openHistory 演示分支会再包一层
 *   {success:true, data:__wbDemoData}），存错层正文就空白。
 *   → 本文件优先走 window.openHistory；openHistory 目前是 app.js 私有函数、
 *     不在 window 上，于是退而把数据喂给原 wbOpenDemo（临时拦一次
 *     /static/demo_sample.json 请求），复用它那套已修好的解析逻辑。
 *
 * ES5 语法，全 try/catch，只暴露 window.wbDemo。
 * ============================================================ */
(function () {
    'use strict';
    if (window.__wbDemoOn) return;                 // 防重复注入
    window.__wbDemoOn = true;

    /* ---------- 常量 ---------- */
    var LIST_URL = '/api/demo/list';
    var SAMPLE_URL = '/api/demo/sample';
    var TIMEOUT = 7000;                 // 6~8s 超时走原路径
    var HOOK_MAX_TRY = 40;              // 40 × 250ms ≈ 10s，等 app.js 挂上 wbOpenDemo

    /* ---------- 状态 ---------- */
    var orig = null;                    // 原 wbOpenDemo（310 轮版本）
    var hooked = false;
    var busy = false;                   // 同一时间只发一个请求
    var opened = false;
    var overlay = null, panel = null, listEl = null, msgEl = null;
    var items = [];
    var btnText = '';
    var hookTries = 0;

    /* ---------- 小工具 ---------- */
    function isMobile() {
        try {
            if (window.innerWidth && window.innerWidth <= 768) return true;
            return /Android|iPhone|iPad|iPod|Mobile|Windows Phone/i.test(navigator.userAgent || '');
        } catch (e) { return false; }
    }

    function toast(msg, type) {
        try {
            if (typeof window.wbToast === 'function') {
                window.wbToast(msg, { type: type || 'info' });
                return;
            }
        } catch (e) {}
        try { if (typeof wbToast === 'function') wbToast(msg, { type: type || 'info' }); } catch (e2) {}
    }

    /* 统一请求：404 / 500 / 非 JSON / 网络异常 / 超时 全收敛成结构化结果。
       调用方只看 res.fail 与 res.data，绝不让它抛到外面去。 */
    function getJSON(url, cb) {
        var done = false;
        function fin(v) {
            if (done) return;
            done = true;
            try { cb(v); } catch (e) { console.warn('[wbdemo] 回调异常：', e); }
        }
        var timer = setTimeout(function () { fin({ fail: true }); }, TIMEOUT);
        function stop() { try { clearTimeout(timer); } catch (e) {} }
        try {
            if (typeof window.fetch !== 'function') { stop(); fin({ fail: true }); return; }
            window.fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
                .then(function (r) {
                    return r.text().then(function (t) { return { status: r.status, text: t }; });
                })
                .then(function (res) {
                    stop();
                    var d = null;
                    try { d = JSON.parse(res.text); } catch (e) { d = null; }
                    fin({ status: res.status, data: d });
                }, function () { stop(); fin({ fail: true }); });
        } catch (e) { stop(); fin({ fail: true }); }
    }

    /* 按钮 loading：记住原文案，恢复时原样写回 */
    function setBtn(on, text) {
        try {
            var b = document.getElementById('wbDemoBtn');
            if (!b) return;
            if (on) {
                if (!btnText) btnText = b.textContent || '';
                b.disabled = true;
                if (text) b.textContent = text;
                b.style.opacity = '.65';
            } else {
                b.disabled = false;
                if (btnText) b.textContent = btnText;
                b.style.opacity = '';
            }
        } catch (e) {}
    }

    /* ---------- 列表解析 ---------- */
    /* 同时兼容 items / samples 两个字段名；字段缺失就不显示，不拿默认值凑数 */
    function parseList(res) {
        try {
            if (!res || res.fail || !res.data) return [];
            var d = res.data;
            if (d.success !== true) return [];
            var arr = null;
            if (d.items && d.items.length) arr = d.items;
            else if (d.samples && d.samples.length) arr = d.samples;
            if (!arr || !arr.length) return [];

            var out = [];
            for (var i = 0; i < arr.length; i++) {
                var it = arr[i];
                if (!it || typeof it !== 'object') continue;
                var key = it.key ? String(it.key) : '';
                var title = it.title ? String(it.title) : '';
                if (!key || !title) continue;      // 没 key 没法取样例，没标题没法选
                out.push({
                    key: key,
                    title: title,
                    competition: it.competition ? String(it.competition) : '',
                    summary: it.summary ? String(it.summary) : '',
                    tier: it.tier ? String(it.tier) : '',
                    chars: (typeof it.chars === 'number' && it.chars > 0) ? it.chars : 0,
                    updated: it.updated ? String(it.updated) : ''
                });
            }
            return out;
        } catch (e) { return []; }
    }

    function tierText(t) {
        if (t === 'deep') return '深度版';
        if (t === 'fast') return '快速版';
        return t;                                   // 认不出的档位原样显示，不编造
    }

    function num(n) {
        return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    /* ---------- 面板 ---------- */
    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }

    function buildPanel() {
        if (panel) return panel;

        overlay = el('div', 'wbdemo-overlay');
        overlay.id = 'wbDemoOverlay';
        overlay.addEventListener('click', function () { close(); });
        document.body.appendChild(overlay);

        panel = el('div', 'wbdemo-panel');
        panel.id = 'wbDemoPanel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'true');
        panel.setAttribute('aria-label', '选择演示样例');

        var head = el('div', 'wbdemo-head');
        head.appendChild(el('b', 'wbdemo-title', '🎬 选择演示样例'));
        var closeBtn = el('button', 'wbdemo-close', '×');
        closeBtn.setAttribute('type', 'button');
        closeBtn.setAttribute('aria-label', '关闭');
        closeBtn.addEventListener('click', function () { close(); });
        head.appendChild(closeBtn);
        panel.appendChild(head);

        listEl = el('div', 'wbdemo-list');
        panel.appendChild(listEl);

        msgEl = el('div', 'wbdemo-msg');
        panel.appendChild(msgEl);

        panel.appendChild(el('div', 'wbdemo-foot',
            '选一份样例直接看完整结果页；内容是预置的，不消耗额度'));

        document.body.appendChild(panel);

        document.addEventListener('keydown', function (e) {
            if (!opened) return;
            if (e.key === 'Escape' || e.keyCode === 27) close();
        });

        return panel;
    }

    function showMsg(text) {
        if (!msgEl) return;
        msgEl.textContent = text || '';
        if (text) msgEl.classList.add('wbdemo-show');
        else msgEl.classList.remove('wbdemo-show');
    }

    function renderCards() {
        if (!listEl) return;
        listEl.innerHTML = '';
        for (var i = 0; i < items.length; i++) {
            (function (it) {
                var card = el('button', 'wbdemo-card');
                card.setAttribute('type', 'button');
                card.appendChild(el('div', 'wbdemo-card-title', it.title));
                if (it.competition) card.appendChild(el('div', 'wbdemo-card-sub', it.competition));
                if (it.summary) card.appendChild(el('div', 'wbdemo-card-sum', it.summary));

                var meta = [];
                if (it.tier) meta.push(tierText(it.tier));
                if (it.chars) meta.push(num(it.chars) + ' 字');
                if (it.updated) meta.push('更新 ' + it.updated);
                if (meta.length) {
                    var m = el('div', 'wbdemo-meta');
                    for (var k = 0; k < meta.length; k++) m.appendChild(el('span', 'wbdemo-tag', meta[k]));
                    card.appendChild(m);
                }

                card.addEventListener('click', function () { pick(it, card); });
                listEl.appendChild(card);
            })(items[i]);
        }
    }

    function showLoading(text) {
        if (!listEl) return;
        listEl.innerHTML = '';
        listEl.appendChild(el('div', 'wbdemo-loading', text));
    }

    function open() {
        try {
            buildPanel();
            if (!panel) return;
            renderCards();
            showMsg('');
            overlay.classList.add('wbdemo-show');
            panel.classList.add('wbdemo-show');
            opened = true;
        } catch (e) { console.warn('[wbdemo] 面板打开失败：', e); }
    }

    function close() {
        try {
            if (overlay) overlay.classList.remove('wbdemo-show');
            if (panel) panel.classList.remove('wbdemo-show');
            opened = false;
        } catch (e) {}
    }

    /* ---------- 打开某一份样例 ---------- */
    /* openHistory 是 app.js 里的私有函数、不在 window 上（已 grep 确认），
       所以退一步：临时拦一次 /static/demo_sample.json，把选中的样例喂给
       原 wbOpenDemo()，原样复用 310 轮修好的那套解析 + 渲染 + 按钮复位。 */
    function openViaOrig(raw) {
        if (typeof orig !== 'function') return null;
        var _f = window.fetch;
        var pending = raw;
        window.fetch = function (input) {
            try {
                var u = (typeof input === 'string') ? input : ((input && input.url) || '');
                if (pending && u && String(u).indexOf('/static/demo_sample.json') >= 0) {
                    var body = JSON.stringify(pending);
                    pending = null;
                    return Promise.resolve(new Response(body, {
                        status: 200, headers: { 'Content-Type': 'application/json' }
                    }));
                }
            } catch (e) {}
            return _f.apply(window, arguments);
        };
        function restore() { try { window.fetch = _f; } catch (e) {} }
        try {
            var r = orig();
            if (r && typeof r.then === 'function') {
                return r.then(function (v) { restore(); return v; },
                              function (e) { restore(); throw e; });
            }
            restore();
            return null;
        } catch (e) { restore(); return null; }
    }

    function openChosen(raw, id, done) {
        var finished = false;
        function fin() {
            if (finished) return;
            finished = true;
            try { window.__wbDemoData = null; } catch (e) {}   // 渲染完立刻清掉
            setBtn(false);
            try { done(); } catch (e) {}
        }
        try {
            var payload = (raw && raw.data && typeof raw.data === 'object') ? raw.data : raw;
            if (typeof window.openHistory === 'function') {
                window.__wbDemoData = payload;                 // 层级铁律：存 data 那一层
                try { toast('已载入演示样例（预置内容，非实时生成）', 'info'); } catch (e) {}
                var p = window.openHistory(id || 0);
                if (p && typeof p.then === 'function') { p.then(fin, fin); return; }
                fin();
                return;
            }
            var p2 = openViaOrig(raw);
            if (p2 && typeof p2.then === 'function') { p2.then(fin, fin); return; }
            fin();
        } catch (e) {
            console.warn('[wbdemo] 渲染演示样例失败：', e);
            fin();
        }
    }

    function pick(it, card) {
        if (busy) return;
        busy = true;
        try {
            var cards = listEl ? listEl.querySelectorAll('.wbdemo-card') : [];
            for (var i = 0; i < cards.length; i++) cards[i].disabled = true;
        } catch (e) {}
        setBtn(true, '演示加载中…');
        showMsg('');
        if (card) showLoading('正在载入这份样例…');

        getJSON(SAMPLE_URL + '?key=' + encodeURIComponent(it.key), function (res) {
            var raw = null;
            try {
                if (!res || res.fail || !res.data) throw new Error('接口不可用');
                var d = res.data;
                if (d.success !== true) throw new Error((d && d.error) || '没有可用的演示样例');
                var payload = (d.data && typeof d.data === 'object') ? d.data : d;
                if (!payload || !payload.proposal) throw new Error('样例正文为空');
                raw = d;
            } catch (e) {
                console.warn('[wbdemo] 样例「' + it.key + '」加载失败，回落到原一键演示：',
                    (e && e.message) || e);
                busy = false;
                close();
                fallback();
                return;
            }
            close();
            var id = (raw && raw.id) || (raw.data && raw.data.id) || 0;
            openChosen(raw, id, function () { busy = false; });
        });
    }

    /* ---------- 降级：一切照旧 ---------- */
    function fallback() {
        setBtn(false);
        try {
            if (typeof orig === 'function') { orig(); return; }
        } catch (e) { console.warn('[wbdemo] 原一键演示调用失败：', e); }
        try { if (typeof window.wbOpenDemo === 'function') window.wbOpenDemo(); } catch (e2) {}
    }

    /* ---------- 入口：接管「一键演示」 ---------- */
    function onDemoClick() {
        if (busy) return;
        busy = true;
        setBtn(true, '加载中…');
        getJSON(LIST_URL, function (res) {
            var list = parseList(res);
            busy = false;
            if (!list || list.length < 2) {
                // 后端没部署 / 空列表 / 只有一份 / 出错 / 超时 —— 一律走原路径
                console.warn('[wbdemo] 样例列表不可用（可用 ' + (list ? list.length : 0)
                    + ' 条），走原一键演示');
                fallback();
                return;
            }
            items = list;
            setBtn(false);
            open();
        });
    }

    function hookedFn() {
        try { onDemoClick(); } catch (e) {
            console.warn('[wbdemo] 选择器异常，走原一键演示：', e);
            busy = false;
            fallback();
        }
    }

    function install() {
        if (hooked) return true;
        var f = window.wbOpenDemo;
        if (typeof f !== 'function' || f === hookedFn) return false;
        orig = f;                       // 原函数留着，任何异常都回落到这里
        window.wbOpenDemo = hookedFn;
        hooked = true;
        return true;
    }

    function waitInstall() {
        if (hooked) return;
        if (install()) return;
        hookTries++;
        if (hookTries < HOOK_MAX_TRY) setTimeout(waitInstall, 250);
    }

    window.wbDemo = {
        open: function () { if (items.length) open(); },
        close: close,
        isHooked: function () { return hooked; },
        itemCount: function () { return items.length; },
        reload: function () {
            getJSON(LIST_URL, function (res) {
                var list = parseList(res);
                if (list && list.length >= 2) { items = list; if (opened) renderCards(); }
            });
        }
    };

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () { waitInstall(); });
        } else {
            waitInstall();
        }
    } catch (e) {}
})();
