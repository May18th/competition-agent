/* 第二百七十二轮：赛事知识库可视化
 *
 * 纯前端只读展示：数据取自已核对的 WB_COMP_PROFILES（官方口径），
 * 没有时回落 window.EVENT_REQ（内置规则）。零后端改动、零 LLM 消耗。
 *
 * 雷达图用**手写 SVG**，不依赖 ECharts —— 顺带避开 253.1「图表 tab 空白」的加载风险。
 * 独立区块（#kbCompare），不侵入赛事选择／生成主链路。
 */
(function () {
    'use strict';
    if (window.__wbKbInit) return;
    window.__wbKbInit = true;

    var A_COLOR = '#0e7490';   // 日间主色（与 --c-a-rgb 一致）
    var B_COLOR = '#c2410c';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // 官方 profiles 缓存。注意：app.js 里的 WB_COMP_PROFILES 是闭包内的局部变量，
    // 外面拿不到，所以这里直接读只读接口 /api/competition_profiles（15 赛事全量）。
    var _profiles = null;
    var _profTried = false;

    function loadProfiles(cb) {
        if (_profiles || _profTried) { cb(_profiles); return; }
        _profTried = true;
        try {
            fetch('/api/competition_profiles', { cache: 'no-cache' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    var arr = (d && d.competitions) || (Array.isArray(d) ? d : null);
                    if (arr && arr.length) _profiles = arr;
                    cb(_profiles);
                })
                .catch(function () { cb(null); });
        } catch (e) { cb(null); }
    }

    // ---- 取赛事数据：官方 profiles 优先，回落内置 ----
    function getComps() {
        var out = [];
        try {
            var ps = _profiles || [];
            for (var i = 0; i < ps.length; i++) {
                var p = ps[i] || {};
                out.push({
                    name: p.name || '',
                    scoring: p.scoring || [],
                    chapters: p.chapters || [],
                    src: 'profiles'
                });
            }
        } catch (e) {}
        if (out.length) return out;

        try {
            var ev = window.EVENT_REQ || {};
            for (var k in ev) {
                var v = ev[k] || {};
                out.push({
                    name: k,
                    scoring: v.scoring || [],
                    chapters: v.sections || [],
                    src: 'builtin'
                });
            }
        } catch (e2) {}
        return out;
    }

    // ---- 手写 SVG 雷达图 ----
    // series: [{name, color, vals:[{label, value}]}]
    function radarSVG(series, size) {
        size = size || 300;
        var cx = size / 2, cy = size / 2 + 6, R = size / 2 - 46;
        // 以所有 series 中最长的维度集为准
        var labels = [], maxV = 0;
        for (var s = 0; s < series.length; s++) {
            var vs = series[s].vals || [];
            if (vs.length > labels.length) {
                labels = [];
                for (var i = 0; i < vs.length; i++) labels.push(vs[i].label);
            }
            for (var j = 0; j < vs.length; j++) {
                if (Number(vs[j].value) > maxV) maxV = Number(vs[j].value);
            }
        }
        var n = labels.length;
        if (!n) return '<div style="color:var(--text-dim);font-size:13px;">该赛事暂无评分维度数据</div>';
        maxV = maxV || 100;
        if (maxV < 10) maxV = 10;

        function pt(idx, ratio) {
            var ang = (Math.PI * 2 * idx) / n - Math.PI / 2;
            return [cx + Math.cos(ang) * R * ratio, cy + Math.sin(ang) * R * ratio];
        }
        function poly(vals) {
            var arr = [];
            for (var i = 0; i < n; i++) {
                var v = (vals && vals[i]) ? Number(vals[i].value) : 0;
                var p = pt(i, Math.max(0.02, v / maxV));
                arr.push(p[0].toFixed(1) + ',' + p[1].toFixed(1));
            }
            return arr.join(' ');
        }

        var g = '';
        // 网格
        for (var r = 1; r <= 4; r++) {
            var ring = [];
            for (var i2 = 0; i2 < n; i2++) {
                var p2 = pt(i2, r / 4);
                ring.push(p2[0].toFixed(1) + ',' + p2[1].toFixed(1));
            }
            g += '<polygon points="' + ring.join(' ') + '" fill="none" stroke="var(--line)" stroke-width="1"/>';
        }
        // 轴线 + 标签
        for (var i3 = 0; i3 < n; i3++) {
            var pe = pt(i3, 1);
            g += '<line x1="' + cx + '" y1="' + cy + '" x2="' + pe[0].toFixed(1) + '" y2="' + pe[1].toFixed(1) +
                 '" stroke="var(--line)" stroke-width="1"/>';
            var lp = pt(i3, 1.22);
            var anchor = lp[0] < cx - 4 ? 'end' : (lp[0] > cx + 4 ? 'start' : 'middle');
            g += '<text x="' + lp[0].toFixed(1) + '" y="' + (lp[1] + 4).toFixed(1) +
                 '" text-anchor="' + anchor + '" font-size="11" fill="var(--text-dim)">' +
                 esc(String(labels[i3]).slice(0, 6)) + '</text>';
        }
        // 数据多边形
        for (var s2 = 0; s2 < series.length; s2++) {
            var sr = series[s2];
            if (!(sr.vals || []).length) continue;
            g += '<polygon points="' + poly(sr.vals) + '" fill="' + sr.color +
                 '" fill-opacity="0.16" stroke="' + sr.color + '" stroke-width="2"/>';
            for (var i4 = 0; i4 < (sr.vals || []).length; i4++) {
                var v2 = Number(sr.vals[i4].value) || 0;
                var pp = pt(i4, Math.max(0.02, v2 / maxV));
                g += '<circle cx="' + pp[0].toFixed(1) + '" cy="' + pp[1].toFixed(1) +
                     '" r="3" fill="' + sr.color + '"/>';
            }
        }

        return '<svg viewBox="0 0 ' + size + ' ' + (size + 12) + '" width="100%" ' +
               'style="max-width:' + size + 'px;overflow:visible;">' + g + '</svg>';
    }

    function valsOf(comp) {
        var out = [];
        var sc = comp.scoring || [];
        for (var i = 0; i < sc.length; i++) {
            var it = sc[i];
            var label = '', value = 0;
            if (Array.isArray(it)) { label = it[0]; value = it[1]; }
            else if (it && typeof it === 'object') { label = it.name; value = it.weight; }
            out.push({ label: String(label || ''), value: Number(value) || 0 });
        }
        return out;
    }

    function optionsHTML(comps, sel) {
        var h = '';
        for (var i = 0; i < comps.length; i++) {
            var nm = comps[i].name;
            h += '<option value="' + esc(nm) + '"' + (nm === sel ? ' selected' : '') + '>' + esc(nm) + '</option>';
        }
        return h;
    }

    function findComp(comps, name) {
        for (var i = 0; i < comps.length; i++) if (comps[i].name === name) return comps[i];
        return null;
    }

    function render() {
        var box = document.getElementById('kbCompare');
        if (!box) return false;
        var comps = getComps();
        if (!comps.length) return false;   // 数据还没到，等下一轮重试

        var names = [];
        for (var i = 0; i < comps.length; i++) names.push(comps[i].name);

        var html = '';
        html += '<h3>赛事知识库速览'
            + '<span style="margin-left:10px;font-size:12px;font-weight:400;color:var(--text-dim);">'
            + '共 ' + comps.length + ' 个赛事 · 可任选两个对比</span></h3>';
        html += '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0;">';
        html += '<select id="kbSelA" style="padding:7px 10px;font-size:13px;border-radius:8px;'
            + 'border:1px solid var(--line);background:var(--surface-solid);color:var(--text);max-width:240px;">'
            + optionsHTML(comps, names[0]) + '</select>';
        html += '<span style="color:var(--text-dim);font-size:13px;">对比</span>';
        html += '<select id="kbSelB" style="padding:7px 10px;font-size:13px;border-radius:8px;'
            + 'border:1px solid var(--line);background:var(--surface-solid);color:var(--text);max-width:240px;">'
            + '<option value="">（不对比）</option>' + optionsHTML(comps, names[1] || '') + '</select>';
        html += '</div>';
        html += '<div id="kbBody"></div>';

        box.innerHTML = html;

        function paint() {
            var a = findComp(comps, (document.getElementById('kbSelA') || {}).value);
            var bv = (document.getElementById('kbSelB') || {}).value;
            var b = bv ? findComp(comps, bv) : null;
            var body = document.getElementById('kbBody');
            if (!body || !a) return;

            var series = [{ name: a.name, color: A_COLOR, vals: valsOf(a) }];
            if (b) series.push({ name: b.name, color: B_COLOR, vals: valsOf(b) });

            var h = '';
            // 图例
            h += '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;margin-bottom:6px;">';
            h += '<span><i style="display:inline-block;width:10px;height:10px;background:' + A_COLOR +
                 ';border-radius:2px;margin-right:5px;"></i>' + esc(a.name) + '</span>';
            if (b) {
                h += '<span><i style="display:inline-block;width:10px;height:10px;background:' + B_COLOR +
                     ';border-radius:2px;margin-right:5px;"></i>' + esc(b.name) + '</span>';
            }
            h += '</div>';

            h += '<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;">';
            h += '<div style="flex:0 0 auto;">' + radarSVG(series, 300) + '</div>';

            h += '<div style="flex:1 1 320px;min-width:280px;">';
            for (var s = 0; s < series.length; s++) {
                var sr = series[s];
                var comp = (s === 0) ? a : b;
                h += '<div style="margin-bottom:12px;">';
                h += '<div style="font-size:13px;font-weight:700;margin-bottom:4px;">' + esc(sr.name) + '</div>';
                var vs = sr.vals;
                if (!vs.length) {
                    h += '<div style="font-size:12.5px;color:var(--text-dim);">暂无评分维度数据</div>';
                } else {
                    h += '<div style="font-size:12.5px;line-height:1.9;">';
                    for (var k = 0; k < vs.length; k++) {
                        h += '<span style="display:inline-block;margin-right:12px;">' + esc(vs[k].label) +
                             ' <b style="color:' + sr.color + ';">' + vs[k].value + '</b></span>';
                    }
                    h += '</div>';
                }
                var chs = comp.chapters || [];
                h += '<div style="font-size:12.5px;color:var(--text-dim);margin-top:6px;">章节要求（' +
                     chs.length + ' 章）</div>';
                h += '<div style="font-size:12.5px;line-height:1.8;">';
                if (!chs.length) h += '<span style="color:var(--text-dim);">（该赛事未列出章节）</span>';
                for (var c = 0; c < chs.length && c < 14; c++) {
                    h += '<div>' + esc(String(chs[c])) + '</div>';
                }
                if (chs.length > 14) h += '<div style="color:var(--text-dim);">…等共 ' + chs.length + ' 章</div>';
                h += '</div></div>';
            }
            h += '</div></div>';

            h += '<div style="margin-top:10px;font-size:12px;color:var(--text-dim);line-height:1.7;">'
               + '数据源：官方赛事档案' + (comps[0].src === 'profiles' ? '（competition_profiles）' : '（内置规则）')
               + '，只读展示，不参与生成。雷达刻度按各维度权重绘制。</div>';

            body.innerHTML = h;
        }

        var sa = document.getElementById('kbSelA');
        var sb = document.getElementById('kbSelB');
        if (sa) sa.addEventListener('change', paint);
        if (sb) sb.addEventListener('change', paint);
        paint();
        return true;
    }

    // profiles 是异步加载的，一次抓不到就重试
    var tries = 0, timer = null;
    function boot() {
        tries++;
        // 先取官方 profiles（15 赛事），拿到后再渲染；拿不到就用内置规则先渲染出来
        loadProfiles(function () {
            var ok = false;
            try { ok = render(); } catch (e) {}
            if (!ok && tries < 15) timer = setTimeout(boot, 500);
            else if (timer) { clearTimeout(timer); timer = null; }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
