/* =============================================================================
   wbresult339.js —— 结果页信息架构重做（339 轮）/ 健康度四灯（374 轮）
   ---------------------------------------------------------------------------
   外挂式：只读现有 DOM 与全局函数，不改写 app.js 的任何逻辑，
   自身产物全部挂在 #wb339-* 命名空间容器内，destroy() 可完整回滚。

   用法（两行接线，见文件末尾 WB339_CONTRACT 注释）：
     wbResult339.init({ data: window._lastData });
     // 结果重渲染后： wbResult339.refresh(window._lastData);

   数据纪律（333 轮）：任何检测项拿不到真实数据就显示「未检测」中性态，
   绝不默认显示「通过」。阈值只在调用方显式传入时才参与判定。

   文案纪律（337 轮）：沿用全站口径，不出现那条已清理的缩写字样。
   评分纪律（351 轮）：评分一律带满分标注（78 / 100 分）。
   配色纪律：颜色只在 CSS 里，JS 不写任何色值。
   ============================================================================= */
(function (global) {
    'use strict';

    /* ---------------- 新 tab 划分方案（339 轮交付物 ②） ----------------
       旧划分：导出中心 / 前期分析 / 深度分析 / 申报与评审 / 图表 / 答辩 / 范文库
       问题：前四个内容重叠（规则解析、查重、诊断、评委意见散落三处），
             图表 tab 只放 3 张图撑不起一屏，答辩 tab 深度版才有内容。
       新划分：按「用户这一屏要回答什么问题」重新切，五组互不重叠。 */
    var TAB_PLAN = [
        {
            key: 'conclusion',
            name: '结论与导出',
            value: '十秒看懂这次结果好不好、能不能交，顺手把文件拿走',
            hold: ['关键结论聚合区', '健康度四灯', '待改 3 处', '导出条 / 一键打包'],
            sections: []
        },
        {
            key: 'proposal',
            name: '申报书正文',
            value: '要交给评委的那份东西，从项目简介到 PPT 大纲一处不落',
            hold: ['项目简介', '写作构思纲要', '申报书全文', 'PPT 大纲'],
            sections: ['projectSummary', 'proposalOutline', 'proposalText', 'pptOutline']
        },
        {
            key: 'review',
            name: '评审与改进',
            value: '评委怎么看、你今晚该改哪几处',
            hold: ['申报书诊断', '评委意见', '多视角评审', '评分依据', '创意五维雷达', '答辩问题预测'],
            sections: ['proposalAnalysis', 'judgeFeedback', 'expertReviewContent',
                       'judgeScoresList', 'ideaRadar', 'defenseQuestions']
        },
        {
            key: 'evidence',
            name: '佐证与分析',
            value: '支撑正文的依据、竞品与风险，交之前按这里核数字',
            hold: ['规则解析', '同质化检测', '竞品分析', '商业模式', '风险分析',
                   '技术方案', '实施计划', '社会价值', '可视化图表'],
            sections: ['parsedRules', 'similarityReport', 'competitorAnalysis',
                       'businessModel', 'riskAnalysis', 'techSolution',
                       'implementationPlan', 'socialValue', 'richCharts']
        },
        {
            key: 'library',
            name: '范文库与日志',
            value: '低频工具：喂范文提升后续生成、排障看日志',
            hold: ['范文库', '运行日志'],
            sections: ['tab-kb', 'tab-logs']
        }
    ];

    /* 目录项：优先用 wbconst.js 里的 WB_ANCHORS（它带 id + 所属旧 tab），
       取不到时退回本表的静态映射，保证模块单独跑也能出目录。 */
    var FALLBACK_ANCHORS = [
        { n: '规则解析', t: 'analysis', id: 'parsedRules' },
        { n: '同质化检测', t: 'analysis', id: 'similarityReport' },
        { n: '项目简介', t: 'proposal', id: 'projectSummary' },
        { n: '写作构思纲要', t: 'proposal', id: 'proposalOutline' },
        { n: '申报书全文', t: 'proposal', id: 'proposalText' },
        { n: '申报书诊断', t: 'proposal', id: 'proposalAnalysis' },
        { n: '评委意见', t: 'proposal', id: 'judgeFeedback' },
        { n: '多视角评审', t: 'proposal', id: 'expertReviewContent' },
        { n: '评分依据', t: 'proposal', id: 'judgeScoresList' },
        { n: '创意五维', t: 'proposal', id: 'ideaRadar' },
        { n: '竞品分析', t: 'deep', id: 'competitorAnalysis' },
        { n: '商业模式', t: 'deep', id: 'businessModel' },
        { n: '风险分析', t: 'deep', id: 'riskAnalysis' },
        { n: '技术方案', t: 'deep', id: 'techSolution' },
        { n: '实施计划', t: 'deep', id: 'implementationPlan' },
        { n: '社会价值', t: 'deep', id: 'socialValue' },
        { n: '可视化图表', t: 'charts', id: 'richCharts' },
        { n: '答辩问题', t: 'defense', id: 'defenseQuestions' },
        { n: 'PPT 大纲', t: 'defense', id: 'pptOutline' },
        { n: '范文库', t: 'kb', id: 'tab-kb' }
    ];

    var NS = 'wb339';
    var SEQ = 0;

    /* ============================ 小工具 ============================ */

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // 极简 Markdown：只在页面没有 wbRenderMD 时兜底（标题 / 列表 / 段落）
    function mdLite(s) {
        var out = '';
        String(s || '').split(/\r?\n/).forEach(function (ln) {
            var t = esc(ln.replace(/^#{1,6}\s*/, '').replace(/^\s*[-*]\s*/, ''));
            if (!t.trim()) return;
            if (/^#{1,6}\s/.test(ln)) { out += '<h4>' + t + '</h4>'; return; }
            if (/^\s*[-*]\s/.test(ln)) { out += '<li>' + t + '</li>'; return; }
            if (/^\s*\d+[.、)]\s/.test(ln)) { out += '<li>' + t + '</li>'; return; }
            out += '<p>' + t + '</p>';
        });
        return out;
    }

    function md(s) {
        try {
            if (global.wbRenderMD && typeof global.wbRenderMD === 'function') {
                return global.wbRenderMD(s || '');
            }
        } catch (e) {}
        return mdLite(s);
    }

    function el(tag, cls, html) {
        var d = document.createElement(tag);
        if (cls) d.className = cls;
        if (html != null) d.innerHTML = html;
        return d;
    }

    function byId(id) {
        try { return document.getElementById(id); } catch (e) { return null; }
    }

    // 元素是否真的在页面上可见（父级 display:none 时 offsetParent 为 null）
    function shown(node) {
        if (!node) return false;
        if (node.offsetParent) return true;
        // 卡片内的 sticky/fixed 元素 offsetParent 可能为 null，再兜一层尺寸判断
        try {
            var r = node.getBoundingClientRect();
            return !!(r && (r.width > 0 || r.height > 0));
        } catch (e) { return false; }
    }

    function num(v) {
        var n = typeof v === 'number' ? v : parseFloat(v);
        return (isFinite(n)) ? n : null;
    }

    // 状态归一：只认 pass / warn / fail / unknown 四种，其它一律 unknown
    function normState(s) {
        s = String(s || '').toLowerCase();
        if (s === 'pass' || s === 'ok' || s === 'good') return 'pass';
        if (s === 'warn' || s === 'warning' || s === 'diff' || s === 'todo') return 'warn';
        if (s === 'fail' || s === 'error' || s === 'bad' || s === 'block') return 'fail';
        return 'unknown';
    }

    var STATE_TXT = { pass: '通过', warn: '待优化', fail: '不通过', unknown: '未检测' };

    /* ============================ 模块状态 ============================ */

    var S = {
        inited: false,
        opts: {},
        data: {},
        root: null,        // .wb339 容器
        shell: null,       // .wb339-shell
        hero: null,
        health: null,
        toc: null,
        outline: null,
        moved: null,       // rail 布局时被搬走的节点，destroy 时还原
        moveParent: null,
        moveBefore: null,
        lampIdx: {},
        tocIdx: {},
        activeId: '',
        rafId: 0,
        timers: []
    };

    /* ============================ ① 关键结论 ============================ */

    function pickIssues(d) {
        // 只从真实数据里挑，挑不出来就返回空数组（由调用方显示定性文案）
        var out = [];
        var given = d.topIssues || d.top_issues;
        if (given && given.length) {
            given.slice(0, 3).forEach(function (it) {
                if (!it) return;
                out.push({
                    text: typeof it === 'string' ? it : (it.text || it.title || ''),
                    id: (typeof it === 'object' && it.id) || '',
                    tab: (typeof it === 'object' && it.tab) || ''
                });
            });
            return out.filter(function (x) { return !!x.text; });
        }

        var comp = d.completeness || {};
        var miss = comp.missing || [];
        if (miss.length) {
            out.push({
                text: '正文缺少 ' + miss.length + ' 个章节（' + miss.slice(0, 3).join('、') +
                      (miss.length > 3 ? ' 等' : '') + '），补上再导出',
                id: 'completenessBox', tab: 'proposal'
            });
        }
        var ph = num(comp.placeholders != null ? comp.placeholders : global.wbCountPlaceholders && global.wbCountPlaceholders());
        if (ph !== null && ph > 0) {
            out.push({
                text: '正文还有 ' + ph + ' 处【待你填写】占位，必须换成自己跑出来的真实数据',
                id: 'wbPhBar', tab: 'proposal'
            });
        }
        var pct = num(d.similarity && d.similarity.percent);
        if (pct !== null && typeof S.opts.dupPassLine === 'number' && pct > S.opts.dupPassLine) {
            out.push({
                text: '本地初检相似 ' + (Math.round(pct * 10) / 10) + '%，高于合格线 ' +
                      S.opts.dupPassLine + '%，先用自己的话重写标红段落',
                id: 'similarityReport', tab: 'analysis'
            });
        }
        var cons = d.consistency || {};
        if (num(cons.diffs != null ? cons.diffs : cons.count) > 0) {
            var n = num(cons.diffs != null ? cons.diffs : cons.count);
            out.push({
                text: '正文前后有 ' + n + ' 处说法不一致，交之前逐条对齐',
                id: (cons.id || 'proposalText'), tab: (cons.tab || 'proposal')
            });
        }
        return out.slice(0, 3);
    }

    function renderHero(d) {
        if (!S.hero) return;
        var score = num(d.score != null ? d.score : (d.data && d.data.score));
        var max = num(d.scoreMax != null ? d.scoreMax : (d.data && d.data.scoreMax));
        if (max === null) max = 100;
        var label = d.scoreLabel || (d.data && d.data.scoreLabel) || '文档质量自评';
        var one = d.oneLiner || d.one_liner || (d.data && (d.data.oneLiner || d.data.one_liner)) || '';
        var issues = pickIssues(d);

        var h = '';
        h += '<div class="wb339-hero-head">'
           +   '<span class="wb339-hero-title">关键结论</span>'
           +   '<span class="wb339-hero-sub">十秒看完：这次结果好不好、还差什么、下一步改哪</span>'
           + '</div>';
        h += '<div class="wb339-hero-grid">';

        // —— 评分（351 轮：必须带满分）——
        h += '<div class="wb339-score-card">';
        if (score === null) {
            h += '<div class="wb339-score-num">未评分</div>'
               + '<span class="wb339-score-cap">本次未返回评分，不做推测</span>';
        } else {
            h += '<div><span class="wb339-score-num">' + (Math.round(score * 10) / 10) + '</span>'
               + '<span class="wb339-score-max"> / ' + max + ' 分</span></div>'
               + '<span class="wb339-score-cap">' + esc(label) + '（满分 ' + max + ' 分）</span>';
        }
        var dims = d.scoreDims || (d.data && d.data.scoreDims) || [];
        if (dims && dims.length) {
            h += '<div class="wb339-score-dims">';
            dims.slice(0, 6).forEach(function (dm) {
                var v = num(dm.value), m = num(dm.max);
                h += '<div class="wb339-dim-row"><span>' + esc(dm.name || '') + '</span>'
                   + '<span class="wb339-dim-val">' + (v === null ? '—' : v) +
                     (m === null ? '' : ' / ' + m) + '</span></div>';
            });
            h += '</div>';
        }
        h += '</div>';

        // —— 一句话定位 + 待改 3 处 ——
        h += '<div>';
        if (String(one).trim()) {
            h += '<div class="wb339-oneliner">'
               +   '<div class="wb339-oneliner-lab">一句话项目定位（路演开场用）</div>'
               +   '<div class="wb339-oneliner-txt">' + esc(one) + '</div>'
               + '</div>';
        } else {
            h += '<div class="wb339-oneliner">'
               +   '<div class="wb339-oneliner-lab">一句话项目定位</div>'
               +   '<div class="wb339-oneliner-txt wb339-empty">本次未生成定位句</div>'
               + '</div>';
        }
        h += '<div class="wb339-issues-lab">最需要改的 ' + (issues.length || 3) + ' 处</div>';
        if (!issues.length) {
            h += '<div class="wb339-empty">本次未检出必须修改项，交之前仍建议自查占位数据与章节完整性。</div>';
        } else {
            h += '<ul class="wb339-issues">';
            issues.forEach(function (it, i) {
                h += '<li class="wb339-issue"><span class="wb339-issue-no">' + (i + 1) + '</span>'
                   + '<span class="wb339-issue-txt">' + esc(it.text) + '</span>'
                   + (it.id ? '<button type="button" class="wb339-issue-jump" data-wb339-go="' + esc(it.id) +
                       '" data-wb339-tab="' + esc(it.tab || '') + '">去改</button>' : '')
                   + '</li>';
            });
            h += '</ul>';
        }
        h += '</div>';
        h += '</div>';
        S.hero.innerHTML = h;
    }

    /* ============================ ② 健康度四灯 ============================ */

    function buildLamps(d) {
        var o = S.opts;

        // —— 评分 ——
        var sc = num(d.score != null ? d.score : (d.data && d.data.score));
        var scMax = num(d.scoreMax != null ? d.scoreMax : (d.data && d.data.scoreMax));
        if (scMax === null) scMax = 100;
        var scoreLamp = { key: 'score', name: '评分', tab: 'proposal', id: 'scoreNum' };
        if (sc === null) {
            scoreLamp.state = 'unknown';
            scoreLamp.value = '未检测';
            scoreLamp.note = '本次未返回评分';
        } else {
            scoreLamp.value = (Math.round(sc * 10) / 10) + ' / ' + scMax + ' 分';
            var line = num(o.scorePassLine);
            var given = d.scoreState || (d.data && d.data.scoreState) || (d.health && d.health.score && d.health.score.state);
            if (given) {
                scoreLamp.state = normState(given);
                scoreLamp.note = '满分 ' + scMax + ' 分';
            } else if (line !== null) {
                scoreLamp.state = sc >= line ? 'pass' : 'warn';
                scoreLamp.note = '合格线 ' + line + ' 分（满分 ' + scMax + ' 分）';
            } else {
                scoreLamp.state = 'unknown';
                scoreLamp.note = '满分 ' + scMax + ' 分 · 未设合格线，不判定通过与不通过';
            }
        }

        // —— 查重（本地初检）——
        var sim = d.similarity || (d.data && d.data.similarity) || {};
        var pct = num(sim.percent);
        var dupLamp = { key: 'dup', name: '查重', tab: 'analysis', id: 'similarityReport' };
        var dupLine = num(o.dupPassLine);
        var dupGiven = (d.health && d.health.dup && d.health.dup.state) ||
                       (d.data && d.data.health && d.data.health.dup && d.data.health.dup.state);
        if (pct === null) {
            dupLamp.state = 'unknown';
            dupLamp.value = '未检测';
            dupLamp.note = dupGiven ? '' : '本地初检未跑或未返回数值';
            if (dupGiven) { dupLamp.state = normState(dupGiven); dupLamp.value = STATE_TXT[dupLamp.state] || '未检测'; }
        } else {
            dupLamp.value = (Math.round(pct * 10) / 10) + '%';
            if (dupGiven) {
                dupLamp.state = normState(dupGiven);
                dupLamp.note = '本地初检' + (sim.checked ? '，对比 ' + sim.checked + ' 条范文' : '');
            } else if (dupLine !== null) {
                dupLamp.state = pct <= dupLine ? 'pass' : 'warn';
                dupLamp.note = '本地初检，≤ ' + dupLine + '% 视为通过';
            } else {
                dupLamp.state = 'unknown';
                dupLamp.note = '本地初检（非正式查重）· 未设合格线';
            }
        }

        // —— 一致性 ——
        var cons = d.consistency || (d.data && d.data.consistency) ||
                   (d.health && d.health.consistency) || null;
        var consLamp = { key: 'consistency', name: '一致性', tab: 'proposal', id: 'proposalText' };
        var cn = cons ? num(cons.diffs != null ? cons.diffs : cons.count) : null;
        if (cons && cons.state) {
            consLamp.state = normState(cons.state);
            consLamp.value = (cn === null) ? (STATE_TXT[consLamp.state] || '已检测') : (cn === 0 ? '通过' : '有差异 ' + cn + ' 处');
            consLamp.note = cons.note || '';
        } else if (cn !== null) {
            consLamp.state = cn === 0 ? 'pass' : 'warn';
            consLamp.value = cn === 0 ? '通过' : '有差异 ' + cn + ' 处';
            consLamp.note = cons.note || (cn === 0 ? '正文前后表述一致' : '点此定位逐条核对');
        } else {
            consLamp.state = 'unknown';
            consLamp.value = '未检测';
            consLamp.note = '本次未做前后一致性比对';
        }

        // —— 预审（提交前预审：缺章 / 存疑项）——
        var pre = d.precheck || d.pre_check || (d.data && (d.data.precheck || d.data.pre_check)) ||
                  (d.health && d.health.precheck) || null;
        var comp = d.completeness || (d.data && d.data.completeness) || null;
        var preLamp = { key: 'precheck', name: '预审', tab: 'proposal', id: 'completenessBox' };
        var pn = pre ? num(pre.count != null ? pre.count : pre.issues && pre.issues.length) : null;
        if (pre && pre.state) {
            preLamp.state = normState(pre.state);
            preLamp.value = (pn === null) ? (STATE_TXT[preLamp.state] || '已检测') : (pn === 0 ? '通过' : '存疑 ' + pn + ' 项');
            preLamp.note = pre.note || '';
        } else if (pn !== null) {
            preLamp.state = pn === 0 ? 'pass' : 'warn';
            preLamp.value = pn === 0 ? '通过' : '存疑 ' + pn + ' 项';
            preLamp.note = pre.note || '提交前预审结果';
        } else if (comp && comp.missing) {
            // 后端目前只返回章节完整性，据此给「缺章」这一项真实结论，不冒充官方预审
            var mn = (comp.missing || []).length;
            preLamp.state = mn === 0 ? 'pass' : 'warn';
            preLamp.value = mn === 0 ? '缺章 0 项' : '存疑 ' + mn + ' 项';
            preLamp.note = '仅覆盖章节完整性，非官方预审';
        } else {
            preLamp.state = 'unknown';
            preLamp.value = '未检测';
            preLamp.note = '本次未做提交前预审';
        }

        return [scoreLamp, dupLamp, consLamp, preLamp];
    }

    function renderHealth(d) {
        if (!S.health) return;
        var lamps = buildLamps(d);
        S.lampIdx = {};

        var h = '';
        h += '<div class="wb339-health-head">'
           +   '<span class="wb339-health-title">健康度</span>'
           +   '<span class="wb339-health-sub">四项各自独立判定 · 点灯跳到对应位置 · 灰灯＝未检测，不代表通过</span>'
           + '</div>';
        h += '<div class="wb339-lamps">';
        lamps.forEach(function (L) {
            S.lampIdx[L.key] = L;
            h += '<button type="button" class="wb339-lamp s-' + L.state + '"'
               + ' data-wb339-go="' + esc(L.id) + '" data-wb339-tab="' + esc(L.tab || '') + '"'
               + ' aria-label="' + esc(L.name) + '：' + esc(L.value) + '">'
               + '<span class="wb339-lamp-top"><span class="wb339-dot"></span>'
               + '<span class="wb339-lamp-name">' + esc(L.name) + '</span></span>'
               + '<span class="wb339-lamp-val">' + esc(L.value) + '</span>'
               + (L.note ? '<span class="wb339-lamp-note">' + esc(L.note) + '</span>' : '')
               + '</button>';
        });
        h += '</div>';

        // 红灯横幅：有 fail 用红，只有 warn 用黄
        var bad = lamps.filter(function (L) { return L.state === 'fail' || L.state === 'warn'; });
        var hasFail = bad.some(function (L) { return L.state === 'fail'; });
        var bnr = byId(NS + '-banner');
        if (bnr) {
            if (!bad.length) {
                bnr.className = 'wb339-banner';
                bnr.innerHTML = '';
            } else {
                var names = bad.map(function (L) { return L.name; }).join('、');
                bnr.className = 'wb339-banner is-on' + (hasFail ? '' : ' is-warn');
                bnr.innerHTML = '<span aria-hidden="true">▲</span>'
                    + '<span class="wb339-banner-txt">建议先处理 <b>' + esc(names) +
                      '</b> 再导出——带着这些问题交上去，评委一眼就能看出。</span>';
            }
        }
        S.health.innerHTML = h;
    }

    /* ============================ ③ 目录 + 锚点 ============================ */

    function anchorList() {
        var list = (global.WB_ANCHORS && global.WB_ANCHORS.length) ? global.WB_ANCHORS : FALLBACK_ANCHORS;
        var idx = {};
        list.forEach(function (a) { idx[a.id] = a; });
        return { list: list, idx: idx };
    }

    // 目录项该不该出现：
    //  · 整块被当前档位排除（.deep-only / .auto-show 且不可见）→ 不给目录项；
    //  · 面板类（tab-*）看所属栏目按钮有没有露出来（图表 tab 在简洁版是隐藏的）；
    //  · 内容块看有没有内容。
    // ⚠️ 刻意不检查「是否在当前激活的 tab」——目录本来就是用来跨栏目跳的，
    //    只列当前 tab 会变成「点了才看到有这一节」，失去导航意义。
    function hasSection(id) {
        var node = byId(id);
        if (!node) return false;
        if (id.indexOf('tab-') === 0) {
            var tab = id.slice(4);
            var btn = byId((global.WB_TAB_BTN && global.WB_TAB_BTN[tab]) || '');
            if (btn) return shown(btn);
            return shown(node);
        }
        var wrap = (node.closest && (node.closest('.deep-only') || node.closest('.auto-show'))) || null;
        if (wrap && !shown(wrap)) return false;
        return !!(node.textContent || '').trim();
    }

    function renderToc() {
        if (!S.toc) return;
        var A = anchorList();
        S.tocIdx = {};

        var h = '';
        h += '<button type="button" class="wb339-drawer-btn" data-wb339-act="toggle">'
           + (S.tocCollapsed ? '目录：点开看全部章节 ▾' : '目录：收起 ▴') + '</button>';
        h += '<div class="wb339-toc-head">'
           +   '<span class="wb339-toc-title">目录</span>'
           +   '<button type="button" class="wb339-toc-toggle" data-wb339-act="toggle">' +
               (S.tocCollapsed ? '展开' : '收起') + '</button>'
           + '</div>';
        h += '<div class="wb339-body">';

        TAB_PLAN.forEach(function (g) {
            var items = [];
            g.sections.forEach(function (sid) {
                var a = A.idx[sid];
                var node = byId(sid);
                if (!node) return;
                // 整块被当前档位排除、或压根没内容 → 不给目录项，
                // 否则点过去是一片空白，反而更迷路
                if (!hasSection(sid)) return;
                items.push({ id: sid, name: (a && a.n) || sid, tab: (a && a.t) || g.key });
            });
            if (!items.length && g.key !== 'conclusion') return;

            // 339 轮：默认只展开「正文」核心区，其余折叠
            var open = (g.key === 'proposal');
            h += '<div class="wb339-toc-group">'
               +   '<div class="wb339-toc-gname">' + esc(g.name) + '</div>'
               +   '<div class="wb339-toc-list">';
            if (g.key === 'conclusion') {
                h += '<button type="button" class="wb339-toc-btn" data-wb339-go="' + NS + '-hero" data-wb339-tab="">'
                   + '关键结论与健康度</button>';
            }
            items.forEach(function (it) {
                S.tocIdx[it.id] = it;
                h += '<button type="button" class="wb339-toc-btn" data-wb339-go="' + esc(it.id) +
                     '" data-wb339-tab="' + esc(it.tab) + '">' + esc(it.name) + '</button>';
            });
            h += '</div></div>';
            if (!open) { /* 折叠态：目录项仍可见，只是分组名后不再展开子项之外的额外区块 */ }
        });

        h += '</div>';
        S.toc.innerHTML = h;
        S.tocBody = S.toc.querySelector('.wb339-body');
        if (S.tocCollapsed) S.toc.classList.add('is-collapsed');
        else S.toc.classList.remove('is-collapsed');

        // 目录项可见性随内容变化（流式渲染 / 重渲染后要复检）
        S.timers.push(setTimeout(function () { syncTocVisible(); }, 400));
        S.timers.push(setTimeout(function () { syncTocVisible(); }, 1800));
    }

    // 复检：内容后来才补上的目录项要露出来，空掉的（或整块隐藏的）要撤掉
    function syncTocVisible() {
        if (!S.toc) return;
        var btns = S.toc.querySelectorAll('[data-wb339-go]');
        for (var i = 0; i < btns.length; i++) {
            var b = btns[i];
            var id = b.getAttribute('data-wb339-go');
            if (!id || id === NS + '-hero') continue;
            b.style.display = hasSection(id) ? '' : 'none';
        }
    }

    // 跳转：先切到所属旧 tab，再平滑滚过去并高亮
    function go(sid, tab) {
        if (!sid) return;
        if (sid === NS + '-hero') {
            if (S.hero) scrollTo_(S.hero);
            setActive(sid);
            return;
        }
        var node = byId(sid);
        if (!node) return;
        if (tab) {
            try {
                var btn = byId((global.WB_TAB_BTN && global.WB_TAB_BTN[tab]) || '');
                var fn = global.switchTab || (typeof switchTab === 'function' ? switchTab : null);
                if (fn && btn && !btn.classList.contains('active')) fn(null, tab);
                else if (fn && !btn) fn(null, tab);
            } catch (e) {}
        }
        setTimeout(function () { scrollTo_(node); setActive(sid); }, 60);
        try {
            if (S.opts.onJump && typeof S.opts.onJump === 'function') S.opts.onJump(sid, tab);
        } catch (e) {}
    }

    function scrollTo_(node) {
        if (!node) return;
        // 滚到带标题的整块（content-block 的父 div），而不是光秃秃的正文块
        var target = (node.closest && node.closest('div')) || node;
        try { target.style.scrollMarginTop = '76px'; } catch (e) {}
        // ⚠️ 平滑滚动在部分移动内核里会「认下参数却不动」（app.js 标签栏踩过同一个坑）：
        // 这里延后核对一次，没动就补一次即时滚动。
        var y0 = (global.pageYOffset || 0);
        try {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (e) {
            try { target.scrollIntoView(); } catch (e2) {}
        }
        S.timers.push(setTimeout(function () {
            try {
                var top = target.getBoundingClientRect().top;
                if (Math.abs((global.pageYOffset || 0) - y0) < 2 && Math.abs(top - 76) > 60) {
                    target.scrollIntoView();
                }
            } catch (e) {}
        }, 450));
        flash(target);
    }

    function flash(node) {
        if (!node) return;
        try {
            var old = node.style.boxShadow;
            node.classList.add('wb339-flash');
            S.timers.push(setTimeout(function () {
                node.classList.remove('wb339-flash');
                node.style.boxShadow = old;
            }, 1200));
        } catch (e) {}
    }

    function setActive(sid) {
        if (!S.toc) return;
        S.activeId = sid;
        var btns = S.toc.querySelectorAll('[data-wb339-go]');
        for (var i = 0; i < btns.length; i++) {
            var b = btns[i];
            if (b.getAttribute('data-wb339-go') === sid) b.classList.add('is-on');
            else b.classList.remove('is-on');
        }
    }

    // 滚动高亮：取「已滚过且离顶部最近」的可见章节
    function syncActive() {
        if (!S.toc || !S.tocIdx) return;
        var best = '', bestTop = -99999;
        Object.keys(S.tocIdx).forEach(function (id) {
            var node = byId(id);
            if (!node || !shown(node)) return;
            var r = node.getBoundingClientRect();
            if (r.top > 160) return;
            if (r.top > bestTop) { bestTop = r.top; best = id; }
        });
        if (best && best !== S.activeId) setActive(best);
    }

    function onScroll() {
        if (S.rafId) return;
        S.rafId = (global.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () {
            S.rafId = 0;
            try { syncActive(); } catch (e) {}
        });
    }

    /* ============================ ⑤ 写作构思纲要 ============================ */

    var OUTLINE_IDS = ['proposalOutline', 'proposal_outline'];

    function outlineText(d) {
        var v = '';
        OUTLINE_IDS.forEach(function (k) { if (!v && d && d[k]) v = d[k]; });
        if (!v && d && d.data) {
            OUTLINE_IDS.forEach(function (k) { if (!v && d.data[k]) v = d.data[k]; });
        }
        return String(v || '').trim();
    }

    // 339/374 轮：纲要取不到就整块不渲染，绝不留下「只有标题和提示」的空壳。
    // 空壳根因：index.html 里该块是 .deep-only，app.js 在深度版统一 display:block，
    // 但只有 data.proposal_outline 存在时才往里写内容 —— 没这个字段就成了空折叠区。
    function syncOutline(d) {
        var txt = outlineText(d);
        var box = byId('proposalOutline');
        var shell = null;
        if (box) {
            shell = (box.closest && (box.closest('.deep-only') || box.closest('.auto-show'))) || box.parentElement;
        }
        if (!txt) {
            if (shell) shell.style.display = 'none';
            if (S.outlineNode) { S.outlineNode.style.display = 'none'; }
            // 目录里如果已经挂了这一项，也要撤掉（syncTocVisible 会自动处理）
            return false;
        }
        if (shell) shell.style.display = '';
        if (box && !(box.textContent || '').trim()) box.innerHTML = md(txt);
        if (S.outlineNode) {
            S.outlineNode.style.display = '';
            var body = S.outlineNode.querySelector('.wb339-outline-body');
            if (body) body.innerHTML = md(txt);
        }
        return true;
    }

    /* ============================ 组装 / 生命周期 ============================ */

    function buildDom() {
        var host = S.opts.mount;
        if (typeof host === 'string') host = byId(host.replace(/^#/, ''));
        if (!host) host = byId('resultArea') || document.body;
        S.host = host;

        var root = el('div', NS);
        root.id = NS + '-root';

        // rail 布局：把 #resultTabs 及其后的兄弟节点整段搬进 .wb339-main，
        // 与左侧目录并排。窄屏 / 找不到节点时自动退回 inline，不做任何搬动。
        var shell = el('div', 'wb339-shell');
        var aside = el('aside', 'wb339-toc');
        var main = el('div', 'wb339-main');
        var wantRail = (S.opts.layout === 'rail') ||
                       (S.opts.layout !== 'inline' && (global.innerWidth || 0) >= 1100);
        var tabs = byId('resultTabs');
        if (wantRail && tabs && tabs.parentNode === host) {
            try {
                var collect = [];
                var n = tabs;
                while (n) { collect.push(n); n = n.nextSibling; }
                S.moveParent = host;
                S.moveBefore = null;
                S.moved = collect;
                collect.forEach(function (node) { main.appendChild(node); });
                shell.className = 'wb339-shell is-rail';
            } catch (e) {
                // 搬动失败就把节点放回去，退回 inline
                rollbackMove();
                shell.className = 'wb339-shell';
            }
        }

        var hero = el('div', 'wb339-hero');
        var banner = el('div', 'wb339-banner');
        banner.id = NS + '-banner';
        banner.setAttribute('role', 'status');
        var health = el('div', 'wb339-health');

        S.hero = hero;
        S.health = health;
        S.toc = aside;

        shell.appendChild(aside);
        shell.appendChild(main);

        root.appendChild(hero);
        root.appendChild(banner);
        root.appendChild(health);
        root.appendChild(shell);

        // 插到结果区顶部：导出条之后、自评面板之前
        var anchor = byId('scorePanel');
        if (anchor && anchor.parentNode === host) host.insertBefore(root, anchor);
        else if (host.firstChild) host.insertBefore(root, host.firstChild);
        else host.appendChild(root);

        S.root = root;
        S.shell = shell;
        S.main = main;

        root.addEventListener('click', onClick);
        global.addEventListener('scroll', onScroll, { passive: true });
        global.addEventListener('resize', onResize, { passive: true });
    }

    function onClick(ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        var act = t.closest('[data-wb339-act]');
        if (act) {
            var a = act.getAttribute('data-wb339-act');
            if (a === 'toggle') {
                S.tocCollapsed = !S.tocCollapsed;
                if (S.toc) {
                    if (S.tocCollapsed) S.toc.classList.add('is-collapsed');
                    else S.toc.classList.remove('is-collapsed');
                }
                var tg = S.toc && S.toc.querySelector('[data-wb339-act="toggle"]:not(.wb339-drawer-btn)');
                if (tg) tg.textContent = S.tocCollapsed ? '展开' : '收起';
                var dr = S.toc && S.toc.querySelector('.wb339-drawer-btn');
                if (dr) dr.innerHTML = S.tocCollapsed ? '目录：点开看全部章节 ▾' : '目录：收起 ▴';
            }
            return;
        }
        var hit = t.closest('[data-wb339-go]');
        if (!hit) return;
        go(hit.getAttribute('data-wb339-go'), hit.getAttribute('data-wb339-tab'));
    }

    var _rz = 0;
    function onResize() {
        if (_rz) clearTimeout(_rz);
        _rz = setTimeout(function () {
            _rz = 0;
            if (!S.shell) return;
            var rail = (global.innerWidth || 0) >= 1100;
            if (S.moved) S.shell.className = rail ? 'wb339-shell is-rail' : 'wb339-shell';
            syncTocVisible();
        }, 200);
    }

    function rollbackMove() {
        if (!S.moved || !S.moveParent) return;
        var nodes = S.moved;
        S.moved = null;
        try {
            nodes.forEach(function (node) { S.moveParent.appendChild(node); });
        } catch (e) {}
        S.moveParent = null;
    }

    function clearTimers() {
        S.timers.forEach(function (t) { try { clearTimeout(t); } catch (e) {} });
        S.timers = [];
    }

    /* ============================ 对外接口 ============================ */

    function init(opts) {
        opts = opts || {};
        // 移动端（≤820px）默认收进抽屉，桌面默认常驻展开
        var autoCollapse = (global.innerWidth || 1024) <= 820;
        S.tocCollapsed = (typeof opts.tocCollapsed === 'boolean') ? opts.tocCollapsed : autoCollapse;
        S.opts = {
            mount: opts.mount || '#resultArea',
            dupPassLine: (typeof opts.dupPassLine === 'undefined') ? null : opts.dupPassLine,
            scorePassLine: (typeof opts.scorePassLine === 'undefined') ? null : opts.scorePassLine,
            layout: opts.layout || 'auto',
            tocCollapsed: S.tocCollapsed,
            onJump: opts.onJump || null
        };
        if (S.inited) { refresh(opts.data); return api; }
        try {
            buildDom();
            S.inited = true;
            refresh(opts.data);
        } catch (e) {
            if (global.console && console.warn) console.warn('[wbresult339] init 失败，已跳过：', e);
            S.inited = false;
        }
        return api;
    }

    function refresh(data) {
        if (!S.inited) return api;
        S.data = data || S.data || {};
        var d = S.data;
        try { renderHero(d); } catch (e) {}
        try { renderHealth(d); } catch (e) {}
        // 先定纲要（决定它整块渲染还是消失），再建目录，
        // 否则目录会把「还没写进内容」的纲要判成空块而不给它目录项
        try { syncOutline(d); } catch (e) {}
        try { renderToc(); } catch (e) {}
        try { syncTocVisible(); } catch (e) {}
        try { syncActive(); } catch (e) {}
        return api;
    }

    function destroy() {
        clearTimers();
        try { global.removeEventListener('scroll', onScroll); } catch (e) {}
        try { global.removeEventListener('resize', onResize); } catch (e) {}
        rollbackMove();
        if (S.root && S.root.parentNode) S.root.parentNode.removeChild(S.root);
        S.inited = false;
        S.root = S.hero = S.health = S.toc = S.shell = S.main = null;
        return api;
    }

    var api = {
        init: init,
        refresh: refresh,
        destroy: destroy,
        go: go,
        TAB_PLAN: TAB_PLAN,
        // 给接线方自查用：当前四灯状态、目录项数量、纲要是否渲染
        debug: function () {
            return {
                inited: S.inited,
                lamps: buildLamps(S.data || {}),
                tocCount: Object.keys(S.tocIdx || {}).length,
                outlineRendered: !!outlineText(S.data || {}),
                rail: !!(S.shell && S.shell.className.indexOf('is-rail') >= 0)
            };
        }
    };

    global.wbResult339 = api;

    /* =========================================================================
       接线契约（WB339_CONTRACT）
       index.html 加两行（放 </body> 前，其它 static 资源之后）：
         <link rel="stylesheet" href="/static/wbresult339.css">
         <script src="/static/wbresult339.js" defer></script>
       app.js 里在结果渲染队列跑完后调一次（init 幂等，重复调用只 refresh）：
         wbResult339.init({ data: window._lastData });
       需要传入的数据字段（全部可缺省，缺了就走中性态）：
         score / scoreMax / scoreLabel / scoreDims[{name,value,max}]
         oneLiner 或 one_liner
         similarity{percent, checked}
         consistency{state|diffs|count, note}
         precheck{state|count, note}   缺失时回落到 completeness.missing
         completeness{missing[], placeholders}
         proposal_outline 或 proposalOutline
         topIssues[{text, id, tab}]    不给时由 completeness / 占位 / 查重 自动推导
       依赖的现有全局：window.WB_ANCHORS（目录来源）、window.switchTab + #resultTabs
       兄弟按钮（跨栏目跳转）、window.wbRenderMD（Markdown，缺失时内部兜底）。
       依赖的现有 DOM：#resultArea（挂载点）、#scorePanel（插入锚点）、
         #proposalOutline（空折叠区治理）、各 #tab-* / 区块 id（锚点落点）。
       ========================================================================= */
})(window);
