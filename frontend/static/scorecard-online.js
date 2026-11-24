/* =============================================================================
   scorecard-online.js —— 线上版「官方评分项自查」
   ---------------------------------------------------------------------------
   挂在 #wbSubPanel-score（评分总览）末尾，跟着该 tab 一起显隐，不碰现有
   switchScoreTab 逻辑（它只 toggle 三个 wbSubPanel-*）。

   与本地版 frontend/static/scorecard-panel.js 的差别：
     本地挂在 .wb339-hero 之后、用 wb339-* 类；线上是 #wbSubPanel-score + wbsc-* 类。
     两套前端结构不同，各维护一份，互不影响。

   线上只做「只读诊断」：定向补写要依赖清理链（_strip_cliches 等），
   线上还没有，所以这里不给补强按钮，避免只改一半。

   API：POST /api/scorecard {history_id}
   ============================================================================= */
(function (g) {
    'use strict';

    var S = { root: null, obs: null, loadedHid: null, raf: 0, locked: false, started: false };

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
        return n === null ? '—' : (Math.round(n * 10) / 10 + '');
    }

    // 线上 _lastHistoryId 在新结果还没落库时会回落到上一条（app.js 5374 行的老写法），
    // 所以优先取结果数据自带的 id，取不到才回退。
    function curHid() {
        var d = g._lastData || {};
        var id = (d.data && d.data.history_id) || d.history_id || g._lastHistoryId || null;
        var n = parseInt(id, 10);
        return isFinite(n) ? n : null;
    }

    function emptyState(msg) {
        return '<div class="wbsc"><div class="wbsc-head"><span class="wbsc-title">官方评分项自查</span></div>'
            + '<div class="wbsc-empty">' + esc(msg) + '</div></div>';
    }

    function renderDiag(d) {
        var dims = d.dims || [];
        var gaps = d.top_gaps || [];
        var h = '<div class="wbsc">';
        h += '<div class="wbsc-head">'
            + '<span class="wbsc-title">官方评分项自查</span>'
            + '<span class="wbsc-sub">' + esc(d.competition || '') + '</span>'
            + '<span class="wbsc-total">' + fmt(d.total) + '<i> / 100 分</i></span>'
            + '</div>';
        h += '<div class="wbsc-dims">';
        dims.forEach(function (dm, i) {
            h += '<div class="wbsc-dim' + (dm.judged === false ? ' is-muted' : '') + '" data-i="' + i + '">'
                + '<span class="wbsc-dim-name">' + esc(dm.name) + '</span>'
                + '<span class="wbsc-dim-val">' + fmt(dm.score) + ' / ' + fmt(dm.weight) + '</span>'
                + '</div>';
        });
        h += '</div>';
        if (gaps.length) {
            h += '<div class="wbsc-gaps">';
            gaps.forEach(function (gp, i) {
                h += '<div class="wbsc-gap"><span class="wbsc-gap-no">' + (i + 1) + '</span>'
                    + '<span class="wbsc-gap-txt">' + esc(gp.gap)
                    + (num(gp.lost) === null ? '' : '<em>· 丢约 ' + fmt(gp.lost) + ' 分</em>')
                    + '</span></div>';
            });
            h += '</div>';
        } else {
            h += '<div class="wbsc-empty">按官方评分项没检出明显缺口。</div>';
        }
        h += '<div class="wbsc-foot">按赛事官方评分项逐项核对，只在找得到原文证据时给分；点维度看证据</div>';
        h += '</div>';
        return h;
    }

    function bindDims(d) {
        var rows = S.root.querySelectorAll('.wbsc-dim');
        Array.prototype.forEach.call(rows, function (row) {
            var i = parseInt(row.getAttribute('data-i'), 10);
            var dm = (d.dims || [])[i];
            if (!dm) return;
            var hasEv = (dm.checks || []).some(function (c) { return c.snippet; });
            if (!hasEv && !(dm.gaps && dm.gaps.length)) return;
            row.classList.add('is-click');
            row.addEventListener('click', function () {
                var next = row.nextElementSibling;
                if (next && next.classList.contains('wbsc-evbox')) {
                    next.parentNode.removeChild(next);
                    return;
                }
                var box = '<div class="wbsc-evbox">';
                (dm.gaps || []).forEach(function (gp) { box += '<div class="wbsc-ev-gap">' + esc(gp) + '</div>'; });
                (dm.checks || []).forEach(function (c) {
                    if (!c.snippet) return;
                    box += '<div class="wbsc-ev"><b>' + esc(c.label) + '</b><span>' + esc(c.snippet) + '</span></div>';
                });
                box += '</div>';
                row.insertAdjacentHTML('afterend', box);
            });
        });
    }

    function load() {
        var hid = curHid();
        S.loadedHid = hid;
        if (!S.root) return;
        if (!hid) {
            S.root.innerHTML = emptyState('这次结果还没入库，评分项自查要等记录生成后才能做');
            return;
        }
        S.root.innerHTML = emptyState('正在按官方评分项核对');
        fetch('/api/scorecard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ history_id: hid })
        }).then(function (r) { return r.json(); })
            .then(function (j) {
                if (!j || !j.success) throw new Error((j && j.error) || '');
                var dd = j.diag || {};
                if (!dd.available) {
                    S.root.innerHTML = emptyState(dd.reason || '该赛事没有官方评分权重，无法按项自查');
                    return;
                }
                S.root.innerHTML = renderDiag(dd);
                bindDims(dd);
            })
            .catch(function () {
                S.root.innerHTML = emptyState('评分项自查暂时取不到数据，正文与导出不受影响');
            });
    }

    function mount() {
        var host = document.getElementById('wbSubPanel-score');
        if (!host) return;
        var old = document.getElementById('wbscRoot');
        // 面板已在、且仍挂在同一个容器里 → 不碰 DOM（observer 到此收敛）
        if (old && old.parentNode === host) {
            if (S.loadedHid !== curHid()) { S.root = old; load(); }
            return;
        }
        if (old && old.parentNode) old.parentNode.removeChild(old);
        var box = document.createElement('div');
        box.id = 'wbscRoot';
        host.appendChild(box);
        S.root = box;
        load();
    }

    function schedule() {
        if (S.raf || S.locked) return;
        S.raf = (g.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () {
            S.raf = 0;
            S.locked = true;
            try { mount(); } catch (e) { } finally { S.locked = false; }
        });
    }

    function init() {
        if (S.started) return;
        S.started = true;
        var tries = 0;
        (function tick() {
            mount();
            var host = document.getElementById('resultArea') || document.getElementById('scorePanel');
            if (host && !S.obs && typeof MutationObserver !== 'undefined') {
                S.obs = new MutationObserver(function () { schedule(); });
                S.obs.observe(host, { childList: true, subtree: true });
                return;
            }
            if (++tries < 150) setTimeout(tick, 400);
        })();
    }

    g.wbScorecardOnline = { init: init, refresh: mount };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
