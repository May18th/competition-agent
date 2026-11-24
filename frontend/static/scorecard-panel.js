/* =============================================================================
   scorecard-panel.js —— 评分项自查（按赛事官方评分维度逐项给分 + 缺口）
   ---------------------------------------------------------------------------
   外挂式：只读 window._lastHistoryId，不改 result-panel.js 的任何逻辑，
   产物挂在 .wb339-hero 之后、命名空间 #wb339ScRoot / .wb339-sc-* 内。

   风格纪律（与 result-panel.css 一致）：
     颜色一律走 CSS 的 --w339-* token，JS 不写任何色值；
     评分一律带满分标注（45 / 100 分）；
     拿不到真实数据就显示中性态，不推测分数。

   API：POST /api/scorecard {history_id}           → 诊断
        POST /api/scorecard/patch {history_id}     → 定向补写（会调用模型，10~40 秒）
   ============================================================================= */
(function (global) {
    'use strict';

    var S = { root: null, obs: null, busy: false, last: null, rafId: 0, locked: false, started: false };

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function num(v) {
        var n = typeof v === 'number' ? v : parseFloat(v);
        return isFinite(n) ? n : null;
    }

    function fmt(v) {
        var n = num(v);
        if (n === null) return '—';
        return Math.round(n * 10) / 10 + '';
    }

    // 章节名带着 Markdown 前缀（「## 七、创业团队」），展示时去掉
    function cleanTitle(t) {
        return String(t == null ? '' : t).replace(/^#{1,6}\s*/, '');
    }

    function post(url, payload) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {})
        }).then(function (r) { return r.json(); });
    }

    /* ---------------- 渲染 ---------------- */

    function shell(headSub, bodyHtml) {
        return '<div class="wb339-hero-head">'
            + '<span class="wb339-hero-title">评分项自查</span>'
            + '<span class="wb339-hero-sub">' + esc(headSub) + '</span>'
            + '</div>'
            + '<div class="wb339-hero-grid">' + bodyHtml + '</div>';
    }

    function renderEmpty(msg) {
        if (!S.root) return;
        S.root.innerHTML = shell('按赛事官方评分项逐项核对',
            '<div class="wb339-empty">' + esc(msg) + '</div>');
    }

    function renderDiag(d) {
        if (!S.root) return;
        S.last = d;
        var total = num(d.total);
        var dims = d.dims || [];

        var left = '<div class="wb339-score-card">';
        if (total === null) {
            left += '<div class="wb339-score-num">未评分</div>';
        } else {
            left += '<div><span class="wb339-score-num">' + fmt(total) + '</span>'
                + '<span class="wb339-score-max"> / 100 分</span></div>';
        }
        left += '<span class="wb339-score-cap">' + esc(d.competition || '') + ' 官方评分项</span>'            + '<div class="wb339-score-dims">';
        dims.forEach(function (dm) {
            var judged = dm.judged !== false;
            left += '<div class="wb339-dim-row' + (judged ? '' : ' wb339-sc-muted') + '">'
                + '<span>' + esc(dm.name) + '</span>'
                + '<span class="wb339-dim-val">' + fmt(dm.score) + ' / ' + fmt(dm.weight) + '</span>'
                + '</div>';
        });
        left += '</div></div>';

        var gaps = d.top_gaps || [];
        var right = '<div>';
        if (!gaps.length) {
            right += '<div class="wb339-empty">按官方评分项没检出明显缺口。</div>';
        } else {
            right += '<div class="wb339-issues-lab">最该补的 ' + gaps.length + ' 处</div>'
                + '<ul class="wb339-issues">';
            gaps.forEach(function (g, i) {
                var lost = num(g.lost);
                right += '<li class="wb339-issue">'
                    + '<span class="wb339-issue-no">' + (i + 1) + '</span>'
                    + '<span class="wb339-issue-txt">' + esc(g.gap)
                    + (lost === null ? '' : '<span class="wb339-sc-lost">· 丢约 ' + fmt(lost) + ' 分</span>')
                    + '</span></li>';
            });
            right += '</ul>';
        }
        right += '<div class="wb339-sc-actions">'
            + '<button type="button" class="wb339-issue-jump wb339-sc-go">按评分项补强</button>'
            + '<span class="wb339-sc-hint">只改缺分的那几章，补完复检；不改原稿</span>'
            + '</div><div class="wb339-sc-out"></div></div>';

        S.root.innerHTML = shell('缺证据的项按 0 计，点维度看证据', left + right);
        var btn = S.root.querySelector('.wb339-sc-go');
        if (btn) btn.addEventListener('click', onPatch);
        // 维度行点开看证据，默认收起
        dims.forEach(function (dm, i) { bindDim(i, dm); });
    }

    function bindDim(i, dm) {
        var rows = S.root.querySelectorAll('.wb339-dim-row');
        var row = rows[i];
        if (!row || !dm.checks) return;
        var hasSnippet = (dm.checks || []).some(function (c) { return c.snippet; });
        if (!hasSnippet && !(dm.gaps && dm.gaps.length)) return;
        row.classList.add('wb339-sc-click');
        row.setAttribute('role', 'button');
        row.setAttribute('tabindex', '0');
        var open = function () {
            var box = row.nextElementSibling;
            if (box && box.classList.contains('wb339-sc-evbox')) {
                box.parentNode.removeChild(box);
                row.classList.remove('wb339-sc-open');
                return;
            }
            var h = '<div class="wb339-sc-evbox">';
            (dm.gaps || []).forEach(function (g) {
                h += '<div class="wb339-sc-gap">' + esc(g) + '</div>';
            });
            (dm.checks || []).forEach(function (c) {
                if (!c.snippet) return;
                h += '<div class="wb339-sc-ev"><span class="wb339-sc-ev-lab">'
                    + esc(c.label) + '</span><span>' + esc(c.snippet) + '</span></div>';
            });
            h += '</div>';
            row.insertAdjacentHTML('afterend', h);
            row.classList.add('wb339-sc-open');
        };
        row.addEventListener('click', open);
        row.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
        });
    }

    /* ---------------- 补强 ---------------- */

    function onPatch() {
        if (S.busy || !S.root) return;
        var hid = global._lastHistoryId;
        if (!hid) return;
        S.busy = true;
        var btn = S.root.querySelector('.wb339-sc-go');
        var out = S.root.querySelector('.wb339-sc-out');
        if (btn) { btn.disabled = true; btn.textContent = '补强中'; }
        if (out) out.innerHTML = '<div class="wb339-empty">正在改缺分章节，约需 10~40 秒</div>';

        post('/api/scorecard/patch', { history_id: hid, limit: 2 })
            .then(function (j) {
                if (!j.success) throw new Error(j.error || '补强失败');
                return j.result;
            })
            .then(function (res) {
                var before = num(res.before), after = num(res.after);
                var h = '<div class="wb339-sc-done">'
                    + '<span class="wb339-sc-delta">' + fmt(before) + ' → ' + fmt(after) + ' 分</span>';
                (res.applied || []).forEach(function (a) {
                    h += '<div class="wb339-sc-line">补了 ' + esc(cleanTitle(a.chapter || a.label))
                        + '（+' + fmt(a.gain) + ' 分）</div>';
                });
                (res.reverted || []).forEach(function (r) {
                    h += '<div class="wb339-sc-line wb339-sc-muted">'
                        + esc(r.label) + ' 未采用：' + esc(r.reason) + '</div>';
                });
                if (!(res.applied || []).length) {
                    h += '<div class="wb339-sc-line wb339-sc-muted">'
                        + '这一版没找到能通过复检的改法，原稿保留。</div>';
                }
                h += '<details class="wb339-sc-full"><summary>查看补强后的正文</summary>'
                    + '<textarea class="wb339-sc-text" readonly></textarea></details>';
                h += '</div>';
                out.innerHTML = h;
                var ta = out.querySelector('.wb339-sc-text');
                if (ta) ta.value = res.proposal || '';
            })
            .catch(function (e) {
                out.innerHTML = '<div class="wb339-empty">' + esc(e.message || '补强失败') + '</div>';
            })
            .then(function () {
                S.busy = false;
                var b = S.root.querySelector('.wb339-sc-go');
                if (b) { b.disabled = false; b.textContent = '按评分项补强'; }
            });
    }

    /* ---------------- 装载 ---------------- */

    function load() {
        var hid = global._lastHistoryId;
        S.loadedHid = hid || null;
        if (!hid) {
            renderEmpty('这次结果还没入库，评分项自查要等记录生成后才能做');
            return;
        }
        renderEmpty('正在按官方评分项核对');
        post('/api/scorecard', { history_id: hid })
            .then(function (j) {
                if (!j.success) throw new Error(j.error || '');
                var d = j.diag || {};
                if (!d.available) {
                    renderEmpty(d.reason || '该赛事没有官方评分权重，无法按项自查');
                    return;
                }
                renderDiag(d);
            })
            .catch(function () {
                renderEmpty('评分项自查暂时取不到数据，正文与导出不受影响');
            });
    }

    function mount() {
        var hero = document.querySelector('.wb339-hero');
        if (!hero || !hero.parentNode) return;
        var old = document.getElementById('wb339ScRoot');
        // 收敛条件：面板已存在且紧跟当前 hero → 不碰 DOM。
        // （index.html 里记过一次 observer 死循环事故：判据永远为真 + 观察整个 body，
        //   DOM 一变就重建、重建又触发 observer，主线程被占满。）
        if (old && old.previousElementSibling === hero) {
            // 例外：结果换了（history_id 变了）就重取一次，否则旧分数会一直挂着
            if (S.loadedHid !== (global._lastHistoryId || null)) {
                S.root = old;
                load();
            }
            return;
        }
        if (old) old.parentNode.removeChild(old);
        var box = document.createElement('div');
        box.id = 'wb339ScRoot';
        box.className = 'wb339-hero wb339-sc';
        hero.insertAdjacentElement('afterend', box);
        S.root = box;
        load();
    }

    function host() {
        return document.getElementById('resultArea') || document.getElementById('scorePanel');
    }

    function schedule() {
        if (S.rafId || S.locked) return;
        S.rafId = (global.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () {
            S.rafId = 0;
            S.locked = true;
            try { mount(); } catch (e) { } finally { S.locked = false; }
        });
    }

    function init() {
        if (S.started) return;
        S.started = true;
        var tries = 0;
        // 结果区是动态渲染的：等它出现，然后只盯它，别盯整个 body
        (function tick() {
            mount();
            var h = host();
            if (h && !S.obs && typeof MutationObserver !== 'undefined') {
                S.obs = new MutationObserver(function () { schedule(); });
                S.obs.observe(h, { childList: true, subtree: true });
                return;
            }
            if (++tries < 150) setTimeout(tick, 400);
        })();
    }

    global.wbScorecard = { init: init, refresh: function () { mount(); } };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
