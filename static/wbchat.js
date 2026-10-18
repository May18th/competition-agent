/* ============================================================
 * 294 轮：智能体聊天系统 UI（独立文件，不碰 app.js / app.py）
 * 297 轮补丁：智能体命名「小可」 + 三档聊天风格（简洁严谨 / 轻松幽默 / 学术详细）
 *
 * - 命名：全站一致——面板标题「小可 · 科创赛事助手智能助手」、欢迎语、气泡提示均含「小可」
 *   （避开小爱/小度/小冰/小艺等大厂语音助手同名，规避侵权）
 * - 风格：气泡右上角小图标切换；三档只影响回复口吻，与生成风格互不影响；
 *   选择持久化走服务端 /api/user_state 的 personalization（配合 292 双端同步），
 *   接口不可用时降级 sessionStorage，**不写 localStorage**（292 要求禁单端私有）
 * - 后端：POST /api/chat 支持 SSE；历史按 comp_uid 隔离持久化
 * - ES5 语法，全 try/catch，只暴露 window.wbChat
 *
 * 第三百三十六轮（移动端实测三处修复）：
 *   1. 开场白去「功能清单式自我介绍」，结合当前所选赛事，短句引导式
 *   2. 提问后立即出「正在思考」动效；20s 超时用 AbortController 真正中断请求并降级，
 *      降级文案友好且仍给可用答案（本地知识库），没命中时给「再问一次」按钮
 *   3. 风格切换：点标题栏或右上角都能弹三档菜单——原实现被 document 上的
 *      关闭监听在同一个 click 冒泡里立刻关掉（按钮没 stopPropagation），已修
 * ============================================================ */
