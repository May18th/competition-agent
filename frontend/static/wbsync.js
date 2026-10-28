/* ============================================================
 * 304 轮：跨设备同步（同步码）前端 UI —— 独立文件，不碰 index.html / app.js
 * ------------------------------------------------------------
 * 背景（根因是查出来的，不是猜的）：
 *   桌面端切赛事 iCAN→挑战杯，移动端刷新仍是 iCAN。原因是两个设备各自持有独立的
 *   comp_uid cookie，而 /api/user_state 按 uid 隔离数据。后端 304 轮已上线跨设备
 *   绑定能力（同步码），本文件只补前端 UI。
 *
 * 接口契约（后端已上线）：
 *   GET  /api/sync_code  → {success:true, sync_code:"AB3CD5E7"} | {success:false, error:"…"}
 *   POST /api/bind_uid   {code:"AB3CD5E7"} → {success:true, bound:true} | {success:false, error:"…"}
 *   ⚠️ 坑 1：错误响应也是 HTTP 200，必须看 success 字段，不能只看 r.ok。
 *   ⚠️ 坑 2：code 后端会 strip().upper()，前端传小写也没关系。
 *   ⚠️ 坑 3：演示只读态（role=readonly）会被全局 403 拦截，响应体仍是 JSON
 *            {success:false, error:"演示账号为只读…"}，403 也要读 body 拿友好文案。
 *
 * 降级纪律：任何 403 / 404 / 网络异常一律静默，不抛错、不弹红字堆栈、不影响页面
 *   其它功能。入口注入前先探测 /api/sync_code，拿不到码就不注入菜单项（演示只读态）。
 *
 * 红线遵守：不新增 text-overflow:ellipsis / -webkit-line-clamp / white-space:nowrap；
 *   不写死深色（跟随 var(--text) / var(--surface-solid) / var(--line) / var(--c-a)）；
 *   不写死任何实测统计数字。
 *
 * ES5 语法，全 try/catch，只暴露 window.wbSync。
 * ============================================================ */
