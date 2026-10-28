/* 科创赛事助手 · 主题 token 系统（第三百四十四轮）
   ------------------------------------------------------------------
   目标：主题不再是「换一张背景图」，而是一整套视觉 token。
   每个预设 × 日间/夜间 各有一套完整配色，落地方式是改写全站 CSS 变量，
   因此卡片 / 表单 / 弹窗 / 导航 / 正文 / 图表全部跟着换，而不是只换最外层背景。

   只依赖：window（不依赖 app.js 的任何内部函数，加载顺序早晚都能自愈）。
   对外：window.WB_THEME
     .presets()                -> 8 个预设（含 id/name/hint）
     .tokens(id, mode)         -> 该预设该模式的完整 token 表
     .current() / .mode()      -> 当前 id / 'light'|'dark'
     .apply(id, mode)          -> 立即换肤
     .setMode(mode)            -> 切日/夜（复用站内 wbToggleTheme）
     .cssVars(id, mode)        -> CSS 变量名 -> 值 的映射表
     .contrast(fg, bg)         -> WCAG 对比度（供自检/联调）
     .pptStyle(key) / .pptStyles()
     .tone(key) / .tones()
     .onChange(fn)
   兼容：旧预设 id（aurora/nebula/ocean/lava/ember/ink/cyber/forest/plain…）映射到新 id，
   老用户 localStorage 里的选择不会失效。 */
