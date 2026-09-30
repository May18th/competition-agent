/* 第二百四十二轮：长结果页导航
   ------------------------------------------------------------------
   ① 242.1 一键到底部：右下角已有 #wbTop（回到顶部，wbpage.js 管显隐），
      这里补一个配对的 ↓「一键到底部」，长的深度版/历史详情页直接翻到
      评分与导出区。按钮由本文件创建，不往 index.html 插 DOM。
   ② 242.2 深度版章节折叠：结果区本来就有一条横向「板块快速定位」锚点条
      （index.html #wbAnchorBar + app.js wbRenderAnchorBar + wbconst.js
      WB_ANCHORS，15 个板块），所以不重复造第二个目录条；
      只补它没有的「章节收起/展开」——非核心的长章节默认收起，
      诊断 / 评审意见（也就是评分区）和导出区默认展开。

   三条纪律：
   - 纯原生 JS，零依赖、零 CDN；
   - 不碰 app.js / wbpage.js / app.py，只在 index.html 追加了一行 script；
   - 折叠只给「内容块的父容器」挂 class + 在既有 h3 里追加一个按钮，
     不插包裹层、不改正文 DOM 结构（导出/复制读的还是同一份 DOM）。
------------------------------------------------------------------ */
(function () {
    'use strict';
    if (window.__wbNavigOn) { return; }
    window.__wbNavigOn = true;

    function $(id) { return document.getElementById(id); }

    /* ================= ① 一键到底部 ================= */

    function docBottom() {
        var b = document.body, d = document.documentElement;
        return Math.max(
            (b && (b.scrollHeight || b.offsetHeight)) || 0,
            (d && (d.scrollHeight || d.offsetHeight)) || 0
        );
    }

    var btnDown = null;

    function ensureBtn() {
        if (btnDown) { return btnDown; }
        var b = document.createElement('button');
        b.id = 'wbBottom';
        b.type = 'button';
        b.title = '一键到底部';
        b.setAttribute('aria-label', '一键到底部');
        b.appendChild(document.createTextNode('\u2193'));
        b.addEventListener('click', function () {
            // 有些老内核吃不下 options 格式的 scrollTo，掉回两参数写法
            try { window.scrollTo({ top: docBottom(), behavior: 'smooth' }); }
            catch (e) { window.scrollTo(0, docBottom()); }
        });
        document.body.appendChild(b);
        btnDown = b;
        return b;
    }

    function syncBtn() {
        try {
            var b = ensureBtn();
            var y = window.scrollY || (document.documentElement && document.documentElement.scrollTop) || 0;
            // 超过一屏才出现，首页短页面别出来挡人
            var show = y > (window.innerHeight || 640);
            if (show) { b.classList.add('wbnav-btn-show'); }
            else { b.classList.remove('wbnav-btn-show'); }
        } catch (e) {}
    }

    // 节流用 setTimeout 而不是 requestAnimationFrame：部分老内核/无合成器的环境里
    // rAF 不回调，按钮的显隐就会卡死在初始状态
    var tickTimer = null;
    window.addEventListener('scroll', function () {
        if (tickTimer) { return; }
        tickTimer = window.setTimeout(function () { tickTimer = null; syncBtn(); }, 80);
    }, { passive: true });
    window.addEventListener('resize', syncBtn, { passive: true });

    /* ================= ② 深度版章节折叠 ================= */

    // 默认收起的「非核心」章节。核心评分区（proposalAnalysis 诊断、
    // judgeFeedback 评审意见）与 tab-export 导出区都不在这个表里 → 永远展开。
    var FOLDABLE = {
        competitorAnalysis: 1, businessModel: 1, riskAnalysis: 1,
        techSolution: 1, implementationPlan: 1, socialValue: 1
    };

    function paint(wrap, collapsed) {
        if (collapsed) { wrap.classList.add('wbnav-folded'); }
        else { wrap.classList.remove('wbnav-folded'); }
        var t = wrap.querySelector('.wbnav-toggle');
        if (t) { t.textContent = collapsed ? '展开' : '收起'; }
    }

    function setCollapsed(id, collapsed) {
        var el = $(id);
        if (!el) { return; }
        var wrap = el.parentElement;
        if (wrap && wrap.getAttribute('data-wbnavig') === '1') { paint(wrap, collapsed); }
    }

    window.wbnavigExpand = function (id) { setCollapsed(id, false); };
    window.wbnavigCollapse = function (id) { setCollapsed(id, true); };

    // 结果区是流式渲染的：这一刻没内容/整块藏着的板块，过几秒可能就出来了。
    // 每次扫描只处理「真有内容且可见」的块，处理完打 data-wbnavig 标记不再动。
    var loops = 0;
    function scan() {
        var left = 0;
        Object.keys(FOLDABLE).forEach(function (id) {
            var el = $(id);
            if (!el) { left++; return; }
            var wrap = el.parentElement;
            if (!wrap || wrap.tagName !== 'DIV') { left++; return; }
            if (wrap.getAttribute('data-wbnavig') === '1') { return; }
            // 空块不加折叠钮：一块白什么都没有，还多个按钮，反而更迷路
            if (wrap.offsetParent === null || !(el.textContent || '').trim()) { left++; return; }
            var head = wrap.querySelector('h3, h2');
            if (!head) { left++; return; }

            wrap.setAttribute('data-wbnavig', '1');
            var t = document.createElement('button');
            t.type = 'button';
            t.className = 'wbnav-toggle';
            t.title = '展开 / 收起本段';
            t.setAttribute('aria-label', '展开或收起本段');
            t.addEventListener('click', function (ev) {
                ev.preventDefault();
                paint(wrap, !wrap.classList.contains('wbnav-folded'));
            });
            head.appendChild(t);
            paint(wrap, true);
        });
        loops++;
        // 全部处理到位就收工；超时也收工，不留长定时器在后台空转
        if (left > 0 && loops < 100) { window.setTimeout(scan, 1200); }
    }

    // 点锚点条跳过去时，目标章节若是收起的就先展开——跳到一片空白最难受
    if (typeof window.wbGoAnchor === 'function') {
        var _go = window.wbGoAnchor;
        window.wbGoAnchor = function (tab, id) {
            try { if (id) { window.wbnavigExpand(id); } } catch (e) {}
            return _go.apply(this, arguments);
        };
    }

    function boot() {
        syncBtn();
        window.setTimeout(scan, 800);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { window.setTimeout(boot, 0); });
    } else {
        boot();
    }
})();
