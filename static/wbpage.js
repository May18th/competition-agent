
/* 165 轮：底部「开始生成」是 sticky 悬浮条，滚动过程中会浮在上层，把正在填的输入框压住。
   实测 375×812 下滚到 y=302：团队成员 textarea 被盖掉 49px（overlap 64px），
   用户看到的就是「按钮夹在成员区中间、内容溢出到按钮下方」。
   这里做统一兜底：展开面板 / 聚焦输入框后，把目标抬到 CTA 上方的安全区。
   平滑滚动在部分内核（微信/夸克）不生效，700ms 后按实测量再补滚一次。 */
function wbEnsureVisible(el) {
    if (!el) return;
    setTimeout(function () {
        try {
            var cta = document.getElementById('startBar');
            var ctaH = cta ? (cta.getBoundingClientRect().height + 20) : 0;
            var safeBottom = window.innerHeight - ctaH - 8;
            var _lift = function () {
                var r = el.getBoundingClientRect();
                if (r.height >= window.innerHeight - ctaH - 20) return;   // 比安全区还高的元素不搬
                var over = r.bottom - safeBottom;
                if (over > 0) {
                    // 最多滚到元素顶部贴屏，别把整块顶出视野外
                    window.scrollBy(0, Math.max(0, Math.min(over, r.top - 8)));
                }
            };
            _lift();
            setTimeout(_lift, 700);
        } catch (e) {}
    }, 280);
}
// 聚焦任何输入框都抬起一次：手机软键盘弹出后可视区变矮，更容易被悬浮条压住
document.addEventListener('focusin', function (e) {
    var t = e.target;
    if (!t || !t.tagName) return;
    var tag = t.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') return;
    if (window.matchMedia && !window.matchMedia('(max-width: 768px)').matches) return;
    wbEnsureVisible(t);
}, true);

function wbAdvToggle(id) {
    var b = document.getElementById(id);
    var a = document.getElementById(id + 'Arrow');
    if (!b) return;
    var open = b.style.display !== 'none';
    b.style.display = open ? 'none' : '';
    if (a) a.textContent = open ? '▸' : '▾';
    // 165 轮：展开后面板要抬到底部悬浮 CTA 之上，否则内容被压住（实测被盖 49px）
    if (!open) wbEnsureVisible(b);
}
var _evUserOpen = false;
function evToggleBody() {
    var b = document.getElementById('evBody');
    var a = document.getElementById('evBodyArrow');
    if (!b) return;
    var open = b.style.display !== 'none';
    _evUserOpen = !open;   // 记住用户亲手展开过，别被 resize 强行收回去
    b.style.display = open ? 'none' : '';
    if (a) a.textContent = open ? '▸' : '▾';
    if (!open) wbEnsureVisible(b);   // 165 轮：同 wbAdvToggle
}
function wbAdvInit() {
    var m = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
    // kbAdvBody（规则区）已按 P0-2 首页精简降级为全端默认折叠，不在这个列表里——
    // 放进来的话桌面端 resize 时会被重新展开，首屏又冒出规则上传入口
    // 105-2（阻塞级）：用户反馈「正常输入栏没有了」——团队成员是第 3 步关键输入栏，
    // 从折叠列表移除，全端默认展开；折叠只留给低频选填项（草稿/实测数据）
    ['draftAdvBody', 'userDataBody'].forEach(function (id) {
        var b = document.getElementById(id);
        var a = document.getElementById(id + 'Arrow');
        if (!b) return;
        b.style.display = m ? 'none' : '';
        if (a) a.textContent = m ? '▸' : '▾';
    });
    // 赛事要求卡：全端默认收起（原来只有手机收），只留标题 + 一行摘要。
    // 它一动就是十几行，占着首屏把「填什么、点哪里」的主线挤没了
    (function () {
        if (_evUserOpen) return;
        var b = document.getElementById('evBody');
        var a = document.getElementById('evBodyArrow');
        if (!b) return;
        b.style.display = 'none';
        if (a) a.textContent = '▸';
    })();
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wbAdvInit);
} else { wbAdvInit(); }
window.addEventListener('resize', function () {
    if (window._advT) return;
    window._advT = setTimeout(function () { window._advT = 0; wbAdvInit(); }, 300);
});


/* ================= 多智能体流程可视化 + 打字机 =================
   后端 /api/stream/<task_id> 已实现 SSE（stage / partial / done 事件），
   但前端一直只轮询 /api/status，所以是「一块一块跳」而不是逐字流出。
   这里接上 SSE 做增量；SSE 不通时轮询照旧，两条路都调同一批幂等函数。 */