(function () {
    if (window.wbChat) return;               // 防重复注入

    var AGENT_NAME = '小可';
    var AGENT_TITLE = '小可 · 科创赛事助手智能助手';
    var STORE_KEY = 'wbChatStyle';           // 仅作服务端不可用时的降级（sessionStorage）

    /* 聊天风格取值必须与后端 /api/chat 的 style 入参一致：
       concise=简洁严谨 / casual=轻松幽默 / academic=学术详细。
       ⚠️ 我第一版写成了 brief/fun，与后端对不上会导致切了风格后端不生效，已对齐。 */
    var STYLES = [
        { id: 'concise',  name: '简洁严谨', hint: '结论先行、步骤清单、风险单列' },
        { id: 'casual',   name: '轻松幽默', hint: '自然口语、类比启发、适度幽默' },
        { id: 'academic', name: '学术详细', hint: '规则依据、假设边界、证据链' }
    ];
    // 旧值兼容（第一版用过 brief/fun，已落在用户会话里的要能认出来）
    var STYLE_ALIAS = { 'brief': 'concise', 'fun': 'casual' };
    var style = 'concise';

    var opened = false, panel = null, bubble = null, listEl = null, inputEl = null;
    var styleMenu = null, styleBadge = null, styleBtn = null;
    var busy = false;
    var historyLoaded = false, historyLoading = false;
    // 交互边界状态：建议只在聊天面板内呈现，不遮挡首页主流程。
    var proactiveEnabled = true, chatPrefsLoaded = false;
    var suggestionKey = '', suggestionNode = null;

    /* 336：等待阈值。后端 /api/chat 命中预设约 3ms，落到 LLM 兜底时可能数秒，
       超过这个时间就中断并降级，绝不让用户干等。 */
    var ASK_TIMEOUT = 20000;
    var thinkNode = null, thinkTimer = null;

    /* ---------- 本地预设问答（接口不可用时兜底，绝不显示红字报错） ----------
       每条目三档口吻：b=简洁严谨（默认）/ f=轻松幽默 / a=学术详细 */
    var PRESET = [
        {
            k: ['谁创造了你', '谁开发了你', '谁创建了你', '你的开发者是谁', '你的开发方是谁', '谁给你取名', '谁给你起名', '谁给你取的名字', '谁给你起的名字', '谁给小创取名', '谁给小创起名', '谁给小可取名', '谁给小可起名', '名字是谁取的', '名字是谁起的', '命名人是谁', '你是谁'],
            b: '小可由可创无限团队打造，名字也由团队统一命名，主要帮助大家准备各类赛事材料、分析项目和练习答辩。',
            f: '我是可创无限团队打造的小可，名字也是团队一起定的。比赛材料、项目思路、答辩练习都能找我聊。',
            a: '小可由可创无限团队打造，名称由团队统一确定，面向各类赛事提供材料准备、项目分析与答辩练习支持。'
        },
        {
            k: ['评分标准是什么', '评分标准有哪些', '评分维度是什么', '评分维度有哪些', '评分权重是什么', '怎么评分', '如何评分'],
            b: '评分维度和权重要看具体赛事及赛道的官方细则，不能把某个赛事的分值套到其他比赛。请先选择赛事，或告诉我赛事名称；我会按对应规则回答。',
            f: '这个得看具体报哪个比赛、哪个赛道，不能拿一家的分数套另一家。告诉我赛事名，我再按对应规则说。',
            a: '评分维度与权重由具体赛事及赛道的官方评审细则确定。未提供赛事名称时，我无法核实适用口径，不会引用其他赛事的分值代替。请提供赛事全称及赛道，以便按对应规则作答。'
        },
        {
            k: ['简洁版和深度版有什么区别', '简洁版与深度版区别', '档位有什么区别', '怎么选生成档位'],
            b: '简洁版快速出申报书骨架，适合先看方向；深度版多轮打磨、章节更厚，附竞品/商业/风险等模块，耗时更长但材料更完整。赶时间先简洁，正式提交用深度。',
            f: '简单说：想先看个方向 → 简洁版，快；要拿去正式交 → 深度版，厚。深度版会把竞品、商业模式、风险这些都给你铺开，就是得多等一会儿。',
            a: '两档的差异在于生成流程与材料厚度：简洁版走快速链路，输出完整申报书骨架，用于验证项目方向；深度版执行多轮打磨，章节更厚，并附加竞品分析、商业模式、风险评估等扩展模块，生成耗时显著更长。若用于正式提交，建议深度版；若仅需快速验证方向或时间受限，可选简洁版。'
        },
        {
            k: ['支持哪些导出格式', '导出格式有哪些', '在哪里导出', '怎么导出文件', '导出有几个文件'],
            b: '「导出中心」会按本次生成结果提供可用格式和文件；实际清单以页面显示为准。',
            f: '去结果页的「导出中心」看这次能下哪些格式，具体文件清单以页面为准。',
            a: '导出中心依据本次生成结果提供可用的 Word、PDF、PPT 或打包文件。产物类型与质量检查提示以当前页面实际显示为准。'
        },
        {
            k: ['申报书有多少字', '正文篇幅是多少', '字数要求是多少', '字数是多少'],
            b: '正文篇幅会随赛事、项目资料和生成版本变化，请以当前档位卡和结果页显示的实际字数为准。',
            f: '字数不是固定的，项目资料和版本都会影响篇幅，看这次结果页上的统计最准。',
            a: '正文篇幅受赛事要求、项目资料和生成版本影响，应以当前档位卡及结果页的实际统计为准，不承诺固定字数。'
        },
        {
            k: ['平台支持哪些赛事', '支持哪些赛事', '有哪些赛事可选', '赛事列表在哪里'],
            b: '可选赛事以首页列表为准，系统会按所选赛事的规则组织内容；如果列表里没有目标赛事，可以提供官方章程，我会据此协助分析。',
            f: '首页赛事列表里能选的都可以按对应规则准备。没看到你的比赛的话，把章程发我，我帮你一起看。',
            a: '可选赛事以首页列表为准，系统按所选赛事的规则组织内容。若目标赛事未收录，可提供官方章程，再根据具体规则分析。'
        },
        {
            k: ['一键演示是什么', '怎么使用一键演示', '如何开启演示', '一键演示会扣额度吗'],
            b: '顶部「🎬 一键演示」用预置样例直接展示完整结果页：不调大模型、不消耗额度、不用等待生成。',
            f: '想看效果又不想等？点顶部「🎬 一键演示」，预置样例直接把完整结果页铺开——不烧额度、不用等～',
            a: '「🎬 一键演示」（270 轮）读取预置样例文件（static/demo_sample.json，取自真实生成记录）直接渲染完整结果页。该路径不调用大模型、不请求 /api/generate、不消耗生成额度，适用于评委演示与功能预览；演示会话为只读，不影响任何业务数据。'
        },
        {
            k: ['额度怎么计算', '当前额度是多少', '收费标准是什么'],
            b: '额度与计费以页面额度展示为准，我这里不掌握实时数字，避免给你错的。',
            f: '这个数字我可不敢瞎说😅 页面上的额度显示是多少就是多少，看那个最靠谱。',
            a: '额度与计费信息以页面实时展示为准。本站遵循「实测统计数字不写死」原则，聊天侧亦不返回未经接口校验的数值，以免与实际额度不一致造成误导。'
        }
    ];

    /* 命中本地预设才返回文本；没命中返回 null，让调用方决定是兜底还是提示重问 */
    function presetAnswer(q) {
        var s = String(q || '');
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
        if (/(没有灵感|没灵感|没有想法|没想法|不知道做什么|不知道做啥|帮我推荐|推荐一个项目|推荐几个方向|帮我想个项目|想不出项目)/.test(String(q || ''))) {
            if (style === 'casual') return '当然可以，先别急着开工。我先给你几个方向参考，也不会替你直接定题：校园/社区服务、绿色与公共治理、智能技术应用。告诉我你的专业、兴趣或手头资源，我陪你把方向收敛成具体题目。';
            if (style === 'academic') return '可以。在启动生成前，建议先完成方向筛选。你可以从校园/社区服务、绿色与公共治理、智能技术应用中选择候选方向，再补充团队专业、可用资源及目标人群，我会据此进一步收敛项目题目。';
            return '可以。我先不把推荐内容当成你的项目，也不会直接启动生成。你可以先从校园/社区服务、绿色与公共治理、智能技术应用里挑一个方向，再告诉我你的专业、兴趣或手头资源，我会帮你收敛成具体题目。';
        }
        var tail = '可以问我：评分维度、档位差异、导出格式、字数口径、赛事选择、演示模式。';
        if (style === 'casual') return '我是' + AGENT_NAME + '～ 这个我还没学会，换个问法试试？' + tail;
        if (style === 'academic') return '我是' + AGENT_NAME + '。当前问题未命中本地知识条目，且后端问答服务暂不可用。' + tail;
        return '我是' + AGENT_NAME + '，擅长回答赛事相关的问题。' + tail;
    }

    /* 336：超时降级文案——友好、说明发生了什么、并给出可用内容。
       hit=true 时这句话作为「小字附注」挂在答案下面，不喧宾夺主。 */
    function degradeNote(q) {
        if (style === 'casual') return '这会儿有点卡，上面是我先知道的，不让你白等～';
        if (style === 'academic') return '在线问答本轮响应偏慢（已超 20 秒并中断），以上依据本地知识库先行作答。';
        return '这会儿有点慢，先按本地知识库答你，没让你干等。';
    }

    /* 没命中本地预设、又超时——这条就没内容可给了，说清楚并给「再问一次」 */
    function degradeMiss(q) {
        if (style === 'casual') return '这会儿有点卡，这条我没能马上想出来。稍等一下再问一次，或者换个问法我很快就能答。';
        if (style === 'academic') return '在线问答本轮响应偏慢（已超 20 秒并中断），且该问题未命中本地知识条目，暂无法作答。可稍后重试，或改问评分维度、档位差异、导出格式、字数口径、赛事选择、演示模式。';
        return '这会儿有点慢，这条我还没想好。稍等一下再问一次会更准；问评分、档位、导出、字数这些我马上能答。';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    var DEFENSE_SCORE_LABELS = ['回应问题', '证据支撑', '逻辑表达', '风险意识'];

    function parseDefenseScorecard(text) {
        var source = String(text == null ? '' : text);
        if (!/答辩评分卡/.test(source)) return null;
        var lines = source.split(/\r?\n/), scores = [], found = {};
        var headerLine = -1;
        for (var h = 0; h < lines.length; h++) {
            if (lines[h].indexOf('答辩评分卡') >= 0) { headerLine = h; break; }
        }
        if (headerLine < 0) return null;
        for (var i = 0; i < lines.length; i++) {
            if (i < headerLine) continue;
            var line = lines[i].replace(/[>*_`#]/g, '');
            for (var j = 0; j < DEFENSE_SCORE_LABELS.length; j++) {
                var label = DEFENSE_SCORE_LABELS[j];
                if (found[label]) continue;
                var at = line.indexOf(label);
                if (at < 0) continue;
                var tail = line.slice(at + label.length, at + label.length + 100);
                var squares = /[■□]{5}/.exec(tail);
                var numeric = /(?:^|[：:\s])([1-5])\s*(?:\/\s*5|分(?:数|值)?(?=$|[\s，,。；;：:、])|(?=[、，,：:;；—–-]|$))/.exec(tail);
                var value = squares ? (squares[0].match(/■/g) || []).length : (numeric ? Number(numeric[1]) : 0);
                if (value >= 1 && value <= 5) found[label] = value;
            }
        }
        for (var k = 0; k < DEFENSE_SCORE_LABELS.length; k++) {
            if (!found[DEFENSE_SCORE_LABELS[k]]) return null;
            scores.push(found[DEFENSE_SCORE_LABELS[k]]);
        }
        return scores;
    }

    function renderDefenseScorecard(scores) {
        if (!scores || scores.length !== 4) return '';
        for (var i = 0; i < scores.length; i++) {
            if (scores[i] < 1 || scores[i] > 5 || Math.floor(scores[i]) !== scores[i]) return '';
        }
        var cx = 120, cy = 100, radius = 65, points = [];
        for (var p = 0; p < scores.length; p++) {
            var angle = (-Math.PI / 2) + p * (Math.PI / 2);
            var scale = scores[p] / 5;
            points.push((cx + Math.cos(angle) * radius * scale).toFixed(1) + ',' + (cy + Math.sin(angle) * radius * scale).toFixed(1));
        }
        var axes = '';
        for (var a = 1; a <= 5; a++) {
            var ring = [];
            for (var r = 0; r < 4; r++) {
                var theta = (-Math.PI / 2) + r * (Math.PI / 2);
                ring.push((cx + Math.cos(theta) * radius * a / 5).toFixed(1) + ',' + (cy + Math.sin(theta) * radius * a / 5).toFixed(1));
            }
            axes += '<polygon points="' + ring.join(' ') + '" fill="none" stroke="currentColor" stroke-opacity=".17" stroke-width="1"/>';
        }
        var axisEnds = [[cx, cy - radius], [cx + radius, cy], [cx, cy + radius], [cx - radius, cy]];
        for (var e = 0; e < axisEnds.length; e++) axes += '<line x1="' + cx + '" y1="' + cy + '" x2="' + axisEnds[e][0] + '" y2="' + axisEnds[e][1] + '" stroke="currentColor" stroke-opacity=".24"/>';
        var labelPositions = [[120, 18], [202, 104], [120, 191], [38, 104]];
        var labels = '';
        for (var l = 0; l < DEFENSE_SCORE_LABELS.length; l++) {
            labels += '<text x="' + labelPositions[l][0] + '" y="' + labelPositions[l][1] + '" text-anchor="middle" font-size="10" fill="currentColor">' + DEFENSE_SCORE_LABELS[l] + '</text>';
        }
        var rows = '';
        for (var s = 0; s < scores.length; s++) {
            rows += '<div style="display:grid;grid-template-columns:5.5em 1fr 2.5em;gap:8px;align-items:center;margin:5px 0;font-size:12px">'
                + '<span>' + DEFENSE_SCORE_LABELS[s] + '</span>'
                + '<span aria-hidden="true" style="display:block;height:6px;border-radius:4px;background:var(--line,rgba(148,163,184,.3));overflow:hidden">'
                + '<span style="display:block;width:' + (scores[s] * 20) + '%;height:100%;background:var(--c-a,#0e7490)"></span></span>'
                + '<strong>' + scores[s] + '/5</strong></div>';
        }
        var description = DEFENSE_SCORE_LABELS.map(function (label, index) { return label + ' ' + scores[index] + ' 分'; }).join('，');
        return '<section class="wbchat-scorecard" aria-label="答辩评分可视化" style="margin-top:10px;padding:10px;border:1px solid var(--line,rgba(148,163,184,.35));border-radius:8px;max-width:100%;">'
            + '<h4 style="margin:0 0 4px;font-size:13px">答辩评分</h4>'
            + '<svg viewBox="0 0 240 205" role="img" aria-label="' + description + '" style="display:block;width:min(100%,280px);height:auto;margin:0 auto;color:var(--text-dim,#526078)">'
            + axes + '<polygon points="' + points.join(' ') + '" fill="var(--c-a,#0e7490)" fill-opacity=".22" stroke="var(--c-a,#0e7490)" stroke-width="2"/>'
            + labels + '</svg>'
            + '<div role="group" aria-label="四个答辩评分维度">' + rows + '</div>'
            + '<p style="margin:7px 0 0;font-size:11px;line-height:1.5;color:var(--text-dim)">仅评价本轮回答，不等同赛事官方评分。</p></section>';
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
        html += renderDefenseScorecard(parseDefenseScorecard(text));
        return html;
    }

    function isMobile() { return window.innerWidth <= 768; }

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

    function chatPreference(field, value) {
        try {
            fetch('/api/chat_profile', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ fields: (function () { var o = {}; o[field] = value; return o; })() })
            }).catch(function () {});
        } catch (e) {}
    }

    function loadChatPreferences(done) {
        if (chatPrefsLoaded) { if (done) done(); return; }
        try {
            var local = sessionStorage.getItem('wbChatProactive');
            if (local === '0') proactiveEnabled = false;
        } catch (e) {}
        try {
            fetch('/api/chat_profile', { method: 'GET', credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (j) {
                    var p = (j && j.profile) || {};
                    var v = p.proactive_suggestions_enabled;
                    if (v === undefined) v = p.suggestions_enabled;
                    if (v !== undefined) proactiveEnabled = !(v === false || String(v) === '0');
                    chatPrefsLoaded = true;
                    if (done) done();
                }).catch(function () { chatPrefsLoaded = true; if (done) done(); });
        } catch (e) { chatPrefsLoaded = true; if (done) done(); }
    }

    function setProactiveEnabled(enabled) {
        proactiveEnabled = !!enabled;
        try { sessionStorage.setItem('wbChatProactive', proactiveEnabled ? '1' : '0'); } catch (e) {}
        try {
            fetch('/api/suggestion_settings', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
                body: JSON.stringify({ enabled: proactiveEnabled })
            }).catch(function () { chatPreference('proactive_suggestions_enabled', proactiveEnabled ? '1' : '0'); });
        } catch (e) { chatPreference('proactive_suggestions_enabled', proactiveEnabled ? '1' : '0'); }
        if (!proactiveEnabled && suggestionNode && suggestionNode.parentNode) {
            suggestionNode.parentNode.removeChild(suggestionNode);
            suggestionNode = null;
        }
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

    /* ---------- 侧边助手入口 + 风格标记 ---------- */
    function makeBubble() {
        var wrap = document.createElement('div');
        wrap.id = 'wbChatBubble';
        wrap.setAttribute('role', 'button');
        wrap.setAttribute('tabindex', '0');
        wrap.setAttribute('aria-label', '打开' + AGENT_NAME + '问答');
        wrap.title = AGENT_NAME + ' · 科创赛事助手智能助手（只答不写，不消耗额度）';
        wrap.innerHTML =
            '<span aria-hidden="true" style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;flex:none;opacity:.9;">'
          + '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" '
          + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
          + '<path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2z"/>'
          + '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z"/></svg></span>'
          + '<span aria-hidden="true" style="font-size:14px;font-weight:700;line-height:1;letter-spacing:0;white-space:nowrap;">小可</span>'
            // 297：右上角风格切换小图标
          + '<span id="wbChatStyleBadge" title="切换聊天风格" style="position:absolute; top:-4px; right:-4px;'
          + ' width:18px; height:18px; border-radius:6px; display:flex; align-items:center; justify-content:center;'
          + ' font-size:11px; font-weight:700; cursor:pointer; border:1px solid var(--line,rgba(148,163,184,.5));'
          + ' background:var(--c-a-soft,rgba(14,116,144,.12)); color:var(--c-a,#0e7490);">文</span>';

        var st = wrap.style;
        st.position = 'fixed';
        st.right = '16px';
        st.bottom = '196px';                 // 302 队形：fab16 / ↑76 / ↓136 / 聊196，间距 12px
        st.width = '88px';
        st.height = '42px';
        st.padding = '0 12px';
        st.boxSizing = 'border-box';
        st.borderRadius = '12px';
        st.display = 'flex';
        st.alignItems = 'center';
        st.justifyContent = 'flex-start';
        st.gap = '8px';
        st.cursor = 'pointer';
        st.zIndex = '2600';
        st.border = '1px solid var(--line, rgba(148,163,184,.45))';
        st.background = 'var(--surface-solid, #fff)';
        st.color = 'var(--c-a, #0e7490)';
        st.boxShadow = '0 6px 18px rgba(15,23,42,.14)';
        st.transition = 'transform .15s ease, box-shadow .18s ease';

        wrap.addEventListener('mouseenter', function () {
            st.transform = 'translateY(-2px)';
            st.boxShadow = '0 9px 22px rgba(15,23,42,.2)';
        });
        wrap.addEventListener('mouseleave', function () {
            st.transform = ''; st.boxShadow = '0 6px 18px rgba(15,23,42,.14)';
        });
        wrap.addEventListener('click', function (e) {
            if (e && e.target && e.target.id === 'wbChatStyleBadge') return;   // 点小图标不开关面板
            toggle();
        });
        wrap.addEventListener('keydown', function (e) {
            if (!e || (e.key !== 'Enter' && e.key !== ' ' && e.keyCode !== 13 && e.keyCode !== 32)) return;
            e.preventDefault();
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

    /* 336：pushMsg 增加 opts —— {sub: 次要小字, action: {label, onClick}}
       只用内联样式，不动任何 css 文件。 */
    function pushMsg(who, text, opts) {
        if (!listEl) return;
        opts = opts || {};
        var d = document.createElement('div');
        d.style.marginBottom = '10px';
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

    function controlButton(label, onClick, primary) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        b.style.cssText = 'min-height:40px;padding:7px 12px;border-radius:9px;cursor:pointer;font-size:12.5px;'
            + 'border:1px solid ' + (primary ? 'var(--c-a)' : 'var(--line)') + ';'
            + 'background:' + (primary ? 'var(--c-a)' : 'var(--surface-solid)') + ';'
            + 'color:' + (primary ? '#fff' : 'var(--text)') + ';';
        b.addEventListener('click', function () { try { onClick(); } catch (e) {} });
        return b;
    }

    function sendQuick(text) {
        if (!inputEl || !text) return;
        inputEl.value = text;
        ask(true);
    }

    function appendCard(title, subtitle) {
        if (!listEl) return null;
        var card = document.createElement('section');
        card.setAttribute('role', 'region');
        card.style.cssText = 'margin:2px 0 12px;padding:11px 12px;border:1px solid var(--line);'
            + 'border-radius:11px;background:var(--surface-2);color:var(--text);';
        var h = document.createElement('div');
        h.style.cssText = 'font-weight:700;font-size:13px;line-height:1.5;';
        h.textContent = title;
        card.appendChild(h);
        if (subtitle) {
            var sub = document.createElement('div');
            sub.style.cssText = 'margin-top:4px;color:var(--text-dim);font-size:12px;line-height:1.55;';
            sub.textContent = subtitle;
            card.appendChild(sub);
        }
        listEl.appendChild(card);
        return card;
    }

    function showGenerationConfirmation(item) {
        var comp = item.competition || '待确认';
        var track = item.track || '未指定';
        var idea = item.idea || '待补充';
        var mode = item.mode === 'deep' ? '深度版' : '简洁版';
        var card = appendCard('开始生成前，请确认这组信息', '小可不会把建议或未确认内容直接写入项目。');
        if (!card) return;
        var dl = document.createElement('dl');
        dl.style.cssText = 'margin:9px 0;display:grid;grid-template-columns:4.5em 1fr;gap:5px 8px;font-size:12px;line-height:1.55;';
        [['赛事', comp], ['赛道', track], ['主题', idea], ['档位', mode]].forEach(function (row) {
            var dt = document.createElement('dt'); dt.style.color = 'var(--text-mute)'; dt.textContent = row[0];
            var dd = document.createElement('dd'); dd.style.margin = '0'; dd.textContent = row[1];
            dl.appendChild(dt); dl.appendChild(dd);
        });
        card.appendChild(dl);
        var actions = document.createElement('div'); actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
        actions.appendChild(controlButton('确认生成', function () { sendQuick('确认生成'); }, true));
        actions.appendChild(controlButton('修改信息', function () { sendQuick('我想修改赛事、赛道或项目主题'); }, false));
        card.appendChild(actions);
        try { listEl.scrollTop = listEl.scrollHeight; } catch (e) {}
    }

    function showRecommendationCandidates(item) {
        var candidates = Array.isArray(item.candidates) ? item.candidates : [];
        if (!candidates.length) return;
        var card = appendCard('这些是候选方向', '候选不等于你的项目事实，先选一个，再确认是否采用。');
        if (!card) return;
        var list = document.createElement('div');
        candidates.slice(0, 6).forEach(function (candidate, index) {
            var value = typeof candidate === 'string' ? candidate : (candidate.title || candidate.name || candidate.label || '候选方向');
            var desc = typeof candidate === 'string' ? '' : (candidate.description || candidate.desc || '');
            var row = document.createElement('div');
            row.style.cssText = 'padding:8px 0;border-top:1px solid var(--line);font-size:12.5px;line-height:1.55;';
            var text = document.createElement('div'); text.textContent = (index + 1) + '. ' + value;
            row.appendChild(text);
            if (desc) { var d = document.createElement('div'); d.style.color = 'var(--text-dim)'; d.textContent = desc; row.appendChild(d); }
            row.appendChild(controlButton('选择这个方向', function () { sendQuick('选择候选 ' + (index + 1)); }, false));
            list.appendChild(row);
        });
        card.appendChild(list);
        try { listEl.scrollTop = listEl.scrollHeight; } catch (e) {}
    }

    function showSuggestion(text) {
        if (!proactiveEnabled || !text || !listEl) return;
        var key = String(text).replace(/\s+/g, ' ').trim();
        if (!key || key === suggestionKey) return;
        try { if (sessionStorage.getItem('wbChatSuggestion:' + key) === '1') return; } catch (e) {}
        suggestionKey = key;
        var card = appendCard('小可建议', text);
        if (!card) return;
        card.style.borderStyle = 'dashed';
        var actions = document.createElement('div'); actions.style.cssText = 'display:flex;gap:8px;margin-top:9px;flex-wrap:wrap;';
        actions.appendChild(controlButton('去处理', function () { sendQuick(text.replace(/^💡\s*/, '')); }, true));
        actions.appendChild(controlButton('收起', function () {
            try { sessionStorage.setItem('wbChatSuggestion:' + key, '1'); } catch (e) {}
            if (card.parentNode) card.parentNode.removeChild(card);
            suggestionNode = null;
        }, false));
        actions.appendChild(controlButton('关闭主动建议', function () { setProactiveEnabled(false); }, false));
        card.appendChild(actions);
        suggestionNode = card;
    }

    function loadSuggestion() {
        loadChatPreferences(function () {
            if (!proactiveEnabled) return;
            try {
                fetch('/api/chat_suggest', { method: 'GET', credentials: 'same-origin' })
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (j) { if (j && j.success) showSuggestion(j.suggestion); })
                    .catch(function () {});
            } catch (e) {}
        });
    }

    function showProofreadControls(node, meta) {
        var issues = meta && Array.isArray(meta.issues) ? meta.issues : [];
        var hid = meta && meta.history_id;
        if (!node || !issues.length || !hid) return;
        var card = document.createElement('section');
        card.style.cssText = 'margin-top:9px;padding-top:8px;border-top:1px solid var(--line);font-size:12px;';
        var title = document.createElement('div'); title.style.fontWeight = '700'; title.textContent = '校对建议（修改前可预览）'; card.appendChild(title);
        var rows = [];
        issues.forEach(function (issue, index) {
            if (!issue || !issue.original || !issue.suggestion) return;
            var row = document.createElement('div'); row.style.cssText = 'margin-top:8px;padding:8px;border:1px solid var(--line);border-radius:8px;';
            var copy = document.createElement('div'); copy.style.lineHeight = '1.55';
            copy.textContent = (index + 1) + '. ' + (issue.type || '文本问题') + '：' + issue.original + ' → ' + issue.suggestion;
            row.appendChild(copy);
            var actions = document.createElement('div'); actions.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;';
            var preview = controlButton('预览', function () {
                if (row.querySelector('.wbchat-proofread-preview')) return;
                var p = document.createElement('div'); p.className = 'wbchat-proofread-preview';
                p.style.cssText = 'margin:6px 0;padding:7px;background:var(--surface-solid);border-radius:7px;line-height:1.55;';
                p.textContent = '将把「' + issue.original + '」替换为「' + issue.suggestion + '」。'; row.insertBefore(p, actions);
                actions.appendChild(controlButton('确认采纳', function () {
                    fetch('/api/chat_apply_proofread', { method: 'POST', headers: {'Content-Type':'application/json'}, credentials:'same-origin',
                        body: JSON.stringify({history_id: hid, original: issue.original, suggestion: issue.suggestion}) })
                        .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
                            if (!j || !j.success) return;
                            preview.disabled = true; preview.textContent = '已采纳';
                            var undo = controlButton('撤销', function () {
                                fetch('/api/proposal_revision/' + encodeURIComponent(hid), { method: 'POST', headers: {'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify({action:'undo'}) })
                                    .then(function (r) { return r.ok ? r.json() : null; }).then(function (u) { if (u && u.success) undo.disabled = true; }).catch(function () {});
                            }, false);
                            actions.appendChild(undo);
                        }).catch(function () {});
                }, true));
            }, false);
            actions.appendChild(preview);
            row.appendChild(actions); card.appendChild(row); rows.push(row);
        });
        if (rows.length) { var content = node.querySelector('.wbchat-bot-content'); if (content) content.appendChild(card); }
    }

    function restoreHistory() {
        if (historyLoaded || historyLoading || !listEl) return;
        historyLoading = true;
        if (inputEl) inputEl.disabled = true;
        fetch('/api/chat_history', { method: 'GET', credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) {
                if (j && j.success && j.messages && j.messages.length) {
                    for (var i = 0; i < j.messages.length; i++) {
                        var m = j.messages[i];
                        pushMsg(m.role === 'user' ? 'me' : 'bot', m.content || '');
                    }
                } else pushMsg('bot', greetText());
                historyLoaded = true;
                historyLoading = false;
                if (inputEl) inputEl.disabled = false;
            })
            .catch(function () {
                pushMsg('bot', greetText());
                historyLoaded = true;
                historyLoading = false;
                if (inputEl) inputEl.disabled = false;
            });
    }

    function greetText() {
        return '你好，我是小可。你正在准备哪项比赛？项目梳理、申报材料、路演答辩，都可以从你最关心的地方聊起。';
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
              historyLoaded = true;
              pushMsg('bot', greetText());
          }).catch(function () {})
          .then(function () { button.disabled = false; });
    }

    /* 336：
       - 提问后立刻渲染「小可正在思考…」动效（此前 14 秒全靠空白，用户以为没点上）
       - 20s 到点用 AbortController 真正中断请求（此前只 setTimeout，fetch 还挂着，
         连接一直占着，且用户看到的是「等完再一次性出字」）
       - 降级文案走 degradeNote/degradeMiss，命中本地预设就照样给答案，没命中给「再问一次」 */
    function pageContext() {
        var competition = '', competitionSelected = false, idea = '', mode = '', track = '', trackOptions = [];
        try { competition = String((document.getElementById('competition') || {}).value || '').trim(); } catch (e) {}
        try {
            competitionSelected = window.wbChatCompetitionSelected
                ? !!window.wbChatCompetitionSelected()
                : (sessionStorage.getItem('wbCompetitionChosen') === '1' ||
                   localStorage.getItem('wbCompetitionChosen') === '1');
        } catch (e) {}
        try { idea = String((document.getElementById('idea') || {}).value || '').trim(); } catch (e) {}
        try {
            var selectedMode = document.querySelector('input[name="mode"]:checked');
            mode = (selectedMode && selectedMode.value) || window._lastGenMode || '';
        } catch (e) {}
        try {
            var selectedTrack = window.wbChatTrackContext && window.wbChatTrackContext();
            if (selectedTrack) {
                track = selectedTrack.track || '';
                trackOptions = selectedTrack.options || [];
            }
        } catch (e) {}
        return {
            competition: competition.slice(0, 120), idea: idea.slice(0, 1200),
            competition_selected: competitionSelected,
            mode: mode, track: track, track_options: trackOptions
        };
    }

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
        var controlShown = false, proofreadMeta = null;
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
                if (!answerNode && !replied && !controlShown) fallback();
                else if (answerNode && !replied) { replied = true; busy = false; removeThinking(); }
                else if (controlShown && !replied) { replied = true; busy = false; removeThinking(); }
                return true;
            }
            var item = null;
            try { item = JSON.parse(payload); } catch (e) { item = { token: payload }; }
            if (item.error_code) { fallback(); return true; }
            if (item.event === 'generation_confirmation' || item.event === 'generation_confirm') {
                removeThinking(); showGenerationConfirmation(item); controlShown = true;
            }
            if (item.event === 'recommendation_candidates') {
                removeThinking(); showRecommendationCandidates(item); controlShown = true;
            }
            if (item.event === 'proofread') proofreadMeta = item;
            if (item.event === 'generation') {
                var started = false;
                try {
                    started = !!(window.wbChatStartGeneration && window.wbChatStartGeneration(item));
                } catch (e) {}
                if (!started) {
                    finish('资料已整理，但首页生成流程没有启动。请确认赛事、项目创意和赛道后，点击首页「开始生成」。');
                    return true;
                }
            }
            if (item.token) {
                if (timer) { clearTimeout(timer); timer = null; }
                if (!answerNode) { removeThinking(); answerNode = pushMsg('bot', ''); }
                answerText += item.token;
                updateBotMsg(answerNode, answerText);
                if (proofreadMeta) { showProofreadControls(answerNode, proofreadMeta); proofreadMeta = null; }
            }
            return false;
        }
        try {
            var opt = {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: q, style: style, stream: true, context: pageContext() })
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
            loadSuggestion();
            renderStyleBadge();
            if (inputEl) { try { inputEl.focus(); } catch (e) {} }
        }
    }

    function toggle() { setOpen(!opened); }

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
        } catch (e) {}
    }

    window.wbChat = {
        open: function () { setOpen(true); },
        close: function () { setOpen(false); },
        toggle: toggle,
        setStyle: saveStyle,
        getStyle: function () { return style; },
        renderMarkdown: renderMarkdown,
        parseDefenseScorecard: parseDefenseScorecard,
        renderDefenseScorecard: renderDefenseScorecard,
        NAME: AGENT_NAME
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
