/* ============================================================
 * 294 轮：智能体聊天系统 UI（独立文件，不碰 app.js / app.py）
 * 297 轮补丁：智能体命名「小创」 + 三档聊天风格（简洁严谨 / 轻松幽默 / 学术详细）
 *
 * - 命名：全站一致——面板标题「小创 · 科创赛事助手智能助手」、欢迎语、气泡提示均含「小创」
 *   （避开小爱/小度/小冰/小艺等大厂语音助手同名，规避侵权）
 * - 风格：气泡右上角小图标切换；三档只影响回复口吻，与生成风格互不影响；
 *   选择持久化走服务端 /api/user_state 的 personalization（配合 292 双端同步），
 *   接口不可用时降级 sessionStorage，**不写 localStorage**（292 要求禁单端私有）
 * - 后端：POST /api/chat 支持 SSE；历史按 comp_uid 隔离持久化
 * - ES5 语法，全 try/catch，只暴露 window.wbChat
 *
 * 第三百三十六轮（移动端实测三处修复）：
 *   1. 开场白去「功能清单式自我介绍」，结合当前所选赛事，短句引导式
 *   2. 提问后立即出「正在思考」动效；6s 超时用 AbortController 真正中断请求并降级，
 *      降级文案友好且仍给可用答案（本地知识库），没命中时给「再问一次」按钮
 *   3. 风格切换：点标题栏或右上角都能弹三档菜单——原实现被 document 上的
 *      关闭监听在同一个 click 冒泡里立刻关掉（按钮没 stopPropagation），已修
 * ============================================================ */