(function () {
    'use strict';

    var KEY = 'wb_theme_v1';
    var LEGACY_BG_KEY = 'wb_bg_cfg_v1';

    /* ---------- 小工具 ---------- */
    function hex2rgb(h) {
        h = String(h || '').trim().replace('#', '');
        if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        var n = parseInt(h, 16);
        if (isNaN(n)) return [0, 0, 0];
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    function rgba(rgbStr, a) {
        var c = String(rgbStr || '0,0,0').split(',');
        return 'rgba(' + (c[0] || 0) + ',' + (c[1] || 0) + ',' + (c[2] || 0) + ',' + a + ')';
    }
    function lum(hex) {
        var c = hex2rgb(hex), i, v = [];
        for (i = 0; i < 3; i++) {
            var s = c[i] / 255;
            v.push(s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4));
        }
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
    }
    function toHex(o) {
        return '#' + o.map(function (x) { var s = Math.round(x).toString(16); return s.length < 2 ? '0' + s : s; }).join('');
    }
    function mix(hexA, hexB, a) {   // 半透明色压在实色底上的等效实色（审计坐标轴/提示框这类 rgba 色用）
        var A = hex2rgb(hexA), B = hex2rgb(hexB), o = [], i;
        for (i = 0; i < 3; i++) o.push(A[i] * a + B[i] * (1 - a));
        return toHex(o);
    }
    function mixRGB(rgbCsv, hexB, a) {   // 同上，但前景给的是 "r,g,b"
        var A = String(rgbCsv).split(',').map(Number), B = hex2rgb(hexB), o = [], i;
        for (i = 0; i < 3; i++) o.push((A[i] || 0) * a + B[i] * (1 - a));
        return toHex(o);
    }
    // WCAG 相对亮度对比度（1~21）
    function contrast(fg, bg) {
        var a = lum(fg), b = lum(bg);
        var hi = Math.max(a, b), lo = Math.min(a, b);
        return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
    }

    /* ---------- token 生成 ----------
       每个预设只给「骨架色」，其余（边框、柔光、提示底色、图表坐标系…）
       统一由 accent / lineRGB 推导，保证 8 套 × 2 模式的结构完全一致。 */
    function build(m) {
        var ar = hex2rgb(m.accent), ars = ar.join(',');
        var br = hex2rgb(m.accent2), brs = br.join(',');
        var lr = m.lineRGB;
        var dark = m.flavor === 'dark';
        var t = {};
        t.flavor = m.flavor;
        t.bg0 = m.bg0; t.bg1 = m.bg1; t.bg2 = m.bg2 || m.bg1;
        t.card = m.card; t.card2 = m.card2 || m.card;
        t.nav = m.nav || m.card;
        t.modal = m.modal || m.card;
        t.modalOverlay = m.modalOverlay || (dark ? 'rgba(2,5,16,.74)' : 'rgba(18,30,66,.52)');
        t.input = m.input || (dark ? m.card2 : '#ffffff');
        t.inputFocus = m.inputFocus || (dark ? m.card : rgba(ars, dark ? 0.16 : 0.08));
        t.text = m.text; t.textSub = m.textSub; t.textMute = m.textMute;
        t.link = m.link || m.accent;
        t.accent = m.accent; t.accent2 = m.accent2;
        t.accentRgb = ars; t.accent2Rgb = brs;
        t.accentSoft = rgba(ars, dark ? 0.18 : 0.12);
        t.btn = m.btn || m.accent; t.btnText = m.btnText || (dark ? '#08122b' : '#ffffff');
        t.btn2 = rgba(ars, dark ? 0.16 : 0.10);
        t.btn2Text = m.btn2Text || (dark ? m.text : m.accent);
        t.grad = 'linear-gradient(120deg,' + m.accent + ' 0%,' + m.accent2 + ' 100%)';
        t.gradSoft = 'linear-gradient(120deg,' + rgba(ars, dark ? 0.18 : 0.14) + ' 0%,' + rgba(brs, dark ? 0.18 : 0.14) + ' 100%)';
        t.track = rgba(ars, dark ? 0.20 : 0.16);
        t.border = rgba(lr, dark ? 0.26 : 0.20);
        t.borderStrong = rgba(lr, dark ? 0.48 : 0.38);
        t.soft1 = rgba(lr, dark ? 0.05 : 0.035);
        t.soft2 = rgba(lr, dark ? 0.09 : 0.06);
        t.soft3 = rgba(lr, dark ? 0.14 : 0.10);
        t.glow1 = m.glow1 || rgba(ars, dark ? 0.30 : 0.26);
        t.glow2 = m.glow2 || rgba(brs, dark ? 0.26 : 0.22);
        t.ok = m.ok; t.warn = m.warn; t.err = m.err; t.info = m.info || m.accent2;
        t.okBg = rgba(hex2rgb(m.ok).join(','), dark ? 0.16 : 0.10);
        t.warnBg = rgba(hex2rgb(m.warn).join(','), dark ? 0.16 : 0.12);
        t.errBg = rgba(hex2rgb(m.err).join(','), dark ? 0.16 : 0.10);
        t.infoBg1 = rgba(hex2rgb(t.info).join(','), dark ? 0.16 : 0.10);
        t.infoBg2 = rgba(hex2rgb(t.info).join(','), dark ? 0.07 : 0.05);
        t.okText = m.ok; t.warnText = m.warnText || m.warn; t.errText = m.errText || m.err;
        t.infoText = m.infoText || t.info;
        t.warnLine = rgba(hex2rgb(m.warn).join(','), dark ? 0.42 : 0.36);
        t.errLine = rgba(hex2rgb(m.err).join(','), dark ? 0.46 : 0.38);
        t.infoStrong = t.info;
        t.shadow = dark
            ? '0 16px 44px rgba(0,0,0,.46), inset 0 1px 0 ' + rgba('255,255,255', 0.06)
            : '0 12px 32px ' + rgba(lr, 0.12) + ', inset 0 1px 0 rgba(255,255,255,.6)';
        t.series = m.series;
        // 坐标轴/刻度线是「有意义图形」，WCAG 1.4.11 要求 ≥3:1，所以这里比分割线实得多
        t.axis = rgba(lr, dark ? 0.62 : 0.72);
        t.split = rgba(lr, dark ? 0.18 : 0.14);
        t.tipBg = dark ? rgba(hex2rgb(m.card).join(','), 0.98) : 'rgba(255,255,255,.98)';
        t.tipBgFlat = dark ? m.card : '#ffffff';                       // 审计用等效实色
        t.axisFlat = mixRGB(lr, m.card, dark ? 0.62 : 0.72);           // 坐标轴压在卡片上的等效实色
        t.tipText = m.text;
        t.tipLine = rgba(lr, dark ? 0.30 : 0.22);
        t.chartBgL = [rgba('255,255,255', dark ? 0.04 : 0.60), rgba('255,255,255', dark ? 0.02 : 0.74)];
        t.chartBgD = [rgba(hex2rgb(m.card).join(','), 0.55), rgba(hex2rgb(m.card2 || m.card).join(','), 0.72)];
        // 背景层（.wb-bg 内 #wbUserBg 那层）用的渐变：日间透明底 + 柔光，夜间实色底 + 光晕
        t.layerImg = dark
            ? 'radial-gradient(1100px 720px at 18% 18%,' + rgba(ars, 0.42) + ', transparent 62%),'
              + 'radial-gradient(980px 660px at 84% 22%,' + rgba(brs, 0.34) + ', transparent 64%),'
              + 'radial-gradient(1200px 800px at 55% 82%,' + rgba(ars, 0.24) + ', transparent 68%)'
            : 'radial-gradient(1100px 700px at 16% 14%,' + rgba(ars, 0.16) + ', transparent 62%),'
              + 'radial-gradient(900px 620px at 86% 20%,' + rgba(brs, 0.14) + ', transparent 64%),'
              + 'radial-gradient(1200px 760px at 50% 96%,' + rgba(ars, 0.10) + ', transparent 70%)';
        t.layerColor = dark ? m.bg0 : 'transparent';
        return t;
    }

    /* ---------- 8 个预设 × 日间/夜间 ----------
       命名向「科创赛事」靠：科技蓝 / 校园绿 / 学术墨 / 极光 / 深海 / 林雾 / 创投金 / 挑战红金。
       日间 3 套偏浅（科技蓝·校园绿·学术墨），夜间 8 套全部深色且色相各不相同。 */
    var RAW = {
        techblue: {
            name: '科技蓝', hint: '理性、工程感，默认推荐',
            alias: ['tech', 'plain', 'default'],
            light: { flavor: 'light', bg0: '#e2ecfb', bg1: '#f4f8ff', bg2: '#eaf1fd', card: '#fafdff', card2: '#f2f7fe',
                text: '#0d1b33', textSub: '#31456e', textMute: '#4d5f85',
                accent: '#1250c4', accent2: '#0e7490', lineRGB: '21,64,150',
                btn: '#1250c4', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#1250c4', '#0e7490', '#3f6ad8', '#2f8f7a', '#7c8fd6', '#0f7a45', '#b45309'] },
            dark: { flavor: 'dark', bg0: '#060c1d', bg1: '#0b1533', bg2: '#101c44', card: '#111c3c', card2: '#17244c',
                text: '#e9eefc', textSub: '#b8c6e8', textMute: '#94a4c9',
                accent: '#5b9bff', accent2: '#2dd4bf', lineRGB: '150,185,245',
                btn: '#5b9bff', btnText: '#08122b', ok: '#3ddc97', warn: '#fbbf24', err: '#ff8a80',
                series: ['#5b9bff', '#2dd4bf', '#a78bfa', '#fbbf24', '#4ade80', '#f472b6', '#67e8f9'] }
        },
        campus: {
            name: '校园绿', hint: '清新、育人与成长',
            alias: ['green'],
            light: { flavor: 'light', bg0: '#e4f4e9', bg1: '#f5fbf7', bg2: '#ecf8f0', card: '#fbfefb', card2: '#f0f9f4',
                text: '#0e2418', textSub: '#2f5540', textMute: '#4a6b55',
                accent: '#0d7a4b', accent2: '#15803d', lineRGB: '20,90,60',
                btn: '#0d7a4b', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#0d7a4b', '#15803d', '#4ba86a', '#0e7490', '#8bbd4f', '#b45309', '#6d8fd6'] },
            dark: { flavor: 'dark', bg0: '#05130d', bg1: '#0a2318', bg2: '#0e2e20', card: '#0e2a1e', card2: '#14382a',
                text: '#e6f5ec', textSub: '#b3d8c2', textMute: '#8fbc9f',
                accent: '#4ade80', accent2: '#34d399', lineRGB: '140,220,175',
                btn: '#4ade80', btnText: '#062013', ok: '#4ade80', warn: '#fbbf24', err: '#ff8a80',
                series: ['#4ade80', '#34d399', '#a3e635', '#22d3ee', '#fbbf24', '#f472b6', '#93c5fd'] }
        },
        scholar: {
            name: '学术墨', hint: '宣纸墨色，论文 / 申报书调性',
            alias: ['ink'],
            light: { flavor: 'light', bg0: '#f4f1e9', bg1: '#fbf9f4', bg2: '#f7f4ec', card: '#fffdf8', card2: '#f6f3ea',
                text: '#1a1a17', textSub: '#454440', textMute: '#5e5c53',
                accent: '#3d4a6b', accent2: '#6b5a3e', lineRGB: '60,58,50',
                btn: '#3d4a6b', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#3d4a6b', '#6b5a3e', '#5c6b8a', '#8a7a58', '#7b8aa8', '#4f7a5e', '#9a6b4f'] },
            dark: { flavor: 'dark', bg0: '#0b0d12', bg1: '#14171f', bg2: '#1b1f29', card: '#171a22', card2: '#1f232d',
                text: '#eceef3', textSub: '#bcc1cd', textMute: '#969ca9',
                accent: '#a9b6d6', accent2: '#c9b48c', lineRGB: '190,196,210',
                btn: '#a9b6d6', btnText: '#0b0d12', ok: '#7fd6a3', warn: '#f0c674', err: '#ff9b91',
                series: ['#a9b6d6', '#c9b48c', '#8fa0c6', '#d6c2a0', '#6f7f9f', '#7fd6a3', '#e0a97a'] }
        },
        aurora: {
            name: '极光', hint: '青紫流光，灵感与创意',
            alias: ['aurora'],
            light: { flavor: 'light', bg0: '#eceafb', bg1: '#f8f7ff', bg2: '#f1eefd', card: '#fcfbff', card2: '#f4f2fe',
                text: '#161338', textSub: '#3d3768', textMute: '#57517f',
                accent: '#5b4bd6', accent2: '#0e7490', lineRGB: '80,70,180',
                btn: '#5b4bd6', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#5b4bd6', '#0e7490', '#8b5cf6', '#22d3ee', '#c084fc', '#0f7a45', '#b45309'] },
            dark: { flavor: 'dark', bg0: '#070b18', bg1: '#0d1130', bg2: '#141a52', card: '#131338', card2: '#1b1a4a',
                text: '#eaecff', textSub: '#c0c2ee', textMute: '#9b9ecd',
                accent: '#7dd3fc', accent2: '#c084fc', lineRGB: '160,175,255',
                btn: '#7dd3fc', btnText: '#060a1a', ok: '#34d399', warn: '#fbbf24', err: '#ff8a80',
                series: ['#7dd3fc', '#c084fc', '#2dd4bf', '#fbbf24', '#f472b6', '#4ade80', '#a78bfa'] }
        },
        ocean: {
            name: '深海', hint: '沉静，数据与技术纵深',
            alias: ['nebula', 'deep'],
            light: { flavor: 'light', bg0: '#e0f3f8', bg1: '#f6fbfd', bg2: '#e9f7fa', card: '#f8fdff', card2: '#eff8fb',
                text: '#0c2733', textSub: '#2c5563', textMute: '#476b78',
                accent: '#0e7490', accent2: '#0f766e', lineRGB: '18,90,110',
                btn: '#0e7490', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#0e7490', '#0f766e', '#38bdf8', '#2f7d8f', '#7dd3fc', '#4f8f6e', '#b45309'] },
            dark: { flavor: 'dark', bg0: '#04121f', bg1: '#072434', bg2: '#0a3145', card: '#0a2233', card2: '#0f3145',
                text: '#e2f4f8', textSub: '#b0d6e2', textMute: '#8cb8c6',
                accent: '#22d3ee', accent2: '#38bdf8', lineRGB: '130,200,225',
                btn: '#22d3ee', btnText: '#04141c', ok: '#34d399', warn: '#fbbf24', err: '#ff8a80',
                series: ['#22d3ee', '#38bdf8', '#5eead4', '#818cf8', '#fbbf24', '#f472b6', '#4ade80'] }
        },
        forest: {
            name: '林雾', hint: '生态、乡村振兴赛道',
            alias: ['forest', 'moss'],
            light: { flavor: 'light', bg0: '#eef1e4', bg1: '#fafbf5', bg2: '#f2f5ea', card: '#fffdf6', card2: '#f5f7ea',
                text: '#18200f', textSub: '#45503a', textMute: '#5e6a52',
                accent: '#4d7c0f', accent2: '#0e7490', lineRGB: '80,95,55',
                btn: '#4d7c0f', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#4d7c0f', '#0e7490', '#84a94a', '#5f8f6e', '#a3b86a', '#b45309', '#6d8fd6'] },
            dark: { flavor: 'dark', bg0: '#0a1109', bg1: '#101a12', bg2: '#162318', card: '#142015', card2: '#1b2d1e',
                text: '#e6f0e0', textSub: '#b6cdad', textMute: '#93ab8b',
                accent: '#86c34a', accent2: '#4ade80', lineRGB: '170,205,150',
                btn: '#86c34a', btnText: '#0a1408', ok: '#86c34a', warn: '#fbbf24', err: '#ff8a80',
                series: ['#86c34a', '#4ade80', '#d9f99d', '#22d3ee', '#fbbf24', '#f472b6', '#a78bfa'] }
        },
        forge: {
            name: '创投金', hint: '路演、商业计划书的暖金质感',
            alias: ['lava', 'ember'],
            light: { flavor: 'light', bg0: '#f8f0e1', bg1: '#fdf9f2', bg2: '#faf3e7', card: '#fffdf8', card2: '#f8f2e7',
                text: '#241a0f', textSub: '#54442f', textMute: '#6d5c45',
                accent: '#9a5b12', accent2: '#b45309', lineRGB: '120,85,35',
                btn: '#9a5b12', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#9a5b12', '#b45309', '#d1a054', '#7c6b3f', '#e0b473', '#0f7a45', '#6d8fd6'] },
            dark: { flavor: 'dark', bg0: '#120d07', bg1: '#1e1710', bg2: '#2a2016', card: '#241b12', card2: '#31251a',
                text: '#f6ecdd', textSub: '#d7c4a6', textMute: '#b39e80',
                accent: '#f0b45f', accent2: '#fbbf24', lineRGB: '225,190,140',
                btn: '#f0b45f', btnText: '#1a1207', ok: '#7fd6a3', warn: '#fbbf24', err: '#ff9b91',
                series: ['#f0b45f', '#fbbf24', '#e8a33d', '#d6c2a0', '#a3e635', '#22d3ee', '#f472b6'] }
        },
        challenge: {
            name: '挑战红金', hint: '挑战杯配色，答辩现场的气势',
            alias: ['cyber', 'redgold'],
            light: { flavor: 'light', bg0: '#fbe9e7', bg1: '#fff7f6', bg2: '#fdeeeb', card: '#fffaf9', card2: '#fbf0ee',
                text: '#26141a', textSub: '#57323c', textMute: '#6f4b54',
                accent: '#b3222b', accent2: '#a1791f', lineRGB: '150,60,70',
                btn: '#b3222b', btnText: '#ffffff', ok: '#0f7a45', warn: '#8a4f04', err: '#a01b14',
                series: ['#b3222b', '#a1791f', '#d9616a', '#c9a227', '#8c2f38', '#0f7a45', '#6d8fd6'] },
            dark: { flavor: 'dark', bg0: '#150a0f', bg1: '#24111a', bg2: '#331823', card: '#2a121b', card2: '#3a1a26',
                text: '#fdeaee', textSub: '#e0b9c1', textMute: '#c0949e',
                accent: '#ff7a88', accent2: '#e8c46a', lineRGB: '235,170,180',
                btn: '#ff7a88', btnText: '#1a0a10', ok: '#7fd6a3', warn: '#fbbf24', err: '#ff9b91',
                series: ['#ff7a88', '#e8c46a', '#ffb3ba', '#d6a24a', '#a78bfa', '#22d3ee', '#4ade80'] }
        }
    };

    // 稳定顺序（面板里按此顺序展示：前面 3 个是浅色系）
    var ORDER = ['techblue', 'campus', 'scholar', 'aurora', 'ocean', 'forest', 'forge', 'challenge'];

    var TOK = {};
    ORDER.forEach(function (id) {
        TOK[id] = { light: build(RAW[id].light), dark: build(RAW[id].dark) };
    });

    // 旧 id / 旧名 -> 新 id（老用户 localStorage 里的值不会失效）
    var ALIAS = {};
    ORDER.forEach(function (id) {
        ALIAS[id] = id;
        (RAW[id].alias || []).forEach(function (a) { ALIAS[String(a).toLowerCase()] = id; });
    });
    ALIAS['纯净'] = 'techblue'; ALIAS['水墨'] = 'scholar'; ALIAS['熔岩'] = 'forge'; ALIAS['赛博'] = 'challenge';
    ALIAS['星云'] = 'ocean'; ALIAS['林雾'] = 'forest'; ALIAS['极光'] = 'aurora'; ALIAS['深海'] = 'ocean';
    ALIAS[''] = 'techblue'; ALIAS['null'] = 'techblue'; ALIAS['undefined'] = 'techblue';

    function normId(id) {
        if (!id) return 'techblue';
        var k = String(id).toLowerCase();
        return ALIAS[k] || ALIAS[id] || 'techblue';
    }

    /* ---------- token -> CSS 变量 ----------
       左边是既有 CSS 正在用的变量名（style.css / wbbtn-*.css / wbsmart.css… 全站都在读），
       右边是给并行 CSS 线用的语义名（--wb-*）。两条路一起喂，谁读都能读到当前主题值。 */
    var VAR_MAP = [
        ['bg0', ['--bg-0', '--wb-bg']],
        ['bg1', ['--bg-1', '--wb-bg-2']],
        ['bg2', ['--wb-bg-3']],
        ['card', ['--surface-solid', '--wb-card']],
        ['card2', ['--wb-card-2']],
        ['nav', ['--wb-nav']],
        ['modal', ['--wb-modal']],
        ['modalOverlay', ['--wb-modal-overlay']],
        ['input', ['--wb-input']],
        ['inputFocus', ['--wb-input-focus']],
        ['text', ['--text', '--wb-text']],
        ['textSub', ['--text-soft', '--text-dim', '--wb-text-sub']],
        ['textMute', ['--text-mute', '--wb-text-mute']],
        ['link', ['--wb-link']],
        ['accent', ['--c-a', '--wb-accent', '--wb-btn']],
        ['accent2', ['--c-b', '--wb-accent-2']],
        ['accentRgb', ['--c-a-rgb', '--wb-accent-rgb']],
        ['accent2Rgb', ['--c-b-rgb', '--wb-accent-2-rgb']],
        ['accentSoft', ['--c-a-soft', '--wb-accent-soft']],
        ['btn', ['--wb-btn']],
        ['btnText', ['--wb-btn-text']],
        ['btn2', ['--btn-ghost', '--wb-btn-2']],
        ['btn2Text', ['--wb-btn-2-text']],
        ['grad', ['--grad', '--wb-grad']],
        ['gradSoft', ['--grad-soft', '--wb-grad-soft']],
        ['track', ['--track', '--wb-track']],
        ['border', ['--line', '--wb-border']],
        ['borderStrong', ['--line-strong', '--wb-border-strong']],
        ['soft1', ['--surface', '--wb-surface']],
        ['soft2', ['--surface-2', '--wb-surface-2']],
        ['soft3', ['--surface-3', '--wb-surface-3']],
        ['glow1', ['--wb-glow-1']],
        ['glow2', ['--wb-glow-2']],
        ['ok', ['--ok', '--wb-ok']],
        ['warn', ['--wb-warn']],
        ['err', ['--wb-err']],
        ['info', ['--info', '--wb-info']],
        ['infoStrong', ['--info-strong']],
        ['infoText', ['--info-text', '--wb-info-text']],
        ['infoBg1', ['--info-bg-1', '--wb-info-bg']],
        ['infoBg2', ['--info-bg-2']],
        ['warnText', ['--warn-text', '--wb-warn-text']],
        ['warnBg', ['--warn-bg', '--wb-warn-bg']],
        ['warnLine', ['--warn-line']],
        ['errText', ['--err-text', '--wb-err-text']],
        ['errBg', ['--err-bg', '--wb-err-bg']],
        ['errLine', ['--err-line']],
        ['shadow', ['--wb-shadow']],
        ['axis', ['--wb-chart-axis']],
        ['split', ['--wb-chart-split']],
        ['tipBg', ['--wb-chart-tip-bg']],
        ['tipText', ['--wb-chart-tip-text']],
        ['tipLine', ['--wb-chart-tip-line']]
    ];

    function tokens(id, mode) {
        return TOK[normId(id)][mode === 'light' ? 'light' : 'dark'];
    }

    function cssVars(id, mode) {
        var t = tokens(id, mode), out = {}, k;
        VAR_MAP.forEach(function (p) {
            var v = t[p[0]];
            if (v == null) return;
            p[1].forEach(function (n) { out[n] = v; });
        });
        for (var i = 0; i < 7; i++) out['--wb-chart-' + (i + 1)] = t.series[i];
        out['--wb-series'] = t.series.join(',');
        return out;
    }

    function presets() {
        return ORDER.map(function (id) {
            return { id: id, name: RAW[id].name, hint: RAW[id].hint, light: TOK[id].light, dark: TOK[id].dark };
        });
    }

    /* ---------- 读写持久化 ---------- */
    function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
    function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

    function readSaved() {
        var s = {};
        try { s = JSON.parse(load(KEY) || '{}') || {}; } catch (e) { s = {}; }
        var bg = {};
        try { bg = JSON.parse(load(LEGACY_BG_KEY) || '{}') || {}; } catch (e) { bg = {}; }
        var id = normId(s.preset || (bg.src === 'user' ? 'techblue' : bg.src));
        return { preset: id, mode: s.mode || '' };
    }

    function mode() {
        var b = document.body;
        return (b && b.classList.contains('light')) ? 'light' : 'dark';
    }

    var _cur = 'techblue', _mode = 'dark', _cbs = [];

    /* ---------- 落地：把 token 写成 CSS 变量 ---------- */
    function paint(id, m) {
        var t = tokens(id, m), v = cssVars(id, m), n;
        var roots = [document.documentElement];
        if (document.body) roots.push(document.body);   // body 上也要写一遍：body.light 那套类选择器优先级高于 :root
        for (var r = 0; r < roots.length; r++) {
            for (n in v) { if (Object.prototype.hasOwnProperty.call(v, n)) roots[r].style.setProperty(n, v[n]); }
        }
        if (document.body) {
            document.body.classList.add('wb-theme-on');
            document.body.classList.toggle('wb-t-light', m === 'light');
            document.body.classList.toggle('wb-t-dark', m === 'dark');
            document.body.setAttribute('data-wb-theme', id);
            document.body.setAttribute('data-wb-mode', m);
        }
        // 图表（echarts）用的一套色：改成当前主题的系列色 + 坐标轴 / 提示框
        try {
            var CT = window.WB_CHART_THEMES, k2;
            if (CT) {
                for (k2 in CT) {
                    if (!Object.prototype.hasOwnProperty.call(CT, k2)) continue;
                    var o = CT[k2];
                    o.series = t.series.slice();
                    o.bar = [t.series[0], t.series[1]];
                    o.line = t.accent;
                    o.area = rgba(t.accentRgb, m === 'dark' ? 0.22 : 0.18);
                    o.text = m === 'dark' ? t.textSub : t.text;
                    o.axis = t.axis;
                    o.split = t.split;
                    o.tip = [t.tipBg, t.tipLine, t.tipText];
                    o.bgL = t.chartBgL.slice();
                    o.bgD = t.chartBgD.slice();
                }
            }
        } catch (e) {}
        // 背景面板的色卡：让旧渲染器（app.js 的 wbBgRenderSwatches）也拿到当前模式的渐变
        try {
            var arr = window.WB_BG_PRESETS;
            if (arr && arr.length) {
                for (var i = 0; i < arr.length; i++) {
                    var p = arr[i], pid = normId(p.id);
                    if (!TOK[pid]) continue;
                    var pt = TOK[pid][m];
                    p.img = pt.layerImg;
                    p.color = pt.layerColor;
                }
            }
        } catch (e) {}
        /* 背景层本体也要同步重画：app.js 的 wbBgApply 用的是「上一次 paint 时」的 p.img，
           于是切主题/切日夜时背景会慢一拍（选了 A 显示的是上一个的颜色）。
           这里按当前 token 直接落一次，保证「色卡看到什么 → 页面就是什么」。 */
        try {
            var bcfg = {};
            try { bcfg = JSON.parse(load(LEGACY_BG_KEY) || '{}') || {}; } catch (e) { bcfg = {}; }
            var L = document.getElementById('wbUserBg');
            // 用户上传了自己的图：不碰，交给 app.js
            if (L && bcfg.src !== 'user') {
                L.style.backgroundImage = t.layerImg;
                L.style.backgroundColor = t.layerColor;
                var dim = (typeof bcfg.dim === 'number') ? bcfg.dim : 0.45;
                L.style.filter = (m === 'light') ? 'none' : 'brightness(' + (1 - dim * 0.45).toFixed(2) + ')';
                // 没选任何预设（「恢复默认背景」）时保持隐藏，但内容同步成当前主题，
                // 免得哪天重新显示出来是上一个主题的旧渐变
                L.style.opacity = bcfg.src ? '1' : '0';
            }
        } catch (e) {}
        _cur = normId(id); _mode = m;
        store(KEY, JSON.stringify({ preset: _cur, mode: m }));
        // 同步旧键，别让 app.js 的启动恢复把自己那套 src 又写回去
        try {
            var bg2 = {};
            try { bg2 = JSON.parse(load(LEGACY_BG_KEY) || '{}') || {}; } catch (e) { bg2 = {}; }
            if (bg2.src !== 'user') bg2.src = _cur;
            store(LEGACY_BG_KEY, JSON.stringify(bg2));
        } catch (e) {}
        for (var c = 0; c < _cbs.length; c++) { try { _cbs[c](_cur, m, t); } catch (e) {} }
        try {
            document.dispatchEvent(new CustomEvent('wbthemechange', { detail: { preset: _cur, mode: m, tokens: t } }));
        } catch (e) {}
    }

    function apply(id, m) {
        paint(normId(id), m || mode());
        try { if (typeof window.wbBgRenderSwatches === 'function') window.wbBgRenderSwatches(); } catch (e) {}
        return _cur;
    }

    function setMode(m) {
        m = (m === 'light') ? 'light' : 'dark';
        var isLight = !!(document.body && document.body.classList.contains('light'));
        if ((m === 'light') !== isLight) {
            // 站内已有切换逻辑（wbpage.js 的 wbToggleTheme），优先复用，避免两套状态打架
            if (typeof window.wbToggleTheme === 'function') { try { window.wbToggleTheme(); } catch (e) {} }
            else if (document.body) document.body.classList.toggle('light', m === 'light');
        }
        paint(_cur, m);
        try { if (typeof window.wbBgRenderSwatches === 'function') window.wbBgRenderSwatches(); } catch (e) {}
        return m;
    }

    /* ---------- 接管背景面板的选择动作 ----------
       app.js 的 wbBgPick 只改背景层；这里在它之后补一次全套 token 落地。 */
    function hook() {
        if (typeof window.wbBgPick !== 'function') return false;
        if (window.wbBgPick.__wbThemeHooked) return true;
        var origPick = window.wbBgPick, origReset = window.wbBgReset, origDim = window.wbBgSetDim;
        function wrapPick(id) {
            var r = origPick.apply(this, arguments);
            if (id && id !== 'user') apply(id, mode());
            else apply(_cur, mode());
            return r;
        }
        wrapPick.__wbThemeHooked = true;
        window.wbBgPick = wrapPick;
        if (typeof origReset === 'function') {
            window.wbBgReset = function () { var r = origReset.apply(this, arguments); apply(_cur, mode()); return r; };
        }
        if (typeof origDim === 'function') {
            window.wbBgSetDim = function () { var r = origDim.apply(this, arguments); apply(_cur, mode()); return r; };
        }
        return true;
    }

    /* ---------- 日/夜被别人切了也要跟着换（不假设是谁切的） ---------- */
    function observeMode() {
        if (!document.body || typeof MutationObserver === 'undefined') return;
        var mo = new MutationObserver(function () {
            var m = mode();
            if (m !== _mode) paint(_cur, m);
        });
        mo.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    /* ---------- PPT 12 种风格：名即效果（第三百四十八轮） ----------
       每种至少在「主色调 / 标题样式 / 图表配色 / 装饰纹理 / 版式骨架」中体现 2 项以上。 */
    var PPT = {
        starblue: { name: '星海蓝', primary: '#123a8a', secondary: '#2f6fd0', accent: '#7fb2ff',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 700, size: '40px', style: '深蓝粗衬线 + 下方渐变下划线', underline: 'linear-gradient(90deg,#123a8a,#7fb2ff)' },
            chart: ['#2f6fd0', '#7fb2ff', '#123a8a', '#5ad0e6', '#a5c8ff'], texture: '星点光斑 + 顶部深蓝渐隐', layout: '顶部标题条 + 左右 6:4 分栏', bg: '#0f2657', ink: '#ffffff' },
        techpurple: { name: '科技紫', primary: '#5b3cc4', secondary: '#8b5cf6', accent: '#c4b5fd',
            title: { font: '"Source Han Sans SC","Noto Sans SC",sans-serif', weight: 800, size: '38px', style: '无衬线超粗 + 紫色辉光描边', underline: 'none' },
            chart: ['#8b5cf6', '#c4b5fd', '#5b3cc4', '#22d3ee', '#f472b6'], texture: '霓虹边框 + 网格线', layout: '左上标题 + 右侧数据卡', bg: '#1a1040', ink: '#f2edff' },
        flatblue: { name: '扁平蓝', primary: '#1f6feb', secondary: '#4c9aff', accent: '#b3d4ff',
            title: { font: '"Source Han Sans SC","Noto Sans SC",sans-serif', weight: 700, size: '34px', style: '纯色块标题（无渐变无阴影）', underline: 'none' },
            chart: ['#1f6feb', '#4c9aff', '#7fc4ff', '#ffb020', '#34d399'], texture: '无纹理，纯色块 + 2px 描边', layout: '等分卡片网格（2×2 / 3×2）', bg: '#ffffff', ink: '#10243e' },
        bizgray: { name: '商务灰', primary: '#374151', secondary: '#6b7280', accent: '#9ca3af',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 600, size: '32px', style: '深灰衬线 + 左侧竖线', underline: 'none' },
            chart: ['#374151', '#6b7280', '#9ca3af', '#2563eb', '#f59e0b'], texture: '细分割线 + 页脚页码条', layout: '经典上下结构（标题区 + 内容区）', bg: '#f5f6f8', ink: '#1f2937' },
        vcgray: { name: '创投深灰', primary: '#111827', secondary: '#374151', accent: '#f0b45f',
            title: { font: '"Source Han Sans SC","Noto Sans SC",sans-serif', weight: 800, size: '42px', style: '大白字压深底 + 金色短横线', underline: 'linear-gradient(90deg,#f0b45f,transparent)' },
            chart: ['#f0b45f', '#9ca3af', '#e5e7eb', '#374151', '#fbbf24'], texture: '暗角渐变 + 金色描边', layout: '整版大标题 + 三栏数据条', bg: '#0b0f16', ink: '#f3f4f6' },
        researchbw: { name: '科研蓝白', primary: '#0e4f8a', secondary: '#3b82c4', accent: '#e8f1fa',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 700, size: '32px', style: '蓝色衬线 + 细双线', underline: '1px dashed #0e4f8a' },
            chart: ['#0e4f8a', '#3b82c4', '#7fb2e0', '#c8dcf0', '#1f7a5c'], texture: '极简无底纹，留白大', layout: '学术两栏（左文右图表）', bg: '#ffffff', ink: '#16212e' },
        modelwhite: { name: '建模白底', primary: '#1f2937', secondary: '#3b82f6', accent: '#93c5fd',
            title: { font: '"Source Han Sans SC","Noto Sans SC",sans-serif', weight: 700, size: '30px', style: '编号式标题（圆点徽标）', underline: 'none' },
            chart: ['#3b82f6', '#93c5fd', '#1f2937', '#10b981', '#f59e0b'], texture: '公式框 + 浅灰网格底', layout: '建模五段式（摘要-假设-模型-求解-检验）', bg: '#ffffff', ink: '#111827' },
        defense: { name: '学术答辩', primary: '#1e3a5f', secondary: '#2f5d8c', accent: '#d8e3f0',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 700, size: '34px', style: '居中粗衬线 + 上下细线夹住', underline: 'none' },
            chart: ['#1e3a5f', '#2f5d8c', '#7ba7d0', '#c9d8e8', '#b45309'], texture: '页眉页脚校徽位 + 页码', layout: '居中对称版式', bg: '#fbfcfd', ink: '#18293d' },
        mistblue: { name: '雾霭蓝灰', primary: '#4a5d6e', secondary: '#7d94a8', accent: '#cfdae4',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 500, size: '34px', style: '细体大字 + 字距拉开', underline: 'none' },
            chart: ['#4a5d6e', '#7d94a8', '#cfdae4', '#8fa8bb', '#d9a86c'], texture: '雾面柔光 + 低对比渐隐', layout: '大留白居中 + 悬浮卡片', bg: '#eef2f5', ink: '#2b3a47' },
        claypink: { name: '陶土藕粉', primary: '#a4655c', secondary: '#d3a094', accent: '#f3e3de',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 600, size: '34px', style: '圆角标题块 + 藕粉底', underline: 'none' },
            chart: ['#a4655c', '#d3a094', '#f3e3de', '#7f8f6f', '#c9853f'], texture: '陶土颗粒噪点 + 圆角卡片', layout: '圆角卡片流（上下错落）', bg: '#fdf7f5', ink: '#3a2a28' },
        challengegold: { name: '挑战杯红金', primary: '#b3222b', secondary: '#d9616a', accent: '#e8c46a',
            title: { font: '"Source Han Sans SC","Noto Sans SC",sans-serif', weight: 800, size: '40px', style: '红色粗体 + 金色分隔线', underline: 'linear-gradient(90deg,#b3222b,#e8c46a)' },
            chart: ['#b3222b', '#e8c46a', '#d9616a', '#8c2f38', '#f0d9a0'], texture: '金色细边框 + 红色色带', layout: '顶部红色标题带 + 下部双栏', bg: '#ffffff', ink: '#241015' },
        blackgold: { name: '黑金', primary: '#0b0b0d', secondary: '#1c1c21', accent: '#f0c674',
            title: { font: '"Source Han Serif SC","Noto Serif SC",serif', weight: 700, size: '40px', style: '金色衬线大字压纯黑底', underline: 'linear-gradient(90deg,#f0c674,transparent)' },
            chart: ['#f0c674', '#d4a94a', '#8a6d2f', '#e8e2d0', '#b98f3c'], texture: '黑底拉丝 + 金色描边角标', layout: '整版居中 + 底部金色细线', bg: '#0b0b0d', ink: '#f5efe2' }
    };
    var PPT_ORDER = ['starblue', 'techpurple', 'flatblue', 'bizgray', 'vcgray', 'researchbw',
        'modelwhite', 'defense', 'mistblue', 'claypink', 'challengegold', 'blackgold'];

    /* ---------- 文风档位：名即效果 ---------- */
    var TONES = {
        rigorous: { name: '严谨学术', titleLen: '长标题（含方法 / 对象）', sentence: '复合长句，术语优先', bullet: '编号条目，每条带数据出处', emoji: 0, termLevel: '高（专业术语 + 英文缩写）', hedge: '据…显示 / 在…条件下' },
        concise: { name: '简洁商务', titleLen: '短标题（≤12 字）', sentence: '短句为主，一句一信息', bullet: '短语并列，去修饰', emoji: 0, termLevel: '中（术语首次出现给白话解释）', hedge: '直接给结论' },
        pitch: { name: '激昂路演', titleLen: '金句式标题（带动词）', sentence: '短促句 + 排比', bullet: '三连短句冲击', emoji: 1, termLevel: '低（类比优先）', hedge: '少用限定词' },
        plain: { name: '平实叙述', titleLen: '陈述式标题', sentence: '中等长度，口语但规范', bullet: '完整句子，不堆词', emoji: 0, termLevel: '低（先说人话再补术语）', hedge: '按实际情况' }
    };
    var TONE_ORDER = ['rigorous', 'concise', 'pitch', 'plain'];

    /* ---------- 对外 ---------- */
    var API = {
        version: '344',
        presets: presets,
        tokens: tokens,
        cssVars: cssVars,
        current: function () { return _cur; },
        mode: mode,
        apply: apply,
        setMode: setMode,
        toggleMode: function () { return setMode(mode() === 'light' ? 'dark' : 'light'); },
        contrast: contrast,
        hex2rgb: hex2rgb,
        pptStyle: function (k) { return PPT[k] || null; },
        pptStyles: function () { return PPT_ORDER.map(function (k) { var o = PPT[k]; o.key = k; return o; }); },
        tone: function (k) { return TONES[k] || null; },
        tones: function () { return TONE_ORDER.map(function (k) { var o = TONES[k]; o.key = k; return o; }); },
        onChange: function (fn) { if (typeof fn === 'function') _cbs.push(fn); },
        // 自检：返回当前主题各关键配对的对比度（正文 / 次要文字 / 按钮）
        audit: function (id, m) {
            var t = tokens(id || _cur, m || _mode);
            return {
                text_on_card: contrast(t.text, t.card),
                sub_on_card: contrast(t.textSub, t.card),
                mute_on_card: contrast(t.textMute, t.card),
                text_on_bg: contrast(t.text, t.bg1),
                btn_text_on_btn: contrast(t.btnText, t.btn),
                link_on_card: contrast(t.link, t.card),
                accent_on_card: contrast(t.accent, t.card),
                tip_text_on_tip: contrast(t.tipText, t.tipBgFlat),
                axis_on_card: contrast(t.axisFlat, t.card)
            };
        }
    };
    window.WB_THEME = API;

    /* ---------- 启动 ---------- */
    function init() {
        if (!document.body) { setTimeout(init, 30); return; }
        var s = readSaved();
        _cur = s.preset;
        _mode = s.mode || mode();
        paint(_cur, _mode);
        hook();
        observeMode();
        try { if (typeof window.wbBgRenderSwatches === 'function') window.wbBgRenderSwatches(); } catch (e) {}
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
    // 兜底：万一 wbBgPick 比我晚挂上（脚本顺序调整），再试几次
    var tries = 0;
    var tmr = setInterval(function () {
        tries++;
        if (hook() || tries > 40) clearInterval(tmr);
    }, 150);
})();

/* ==================================================================
 * 402-3 全局对比度开关（追加的独立 IIFE，不改动上方任何主题逻辑）
 * 背景：三档变量已由 static/style.css 定义（html.contrast-high /
 *       html.contrast-max，夜间与日间都已覆盖），但此前没有任何脚本
 *       去切换这两个类 —— 等于「有样式、没开关」，用户根本用不到。
 * 这里补上开关：选择写入 localStorage，刷新后保持；
 * 位置运行时贴着 #themeToggle 自适应排布，不写死坐标避免重叠。
 * ================================================================== */
(function () {
    'use strict';
    var KEY = 'wb_contrast_level';
    var ID = 'wbContrast344';

    function apply(level) {
        try {
            var lv = (level === 'high' || level === 'max') ? level : 'normal';
            var h = document.documentElement;
            h.classList.remove('contrast-high', 'contrast-max');
            if (lv !== 'normal') h.classList.add('contrast-' + lv);
            try { localStorage.setItem(KEY, lv); } catch (e) {}
            var sel = document.getElementById(ID);
            if (sel && sel.value !== lv) sel.value = lv;
        } catch (e) {}
    }

    function place(el) {
        var top = 16, left = 66;
        var t = document.getElementById('themeToggle');
        if (t) {
            try {
                var r = t.getBoundingClientRect();
                if (r && r.width) { top = Math.round(r.top); left = Math.round(r.right + 10); }
            } catch (e) {}
        }
        el.style.top = top + 'px';
        el.style.left = left + 'px';
    }

    function build() {
        if (document.getElementById(ID)) return null;
        var sel = document.createElement('select');
        sel.id = ID;
        sel.className = 'wb-contrast344';
        sel.setAttribute('aria-label', '全局对比度');
        sel.title = '全局对比度：投屏或户外可拉高';
        sel.innerHTML = '<option value="normal">对比度 标准</option>'
            + '<option value="high">对比度 高</option>'
            + '<option value="max">对比度 最高</option>';
        sel.addEventListener('change', function () { apply(sel.value); });
        document.body.appendChild(sel);
        place(sel);
        window.addEventListener('resize', function () { place(sel); });
        return sel;
    }

    function init() {
        try { build(); } catch (e) {}
        var lv = 'normal';
        try { lv = localStorage.getItem(KEY) || 'normal'; } catch (e) {}
        apply(lv);
    }

    window.wbContrastApply = apply;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { setTimeout(init, 60); });
    } else { setTimeout(init, 60); }
})();
