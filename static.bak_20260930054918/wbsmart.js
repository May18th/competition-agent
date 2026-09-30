/* ============================================================
 * 第三百零八轮：段落 / 图表「智能解读」前端 UI
 * 独立文件：浮层一律 appendChild 到 document.body，不碰正文 DOM、不改 app.js / index.html
 *
 * - 触发一：划选 / 长按选中段落（≥8 字）→ 在选区上方弹出「智能解读」浮动操作
 * - 触发二：图表不可划选，改为点按（移动端）与悬停 300ms（桌面）弹出同样的浮动操作
 *   覆盖：结果页智能图表卡片（#richCharts）、ECharts 容器（预算/市场/时间线）、
 *         创意五维雷达 SVG（#ideaRadar）
 * - 接口：POST /api/analyze_segment {text, kind} → {success, analysis, error}
 *   失败一律降级成气泡内友好文案，不弹堆栈、不影响正文；404 / 网络异常显示「解读服务暂不可用」
 * - 文案红线：按钮与标题只写「智能解读」，不出现其它含 AI 字样的叫法
 * - 数据红线：图表读不到数据就只发标题，绝不编造数字
 * - ES5 语法，全 try/catch，只暴露 window.wbSmart
 * ============================================================ */
(function () {
    if (window.wbSmart) return;                 // 防重复注入

    var API = '/api/analyze_segment';
    var MIN_LEN = 8;          // 太短不解读：避免评分数字、单词标签误触发
    var MAX_LEN = 3000;       // 后端同样按 3000 截断，前端先截一次省流量
    var HOVER_DELAY = 300;    // 桌面悬停防误触
    var WAIT_MS = 8000;       // 8 秒无响应给「稍后再试」
    var EDGE = 10;            // 视口安全边距

    var ICON = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none"'
        + ' stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M12 3.2l1.7 4.3 4.3 1.7-4.3 1.7L12 15.2l-1.7-4.3L6 9.2l4.3-1.7z"/>'
        + '<path d="M18.4 15.4l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"/></svg>';

    var busy = false;
    var bar = null, pop = null, popBody = null;
    var hoverTimer = null, reqSeq = 0;
    var ctx = { text: '', kind: 'text', el: null };

    /* ---------------- 小工具 ---------------- */
    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function isMobile() { return window.innerWidth <= 768; }
    function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
    function txtOf(node) {
        return node ? String(node.textContent || '').replace(/\s+/g, ' ').trim() : '';
    }
    function rectOf(el) {
        try { return el.getBoundingClientRect(); } catch (e) { return null; }
    }
    function inOverlay(t) {
        if (!t) return false;
        if (bar && bar.contains && bar.contains(t)) return true;
        if (pop && pop.contains && pop.contains(t)) return true;
        return false;
    }
    function clearHover() {
        if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null; }
    }

    /* ---------------- 图表识别：事件委托，图表后生成也能命中 ---------------- */
    function chartFrom(t) {
        if (!t || t.nodeType !== 1 || !t.closest) return null;
        try {
            var card = t.closest('#richCharts > div');
            if (card) return { el: card };
            var radar = t.closest('#ideaRadar');
            if (radar) return { el: radar };
            var n = t;
            for (var i = 0; i < 6 && n; i++) {
                if (window.echarts && typeof echarts.getInstanceByDom === 'function'
                    && echarts.getInstanceByDom(n)) return { el: n };
                n = n.parentElement;
            }
        } catch (e) {}
        return null;
    }

    /* 图表标题：data 属性 → 自身内标题 → 前置兄弟标题 → 图片 alt，读不到就返回「图表」 */
    function chartTitle(el) {
        var i, n = el;
        for (i = 0; i < 3 && n && n.getAttribute; i++) {
            var d = n.getAttribute('data-chart-title') || n.getAttribute('data-title') || n.getAttribute('aria-label');
            if (d && String(d).trim().length && String(d).length < 80) return String(d).trim();
            n = n.parentElement;
        }
        var h = el.querySelector && el.querySelector('h1,h2,h3,h4,h5,h6,.chart-title,[data-chart-title]');
        if (h) {
            var ht = txtOf(h);
            if (ht && ht.length < 80) return ht;
        }
        n = el;
        for (i = 0; i < 3 && n; i++) {
            var p = n.previousElementSibling;
            if (p) {
                var pt = txtOf(p);
                if (pt && pt.length > 0 && pt.length <= 40
                    && (/^H[1-6]$/.test(p.tagName) || p.children.length === 0)) return pt;
            }
            n = n.parentElement;
        }
        var img = el.querySelector && el.querySelector('img[alt]');
        if (img && img.alt) return String(img.alt).trim();
        return '图表';
    }

    /* 图表关键数据：只从 ECharts 实例 / SVG 文本里读真值，读不到就返回空串（绝不编数字） */
    function chartData(el) {
        var parts = [];
        try {
            var inst = null;
            if (window.echarts && typeof echarts.getInstanceByDom === 'function') {
                inst = echarts.getInstanceByDom(el);
                var n = el.parentElement;
                for (var i = 0; i < 6 && n && !inst; i++) {
                    inst = echarts.getInstanceByDom(n);
                    n = n.parentElement;
                }
            }
            if (inst && inst.getOption) {
                var op = inst.getOption() || {};
                var xs = (op.xAxis && op.xAxis[0] && op.xAxis[0].data) || null;
                var ss = op.series || [];
                for (var s = 0; s < ss.length && parts.length < 16; s++) {
                    var se = ss[s] || {};
                    var ds = se.data || [];
                    for (var k = 0; k < ds.length && parts.length < 16; k++) {
                        var it = ds[k];
                        if (it && typeof it === 'object' && it.name !== undefined && it.value !== undefined) {
                            parts.push(String(it.name) + ' ' + String(it.value));      // 饼图/类目值
                        } else {
                            var lb = (xs && xs[k] !== undefined && xs[k] !== null) ? String(xs[k]) : ('第' + (k + 1) + '项');
                            parts.push(lb + '：' + String(it));
                        }
                    }
                }
            }
        } catch (e) {}

        // 纯 SVG 图（如创意五维雷达）：读画布上的真实文字标签
        if (!parts.length && el.querySelectorAll) {
            try {
                var ts = el.querySelectorAll('svg text');
                for (var j = 0; j < ts.length && parts.length < 12; j++) {
                    var v = txtOf(ts[j]);
                    if (v && /[\u4e00-\u9fa5]/.test(v) && parts.indexOf(v) < 0) parts.push(v);
                }
            } catch (e2) {}
        }
        return parts.join('；');
    }

    function buildChartText(el) {
        var t = chartTitle(el);
        var d = chartData(el);
        return (d ? t + '\n关键数据：' + d : t).slice(0, MAX_LEN);
    }

    /* ---------------- 浮动操作条 ---------------- */
    function ensureBar() {
        if (bar) return bar;
        bar = document.createElement('div');
        bar.id = 'wbSmartBar';
        bar.className = 'wb-smart-bar';
        bar.setAttribute('role', 'button');
        bar.setAttribute('aria-label', '智能解读选中内容');
        bar.innerHTML = '<span class="wb-smart-ico">' + ICON + '</span>'
            + '<span class="wb-smart-txt">智能解读</span>';
        bar.addEventListener('click', function (e) {
            if (e && e.stopPropagation) e.stopPropagation();
            if (busy) return;
            openPop();
        });
        bar.addEventListener('mousedown', function (e) { if (e && e.stopPropagation) e.stopPropagation(); });
        bar.addEventListener('mouseup', function (e) { if (e && e.stopPropagation) e.stopPropagation(); });
        bar.addEventListener('touchstart', function (e) { if (e && e.stopPropagation) e.stopPropagation(); }, { passive: true });
        document.body.appendChild(bar);
        return bar;
    }

    /* 定位：优先放锚点上方，上方放不下翻到下方；left 用 min/max 夹在视口内 */
    function place(el, rect, preferAbove, fullWidth) {
        el.style.display = 'flex';
        el.style.visibility = 'hidden';
        var w = el.offsetWidth, h = el.offsetHeight;
        var vw = window.innerWidth, vh = window.innerHeight;
        if (fullWidth && isMobile()) {
            el.style.left = EDGE + 'px';
            el.style.right = EDGE + 'px';
            el.style.width = 'auto';
        } else {
            el.style.right = '';
            el.style.width = '';
            var left = rect.left + rect.width / 2 - w / 2;
            el.style.left = clamp(left, EDGE, Math.max(EDGE, vw - w - EDGE)) + 'px';
        }
        var top = preferAbove ? (rect.top - h - 8) : (rect.bottom + 8);
        if (preferAbove && top < EDGE) top = rect.bottom + 8;
        if (!preferAbove && top + h > vh - EDGE) top = rect.top - h - 8;
        el.style.top = clamp(top, EDGE, Math.max(EDGE, vh - h - EDGE)) + 'px';
        el.style.visibility = '';
    }

    function showBar(rect, text, kind, el) {
        if (!rect || !text) return;
        if (busy) return;                       // 请求中忽略新触发
        hidePop();
        ensureBar();
        ctx.text = text; ctx.kind = kind; ctx.el = el || null;
        place(bar, rect, true, false);
    }

    function hideBar() {
        if (bar) bar.style.display = 'none';
        ctx.el = null;
    }

    /* ---------------- 解读气泡 ---------------- */
    function ensurePop() {
        if (pop) return pop;
        pop = document.createElement('div');
        pop.id = 'wbSmartPop';
        pop.className = 'wb-smart-pop';
        pop.innerHTML =
            '<div class="wb-smart-head">'
          + '<span class="wb-smart-ico">' + ICON + '</span>'
          + '<b class="wb-smart-title">智能解读</b>'
          + '<button class="wb-smart-close" id="wbSmartClose" aria-label="收起" type="button">×</button>'
          + '</div>'
          + '<div class="wb-smart-body" id="wbSmartBody"></div>';
        pop.addEventListener('mousedown', function (e) { if (e && e.stopPropagation) e.stopPropagation(); });
        pop.addEventListener('mouseup', function (e) { if (e && e.stopPropagation) e.stopPropagation(); });
        pop.addEventListener('click', function (e) { if (e && e.stopPropagation) e.stopPropagation(); });
        pop.addEventListener('touchstart', function (e) { if (e && e.stopPropagation) e.stopPropagation(); }, { passive: true });
        document.body.appendChild(pop);
        popBody = document.getElementById('wbSmartBody');
        var close = document.getElementById('wbSmartClose');
        if (close) close.addEventListener('click', function (e) {
            if (e && e.stopPropagation) e.stopPropagation();
            hidePop();
        });
        return pop;
    }

    function popRect() {
        var r = (ctx.el && rectOf(ctx.el)) || null;
        if (r && r.width) return r;
        if (bar && bar.style.display === 'flex') return rectOf(bar);
        return { left: window.innerWidth / 2 - 40, top: window.innerHeight / 2, width: 80, bottom: window.innerHeight / 2, height: 0 };
    }

    function openPop() {
        if (!ctx.text) return;
        ensurePop();
        hideBar();
        var r = popRect();
        var below = r.bottom + 8 + 320 < window.innerHeight;
        place(pop, r, !below, true);
        analyze();
    }

    function hidePop() {
        if (pop) pop.style.display = 'none';
        if (busy) { reqSeq++; busy = false; }   // 中途收起：丢弃迟到的响应，不留死界面
    }

    function renderLoading() {
        if (!popBody) return;
        popBody.innerHTML = '';
        var d = document.createElement('div');
        d.className = 'wb-smart-loading';
        d.innerHTML = '<span class="wb-smart-spin" aria-hidden="true"></span><span>正在解读…</span>';
        popBody.appendChild(d);
        var sk = document.createElement('div');
        sk.className = 'wb-smart-skel';
        sk.innerHTML = '<i></i><i></i><i></i>';
        popBody.appendChild(sk);
    }

    function renderText(s) {
        if (!popBody) return;
        popBody.innerHTML = '';
        var lines = String(s || '').split(/\n+/);
        for (var i = 0; i < lines.length; i++) {
            var t = lines[i].replace(/^\s+|\s+$/g, '');
            if (!t) continue;
            var p = document.createElement('p');
            p.className = 'wb-smart-p';
            p.textContent = t;                  // textContent 落地，杜绝注入
            popBody.appendChild(p);
        }
    }

    function renderMsg(s, retry) {
        if (!popBody) return;
        popBody.innerHTML = '';
        var d = document.createElement('div');
        d.className = 'wb-smart-msg';
        d.textContent = String(s || '');
        popBody.appendChild(d);
        if (retry) {
            var b = document.createElement('button');
            b.className = 'wb-smart-retry';
            b.type = 'button';
            b.textContent = '重试';
            b.addEventListener('click', function (e) {
                if (e && e.stopPropagation) e.stopPropagation();
                analyze();
            });
            popBody.appendChild(b);
        }
    }

    /* ---------------- 请求：同一时间只发一个 ---------------- */
    function analyze() {
        if (busy || !ctx.text) return;
        busy = true;
        var seq = ++reqSeq;
        if (bar) bar.classList.add('wb-smart-busy');
        renderLoading();
        var settled = false;
        var timer = setTimeout(function () {
            if (seq !== reqSeq) return;
            reqSeq++;                           // 迟到响应作废
            busy = false;
            if (bar) bar.classList.remove('wb-smart-busy');
            renderMsg('解读有点慢，稍后再试', true);
        }, WAIT_MS);

        function done(msg, retry) {
            if (settled || seq !== reqSeq) return;
            settled = true;
            clearTimeout(timer);
            busy = false;
            if (bar) bar.classList.remove('wb-smart-busy');
            renderMsg(msg, retry);
        }
        function ok(s) {
            if (settled || seq !== reqSeq) return;
            settled = true;
            clearTimeout(timer);
            busy = false;
            if (bar) bar.classList.remove('wb-smart-busy');
            renderText(s);
        }

        try {
            fetch(API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: String(ctx.text).slice(0, MAX_LEN), kind: ctx.kind })
            }).then(function (r) {
                if (!r) return null;
                if (r.status === 404) return null;                 // 未部署 → 静默降级
                return r.json().catch(function () { return null; });
            }).then(function (j) {
                if (j && j.success === true && j.analysis) { ok(String(j.analysis)); return; }
                if (j && j.error) { done(String(j.error), false); return; }
                done('解读服务暂不可用', false);
            }).catch(function () { done('解读服务暂不可用', false); });
        } catch (e) {
            done('解读服务暂不可用', false);
        }
    }

    /* ---------------- 事件 ---------------- */
    function hasWord(s) { return /[\u4e00-\u9fa5A-Za-z]/.test(s); }

    function onUp(e) {
        try {
            if (inOverlay(e && e.target)) return;
            var sel = window.getSelection ? window.getSelection() : null;
            var s = sel ? String(sel.toString() || '').trim() : '';
            if (!s || s.length < MIN_LEN || !hasWord(s)) { hideBar(); return; }
            var rect = null;
            try { if (sel.rangeCount) rect = sel.getRangeAt(0).getBoundingClientRect(); } catch (e2) {}
            if (!rect || (!rect.width && !rect.height && !rect.top)) { hideBar(); return; }
            showBar(rect, s.slice(0, MAX_LEN), 'text', null);
        } catch (e3) {}
    }

    function onDown(e) {
        if (inOverlay(e && e.target)) return;
        if (busy) return;                        // 请求中忽略新触发
        if (chartFrom(e && e.target)) { clearHover(); return; }
        hideBar();
        hidePop();
    }

    function boot() {
        try {
            document.addEventListener('mouseup', onUp);
            document.addEventListener('touchend', function (e) {
                // 移动端长按选中：等一帧让选区落定再读
                setTimeout(function () { onUp(e); }, 80);
            });
            document.addEventListener('mousedown', onDown);
            document.addEventListener('touchstart', function (e) { onDown(e); }, { passive: true });

            document.addEventListener('mouseover', function (e) {
                var c = chartFrom(e && e.target);
                if (!c) { clearHover(); return; }
                if (bar && ctx.el === c.el && bar.style.display === 'flex') return;
                clearHover();
                hoverTimer = setTimeout(function () {
                    var r = rectOf(c.el);
                    if (r) showBar(r, buildChartText(c.el), 'chart', c.el);
                }, HOVER_DELAY);
            });
            document.addEventListener('mouseout', clearHover);
            document.addEventListener('click', function (e) {
                clearHover();
                var c = chartFrom(e && e.target);
                if (!c) return;
                var r = rectOf(c.el);
                if (r) showBar(r, buildChartText(c.el), 'chart', c.el);
            });

            document.addEventListener('keydown', function (e) {
                if (e && (e.key === 'Escape' || e.keyCode === 27)) { hidePop(); hideBar(); }
            });
            window.addEventListener('scroll', function () { if (!busy) hideBar(); }, { passive: true });
            window.addEventListener('resize', function () {
                clearHover();
                if (!busy) { hideBar(); hidePop(); }
            });
        } catch (e) {}
    }

    window.wbSmart = {
        close: function () { hidePop(); hideBar(); },
        analyzeText: function (t) {
            if (!t) return;
            ctx.text = String(t).slice(0, MAX_LEN); ctx.kind = 'text'; ctx.el = null;
            var r = { left: window.innerWidth / 2 - 60, top: window.innerHeight / 2, width: 120, bottom: window.innerHeight / 2, height: 0 };
            ensurePop();
            place(pop, r, true, true);
            analyze();
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