(function () {
    'use strict';
    if (window.__wbSyncOn) return;               // 防重复注入
    window.__wbSyncOn = true;

    /* ---------- 状态 ---------- */
    var CODE_URL = '/api/sync_code';
    var BIND_URL = '/api/bind_uid';

    var cachedCode = '';        // 探测成功后缓存，开面板直接用
    var probeOk = false;        // 探测通过才注入入口
    var entryInjected = false;
    var menuTries = 0;
    var MENU_MAX_TRY = 40;      // 轮询 40 次 × 300ms ≈ 12s，等 #wbMoreMenu 出现

    var busy = false;           // 同时只发一个请求，防连点
    var opened = false;
    var overlay = null, panel = null;
    var codeBox = null, codeText = null, copyBtn = null;
    var inputEl = null, bindBtn = null, msgEl = null;

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
        // 兜底：项目 toast 不可用时的极简提示（不阻塞、不影响其它功能）
        try {
            var t = document.createElement('div');
            t.textContent = msg;
            t.style.cssText = 'position:fixed; left:50%; bottom:24px; transform:translateX(-50%);'
                + ' z-index:3200; max-width:min(92vw,360px); padding:10px 14px; border-radius:10px;'
                + ' background:var(--surface-solid,#fff); color:var(--text);'
                + ' border:1px solid var(--line,rgba(148,163,184,.4));'
                + ' box-shadow:0 18px 50px rgba(15,23,42,.28); font-size:13px; line-height:1.5;';
            document.body.appendChild(t);
            setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3000);
        } catch (e2) {}
    }

    /* 统一请求：把 403/404/网络异常都收敛成结构化结果，调用方只看字段 */
    function request(url, opt, cb) {
        var done = false;
        function fin(res) { if (done) return; done = true; try { cb(res); } catch (e) {} }
        try {
            if (typeof window.fetch !== 'function') { fin({ net: true }); return; }
            var init = { method: opt && opt.method ? opt.method : 'GET', credentials: 'same-origin' };
            if (opt && opt.body) {
                init.headers = { 'Content-Type': 'application/json' };
                init.body = JSON.stringify(opt.body);
            } else {
                init.headers = { 'Accept': 'application/json' };
            }
            window.fetch(url, init).then(function (r) {
                var status = r.status;
                // 403（演示只读）/ 404（接口未部署）也要尝试读 body，拿后端给的友好文案
                return r.text().then(function (txt) {
                    var data = null;
                    try { data = JSON.parse(txt); } catch (e) { data = null; }
                    return { status: status, data: data };
                });
            }).then(function (res) {
                fin(res);
            })['catch'](function () { fin({ net: true }); });
        } catch (e) { fin({ net: true }); }
    }

    /* ---------- 接口封装 ---------- */
    function fetchCode(cb) {
        request(CODE_URL, null, function (res) {
            if (!res || res.net) { cb({ state: 'down' }); return; }
            if (res.status === 403) {
                cb({ state: 'deny', msg: (res.data && res.data.error) || '' });
                return;
            }
            if (res.status === 404 || res.status >= 500) { cb({ state: 'down' }); return; }
            var d = res.data;
            if (d && d.success === true && d.sync_code) { cb({ state: 'ok', code: String(d.sync_code) }); return; }
            // success:false（含演示态拿不到码、生成失败）
            cb({ state: 'deny', msg: (d && d.error) || '' });
        });
    }

    function doBind(code, cb) {
        request(BIND_URL, { method: 'POST', body: { code: code } }, function (res) {
            if (!res || res.net) { cb({ ok: false, msg: '网络异常，请稍后再试' }); return; }
            if (res.status === 403) {
                cb({ ok: false, msg: (res.data && res.data.error) || '演示账号为只读，暂不支持绑定' });
                return;
            }
            if (res.status === 404 || res.status >= 500) { cb({ ok: false, msg: '同步功能暂不可用' }); return; }
            var d = res.data;
            if (d && d.success === true) { cb({ ok: true }); return; }
            cb({ ok: false, msg: (d && d.error) || '绑定失败，请稍后再试' });
        });
    }

    /* ---------- 面板 ---------- */
    function esc(s) {
        return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function buildPanel() {
        if (panel) return panel;

        overlay = document.createElement('div');
        overlay.id = 'wbXSyncOverlay';
        overlay.style.cssText = 'position:fixed; left:0; top:0; right:0; bottom:0;'
            + ' z-index:2999; background:rgba(15,23,42,.45); display:none;';
        overlay.addEventListener('click', function () { close(); });
        document.body.appendChild(overlay);

        panel = document.createElement('div');
        panel.id = 'wbXSyncPanel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'true');
        panel.setAttribute('aria-label', '跨设备同步');
        panel.style.cssText = 'position:fixed; left:50%; top:50%; transform:translate(-50%,-50%);'
            + ' z-index:3000; display:none; width:min(92vw,360px); max-width:92vw;'
            + ' max-height:86vh; overflow-y:auto; box-sizing:border-box;'
            + ' background:var(--surface-solid,#fff); color:var(--text);'
            + ' border:1px solid var(--line,rgba(148,163,184,.4)); border-radius:14px;'
            + ' box-shadow:0 18px 50px rgba(15,23,42,.28);';

        var mob = isMobile();
        var btnMinH = '40px';

        panel.innerHTML =
            // 标题栏
            '<div style="display:flex; align-items:center; gap:8px; padding:12px 14px;'
          + ' border-bottom:1px solid var(--line,rgba(148,163,184,.3));">'
          + '<b style="font-size:13.5px; color:var(--text); line-height:1.35;">📱 跨设备同步</b>'
          + '<button id="wbXSyncClose" aria-label="关闭" style="margin-left:auto; width:28px; height:28px;'
          + ' border-radius:8px; border:1px solid var(--line); background:transparent;'
          + ' color:var(--text-dim); cursor:pointer; line-height:1;">×</button></div>'

            // 本机同步码
          + '<div style="padding:14px 14px 0;">'
          + '<div style="font-size:12px; color:var(--text-dim); margin-bottom:8px;">本机同步码</div>'
          + '<div id="wbXSyncCodeBox" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">'
          + '<div id="wbXSyncCodeText" style="flex:1 1 auto; min-width:0; padding:10px 4px 10px 10px;'
          + ' border:1px dashed var(--line,rgba(148,163,184,.5)); border-radius:10px;'
          + ' font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
          + ' font-size:' + (mob ? '24px' : '26px') + '; font-weight:700; letter-spacing:6px;'
          + ' color:var(--text); text-align:center; line-height:1.3;">加载中…</div>'
          + '<button id="wbXSyncCopy" style="flex:0 0 auto; min-height:' + btnMinH + '; padding:0 14px;'
          + ' border-radius:10px; border:1px solid var(--line); background:transparent;'
          + ' color:var(--text-dim); font-size:13px; cursor:pointer;">复制</button>'
          + '</div></div>'

            // 说明
          + '<div style="margin:12px 14px 0; padding-top:12px;'
          + ' border-top:1px solid var(--line,rgba(148,163,184,.3));'
          + ' font-size:11.5px; color:var(--text-mute); line-height:1.6;">'
          + '在另一台设备输入这个码，两台设备就会共享同一份历史、草稿与赛事选择</div>'

            // 输入对方码
          + '<div style="padding:12px 14px 14px;">'
          + '<div style="display:flex; gap:8px; align-items:stretch; flex-wrap:wrap;">'
          + '<input id="wbXSyncInput" placeholder="输入对方的同步码" autocomplete="off"'
          + ' style="flex:1 1 auto; min-width:0; min-height:' + btnMinH + '; padding:8px 12px;'
          + ' border-radius:10px; border:1px solid var(--line,rgba(148,163,184,.4));'
          + ' background:transparent; color:var(--text); font-size:14px; letter-spacing:2px;'
          + ' font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; box-sizing:border-box;">'
          + '<button id="wbXSyncBind" style="flex:0 0 auto; min-height:' + btnMinH + '; padding:0 16px;'
          + ' border-radius:10px; border:none; background:var(--c-a,#2563eb); color:#fff;'
          + ' font-size:13px; cursor:pointer;">绑定</button>'
          + '</div>'
          + '<div id="wbXSyncMsg" style="margin-top:10px; font-size:12px; line-height:1.6;'
          + ' color:var(--text-dim); display:none;"></div>'
          + '</div>';

        document.body.appendChild(panel);

        codeBox = panel.querySelector('#wbXSyncCodeBox');
        codeText = panel.querySelector('#wbXSyncCodeText');
        copyBtn = panel.querySelector('#wbXSyncCopy');
        inputEl = panel.querySelector('#wbXSyncInput');
        bindBtn = panel.querySelector('#wbXSyncBind');
        msgEl = panel.querySelector('#wbXSyncMsg');

        panel.querySelector('#wbXSyncClose').addEventListener('click', function () { close(); });

        copyBtn.addEventListener('click', function () {
            if (busy) return;
            var code = codeText && codeText.getAttribute('data-code') || '';
            if (!code) { setMsg('同步码还没取到，稍等一下再试'); return; }
            copyText(code);
        });

        bindBtn.addEventListener('click', function () { submitBind(); });
        inputEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.keyCode === 13) { submitBind(); }
        });

        document.addEventListener('keydown', function (e) {
            if (!opened) return;
            if (e.key === 'Escape' || e.keyCode === 27) close();
        });

        return panel;
    }

    function setMsg(text, tone) {
        if (!msgEl) return;
        msgEl.textContent = text || '';
        msgEl.style.color = (tone === 'ok') ? 'var(--c-a,#2563eb)' : 'var(--text-dim)';
        msgEl.style.display = text ? 'block' : 'none';
    }

    function copyText(text) {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function () {
                    toast('同步码已复制', 'ok');
                }, function () { legacyCopy(text); });
                return;
            }
        } catch (e) {}
        legacyCopy(text);
    }

    function legacyCopy(text) {
        try {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', 'readonly');
            ta.style.cssText = 'position:fixed; left:-9999px; top:0; opacity:0;';
            document.body.appendChild(ta);
            ta.select();
            var ok = false;
            try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
            if (ta.parentNode) ta.parentNode.removeChild(ta);
            toast(ok ? '同步码已复制' : '复制失败，请手动抄写', ok ? 'ok' : 'warn');
        } catch (e) {
            toast('复制失败，请手动抄写', 'warn');
        }
    }

    /* 渲染同步码区：三种状态 ok / deny(演示态) / down(接口不可用) */
    function renderCode(state, code) {
        if (!codeText) return;
        if (state === 'ok' && code) {
            codeText.textContent = code;
            codeText.setAttribute('data-code', code);
            codeText.style.fontSize = isMobile() ? '24px' : '26px';
            codeText.style.letterSpacing = '6px';
            if (copyBtn) copyBtn.style.display = '';
            return;
        }
        codeText.removeAttribute('data-code');
        codeText.textContent = '暂不可用';
        codeText.style.fontSize = '14px';
        codeText.style.letterSpacing = '0';
        if (copyBtn) copyBtn.style.display = 'none';
    }

    function loadCode() {
        if (busy) return;
        busy = true;
        if (codeText) codeText.textContent = '加载中…';
        fetchCode(function (res) {
            busy = false;
            if (!res) { renderCode('down'); setMsg('同步功能暂不可用'); return; }
            if (res.state === 'ok') {
                cachedCode = res.code;
                renderCode('ok', res.code);
                setMsg('');
                return;
            }
            if (res.state === 'deny') {
                // 演示只读态：后端给了友好文案就照显示，绝不弹红字堆栈
                renderCode('deny');
                setMsg(res.msg || '同步功能暂不可用');
                return;
            }
            renderCode('down');
            setMsg('同步功能暂不可用');
        });
    }

    function submitBind() {
        if (busy) return;
        var code = inputEl ? String(inputEl.value || '').replace(/\s+/g, '') : '';
        if (!code) { setMsg('请输入对方的同步码'); return; }
        busy = true;
        bindBtn.disabled = true;
        bindBtn.textContent = '绑定中…';
        bindBtn.style.opacity = '.65';
        setMsg('');
        doBind(code, function (res) {
            busy = false;
            if (!panel) return;
            bindBtn.disabled = false;
            bindBtn.textContent = '绑定';
            bindBtn.style.opacity = '';
            if (res && res.ok) {
                setMsg('已绑定，跨设备同步已开启', 'ok');
                toast('已绑定，跨设备同步已开启', 'ok');
                // 后端已重签 cookie，刷新后才是共享的那份 state
                setTimeout(function () {
                    try { location.reload(); } catch (e) {}
                }, 600);
                return;
            }
            setMsg((res && res.msg) || '绑定失败，请稍后再试');
        });
    }

    function open() {
        try {
            buildPanel();
            if (!panel) return;
            if (cachedCode) renderCode('ok', cachedCode);
            overlay.style.display = 'block';
            panel.style.display = 'block';
            opened = true;
            setMsg('');
            loadCode();
            setTimeout(function () { try { inputEl && inputEl.focus(); } catch (e) {} }, 60);
        } catch (e) {}
    }

    function close() {
        try {
            if (overlay) overlay.style.display = 'none';
            if (panel) panel.style.display = 'none';
            opened = false;
        } catch (e) {}
    }

    /* ---------- 入口注入（#wbMoreMenu 默认 display:none，轮询等它出现） ---------- */
    function injectEntry() {
        if (entryInjected) return true;
        var menu = document.getElementById('wbMoreMenu');
        if (!menu) return false;

        var btn = document.createElement('button');
        btn.className = 'wb-glass-btn wb-glass-btn-sm';
        btn.id = 'wbXSyncEntry';
        btn.setAttribute('type', 'button');
        btn.title = '用同步码让两台设备共享同一份历史、草稿与赛事选择';
        btn.style.cssText = 'display:flex; width:100%; justify-content:flex-start;'
            + ' border:none; background:transparent; min-height:36px;';
        btn.innerHTML = '<span class="wb-dot"></span>📱 跨设备同步';
        btn.addEventListener('click', function () {
            try { if (typeof window.wbMoreClose === 'function') window.wbMoreClose(); } catch (e) {}
            open();
        });
        menu.appendChild(btn);
        entryInjected = true;
        return true;
    }

    function waitAndInject() {
        if (entryInjected) return;
        if (injectEntry()) return;
        menuTries++;
        if (menuTries < MENU_MAX_TRY) {
            setTimeout(waitAndInject, 300);
        }
    }

    /* ---------- 启动：先探测接口，拿不到码就不注入入口（演示只读态） ---------- */
    function boot() {
        fetchCode(function (res) {
            if (res && res.state === 'ok' && res.code) {
                probeOk = true;
                cachedCode = res.code;
                waitAndInject();
            }
            // 演示只读态 / 404 / 网络异常：不注入入口，页面其它功能不受影响
        });
    }

    window.wbSync = {
        open: open,
        close: close,
        isAvailable: function () { return probeOk; }
    };

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    } catch (e) { boot(); }
})();