(function () {
    var ESC = (typeof _esc === 'function') ? _esc : function (x) {
        return String(x == null ? '' : x).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    };

    /* ---------- 1. Agent 面板 ---------- */
    var AGENTS = [
        { k: 'rules',    n: '规则解析 Agent',   s: ['start', 'parsing_rules'] },
        { k: 'similar',  n: '竞品检索 Agent',   s: ['similarity'] },
        { k: 'idea',     n: '创意定位 Agent',   s: ['idea_scoring'] },
        { k: 'analysis', n: '方案分析 Agent',   s: ['analysis'] },
        { k: 'assets',   n: '素材生成 Agent',   s: ['rich_assets'] },
        { k: 'write',    n: '申报书写作 Agent', s: ['writing'] },
        { k: 'judge',    n: '评审 Agent',   s: ['judging', 'expert_review', 'diagnosis', 'revision'] },
        { k: 'defense',  n: '答辩预测 Agent',   s: ['defense'] },
        { k: 'road',     n: '路演生成 Agent',   s: ['ppt', 'speech', 'done'] }
    ];
    // 后端 SSE 的 stage 事件只带代号，本地补一份中文动作
    var STAGE_LABEL = {
        start: '正在启动', parsing_rules: '解析评分规则', similarity: '检索同质化项目',
        idea_scoring: '提炼一句话定位', analysis: '分析赛题与方案', rich_assets: '生成图表与 PPT 素材',
        writing: '撰写申报书正文', judging: 'AI 评审打分', expert_review: '多视角评审（AI）',
        diagnosis: '诊断短板', revision: '按意见定向改写', defense: '预测答辩问题',
        ppt: '生成 PPT 大纲', speech: '撰写路演稿', done: '收尾'
    };
    var st = {}, timer = 0;

    function reset() {
        st = {};
        // 126 轮：已用时间计时归零。不归零的话第二次生成会从上次的时间接着走
        try { window._wbGenT0 = 0; } catch (e) {}
        AGENTS.forEach(function (a) { st[a.k] = { s: 'wait', label: '', t0: 0, ms: 0 }; });
        if (timer) { clearTimeout(timer); timer = 0; }
        var p = document.getElementById('agentPanel');
        if (p) p.style.display = 'block';
        render();
    }

    function stage(code, label) {
        if (!code) return;
        var hit = null, hi = -1;
        for (var i = 0; i < AGENTS.length; i++) {
            if (AGENTS[i].s.indexOf(code) >= 0) { hit = AGENTS[i]; hi = i; break; }
        }
        if (!hit) return;
        if (!st[hit.k]) st[hit.k] = { s: 'wait', label: '', t0: 0, ms: 0 };   // 未 reset 就先被调到的防御
        var now = Date.now();
        // 后端前几个节点并行跑、stage 会乱序跳变：只把「排在它前面」的收尾，
        // 后面的保持原状，免得把还没跑的标成已完成
        for (var j = 0; j < hi; j++) {
            var o = st[AGENTS[j].k];
            if (o && o.s === 'run') { o.s = 'done'; o.ms = o.t0 ? (now - o.t0) : 0; }
        }
        var cur = st[hit.k];
        if (cur.s !== 'run') { cur.s = 'run'; cur.t0 = now; }
        cur.label = label || STAGE_LABEL[code] || '';
        render();
        // 运行中每秒重绘一次，让耗时数字自己走
        if (!timer) timer = setTimeout(function () { timer = 0; render(); }, 1000);
    }

    function finish(ok) {
        var now = Date.now();
        // 生成结束：停掉已用时间计时（成功/失败都停，下次 reset 才归零）
        try { window._wbGenT0 = 0; } catch (e) {}
        Object.keys(st).forEach(function (k) {
            var o = st[k];
            if (o.s === 'run') { o.s = ok === false ? 'err' : 'done'; o.ms = o.t0 ? (now - o.t0) : 0; }
        });
        if (timer) { clearTimeout(timer); timer = 0; }
        render();
        setTimeout(function () {
            var p = document.getElementById('agentPanel');
            if (p) p.style.display = 'none';
        }, 2600);
    }

    function render() {
        var box = document.getElementById('agentPanel');
        if (!box) return;
        var runCnt = 0, doneCnt = 0;
        var html = '<div class="wb-agent-hd"><svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-layers"/></svg> 多智能体协同流程 · 实时</div>';
        AGENTS.forEach(function (a) {
            var o = st[a.k] || { s: 'wait' };
            if (o.s === 'run') runCnt++;
            if (o.s === 'done') doneCnt++;
            var cls = o.s, dot = cls === 'done' ? '●' : (cls === 'run' ? '◐' : (cls === 'err' ? '✕' : '○'));
            var tail = '';
            if (cls === 'run') tail = '<span class="wb-agent-act">' + ESC(o.label) + '</span>';
            else if (cls === 'done') tail = '<span class="wb-agent-ms">' + (o.ms ? (o.ms / 1000).toFixed(1) + 's' : '✓') + '</span>';
            else if (cls === 'err') tail = '<span class="wb-agent-ms">中断</span>';
            else tail = '<span class="wb-agent-wait">等待</span>';
            html += '<div class="wb-agent-row ' + cls + '"><span class="wb-agent-dot">' + dot +
                '</span><span class="wb-agent-nm">' + a.n + '</span>' + tail + '</div>';
        });
        // 169 轮：这里的 x/9 是「已完成的环节数」，和进度条上那个整体百分比是两回事——
        // 原来两侧都裸着数字（84% 和 2/9），用户以为同一个指标前后矛盾。
        // 现在各自写明口径：本面板=环节，进度条/按钮=整体进度
        html = html.replace('多智能体协同流程 · 实时',
            '多智能体协同流程 · 实时（环节 ' + doneCnt + '/' + AGENTS.length + '）');
        box.innerHTML = html;
        if (runCnt && !timer) timer = setTimeout(function () { timer = 0; render(); }, 1000);
    }

    /* ---------- 2. 打字机 ---------- */
    // key -> { full: 后端已产出的全文, shown: 已揭示字数, painted: 已渲染字数 }
    var tw = {}, raf = 0;
    var rAF = window.requestAnimationFrame || function (f) { return setTimeout(f, 16); };

    function twReset() { tw = {}; }

    function fieldMeta(key) {
        if (typeof _STREAM_MAP === 'undefined') return null;
        for (var i = 0; i < _STREAM_MAP.length; i++) if (_STREAM_MAP[i][0] === key) return _STREAM_MAP[i];
        return null;
    }

    function twSet(key, text) {
        if (!key || typeof text !== 'string') return;
        var m = fieldMeta(key);
        if (!m) return;
        var o = tw[key];
        if (!o) o = tw[key] = { full: '', shown: 0, painted: -1, id: m[1], tab: m[2] };
        if (text.length < o.full.length) {           // 内容被重写（少见），直接对齐
            o.full = text; o.shown = Math.min(o.shown, text.length); return;
        }
        o.full = text;
        if (o.full.length - o.shown > 6000) o.shown = o.full.length;   // 落后太多就不动画，直接追上
        if (!raf) raf = rAF(tick);
    }

    // 切断处可能剩下半截 ** 或 `，去掉一个，免得渲染时闪出符号
    function twSlice(t, n) {
        return t.slice(0, n).replace(/(\*{1,3})$/, '').replace(/`+$/, '');
    }

    function twPaint(o, txt) {
        var el = document.getElementById(o.id);
        if (!el) return;
        if (!window.marked) { el.textContent = txt; return; }
        // 闪屏根因（用户实测「不稳定要闪屏」）：原来每帧 el.innerHTML = marked.parse(全文)，
        // 深度版 1.2 万字时每秒整段重排约 60 次 —— 高度反复跳动就是这么来的。
        // 改成「稳定区 + 尾段」：以空行分界，已经写完的段落固化在 DOM 里不再重绘，
        // 只有正在增长的最后一段放进独立子节点、每帧只更新这一小段。
        var cut = txt.lastIndexOf('\n\n');
        var stable = cut >= 0 ? txt.slice(0, cut) : '';
        var tail = cut >= 0 ? txt.slice(cut) : txt;
        var scroller = document.scrollingElement || document.documentElement;
        var y0 = scroller ? scroller.scrollTop : 0;
        try {
        if (o.paintedStable !== stable) {
            // 稳定区只在段落边界推进时重绘一次，不是每帧
            var oldTail = document.getElementById(o.id + '__tail');
            if (oldTail && oldTail.parentNode === el) el.removeChild(oldTail);
            el.innerHTML = marked.parse(stable);
            o.paintedStable = stable;
        }
        if (tail) {
            var tEl = document.getElementById(o.id + '__tail');
            if (!tEl) {
                tEl = document.createElement('div');
                tEl.id = o.id + '__tail';
                el.appendChild(tEl);
            }
            tEl.innerHTML = marked.parse(tail);
        }
        // 内容变长会把用户正在看的位置顶走（跳动的观感来源），渲染后把滚动位置补回去
        if (scroller && y0 > 0 && scroller.scrollTop !== y0) scroller.scrollTop = y0;
        } catch (err) {
            // 增量渲染是新写的路径，万一哪段 Markdown 切出异常结构，
            // 回退到原来的全文渲染——宁可慢一点闪一点，也不能什么都不显示
            el.innerHTML = marked.parse(txt);
            o.paintedStable = null;
        }
        el.classList.add('streaming');
        var tb = document.querySelector('.tab[onclick*="' + o.tab + '"]');
        if (tb) {
            if (o.tab === 'defense') tb.style.display = 'block';
            if (!tb.classList.contains('active')) tb.classList.add('has-stream');
        }
        // 第一次有真内容就把骨架屏换成结果区
        if (typeof _streamShown !== 'undefined' && !_streamShown) {
            _streamShown = true;
            var sk = document.getElementById('skeletonArea');
            var ra = document.getElementById('resultArea');
            if (sk) sk.style.display = 'none';
            if (ra) ra.style.display = 'block';
        }
    }

    function tick() {
        raf = 0;
        var busy = false;
        Object.keys(tw).forEach(function (k) {
            var o = tw[k];
            var rem = o.full.length - o.shown;
            if (rem > 0) {
                // 自适应步长：约 1.2s 内追平当前积压，最少 2 字/帧
                o.shown = Math.min(o.full.length, o.shown + Math.max(2, Math.ceil(rem / 72)));
                busy = true;
            }
            if (o.shown === o.full.length) {
                if (o.shown !== o.painted) { twPaint(o, o.full); o.painted = o.shown; }
                return;
            }
            // 重绘门槛从 8 字提到 24 字：配合上面的增量渲染，重排次数降到原来的三分之一，
            // 观感上仍是连续的打字机效果，但不再每帧动一次布局
            if (o.shown - o.painted >= 24) {
                twPaint(o, twSlice(o.full, o.shown));
                o.painted = o.shown;
            }
        });
        if (busy) raf = rAF(tick);
    }

    /* ---------- 3. SSE（拿不到就靠轮询兜底） ---------- */
    var es = null, esId = null;
    function sseOpen(tid) {
        if (!tid || esId === tid || typeof EventSource === 'undefined') return;
        if (es) { try { es.close(); } catch (e) {} }
        esId = tid;
        try { es = new EventSource('/api/stream/' + tid); } catch (e) { es = null; return; }
        es.addEventListener('stage', function (ev) {
            try { var d = JSON.parse(ev.data); stage(d.stage, ''); } catch (e) {}
        });
        es.addEventListener('partial', function (ev) {
            try {
                var d = JSON.parse(ev.data);
                var prev = (tw[d.field] && tw[d.field].full) || '';
                twSet(d.field, prev + (d.delta || ''));
            } catch (e) {}
        });
        es.addEventListener('done', function () { sseClose(); });
        es.onerror = function () { sseClose(); };
    }
    function sseClose() {
        if (es) { try { es.close(); } catch (e) {} }
        es = null; esId = null;
    }

    /* ---------- 4. 挂到现有流程上 ---------- */
    if (typeof window.streamPrepare === 'function') {
        var _p = window.streamPrepare;
        window.streamPrepare = function () { reset(); twReset(); sseOpen(window._currentTaskId); return _p.apply(this, arguments); };
    }
    if (typeof window.paintPartial === 'function') {
        var _q = window.paintPartial;
        // 轮询拿到第一个 partial 时才拿到 task_id，这里补开 SSE
        window.paintPartial = function () {
            var r = _q.apply(this, arguments);
            sseOpen(window._currentTaskId);
            return r;
        };
    }
    if (typeof window.streamFinish === 'function') {
        var _f = window.streamFinish;
        window.streamFinish = function () { sseClose(); return _f.apply(this, arguments); };
    }

    /* ---------- 5. 结果页顶部风格切换 ---------- */
    var _sfTried = false;
    function styleFill() {
        var bar = document.getElementById('wbStyleBar');
        var sel = document.getElementById('styleQuickSel');
        if (!bar || !sel) return;
        var lib = window._themeLib || [];
        // 主题库走 /api/ppt_themes 异步拉，result 先渲染完时还拿不到 → 主动拉一次再填
        if (!lib.length && !_sfTried && typeof loadThemeLib === 'function') {
            _sfTried = true;
            try { Promise.resolve(loadThemeLib()).then(function () { styleFill(); }); } catch (e) {}
            return;
        }
        if (!lib.length) { bar.style.display = 'none'; return; }
        _sfTried = false;
        var cur = (document.getElementById('deckTheme') || {}).value || '';
        sel.innerHTML = lib.map(function (t) {
            var nm = t.name || t.label || t.key;
            // 窄屏上「星海蓝（科技星空・iCAN / 电子设计 / 工程类）」会被截成半句，
            // 下拉里只放主名，完整说明挂到 title 上，鼠标悬停 / 长按仍看得到
            var p = String(nm).indexOf('（');
            var short = p > 0 ? String(nm).slice(0, p) : String(nm);
            return '<option value="' + ESC(t.key) + '"' + (t.key === cur ? ' selected' : '') +
                   ' title="' + ESC(nm) + '">' + ESC(short) + '</option>';
        }).join('');
        // 样式表里 #wbStyleBar 初始 display:none，必须显式写 flex ——
        // 写 '' 会回落到样式表的 none，整条永远不显示（这个坑踩过两次）
        bar.style.display = 'flex';
        stylePrevFill();
    }
    // 结果页风格条的小预览：复用导出中心那套缩略图（wbThemeThumb 在主 IIFE 里是全局函数）。
    // 拿不到主题库 / 函数不存在时整块隐藏，最坏结果是少一张小图，不影响切换。
    function stylePrevFill() {
        var box = document.getElementById('styleQuickPrev');
        if (!box) return;
        var lib = window._themeLib || [];
        var cur = (document.getElementById('deckTheme') || {}).value || '';
        var t = null;
        lib.forEach(function (x) { if (x.key === cur) t = x; });
        var html = '';
        if (t) {
            try {
                if (typeof wbThemeThumb === 'function' && typeof wbThemeColors === 'function') {
                    html = wbThemeThumb(wbThemeColors(t), t.layout);
                }
            } catch (e) { html = ''; }
        }
        if (!html) { box.innerHTML = ''; box.style.display = 'none'; return; }
        var lb = String(t.name || t.label || t.key);
        var p = lb.indexOf('（');
        var short = p > 0 ? lb.slice(0, p) : lb;
        box.style.display = 'inline-flex';
        box.innerHTML =
            '<span style="width:76px; height:42px; display:inline-block; border-radius:5px; overflow:hidden; flex:none;">'
            + html + '</span>' +
            '<span style="margin-left:6px; font-size:11.5px; color:var(--text-mute); white-space:nowrap;">'
            + ESC(short) + '</span>';
        box.title = lb;   // 完整名（含适用场景）仍挂在这里，悬停/长按可见
    }
    window.wbStyleQuick = function () {
        var sel = document.getElementById('styleQuickSel');
        var d = document.getElementById('deckTheme');
        if (!sel || !d) return;
        d.value = sel.value;
        try { if (typeof wbSyncThemeCards === 'function') wbSyncThemeCards(sel.value); } catch (e) {}
        try { _themeManual = true; } catch (e) {}
        if (typeof onThemeChange === 'function') onThemeChange();
        try { stylePrevFill(); } catch (e) {}
        if (typeof wbToast === 'function') {
            var _lb = sel.options[sel.selectedIndex].getAttribute('title') || sel.options[sel.selectedIndex].text;
            wbToast('已切到「' + _lb + '」，下方预览已刷新', { type: 'ok', ms: 2000 });
        }
    };
    // 主题库是异步拉的，renderRich 之后再补一次，避免下拉框是空的
    function styleFillSoon() {
        styleFill();
        setTimeout(styleFill, 900);
        setTimeout(styleFill, 2500);
    }
    if (typeof window.previewDeckStyle === 'function') {
        var _d = window.previewDeckStyle;
        window.previewDeckStyle = function () { var r = _d.apply(this, arguments); styleFill(); return r; };
    }
    if (typeof window.renderRich === 'function') {
        var _r = window.renderRich;
        window.renderRich = function () { var r = _r.apply(this, arguments); styleFillSoon(); return r; };
    }
    if (typeof window.wbPickTheme === 'function') {
        var _t = window.wbPickTheme;
        window.wbPickTheme = function () { var r = _t.apply(this, arguments); styleFill(); return r; };
    }

    // 导出给外部（paintPartial / 轮询路径直接用）
    window.wbAgentStage = stage;
    window.wbAgentFinish = finish;
    window.wbAgentReset = reset;
    window.twSet = twSet;          // paintPartial 内部调用，必须挂全局
    window.wbStyleFill = styleFill;
    window.twReset = twReset;
})();


/* ===== Codex 接手：手机端 5 个细节优化 ===== */
(function () {
    // 1) 首屏骨架屏：JS 就绪后淡出（最迟 window load 兜底隐藏）
    function hideSkeleton() {
        var s = document.getElementById('pageSkeleton');
        if (!s) return;
        s.classList.add('hide');
        setTimeout(function () { try { s.remove(); } catch (e) {} }, 400);
    }
    if (document.readyState === 'complete') { hideSkeleton(); }
    else {
        window.addEventListener('load', hideSkeleton);
        setTimeout(hideSkeleton, 2500);  // 兜底：万一 load 迟迟不来也别一直挡着
    }

    // 2) 回到顶部按钮：下滑一段距离才出现
    var topBtn = document.getElementById('wbTop');
    function toggleTop() {
        if (topBtn) topBtn.style.display = (window.scrollY || document.documentElement.scrollTop) > 800 ? 'flex' : 'none';
    }
    window.addEventListener('scroll', toggleTop, { passive: true });
    toggleTop();

    // 3) 虚拟键盘遮挡：输入框/文本域聚焦后，把页面往上顶，让输入框进入视口
    document.addEventListener('focusin', function (e) {
        var t = e.target;
        if (!t) return;
        // 只对「会弹出虚拟键盘」的文本类输入滚动；radio/checkbox/button/file 一律不滚
        var scrollable = (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT');
        if (t.tagName === 'INPUT' && (!t.type ||
            ['text', 'number', 'email', 'tel', 'url', 'search', 'password'].indexOf(t.type) >= 0)) {
            scrollable = true;
        }
        if (!scrollable) return;
        setTimeout(function () {
            try { t.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
            catch (err) { try { t.scrollIntoView(); } catch (e2) {} }
        }, 320);
    });

    // 4) 切后台回来：立即把可见状态唤醒（生成轮询会恢复；这里再触发一次 scroll 重算，避免键盘/高度错乱）
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) { try { toggleTop(); } catch (e) {} }
    });

    // 5) 日间/夜间切换：localStorage 记忆，按钮图标随主题换
    function applyTheme(light) {
        document.body.classList.toggle('light', !!light);
        var b = document.getElementById('themeToggle');
        if (b) {
            b.innerHTML = light
                ? '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
                : '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        }
        try { _wbStoreSet('wbLight', light ? '1' : '0'); } catch (e) {}
    }

    window.wbToggleTheme = function () {
        applyTheme(!document.body.classList.contains('light'));
    };
    (function initTheme() {
        // 默认日间（白底柔和）：负责人实测反馈深色背景刺眼，白底 + 柔和点缀色为默认。
        // 用户手动切过夜间仍按记忆走：wbLight='0' 才夜间；没记录过的老用户一律日间。
        var light = true;
        try {
            var v = _wbStoreGet('wbLight');
            if (v === '0') light = false; else if (v === '1') light = true;
        } catch (e) {}
        applyTheme(light);
    })();
})();


/* ===== WorkBuddy 接手：等待期三件套 =====
   A 冷知识轮播 / B 实时字数徽章 / C 点灵感碎片
   设计原则：自驱动 + 零侵入。只在 #progressSteps 上挂一个 MutationObserver 感知「生成开始/结束」，
   不往主流程塞任何回调，也不调用主 IIFE 的内部函数（wbToast 之类跨块取不到，这里自带轻量提示）。
   万一整块失效，最坏结果是等待区少三样装饰，不影响生成。 */
(function () {
    // 冷知识：以科技史趣闻为主 + 少量「真的吗」调剂。全部是有据可查的真事，不编数字。
    // 写法刻意走「钩子 + 反转」：用户在等生成，要的是有意思，不是比赛条文。
    var TIPS = [
        '评委最先看的是「问题是否真实存在」：开头写清目标用户在什么场景下遇到什么麻烦，比先讲技术架构更容易拿分。',
        '能量化的地方一定量化：「识别准确率 92%」「单次成本 0.4 元」比「效果良好」有说服力得多；没有实测就写明测算口径和依据。',
        '技术章节别堆名词：写清「为什么选它、放弃了什么」，评委更在意取舍逻辑而不是技术清单。',
        '创新性要落在对比上：和现有方案比，你在哪一处做得更轻、更快、更便宜——最好是一句话能说清的那一处。',
        '可行性靠证据支撑：Demo 截图、测试记录、试用人数的原始记录，都比形容词管用。',
        '团队分工写「谁负责什么、做过什么同类事」，不要只列姓名和专业。',
        '风险章节别写一句「风险可控」就结束：写出你识别到的具体风险和对应的应对动作。',
        '商业 / 落地部分忌空话：给出定价依据、获客渠道和成本结构，哪怕是测算也要写明假设。',
        '篇幅不是越长越好：评委是快速翻阅，章节标题要能自解释，关键句放段首。',
        '答辩最常被追问的三件事：数据哪来的、和现有方案差在哪、你能不能真的做出来——提前各准备一句。',
        '同一份材料投不同赛道要改侧重：工程类看实现与测试，创业类看市场与商业模式，别一份稿子通投。',
        '提交前务必查一遍学校 / 导师信息：双盲赛事出现这些信息会直接扣分。',
        '图表要能自解释：标题写清「什么指标、什么口径、什么时间」，别让评委猜。',
        '占位符和示例数据一定要替换掉：评委一问「这个数怎么来的」，答不上来就很被动。'
    ];
;

    var tipCard = null, tipText = null, lenBadge = null, sparkCount = null, tipNext = null;
    var tipTimer = null, lenTimer = null, sparkTimer = null, layer = null;
    var tipQueue = [], tipIdx = 0, score = 0, running = false;

    function el(id) { return document.getElementById(id); }
    function shuffle(a) {
        for (var i = a.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var t = a[i]; a[i] = a[j]; a[j] = t;
        }
        return a;
    }
    function clear(t) { if (t) { clearInterval(t); } return null; }

    /* ---------- A 冷知识轮播 ---------- */
    function tipBuild() {
        tipQueue = shuffle(TIPS.slice());   // 纯趣味内容，不再按赛事排序
        tipIdx = 0;
    }
    function tipShow() {
        if (!tipText || !tipQueue.length) return;
        tipText.style.opacity = '0';
        setTimeout(function () {
            if (!tipText) return;
            tipText.innerText = tipQueue[tipIdx % tipQueue.length];
            tipIdx++;
            tipText.style.opacity = '1';
        }, 180);
    }
    function restartTipTimer() {
        tipTimer = clear(tipTimer);
        tipTimer = setInterval(tipShow, 7000);   // 条数变长，6 秒→7 秒，读起来从容些
    }
    function tipStart() {
        tipBuild();
        if (tipCard) tipCard.style.display = 'block';
        if (tipText) tipText.style.transition = 'opacity .3s';
        tipShow();
        restartTipTimer();
    }
    function tipStop() {
        tipTimer = clear(tipTimer);
        if (tipCard) tipCard.style.display = 'none';
    }

    /* ---------- B 实时字数徽章（口径对齐后端 _cjk_len） ---------- */
    function lenStart() {
        lenTimer = clear(lenTimer);
        lenTimer = setInterval(function () {
            if (!lenBadge) return;
            var n = window._wbCjkLen || 0;
            if (n > 0) {
                lenBadge.style.display = 'inline-block';
                // 169 轮：写成「正文 N 字」而不是「已生成 N 字」——这是等待界面唯一的字数入口，
            // 把口径写进标签本身，用户才不会拿它和别的数字对不上
            lenBadge.innerText = '正文 ' + n + ' 字';
            } else {
                lenBadge.style.display = 'none';
            }
        }, 500);
    }
    function lenStop() {
        lenTimer = clear(lenTimer);
        if (lenBadge) lenBadge.style.display = 'none';
    }

    /* ---------- C 点灵感碎片 ---------- */
    function injectCss() {
        if (el('wbSparkCss')) return;
        var s = document.createElement('style');
        s.id = 'wbSparkCss';
        s.textContent =
            '@keyframes wbSparkFloat{0%{transform:translateY(0) scale(.85);opacity:0}' +
            '12%{opacity:1}100%{transform:translateY(-78vh) scale(1.05);opacity:0}}' +
            '.wb-spark{position:absolute;pointer-events:auto;cursor:pointer;font-size:22px;' +
            'line-height:1;-webkit-user-select:none;user-select:none;animation:wbSparkFloat 7s linear forwards}' +
            '.wb-spark-hit{animation:none;transition:transform .25s ease-out,opacity .25s ease-out;' +
            'transform:scale(1.7);opacity:0}';
        document.head.appendChild(s);
    }
    function spawnSpark() {
        if (!layer || layer.childNodes.length > 5) return;   // 同屏最多 5 个，别糊满屏幕
        var s = document.createElement('div');
        s.className = 'wb-spark';
        // 去 emoji（第十七轮 #1）：老内核里 emoji 是豆腐块，改用页面已有的灯泡 SVG
        s.innerHTML = '<svg class="wb-ico" viewBox="0 0 24 24" style="width:20px;height:20px;"><use href="#wb-i-bulb"/></svg>';
        s.style.left = (6 + Math.random() * 84) + '%';
        s.style.bottom = (6 + Math.random() * 10) + '%';
        s.style.animationDuration = (6 + Math.random() * 2.5) + 's';
        var dead = false;
        function pop() {
            if (dead) return;
            dead = true;
            score++;
            if (sparkCount) {
                sparkCount.style.display = 'inline-block';
                sparkCount.innerText = '灵感 ' + score;
            }
            s.className = 'wb-spark wb-spark-hit';
            setTimeout(function () { if (s.parentNode) s.parentNode.removeChild(s); }, 280);
        }
        s.addEventListener('click', pop);
        s.addEventListener('touchstart', function (e) {
            if (e.cancelable) e.preventDefault();
            pop();
        }, { passive: false });
        layer.appendChild(s);
        setTimeout(function () { if (s.parentNode && !dead) s.parentNode.removeChild(s); }, 8500);
    }
    function sparkStart() {
        score = 0;
        injectCss();
        if (!layer) {
            layer = document.createElement('div');
            layer.id = 'wbSparkLayer';
            // 全屏飘浮层独立 fixed（不用 box-shadow 大扩散，祖先 overflow 一裁就没了）
            layer.style.cssText = 'position:fixed;left:0;top:0;width:100%;height:100%;' +
                'pointer-events:none;z-index:9998;overflow:hidden;';
            document.body.appendChild(layer);
        }
        if (sparkCount) { sparkCount.style.display = 'inline-block'; sparkCount.innerText = '灵感 0'; }
        sparkTimer = clear(sparkTimer);
        sparkTimer = setInterval(spawnSpark, 1100);
        setTimeout(spawnSpark, 400);
    }
    function sparkStop() {
        sparkTimer = clear(sparkTimer);
        if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
        layer = null;
        if (sparkCount) sparkCount.style.display = 'none';
        if (score > 0) miniToast('本次收集了 ' + score + ' 个灵感碎片');
    }
    // 自带轻量提示：主 IIFE 里的 wbToast 挂不到 window 上，跨块取不到，这里不依赖它
    function miniToast(msg) {
        var t = document.createElement('div');
        t.innerText = msg;
        t.style.cssText = 'position:fixed;left:50%;bottom:88px;transform:translateX(-50%);' +
            'z-index:9999;max-width:80%;padding:9px 16px;border-radius:999px;white-space:nowrap;' +
            'background:var(--surface-2);border:1px solid var(--line);color:var(--text);' +
            'font-size:13px;opacity:0;transition:opacity .25s;';
        document.body.appendChild(t);
        setTimeout(function () { t.style.opacity = '1'; }, 20);
        setTimeout(function () {
            t.style.opacity = '0';
            setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
        }, 2600);
    }

    /* ---------- 总控：生成开始/结束 ---------- */
    function allStart() {
        if (running) return;
        running = true;
        try { tipStart(); } catch (e) {}
        try { lenStart(); } catch (e) {}
        try { sparkStart(); } catch (e) {}
    }
    function allStop() {
        if (!running) return;
        running = false;
        try { sparkStop(); } catch (e) {}
        try { lenStop(); } catch (e) {}
        try { tipStop(); } catch (e) {}
    }
    function check() {
        var ps = el('progressSteps');
        if (!ps) return;
        if (ps.style.display !== 'none') allStart();
        else allStop();
    }

    function init() {
        tipCard = el('wbTipCard');
        tipText = el('wbTipText');
        tipNext = el('wbTipNext');
        lenBadge = el('lenBadge');
        sparkCount = el('wbSparkCount');
        if (tipNext) tipNext.onclick = function () { tipShow(); restartTipTimer(); };
        var ps = el('progressSteps');
        if (!ps) return;
        if (window.MutationObserver) {
            try {
                new MutationObserver(check).observe(ps, { attributes: true, attributeFilter: ['style'] });
                return;
            } catch (e) {}
        }
        setInterval(check, 800);   // 老内核兜底：没有 MutationObserver 就轮询
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    window.wbWaitKit = { start: allStart, stop: allStop };
})();
