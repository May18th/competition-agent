/* 398 轮：顶部「更多 ▾」下拉 —— 分组重排的外挂模块
   ------------------------------------------------------------------
   为什么是外挂模块：index.html / app.js / style.css 正被多条线并发修改，
   本项目已经因为「同一文件并发写」丢过三次改动。本文件只做两件事：
     1. 往既有 #wbMoreMenu 里插入一个 #wbMenu398Body，把菜单项按分组重排；
     2. 把**既有菜单项原封不动搬进对应分组**（不重建、不改它们的 onclick），
        这样 index.html 里的「页面背景」和 wbsync.js 异步注入的「跨设备同步」都保留原行为。

   硬约束：
     - 只挂**已上线**的能力。每项都有 probe()，不满足就整条隐藏，绝不留点了没反应的空入口；
     - 尚未实现的（收藏夹 / 灵感库 / 备赛进度看板 / 查重报告）一律不写死成按钮，
       而是登记在 PENDING 里：等对应全局函数上线后**自动出现**，不需要再改本文件；
     - 不新增依赖、不改任何既有文件的逻辑，全部 ES5 + try/catch，任一环节炸了也不影响主流程。

   接线契约（由负责 index.html 的同学加，本文件不自己加）：
     <link rel="stylesheet" href="/static/wbmenu398.css?v=20260930">        ← 放在 wbdemo.css 之后
     <script src="/static/wbmenu398.js?v=20260930"></script>                ← 放在 wbpage.js 之后
   标签加上后本模块自动 init（无需在 app.js 里调用）；若要在某个时机手动重扫，调 wbMenu398.init()。
*/
(function () {
    'use strict';
    if (window.wbMenu398) { return; }

    var MAX_TRY = 60;          // 60 × 300ms ≈ 18s，等 #wbMoreMenu 出现（它可能在 DOMContentLoaded 之后才就绪）
    var tries = 0;
    var built = false;
    var menuEl = null;
    var bodyEl = null;
    var lastPendingSig = '';   // 待注册清单的「上线情况」快照，变了才重建

    var ICON_BOOK = 'wb-i-book', ICON_HISTORY = 'wb-i-history', ICON_DOWNLOAD = 'wb-i-download',
        ICON_LAYERS = 'wb-i-layers', ICON_SPARKLE = 'wb-i-sparkle', ICON_SEARCH = 'wb-i-search',
        ICON_QUOTE = 'wb-i-quote', ICON_GLOBE = 'wb-i-globe', ICON_TROPHY = 'wb-i-trophy';

    /* ---------- 分组：个性化 / 数据 / 工具 ---------- */
    var GROUPS = [
        { key: 'personalize', title: '个性化' },
        { key: 'data', title: '数据' },
        { key: 'tools', title: '工具' }
    ];

    /* ---------- 菜单项清单 ----------
       adopt：接管既有 DOM（页面背景来自 index.html、跨设备同步由 wbsync.js 异步注入），
              拿到就原样搬进分组；拿不到且 probe() 通过时才自己建按钮。
       probe：这一项现在能不能用。false 就隐藏 —— 宁可少一项，也不要点了没反应。
       state：右侧灰色小字，回显当前生效值（纯提示）。 */
    var ITEMS = [
        {
            key: 'bg', group: 'personalize', adopt: 'bg', title: '页面背景', hint: '换一张页面底图，图片只存本机',
            icon: ICON_GLOBE, probe: function () { return typeof window.wbBgPanelToggle === 'function'; },
            run: function () { window.wbBgPanelToggle(); }
        },
        {
            key: 'theme', group: 'personalize', title: '深浅配色', hint: '在白底与夜间两套配色间切换',
            icon: ICON_SPARKLE, probe: function () { return typeof window.wbToggleTheme === 'function'; },
            state: function () { return document.body && document.body.classList.contains('light') ? '日间' : '夜间'; },
            run: function () { window.wbToggleTheme(); }
        },
        {
            key: 'deckStyle', group: 'personalize', title: '风格选择', hint: '调整成稿的版式与配色',
            icon: ICON_LAYERS,
            // 风格选择器挂在结果区里，没出结果时它不可见 —— 此时不给入口，避免点了没地方跳
            probe: function () {
                var bar = document.getElementById('wbStyleBar');
                return !!bar && bar.offsetParent !== null;
            },
            run: function () {
                var bar = document.getElementById('wbStyleBar');
                try { bar.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
                var sel = document.getElementById('styleQuickSel');
                if (sel) { try { sel.focus(); } catch (e2) {} }
            }
        },
        {
            key: 'history', group: 'data', title: '历史记录', hint: '回看历次生成的内容与评分',
            icon: ICON_HISTORY, probe: function () { return typeof window.showHistory === 'function'; },
            run: function () { window.showHistory(); }
        },
        {
            key: 'export', group: 'data', title: '导出中心', hint: 'Word / PDF / 路演稿等分项下载',
            icon: ICON_DOWNLOAD,
            // 结果区没显示时导出中心是空面板，给了入口等于敷衍 —— 出结果后才出现
            probe: function () {
                var ra = document.getElementById('resultArea');
                return !!ra && ra.offsetParent !== null && !!document.getElementById('exportTab');
            },
            run: function () { window.wbGoExport(); }
        },
        {
            key: 'share', group: 'data', title: '分享这次结果', hint: '生成链接，换台设备也能打开',
            icon: ICON_QUOTE,
            probe: function () { return !!window._lastHistoryId && typeof window.wbShare === 'function'; },
            run: function () { window.wbShare(); }
        },
        {
            key: 'sync', group: 'data', adopt: 'sync', title: '跨设备同步', hint: '用同步码共享历史与草稿',
            icon: ICON_GLOBE, probe: function () { return true; }, run: null
        },
        {
            key: 'intro', group: 'tools', title: '使用说明', hint: '三步走完：填信息 → 生成 → 导出',
            icon: ICON_BOOK, probe: function () { return typeof window.showIntro === 'function'; },
            run: function () { window.showIntro(true); }
        },
        {
            key: 'material', group: 'tools', title: '材料识别填充', hint: '粘申报书或传文件，自动填表单',
            icon: ICON_SEARCH, probe: function () { return typeof window.wbMatOpen === 'function'; },
            run: function () { window.wbMatOpen(); }
        },
        {
            key: 'demo', group: 'tools', title: '演示样例', hint: '载入预置样例，先看效果再动手',
            icon: ICON_TROPHY, probe: function () { return typeof window.wbOpenDemo === 'function'; },
            run: function () { window.wbOpenDemo(); }
        },
        {
            key: 'feedback', group: 'tools', title: '意见反馈', hint: '任何状态下都能提问题和建议',
            icon: ICON_QUOTE, probe: function () { return typeof window.wbFeedbackOpen === 'function'; },
            run: function () { window.wbFeedbackOpen(); }
        }
    ];

    /* ---------- 待注册清单（354-393 轮提的需求，当前线上还没实现的功能）----------
       这里登记的是**契约**：全局函数名 + 归属分组 + 文案。只要负责那条线的同学上线时
       在自己文件里挂上 window.wbFavOpen = function(){...}，菜单里就会自动多出这一项，
       本文件一行都不用改。反之，函数没挂着就永远不会出现 —— 不会先摆一个点了没反应的按钮。

       也可以在控制台手动补登记：wbMenu398.register({key:'xxx', group:'tools', title:'…'}); */
    var PENDING = [
        { key: 'favorites', group: 'data', title: '收藏夹', hint: '存下想反复对比的几版成稿', icon: ICON_HISTORY, runName: 'wbFavOpen' },
        { key: 'inspiration', group: 'tools', title: '灵感库', hint: '按赛道给的选题与切入角度', icon: ICON_SPARKLE, runName: 'wbInspireOpen' },
        { key: 'board', group: 'tools', title: '备赛进度看板', hint: '材料清单与提交截止提醒', icon: ICON_BOOK, runName: 'wbBoardOpen' },
        { key: 'dupcheck', group: 'tools', title: '查重报告', hint: '与本地范文的重合度自查', icon: ICON_SEARCH, runName: 'wbDupReportOpen' }
    ];

    /* ---------- 既有菜单项 → 归属分组的认领规则 ---------- */
    var ADOPT_RULES = [
        { key: 'bg', test: function (n) { return /页面背景/.test(n.textContent || '') || /wbBgPanelToggle/.test(n.getAttribute('onclick') || ''); } },
        { key: 'sync', test: function (n) { return (n.id || '') === 'wbXSyncEntry' || /同步/.test(n.textContent || ''); } }
    ];

    function adoptKey(node) {
        for (var i = 0; i < ADOPT_RULES.length; i++) {
            try { if (ADOPT_RULES[i].test(node)) return ADOPT_RULES[i].key; } catch (e) {}
        }
        return '';
    }

    function closeMenu() {
        try { if (typeof window.wbMoreClose === 'function') window.wbMoreClose(); } catch (e) {}
    }

    /* 菜单是按 #wbMoreWrap 右对齐的绝对定位元素：手机上工具栏排成两列，「更多」落在左列，
       按右对齐展开会往左溢出屏幕（实测 390px 下菜单左边到了 -9px，左边的字被切掉）。
       每次打开都按真实 rect 夹一次，桌面 / 手机、左列 / 右列都不会跑出可视区。 */
    function clampIntoViewport() {
        if (!menuEl || !visible(menuEl)) return;
        try {
            var pad = 8;
            var r = menuEl.getBoundingClientRect();
            var vw = window.innerWidth || 0;
            if (!vw) return;
            if (r.left < pad) { menuEl.style.right = '-' + Math.ceil(pad - r.left) + 'px'; }
            else if (r.right > vw - pad) { menuEl.style.right = Math.ceil(r.right - (vw - pad)) + 'px'; }
        } catch (e) {}
    }

    function visible(el) {
        try { return !!el && el.offsetParent !== null; } catch (e) { return !el; }
    }

    /* 待注册清单 → 真实菜单项：只有「对应的全局函数已经挂上」时才兑现。
       这样负责那条线的同学上线时不用碰本文件，也不用提前摆一个点了没反应的按钮。 */
    function availablePending(p) {
        return !!p && !!p.runName && typeof window[p.runName] === 'function';
    }

    function pendingSig() {
        var keys = [];
        PENDING.forEach(function (p) { if (availablePending(p)) keys.push(p.key); });
        return keys.join(',');
    }

    function resolvePending() {
        var list = [];
        PENDING.forEach(function (p) {
            if (!availablePending(p)) return;
            var copy = {};
            for (var k in p) { if (Object.prototype.hasOwnProperty.call(p, k)) copy[k] = p[k]; }
            copy.run = (function (name) {
                return function () { window[name](); };
            })(p.runName);
            list.push(copy);
        });
        return list;
    }

    /* ---------- 建一个菜单项 ---------- */
    function makeItem(cfg) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'wbmenu398-item';
        b.setAttribute('role', 'menuitem');
        b.dataset.wb398 = cfg.key;
        b.dataset.wb398own = '1';   // 标记「本模块自建」，teardown 时区分自建与收编来的别人的 DOM
        var html = '<svg class="wb-ico wbmenu398-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#'
            + (cfg.icon || ICON_LAYERS) + '"/></svg>';
        html += '<span class="wbmenu398-txt"><span class="wbmenu398-title">' + (cfg.title || '') + '</span>';
        if (cfg.hint) html += '<span class="wbmenu398-hint">' + cfg.hint + '</span>';
        html += '</span><span class="wbmenu398-state" data-role="state"></span>';
        b.innerHTML = html;
        b.addEventListener('click', function (e) {
            try { if (e && e.stopPropagation) e.stopPropagation(); } catch (er) {}
            closeMenu();
            try { cfg.run(); } catch (e2) {}
        });
        return b;
    }

    /* 把既有节点（别的线生成的）搬进分组，保留它原本的行为，只补视觉 class */
    function dressAdopted(node, cfg) {
        node.className += ' wbmenu398-item';
        try { node.setAttribute('type', 'button'); } catch (e) {}
        try { node.setAttribute('role', 'menuitem'); } catch (e2) {}
        node.dataset.wb398 = cfg.key;
        // 收编来的节点带着自己的内联样式（wbsync.js 写死过 min-height:36px），
        // 会压过本模块的 44px 触控标准；这些视觉项统一交回 CSS 管，行为属性一律不动。
        ['min-height', 'padding', 'border', 'background', 'border-radius', 'font-size', 'color'].forEach(function (p) {
            try { node.style.removeProperty(p); } catch (e5) {}
        });
        // 原节点可能缺可访问名（如只有 emoji + 文字），补一条 aria-label
        if (!node.getAttribute('aria-label')) {
            try { node.setAttribute('aria-label', (cfg.title || node.textContent || '').trim()); } catch (e3) {}
        }
        return node;
    }

    /* 拆掉上一版结构重建时用：把从别处认领来的节点交还 #wbMoreMenu，
       避免重建过程中把 index.html / wbsync.js 的入口连带丢掉。 */
    function teardown() {
        if (!bodyEl || !menuEl) return;
        var nodes = bodyEl.querySelectorAll('.wbmenu398-item');
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node.dataset) continue;
            if (node.dataset.wb398own === '1') continue;       // 自建节点直接随旧结构丢弃
            node.className = String(node.className || '').replace(/\s*wbmenu398-item/g, '');
            node.removeAttribute('data-wb398');
            node.removeAttribute('role');
            node.style.removeProperty('display');
            try { menuEl.appendChild(node); } catch (e2) {}      // 交还给菜单，重建时会再认领一次
        }
        try { menuEl.removeChild(bodyEl); } catch (e3) {}
        bodyEl = null;
        built = false;
    }

    /* ---------- 构建整个菜单 ---------- */
    function build(menu) {
        menuEl = menu;
        teardown();
        bodyEl = document.createElement('div');
        bodyEl.id = 'wbMenu398Body';

        // 先把既有菜单项从菜单里「摘出来」，避免构建过程中被别处的 appendChild 插到中间
        var existing = [];
        try {
            while (menu.firstChild) {
                var n = menu.removeChild(menu.firstChild);
                if (n.nodeType === 1) existing.push(n);
            }
        } catch (e) {}

        var groupMap = {};
        GROUPS.forEach(function (g) {
            var box = document.createElement('div');
            box.className = 'wbmenu398-groupbox';
            box.dataset.group = g.key;
            var t = document.createElement('div');
            t.className = 'wbmenu398-group';
            t.textContent = g.title;
            box.appendChild(t);
            groupMap[g.key] = box;
            bodyEl.appendChild(box);
        });

        // 认领既有节点
        var claimed = {};
        existing.forEach(function (n) {
            var k = adoptKey(n);
            if (k) { claimed[k] = n; return; }
            // 认领不了的（别的线以后新增的入口）：原样保留在末尾，宁可贵也不删别人的东西
            groupMap.tools.appendChild(dressAdopted(n, { key: 'foreign-' + (Date.now()) }));
        });

        ITEMS.concat(resolvePending()).forEach(function (cfg) {
            var box = groupMap[cfg.group] || groupMap.tools;
            var adopted = cfg.adopt ? claimed[cfg.adopt] : null;
            if (adopted) {
                box.appendChild(dressAdopted(adopted, cfg));
                return;
            }
            if (cfg.adopt && !cfg.run) { return; }           // 纯接管项又拿不到节点：不造重复入口
            if (typeof cfg.run !== 'function') { return; }    // 未上线 / 未注册：不显示
            box.appendChild(makeItem(cfg));
        });

        // MutationObserver 只监听 #wbMoreMenu 的直接子节点：bodyEl 是一次性整体挂进去的
        // （靠 id / data-wb398own 认出是自己的，不会把自己新挂的节点当成「别人插进来的」），
        // 内部怎么排序都不会触发自激搬运。
        try { menu.appendChild(bodyEl); } catch (e4) {}
        built = true;
        refresh();
    }

    /* ---------- 每次开菜单都重扫一遍可用性 + 状态值 ---------- */
    function refresh() {
        if (!bodyEl) return;
        // 某条待注册功能中途上线了（别的线后加载的脚本挂上了全局函数）→ 重建一次把入口补上。
        // 用「可用清单签名」比对，避免每次开菜单都无意义重建，也避免自激递归。
        var sig = pendingSig();
        if (sig !== lastPendingSig) {
            lastPendingSig = sig;
            try { build(menuEl || document.getElementById('wbMoreMenu')); } catch (e0) {}
            return;
        }
        var nodes = bodyEl.querySelectorAll('[data-wb398]');
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            var cfg = null;
            ITEMS.concat(PENDING).forEach(function (c) { if (c.key === node.dataset.wb398) cfg = c; });
            if (!cfg) continue;
            var ok = true;
            try { ok = !cfg.probe || cfg.probe(); } catch (e) { ok = true; }
            if (cfg.runName) { ok = typeof window[cfg.runName] === 'function'; }   // 待注册清单靠函数是否上线决定
            node.style.display = ok ? '' : 'none';
            if (!ok) continue;
            var st = node.querySelector('[data-role="state"]');
            if (st) {
                var txt = '';
                try { txt = cfg.state ? (cfg.state() || '') : ''; } catch (e2) { txt = ''; }
                st.textContent = txt;
                st.style.display = txt ? '' : 'none';
            }
        }
        // 整组都空就把分组标题一起藏掉，别留一个孤零零的「工具」
        var boxes = bodyEl.querySelectorAll('.wbmenu398-groupbox');
        for (var j = 0; j < boxes.length; j++) {
            var items = boxes[j].querySelectorAll('.wbmenu398-item');
            var shown = 0;
            for (var k = 0; k < items.length; k++) { if (items[k].style.display !== 'none') shown++; }
            boxes[j].style.display = shown ? '' : 'none';
        }
    }

    /* 别人后来往 #wbMoreMenu 里 append 的节点（比如 wbsync.js 轮询到接口可用才注入的同步入口），
       不能让它掉在 #wbMenu398Body 外面变成「分组之外的野老大」——按认领规则搬进去。 */
    function watchForeign() {
        if (!menuEl || typeof MutationObserver === 'undefined') return;
        var obs = new MutationObserver(function (recs) {
            for (var i = 0; i < recs.length; i++) {
                var added = recs[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var n = added[j];
                    if (n.nodeType !== 1 || !bodyEl) continue;
                    if (n.id === 'wbMenu398Body' || (n.dataset && n.dataset.wb398)) continue;
                    var key = adoptKey(n) || '';
                    var target;
                    if (key) {
                        var slot = bodyEl.querySelector('[data-wb398="' + key + '"]');
                        if (slot) continue;                       // 该槽位已有节点，避免重复插入
                        target = bodyEl.querySelector('[data-group="data"]');
                        if (!target) continue;
                    } else {
                        target = bodyEl.querySelector('[data-group="tools"]');
                        if (!target) continue;
                    }
                    try { target.appendChild(dressAdopted(n, { key: key || 'foreign' })); } catch (e) {}
                    refresh();
                }
            }
        });
        obs.observe(menuEl, { childList: true });
    }

    /* 开菜单时刷新可用性：既有 wbMoreToggle 是把 #wbMoreMenu 的 display 改成 block，
       这里盯着 style 属性变化即可，不需要改它的函数，也就不会和别的线冲突。 */
    function watchOpen() {
        if (!menuEl || typeof MutationObserver === 'undefined') return;
        var obs = new MutationObserver(function () {
            try { refresh(); clampIntoViewport(); } catch (e) {}
        });
        obs.observe(menuEl, { attributes: true, attributeFilter: ['style'] });
    }

    /* Esc 关闭：既有 app.js 只处理了「点页面别处」，键盘这一路是缺的 */
    function bindEsc() {
        document.addEventListener('keydown', function (e) {
            if (!e) return;
            if (e.key !== 'Escape' && e.keyCode !== 27) return;
            if (!menuEl || !visible(menuEl)) return;
            closeMenu();
            var btn = document.getElementById('wbMoreBtn');
            try { if (btn) btn.focus(); } catch (er) {}
        });
    }

    function init() {
        if (built) { refresh(); return true; }
        var menu = document.getElementById('wbMoreMenu');
        if (!menu) return false;
        try { build(menu); } catch (e) { return false; }
        try { watchForeign(); } catch (e2) {}
        try { watchOpen(); } catch (e3) {}
        try { bindEsc(); } catch (e4) {}
        return true;
    }

    function boot() {
        if (init()) return;
        tries++;
        if (tries < MAX_TRY) setTimeout(boot, 300);
    }

    window.wbMenu398 = {
        init: init,
        refresh: refresh,
        pending: PENDING,
        // 上线某功能后让它出现在菜单里：wbMenu398.register({key:'fav', group:'data', title:'收藏夹', runName:'wbFavOpen', icon:'wb-i-history'});
        register: function (cfg) {
            if (!cfg || !cfg.key) return false;
            for (var i = 0; i < PENDING.length; i++) { if (PENDING[i].key === cfg.key) return false; }
            if (!cfg.runName) return false;
            PENDING.push(cfg);
            if (built) build(document.getElementById('wbMoreMenu'));
            return true;
        }
    };

    try {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () { setTimeout(boot, 0); });
        } else {
            boot();
        }
    } catch (e) { boot(); }
})();