(function () {
    if (window.wbChat) return;               // 防重复注入

    var AGENT_NAME = '小创';
    var AGENT_TITLE = '小创 · 科创赛事助手智能助手';
    var STORE_KEY = 'wbChatStyle';           // 仅作服务端不可用时的降级（sessionStorage）

    /* 297 轮：三档风格。取值必须与后端 /api/chat 的 style 入参一致（Codex 297 回执定稿）：
       concise=简洁严谨(默认) / casual=轻松幽默 / academic=学术详细。
       ⚠️ 我第一版写成了 brief/fun，与后端对不上会导致切了风格后端不生效，已对齐。 */
    var STYLES = [
        { id: 'concise',  name: '简洁严谨', hint: '精炼直给要点，适合评委/正式场景' },
        { id: 'casual',   name: '轻松幽默', hint: '口语化、带点趣味，适合日常答疑' },
        { id: 'academic', name: '学术详细', hint: '引用规则依据、展开论证，适合深挖细节' }
    ];
    // 旧值兼容（第一版用过 brief/fun，已落在用户会话里的要能认出来）
    var STYLE_ALIAS = { 'brief': 'concise', 'fun': 'casual' };
    var style = 'concise';

    var BUBBLE_SIZE = 48;
    var opened = false, panel = null, bubble = null, listEl = null, inputEl = null;
    var styleMenu = null, styleBadge = null, styleBtn = null;
    var busy = false;
    var historyLoaded = false, historyLoading = false;

    /* 336：等待阈值。后端 /api/chat 命中预设约 3ms，落到 LLM 兜底时可能数秒，
       超过这个时间就中断并降级，绝不让用户干等。 */
    var ASK_TIMEOUT = 6000;
    var thinkNode = null, thinkTimer = null;

    /* ---------- 本地预设问答（接口不可用时兜底，绝不显示红字报错） ----------
       每条目三档口吻：b=简洁严谨（默认）/ f=轻松幽默 / a=学术详细 */
    var PRESET = [
        {
            k: ['评分', '维度', '权重', '怎么打分', '评分标准'],
            b: '评分维度以所选赛事的官方口径为准，选中赛事后首页会显示该赛事的真实维度。例如 iCAN 创新赛道：创新性 35 / 实用性 25 / 原创性 20 / 技术方案 20（四项、双盲）。',
            f: '这个得看你报哪个赛事——官方口径说了算😉 选好赛事，首页就会把真实维度列出来。比如 iCAN 创新赛道是四门：创新性 35、实用性 25、原创性 20、技术方案 20，还是双盲评审。',
            a: '评分维度的权威来源是各赛事官方评审细则（data/competition_profiles.json）。以 iCAN 大学生创新创业大赛创新赛道为例，官方口径为四项：创新性 35 分、实用性 25 分、原创性 20 分、技术方案 20 分，合计 100 分，评审采用双盲方式。不同赛事、乃至同一赛事的不同赛道（如 iCAN 创新/创业/挑战赛道）口径可能不同，选中赛事后以页面显示的维度为准。'
        },
        {
            k: ['档位', '简洁', '深度', '有什么区别', '选哪个'],
            b: '简洁版快速出申报书骨架，适合先看方向；深度版多轮打磨、章节更厚，附竞品/商业/风险等模块，耗时更长但材料更完整。赶时间先简洁，正式提交用深度。',
            f: '简单说：想先看个方向 → 简洁版，快；要拿去正式交 → 深度版，厚。深度版会把竞品、商业模式、风险这些都给你铺开，就是得多等一会儿。',
            a: '两档的差异在于生成流程与材料厚度：简洁版走快速链路，输出完整申报书骨架，用于验证项目方向；深度版执行多轮打磨，章节更厚，并附加竞品分析、商业模式、风险评估等扩展模块，生成耗时显著更长。若用于正式提交，建议深度版；若仅需快速验证方向或时间受限，可选简洁版。'
        },
        {
            k: ['导出', '下载', 'word', 'ppt', 'pdf', '格式'],
            b: '导出中心支持 Word、PDF、PPT、打包 zip 等。导出会过一遍内容质检，没通过时会明确告诉你原因（如章节层级不足），内容不会丢，补齐后再导即可。',
            f: '导出中心里 Word / PDF / PPT / zip 打包都有。导出前会先过一遍质检，万一卡住它会直接告诉你卡在哪（比如章节层级不够），内容都还在，补齐再点一次就行。',
            a: '导出入口位于结果页「导出中心」，支持 Word（.docx）、PDF、PPT 及打包 zip 等形态。导出前系统会执行内容质检（quality_gate）：未通过时返回具体原因（如 Heading 层级过少），并以提示条明示；正文内容保留在页面上，补齐章节或重新生成后可再次导出，不会造成内容丢失。'
        },
        {
            k: ['字数', '多少字', '篇幅'],
            b: '不同赛事/档位字数口径不同，页面档位卡会显示该档位的实测字数区间，以页面显示为准。',
            f: '这个没有固定数——不同赛事、不同档位都不一样。页面上档位卡会写清楚实测区间，看那个最准。',
            a: '字数口径随赛事与档位变化，不存在统一数值。系统在档位卡中展示对应档位的实测字数区间（基于真实生成记录统计），请以页面实时显示为准——页面不写入固定数字，以避免与真实统计不一致。'
        },
        {
            k: ['赛事', '比赛', '选哪个赛事', '支持哪些'],
            b: '已内置 15 个赛事知识库（iCAN、互联网+、挑战杯、大创、电子设计等）。不确定报哪个？把项目创意写进输入框，系统会智能推荐。',
            f: '内置了 15 个赛事，iCAN、互联网+、挑战杯、大创、电子设计这些都在。拿不准报哪个？把你的创意往输入框一写，系统帮你猜一个～',
            a: '系统内置 15 个赛事的知识库（含 iCAN 大学生创新创业大赛、中国国际大学生创新大赛（互联网+）、挑战杯、大学生创新创业训练计划、电子设计竞赛等），来源为后端 knowledge/data/*.txt 的结构化索引。若不确定申报方向，可在「项目创意」中填写内容，系统会基于关键词匹配自动推荐赛事（关键词取长不取短，避免「建模」误覆盖「数学建模」）。'
        },
        {
            k: ['演示', 'demo', '一键演示', '额度'],
            b: '顶部「🎬 一键演示」用预置样例直接展示完整结果页：不调大模型、不消耗额度、不用等待生成。',
            f: '想看效果又不想等？点顶部「🎬 一键演示」，预置样例直接把完整结果页铺开——不烧额度、不用等～',
            a: '「🎬 一键演示」（270 轮）读取预置样例文件（static/demo_sample.json，取自真实生成记录）直接渲染完整结果页。该路径不调用大模型、不请求 /api/generate、不消耗生成额度，适用于评委演示与功能预览；演示会话为只读，不影响任何业务数据。'
        },
        {
            k: ['多少钱', '价格', '收费', '免费'],
            b: '额度与计费以页面额度展示为准，我这里不掌握实时数字，避免给你错的。',
            f: '这个数字我可不敢瞎说😅 页面上的额度显示是多少就是多少，看那个最靠谱。',
            a: '额度与计费信息以页面实时展示为准。本站遵循「实测统计数字不写死」原则，聊天侧亦不返回未经接口校验的数值，以免与实际额度不一致造成误导。'
        }
    ];

    /* 命中本地预设才返回文本；没命中返回 null，让调用方决定是兜底还是提示重问 */
    function presetAnswer(q) {
        var s = String(q || '');
        var contextual = ['项目', '创意', '评委', '匹配', '适合', '赛道',
            '可行性', '竞品', '市场', '怎么改', '如何优化', '分析一下', '评估一下', '根据我的',
            '那深度版', '那简洁版', '刚才', '前面', '上面说的'];
        if (s.length > 32) return null;
        for (var c = 0; c < contextual.length; c++) {
            if (s.indexOf(contextual[c]) >= 0) return null;
        }
        if (currentCompName() && ['评分', '打分', '维度', '权重', '章节', '结构', '目录', '赛事', '比赛']
            .some(function (term) { return s.indexOf(term) >= 0; })) return null;
        for (var i = 0; i < PRESET.length; i++) {
            for (var j = 0; j < PRESET[i].k.length; j++) {
                if (s.indexOf(PRESET[i].k[j]) >= 0) {
                    var p = PRESET[i];
                    if (style === 'casual') return p.f;
                    if (style === 'academic') return p.a;
                    return p.b;
                }
            }
        }
        return null;
    }

    function localAnswer(q) {
        var hit = presetAnswer(q);
        if (hit) return hit;
        var tail = '可以问我：评分维度、档位差异、导出格式、字数口径、赛事选择、演示模式。';
        if (style === 'casual') return '我是' + AGENT_NAME + '～ 这个我还没学会，换个问法试试？' + tail;
        if (style === 'academic') return '我是' + AGENT_NAME + '。当前问题未命中本地知识条目，且后端问答服务暂不可用。' + tail;
        return '我是' + AGENT_NAME + '，擅长回答赛事相关的问题。' + tail;
    }

    /* 336：超时降级文案——友好、说明发生了什么、并给出可用内容。
       hit=true 时这句话作为「小字附注」挂在答案下面，不喧宾夺主。 */
    function degradeNote(q) {
        if (style === 'casual') return '这会儿有点卡，上面是我先知道的，不让你白等～';
        if (style === 'academic') return '在线问答本轮响应偏慢（已超 6 秒并中断），以上依据本地知识库先行作答。';
        return '这会儿有点慢，先按本地知识库答你，没让你干等。';
    }

    /* 没命中本地预设、又超时——这条就没内容可给了，说清楚并给「再问一次」 */
    function degradeMiss(q) {
        if (style === 'casual') return '这会儿有点卡，这条我没能马上想出来。稍等一下再问一次，或者换个问法我很快就能答。';
        if (style === 'academic') return '在线问答本轮响应偏慢（已超 6 秒并中断），且该问题未命中本地知识条目，暂无法作答。可稍后重试，或改问评分维度、档位差异、导出格式、字数口径、赛事选择、演示模式。';
        return '这会儿有点慢，这条我还没想好。稍等一下再问一次会更准；问评分、档位、导出、字数这些我马上能答。';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function renderMarkdown(text) {
        var code = [];
        var html = esc(text).replace(/```([^\n]*)\n([\s\S]*?)```/g, function (_, lang, body) {
            var key = '@@WBCODE' + code.length + '@@';
            code.push('<pre><code>' + body.replace(/\n$/, '') + '</code></pre>');
            return key;
        });
        html = html.replace(/`([^`\n]+)`/g, function (_, body) {
            var key = '@@WBCODE' + code.length + '@@';
            code.push('<code>' + body + '</code>');
            return key;
        });
        html = html.replace(/\[([^\]]{1,200})\]\((https?:\/\/[^\s)]+)\)/gi, function (_, label, url) {
            return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
        });
        html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
                   .replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
        var lines = html.split(/\r?\n/), out = [], list = '';
        function closeList() {
            if (list) { out.push('</' + list + '>'); list = ''; }
        }
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i], ul = /^\s*[-*]\s+(.+)$/.exec(line), ol = /^\s*\d+\.\s+(.+)$/.exec(line);
            if (ul || ol) {
                var kind = ul ? 'ul' : 'ol';
                if (list !== kind) { closeList(); out.push('<' + kind + '>'); list = kind; }
                out.push('<li>' + (ul || ol)[1] + '</li>');
            } else {
                closeList();
                if (line) out.push('<p>' + line + '</p>');
            }
        }
        closeList();
        html = out.join('');
        for (var c = 0; c < code.length; c++) html = html.replace('@@WBCODE' + c + '@@', code[c]);
        return html;
    }

    function isMobile() { return window.innerWidth <= 768; }

    /* ---------- 336：当前所选赛事名（开场白要用） ----------
       首页赛事输入框是 #competition（input + datalist）。取不到就返回 ''，
       由调用方退回不带赛事名的短句——绝不写死赛事名。 */
    function currentCompName() {
        try {
            var el = document.getElementById('competition');
            var v = el ? String(el.value || '').trim() : '';
            if (!v) return '';
            v = v.replace(/\s+/g, ' ');
            return v.length > 20 ? v.slice(0, 20) : v;   // 开场白要短，过长截断（不加省略号）
        } catch (e) { return ''; }
    }

    function currentPageContext() {
        function value(id, max) {
            try {
                var el = document.getElementById(id);
                return el ? String(el.value || '').trim().slice(0, max) : '';
            } catch (e) { return ''; }
        }
        var selectedMode = document.querySelector('input[name="mode"]:checked');
        return {
            competition: value('competition', 120),
            idea: value('idea', 1200),
            mode: selectedMode && (selectedMode.value === 'deep' || selectedMode.value === 'fast')
                ? selectedMode.value : ''
        };
    }

    /* ---------- 风格持久化：优先服务端（292 双端同步），降级 sessionStorage ---------- */
    function loadStyle() {
        // 先读本地降级值，保证首屏不闪；随后由服务端覆盖（服务端为准）
        try {
            var v = normalizeStyle(sessionStorage.getItem(STORE_KEY));
            if (v && validStyle(v)) style = v;
        } catch (e) {}
        try {
            fetch('/api/user_state', { method: 'GET' }).then(function (r) { return r.ok ? r.json() : null; })
                .then(function (j) {
                    if (!j || j.success !== true || !j.state) return;
                    var p = j.state.personalization || {};
                    var v = normalizeStyle(p.chatStyle || p.chat_style);
                    if (v && validStyle(v)) { style = v; renderStyleBadge(); }
                }).catch(function () {});
        } catch (e) {}
    }

    function saveStyle(v) {
        style = v;
        try { sessionStorage.setItem(STORE_KEY, v); } catch (e) {}
        try {
            fetch('/api/user_state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: { personalization: { chatStyle: v } } })
            }).catch(function () {});
        } catch (e) {}
        renderStyleBadge();
    }

    function normalizeStyle(v) {
        // 第一版用过 brief/fun，落在用户会话里的旧值要认出来并映射成后端口径
        return (v && STYLE_ALIAS[v]) ? STYLE_ALIAS[v] : v;
    }

    function validStyle(v) {
        for (var i = 0; i < STYLES.length; i++) { if (STYLES[i].id === v) return true; }
        return false;
    }

    function styleName() {
        for (var i = 0; i < STYLES.length; i++) { if (STYLES[i].id === style) return STYLES[i].name; }
        return STYLES[0].name;
    }

    /* ---------- 气泡 + 右上角风格小图标 ---------- */
    function makeBubble() {
        var wrap = document.createElement('div');
        wrap.id = 'wbChatBubble';
        wrap.setAttribute('role', 'button');
        wrap.setAttribute('aria-label', '打开' + AGENT_NAME + '问答');
        wrap.title = AGENT_NAME + ' · 科创赛事助手智能助手（只答不写，不消耗额度）';
        wrap.innerHTML =
            '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" '
          + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
          + '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.9-.9L3 20l1.4-4.2A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/></svg>'
            // 297：右上角风格切换小图标
          + '<span id="wbChatStyleBadge" title="切换聊天风格" style="position:absolute; top:-4px; right:-4px;'
          + ' width:20px; height:20px; border-radius:50%; display:flex; align-items:center; justify-content:center;'
          + ' font-size:11px; font-weight:700; cursor:pointer; border:1px solid var(--line,rgba(148,163,184,.5));'
          + ' background:var(--surface-solid,#fff); color:var(--c-a,#0e7490);">文</span>';

        var st = wrap.style;
        st.position = 'fixed';
        st.right = '16px';
        st.bottom = '196px';                 // 302 队形：fab16 / ↑76 / ↓136 / 聊196，间距 12px
        st.width = st.height = BUBBLE_SIZE + 'px';
        st.borderRadius = '50%';
        st.display = 'flex';
        st.alignItems = 'center';
        st.justifyContent = 'center';
        st.cursor = 'pointer';
        st.zIndex = '2600';
        st.border = '1px solid var(--line, rgba(148,163,184,.45))';
        st.background = 'linear-gradient(135deg, rgba(var(--c-a-rgb,14,116,144),.95), rgba(var(--c-b-rgb,15,118,110),.95))';
        st.color = '#fff';
        st.boxShadow = '0 6px 18px rgba(15,23,42,.22)';
        st.transition = 'transform .15s ease, box-shadow .18s ease';

        wrap.addEventListener('mouseenter', function () { st.transform = 'translateY(-2px)'; });
        wrap.addEventListener('mouseleave', function () { st.transform = ''; });
        wrap.addEventListener('click', function (e) {
            if (e && e.target && e.target.id === 'wbChatStyleBadge') return;   // 点小图标不开关面板
            toggle();
        });
        document.body.appendChild(wrap);

        styleBadge = document.getElementById('wbChatStyleBadge');
        if (styleBadge) {
            styleBadge.setAttribute('aria-haspopup', 'menu');
            styleBadge.setAttribute('aria-expanded', 'false');
            styleBadge.addEventListener('click', function (e) { toggleStyleMenu(e, styleBadge); });
        }
        return wrap;
    }

    function paintStyleBtn(bg, bd) {
        if (!styleBtn) return;
        try { styleBtn.style.background = bg; styleBtn.style.borderColor = bd; } catch (e) {}
    }

    /* 回显当前风格：气泡角标 + 标题栏标签文字 + 箭头方向 + aria，三处同步 */
    function renderStyleBadge() {
        if (styleBadge) {
            styleBadge.textContent = style === 'casual' ? '趣' : (style === 'academic' ? '详' : '简');
            styleBadge.title = '聊天风格：' + styleName() + '（点击切换）';
        }
        var active = document.getElementById('wbChatStyleCur');
        if (active) active.textContent = styleName();
        if (styleBtn) {
            styleBtn.title = '聊天风格：' + styleName() + '（点击切换）';
            styleBtn.setAttribute('aria-label', '聊天风格：' + styleName() + '，点击切换');
        }
        var caret = document.getElementById('wbChatStyleCaret');
        if (caret) caret.textContent = menuIsOpen() ? '▴' : '▾';
        var items = document.querySelectorAll('#wbChatStyleMenu .wbchat-style-item');
        for (var i = 0; i < items.length; i++) {
            var on = items[i].getAttribute('data-style') === style;
            /* 399/402：选中态用「淡底色 + 描边环 + 加粗」表达，文字仍走 --text。
               此前选中项文字用了 --c-a，在 14% 青色底上只有 4.28:1，13px 正文不满足 AA，已改。 */
            items[i].style.background = on ? 'rgba(var(--c-a-rgb,14,116,144),.14)' : 'transparent';
            items[i].style.boxShadow = on ? 'inset 0 0 0 1px rgba(var(--c-a-rgb,14,116,144),.5)' : 'none';
            items[i].style.fontWeight = on ? '700' : '400';
            items[i].style.color = 'var(--text)';
            try { items[i].setAttribute('aria-checked', on ? 'true' : 'false'); } catch (e) {}
        }
    }

    /* 336：风格弹层
       原实现点标题栏按钮不弹，原因是按钮 handler 没 stopPropagation，同一个 click 冒泡到
       document 上的「点外面就关」监听，刚 open 就被立刻 close（badge 有 stopPropagation 所以只有它能开）。
       修法：所有触发入口都 stopPropagation；再顺手把定位改成锚在触发元素下方，移动端不再飘在屏幕外。 */
    function setMenuOpen(v) {
        if (!styleMenu) return;
        styleMenu.style.display = v ? 'block' : 'none';
        try {
            if (styleBtn) styleBtn.setAttribute('aria-expanded', v ? 'true' : 'false');
            if (styleBadge) styleBadge.setAttribute('aria-expanded', v ? 'true' : 'false');
        } catch (e) {}
        renderStyleBadge();     // 箭头 ▾/▴ 与选中态跟着开合一起回显
    }

    function menuIsOpen() { return !!styleMenu && styleMenu.style.display === 'block'; }

    function placeMenu(anchor) {
        if (!styleMenu) return;
        var w = Math.min(230, (window.innerWidth || 360) - 24);
        var left = 16, top = 0;
        try {
            var r = (anchor || styleBtn || styleBadge).getBoundingClientRect();
            left = Math.round(r.right) - w;              // 右对齐触发元素
            if (left < 8) left = 8;
            if (left + w > (window.innerWidth || 360) - 8) left = (window.innerWidth || 360) - 8 - w;
            top = Math.round(r.bottom) + 8;              // 落在触发元素正下方
            var h = styleMenu.offsetHeight || 190;
            if (top + h > (window.innerHeight || 640) - 8) top = Math.max(8, Math.round(r.top) - h - 8);
        } catch (e) { top = 60; }
        styleMenu.style.left = left + 'px';
        styleMenu.style.top = top + 'px';
        styleMenu.style.width = w + 'px';
    }

    function toggleStyleMenu(ev, anchor) {
        try { if (ev && ev.stopPropagation) ev.stopPropagation(); } catch (e) {}
        if (!styleMenu) buildStyleMenu();
        if (menuIsOpen()) { setMenuOpen(false); return; }
        styleMenu.style.display = 'block';
        placeMenu(anchor);
        setMenuOpen(true);
        renderStyleBadge();
    }

    function buildStyleMenu() {
        styleMenu = document.createElement('div');
        styleMenu.id = 'wbChatStyleMenu';
        styleMenu.setAttribute('role', 'menu');
        styleMenu.style.cssText = 'position:fixed; z-index:2800; display:none; padding:6px;'
            + ' background:var(--surface-solid,#fff); color:var(--text);'
            + ' border:1px solid var(--line,rgba(148,163,184,.4)); border-radius:12px;'
            + ' box-shadow:0 12px 32px rgba(15,23,42,.24);';
        var html = '<div style="font-size:11.5px; color:var(--text-dim); padding:6px 8px;">聊天风格（只影响回复口吻）</div>';
        for (var i = 0; i < STYLES.length; i++) {
            html += '<div class="wbchat-style-item" role="menuitemradio" data-style="' + STYLES[i].id + '"'
                + ' style="padding:11px 10px; border-radius:9px; cursor:pointer; font-size:13px;">'
                + '<div>' + STYLES[i].name + '</div>'
                + '<div style="font-size:11px; color:var(--text-dim); margin-top:2px; line-height:1.5;">'
                + STYLES[i].hint + '</div></div>';
        }
        styleMenu.innerHTML = html;
        document.body.appendChild(styleMenu);
        var items = styleMenu.querySelectorAll('.wbchat-style-item');
        (function (nodes) {
            for (var j = 0; j < nodes.length; j++) {
                nodes[j].addEventListener('click', function (e) {
                    try { if (e && e.stopPropagation) e.stopPropagation(); } catch (er) {}
                    saveStyle(this.getAttribute('data-style'));
                    setMenuOpen(false);
                    refreshGreet();      // 399：开场白口吻跟着风格一起换，别留着上一个风格的旧话术
                    pushMsg('bot', '已切到「' + styleName() + '」，后面就按这个口吻聊。');
                });
            }
        })(items);
        setMenuOpen(false);
    }

    /* ---------- 面板 ---------- */
    function makePanel() {
        var p = document.createElement('div');
        p.id = 'wbChatPanel';
        var st = p.style;
        st.position = 'fixed';
        st.zIndex = '2700';
        st.display = 'none';
        st.flexDirection = 'column';
        st.background = 'var(--surface-solid, #fff)';
        st.border = '1px solid var(--line, rgba(148,163,184,.4))';
        st.borderRadius = '14px';
        st.boxShadow = '0 18px 50px rgba(15,23,42,.28)';
        st.overflow = 'hidden';
        if (isMobile()) {
            st.left = '0'; st.right = '0'; st.bottom = '0';
            st.width = '100%';
            st.height = '70vh';
            st.maxHeight = '70vh';
            st.borderRadius = '14px 14px 0 0';
        } else {
            st.right = '16px';
            st.bottom = '196px';
            st.width = '360px';
            st.height = '520px';
        }

        /* 399：风格标签做成一眼可点的控件——整块热区 ≥44px、右侧 ▾ 箭头、hover/active 有反馈 */
        p.innerHTML =
            '<div id="wbChatHead" style="display:flex; align-items:center; gap:8px; padding:8px 14px;'
          + ' min-height:60px;'
          + ' border-bottom:1px solid var(--line,rgba(148,163,184,.3)); cursor:pointer;">'
          + '<b style="font-size:13.5px; color:var(--text); line-height:1.35;">' + AGENT_TITLE + '</b>'
          + '<button id="wbChatStyleBtn" title="切换聊天风格" aria-haspopup="menu" aria-expanded="false"'
          + ' style="flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center;'
          + ' gap:5px; min-height:44px; min-width:104px; padding:0 12px;'
          + ' border-radius:11px; border:1px solid var(--line,rgba(148,163,184,.55));'
          + ' background:var(--btn-ghost); color:var(--text); font-size:12.5px; cursor:pointer;'
          + ' -webkit-tap-highlight-color:transparent; touch-action:manipulation;">'
          /* 402：三个内部 span 一律 color:inherit。
             style.css 的 !important 规则会把按钮 hover 态底色刷成 --c-a（#0e7490）配白字，
             若这里写死深色/次要色，hover 时文字只有 2.9:1 基本看不见；跟着父亲继承才能一起变白。
             层级感改用字号 + 字重表达（「风格：」400、当前风格名 600）。 */
          + '<span style="color:inherit; font-weight:400;">风格：</span>'
          + '<span id="wbChatStyleCur" style="font-weight:600; color:inherit;">简洁严谨</span>'
          + '<span id="wbChatStyleCaret" aria-hidden="true" style="font-size:10px; line-height:1;'
          + ' color:inherit;">▾</span></button>'
          + '<button id="wbChatClear" title="清空对话历史" style="flex:0 0 auto; min-width:48px; min-height:40px;'
          + ' border-radius:9px; border:1px solid var(--line); background:var(--btn-ghost);'
          + ' color:var(--text-dim); cursor:pointer; font-size:12px;">清空</button>'
          + '<button id="wbChatClose" aria-label="收起" style="margin-left:auto; width:44px; height:44px;'
          + ' border-radius:11px; border:1px solid var(--line); background:var(--btn-ghost);'
          + ' color:var(--text-dim,#6b7280); cursor:pointer; line-height:1;">×</button></div>'
          + '<div id="wbChatList" style="flex:1 1 auto; overflow-y:auto; padding:12px 14px;'
          + ' font-size:13px; line-height:1.7; color:var(--text);"></div>'
          + '<div style="display:flex; gap:8px; padding:10px 12px;'
          + ' border-top:1px solid var(--line,rgba(148,163,184,.3));">'
          + '<input id="wbChatInput" placeholder="问问' + AGENT_NAME + '：评分维度、档位差异、导出格式…" '
          + 'style="flex:1 1 auto; min-width:0; min-height:44px; padding:8px 12px; border-radius:11px;'
          + ' border:1px solid var(--line); background:var(--surface-2); color:var(--text); font-size:13px;">'
          + '<button id="wbChatSend" style="flex:0 0 auto; min-height:44px; padding:8px 16px;'
          + ' border-radius:10px; border:none; cursor:pointer; font-size:13px; font-weight:600; color:#fff;'
          + ' background:linear-gradient(135deg, rgba(var(--c-a-rgb,14,116,144),.95), rgba(var(--c-b-rgb,15,118,110),.95));">发送</button>'
          + '</div>';

        document.body.appendChild(p);

        var close = document.getElementById('wbChatClose');
        if (close) close.addEventListener('click', function (e) {
            try { if (e && e.stopPropagation) e.stopPropagation(); } catch (er) {}
            setOpen(false);
        });
        var clearBtn = document.getElementById('wbChatClear');
        if (clearBtn) clearBtn.addEventListener('click', function (e) {
            try { if (e && e.stopPropagation) e.stopPropagation(); } catch (er) {}
            clearHistory(clearBtn);
        });
        var sb = document.getElementById('wbChatStyleBtn');
        styleBtn = sb;
        // 336：标题栏整条也可点（除关闭按钮），右上角按钮同理——两处入口都 stopPropagation
        var head = document.getElementById('wbChatHead');
        if (head) head.addEventListener('click', function (e) { toggleStyleMenu(e, sb || head); });
        if (sb) {
            sb.addEventListener('click', function (e) { toggleStyleMenu(e, sb); });
            // 399：hover / active 反馈——一眼看出这玩意儿能点（不新增 css 文件，只写内联）
            var normalBg = 'var(--btn-ghost)';
            var normalBd = 'var(--line,rgba(148,163,184,.55))';
            sb.addEventListener('mouseenter', function () {
                sb.style.background = 'rgba(var(--c-a-rgb,14,116,144),.12)';
                sb.style.borderColor = 'var(--c-a,#0e7490)';
            });
            sb.addEventListener('mouseleave', function () { paintStyleBtn(normalBg, normalBd); });
            sb.addEventListener('mousedown', function () {
                sb.style.background = 'rgba(var(--c-a-rgb,14,116,144),.22)';
            });
            sb.addEventListener('mouseup', function () { paintStyleBtn(normalBg, normalBd); });
            sb.addEventListener('focus', function () { sb.style.borderColor = 'var(--c-a,#0e7490)'; });
            sb.addEventListener('blur', function () { paintStyleBtn(normalBg, normalBd); });
        }
        inputEl = document.getElementById('wbChatInput');
        var send = document.getElementById('wbChatSend');
        if (send) send.addEventListener('click', ask);
        if (inputEl) {
            inputEl.addEventListener('keydown', function (e) {
                if (e && (e.key === 'Enter' || e.keyCode === 13)) ask();
            });
        }
        listEl = document.getElementById('wbChatList');
        return p;
    }

    /* ---------- 336：等待态气泡（点阵动效，纯 JS 驱动，不新增 CSS 文件） ---------- */
    function pushThinking() {
        removeThinking();
        if (!listEl) return;
        var d = document.createElement('div');
        d.id = 'wbChatThinking';
        d.setAttribute('aria-live', 'polite');
        d.innerHTML = '<div style="display:inline-block; padding:8px 11px;'
            + ' border-radius:12px 12px 12px 2px; background:var(--btn-ghost); color:var(--text-dim);">'
            + '<span>' + AGENT_NAME + '正在思考</span>'
            + '<span id="wbChatDot0" style="display:inline-block; width:6px;">.</span>'
            + '<span id="wbChatDot1" style="display:inline-block; width:6px;">.</span>'
            + '<span id="wbChatDot2" style="display:inline-block; width:6px;">.</span>'
            + '</div>';
        listEl.appendChild(d);
        try { listEl.scrollTop = listEl.scrollHeight; } catch (e) {}
        thinkNode = d;
        var step = 0;
        try {
            thinkTimer = setInterval(function () {
                step = (step + 1) % 3;
                for (var i = 0; i < 3; i++) {
                    var n = document.getElementById('wbChatDot' + i);
                    if (n) n.style.opacity = (i === step) ? '1' : '.28';
                }
            }, 380);
        } catch (e) {}
    }

    function removeThinking() {
        try { if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null; } } catch (e) {}
        try { if (thinkNode && thinkNode.parentNode) thinkNode.parentNode.removeChild(thinkNode); } catch (e) {}
        thinkNode = null;
    }

    /* 336：pushMsg 增加 opts —— {sub: 次要小字, action: {label, onClick}, greet: true}
       只用内联样式，不动任何 css 文件。 */
    function pushMsg(who, text, opts) {
        if (!listEl) return;
        opts = opts || {};
        var d = document.createElement('div');
        d.style.marginBottom = '10px';
        if (opts.greet) d.setAttribute('data-wbgreet', '1');
        if (who === 'me') {
            d.style.textAlign = 'right';
            d.innerHTML = '<span style="display:inline-block; max-width:82%; padding:8px 11px;'
                + ' border-radius:12px 12px 2px 12px; background:rgba(var(--c-a-rgb,14,116,144),.14);'
                + ' color:var(--text); white-space:normal; word-break:break-word;">' + esc(text) + '</span>';
        } else {
            d.innerHTML = '<div style="display:inline-block; max-width:88%; padding:8px 11px;'
                + ' border-radius:12px 12px 12px 2px; background:var(--btn-ghost); color:var(--text);'
                + ' white-space:normal; word-break:break-word;"><div class="wbchat-bot-content">' + renderMarkdown(text) + '</div>'
                + (opts.sub ? '<div style="margin-top:4px; font-size:11.5px; line-height:1.5;'
                    + ' color:var(--text-dim);">' + esc(opts.sub) + '</div>' : '')
                + '</div>';
        }
        listEl.appendChild(d);
        if (opts.action && opts.action.label) {
            var a = opts.action;
            var b = document.createElement('button');
            b.id = a.id || '';
            b.style.cssText = 'display:block; margin:2px 0 6px; min-height:44px; padding:9px 14px;'
                + ' border-radius:11px; border:1px solid var(--line,rgba(148,163,184,.5));'
                + ' background:transparent; color:var(--c-a,#0e7490); font-size:12.5px; cursor:pointer;';
            b.textContent = a.label;
            b.addEventListener('click', function () { try { a.onClick(); } catch (e) {} });
            listEl.appendChild(b);
        }
        try { listEl.scrollTop = listEl.scrollHeight; } catch (e) {}
        return d;
    }

    function updateBotMsg(node, text) {
        if (!node) return;
        var content = node.querySelector('.wbchat-bot-content');
        if (content) content.innerHTML = renderMarkdown(text);
        try { if (listEl) listEl.scrollTop = listEl.scrollHeight; } catch (e) {}
    }

    function restoreHistory() {
        if (historyLoaded || historyLoading || !listEl) return;
        historyLoading = true;
        if (inputEl) inputEl.disabled = true;
        pushThinking();
        fetch('/api/chat_history', { method: 'GET', credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) {
                removeThinking();
                if (j && j.success && j.messages && j.messages.length) {
                    for (var i = 0; i < j.messages.length; i++) {
                        var m = j.messages[i];
                        pushMsg(m.role === 'user' ? 'me' : 'bot', m.content || '');
                    }
                } else {
                    pushMsg('bot', greetText(), { greet: true, sub: greetSub() });
                }
                historyLoaded = true;
                historyLoading = false;
                if (inputEl) inputEl.disabled = false;
            })
            .catch(function () {
                removeThinking();
                if (!listEl.children.length) pushMsg('bot', greetText(), { greet: true, sub: greetSub() });
                historyLoaded = true;
                historyLoading = false;
                if (inputEl) inputEl.disabled = false;
            });
    }

    function clearHistory(button) {
        if (busy || historyLoading || !button) return;
        button.disabled = true;
        fetch('/api/chat_clear', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: '{}'
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
              if (!j || !j.success) return;
              listEl.innerHTML = '';
              pushMsg('bot', greetText(), { greet: true, sub: greetSub() });
              historyLoaded = true;
          }).catch(function () {})
          .then(function () { button.disabled = false; });
    }

    /* 336：
       - 提问后立刻渲染「小创正在思考…」动效（此前 14 秒全靠空白，用户以为没点上）
       - 6s 到点用 AbortController 真正中断请求（此前只 setTimeout，fetch 还挂着，
         连接一直占着，且用户看到的是「等完再一次性出字」）
       - 降级文案走 degradeNote/degradeMiss，命中本地预设就照样给答案，没命中给「再问一次」 */
    function ask(force) {
        if (!inputEl) return;
        var q = String(inputEl.value || '').trim();
        if (!q) return;
        if (busy && force !== true) { pushMsg('bot', '上一条我还在想，稍等一下就好。'); return; }
        inputEl.value = '';
        pushMsg('me', q);
        busy = true;
        pushThinking();

        var replied = false, answerNode = null, answerText = '', timer = null, ctl = null;
        function finish(text, opts) {
            if (replied) return;
            if (timer) { clearTimeout(timer); timer = null; }
            replied = true; busy = false; removeThinking(); pushMsg('bot', text, opts);
        }
        function fallback() {
            if (replied) return;
            if (timer) { clearTimeout(timer); timer = null; }
            var hit = presetAnswer(q), answer = hit || localAnswer(q);
            if (answerNode) {
                updateBotMsg(answerNode, answer);
                replied = true; busy = false; removeThinking();
            } else finish(answer, hit ? { sub: degradeNote(q) } : null);
        }
        function handleEvent(event) {
            var lines = event.split(/\r?\n/), payload = '';
            for (var i = 0; i < lines.length; i++) {
                if (lines[i].indexOf('data:') === 0) payload += (payload ? '\n' : '') + lines[i].slice(5).replace(/^ /, '');
            }
            if (!payload) return false;
            if (payload === '[DONE]') {
                if (!answerNode && !replied) fallback();
                else if (answerNode && !replied) { replied = true; busy = false; removeThinking(); }
                return true;
            }
            var item = null;
            try { item = JSON.parse(payload); } catch (e) { item = { token: payload }; }
            if (item.error_code) { fallback(); return true; }
            if (item.token) {
                if (timer) { clearTimeout(timer); timer = null; }
                if (!answerNode) { removeThinking(); answerNode = pushMsg('bot', ''); }
                answerText += item.token;
                updateBotMsg(answerNode, answerText);
            }
            return false;
        }
        try {
            var opt = {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: q, style: style, stream: true,
                    context: currentPageContext() })
            };
            if (window.AbortController) { ctl = new window.AbortController(); opt.signal = ctl.signal; }
            timer = setTimeout(function () {
                try { if (ctl) ctl.abort(); } catch (e) {}
                fallback();
            }, ASK_TIMEOUT);
            fetch('/api/chat', opt).then(function (r) {
                var type = (r.headers.get('content-type') || '').toLowerCase();
                if (type.indexOf('text/event-stream') >= 0 && r.body && r.body.getReader) {
                    var reader = r.body.getReader(), decoder = new window.TextDecoder('utf-8'), buffer = '', done = false;
                    function pump() {
                        return reader.read().then(function (part) {
                            if (part.done) {
                                buffer += decoder.decode();
                                if (buffer) done = handleEvent(buffer);
                                if (!done && !replied) fallback();
                                if (answerNode && !replied) { replied = true; busy = false; removeThinking(); }
                                return;
                            }
                            buffer += decoder.decode(part.value, { stream: true });
                            var split;
                            while ((split = buffer.search(/\r?\n\r?\n/)) >= 0) {
                                var separatorLength = buffer.substr(split, 2) === '\r\n' ? 4 : 2;
                                var event = buffer.slice(0, split);
                                buffer = buffer.slice(split + separatorLength);
                                done = handleEvent(event);
                                if (done) { try { reader.cancel(); } catch (e) {} break; }
                            }
                            if (!done && !replied) return pump();
                        });
                    }
                    return pump();
                }
                return r.json().then(function (j) {
                    if (timer) { clearTimeout(timer); timer = null; }
                    if (j && j.success && j.reply) finish(j.reply);
                    else fallback();
                });
            }).catch(function () {
                if (timer) { clearTimeout(timer); timer = null; }
                if (!replied) fallback();
            });
        } catch (e) {
            if (timer) { clearTimeout(timer); timer = null; }
            fallback();
        }
    }

    function setOpen(v) {
        opened = !!v;
        if (!panel) panel = makePanel();
        panel.style.display = opened ? 'flex' : 'none';
        // 336：面板收起时风格弹层一起收，避免留下悬空浮层
        if (!opened) { setMenuOpen(false); removeThinking(); }
        // 302：面板展开时 ↑/↓ 淡出并停止接收点击，避免与面板边缘互相干扰
        try { document.body.classList.toggle('wbchat-open', opened); } catch (e) {}
        if (opened) {
            if (!listEl || !listEl.children.length) restoreHistory();
            else refreshGreet();
            renderStyleBadge();
            if (inputEl) { try { inputEl.focus(); } catch (e) {} }
        }
    }

    function toggle() { setOpen(!opened); }

    /* ---------- 336：开场白——结合当前所选赛事，短句、引导式、不做功能清单自我介绍 ---------- */
    function greetText() {
        var c = currentCompName();
        if (style === 'casual') {
            return c ? ('我在～关于「' + c + '」的评分、档位、导出，想问啥直接说。')
                     : '我在～评分、档位、导出这些，想问啥直接说。';
        }
        if (style === 'academic') {
            return c ? ('我在。关于「' + c + '」的评分维度、档位差异与导出格式，可随时提问。')
                     : '我在。关于评分维度、档位差异与导出格式，可随时提问。';
        }
        return c ? ('我在，关于「' + c + '」的评分、档位、导出，随时问。')
                 : '我在，关于评分、档位、导出这些，随时问。';
    }

    function greetSub() {
        return '想换个口吻，点右上角「风格」就行。';
    }

    /* 开场白节点还在（用户没聊过）时，按最新赛事名刷新文案 */
    function refreshGreet() {
        if (!listEl) return;
        try {
            var n = listEl.querySelector('[data-wbgreet="1"]');
            if (!n) return;
            var box = n.firstChild;
            if (box && box.firstChild) box.firstChild.nodeValue = greetText();
            var sub = box ? box.querySelector('div') : null;
            if (sub) sub.textContent = greetSub();
        } catch (e) {}
    }

    function boot() {
        try {
            if (document.getElementById('wbChatBubble')) return;
            loadStyle();
            bubble = makeBubble();
            renderStyleBadge();
            window.addEventListener('resize', function () {
                if (!panel) return;
                var st = panel.style;
                if (isMobile()) {
                    st.left = '0'; st.right = '0'; st.bottom = '0'; st.width = '100%';
                    st.height = '70vh'; st.borderRadius = '14px 14px 0 0';
                } else {
                    st.left = ''; st.right = '16px'; st.bottom = '196px';
                    st.width = '360px'; st.height = '520px'; st.borderRadius = '14px';
                }
                if (menuIsOpen()) placeMenu(styleBtn || styleBadge);   // 336：转屏/改窗口后重新定位
            });
            // 336：点弹层外关闭（触发按钮已 stopPropagation，不会误关）；Esc 也关
            document.addEventListener('click', function (e) {
                if (!menuIsOpen()) return;
                if (styleMenu.contains(e.target)) return;
                if (styleBadge && styleBadge.contains(e.target)) return;
                if (styleBtn && styleBtn.contains(e.target)) return;
                setMenuOpen(false);
            });
            document.addEventListener('keydown', function (e) {
                if (menuIsOpen() && e && (e.key === 'Escape' || e.keyCode === 27)) setMenuOpen(false);
            });
            // 336：赛事输入框变化后，开场白跟着换赛事名（只在用户还没开聊时）
            var compEl = document.getElementById('competition');
            if (compEl) {
                var onComp = function () { if (opened) refreshGreet(); };
                compEl.addEventListener('change', onComp);
                compEl.addEventListener('blur', onComp);
            }
        } catch (e) {}
    }

    window.wbChat = {
        open: function () { setOpen(true); },
        close: function () { setOpen(false); },
        toggle: toggle,
        setStyle: saveStyle,
        getStyle: function () { return style; },
        renderMarkdown: renderMarkdown,
        NAME: AGENT_NAME
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
