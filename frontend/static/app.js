

        /* ---------- 带超时的 fetch（2026-09-30 加） ----------
           背景：上传 / 主题列表 / 赛事索引等请求原先没有超时，网络慢或隧道抖动时
           按钮永久转圈、UI 卡在"加载中"，用户只能刷新。统一走 _wbFetch：
           - 默认 30s 超时（大文件上传放宽到 120s）
           - 超时后抛错走原有 catch 分支，提示"网络超时，请重试"
           - AbortController 不存在时（极老浏览器）退化为普通 fetch，不影响功能 */
        function _wbFetch(url, opt, timeoutMs) {
            opt = opt || {};
            var ms = timeoutMs || 30000;
            if (typeof AbortController !== 'function') return fetch(url, opt);
            var ctl = new AbortController();
            var merged = {};
            for (var k in opt) merged[k] = opt[k];
            merged.signal = ctl.signal;
            var timer = setTimeout(function () { ctl.abort(); }, ms);
            return fetch(url, merged).then(
                function (r) { clearTimeout(timer); return r; },
                function (e) { clearTimeout(timer); throw e; }
            );
        }

        /* ---------- 本机存储降级（2026-09-28 移动端实测） ----------
           iOS Safari / 微信 / QQ 内核会拦掉本机存储，控制台报
           "Tracking Prevention blocked access to storage"，此时 localStorage 读写直接抛异常。
           后果不只是草稿丢：引导状态记不住（每次进页面都重新弹遮罩，还会吃掉顶栏点击）、
           历史页因为 uid 对不上查不到自己的记录。
           统一包一层：localStorage → sessionStorage → 内存。写不进 localStorage 时打标记，
           页面给一次明确提示，功能继续走，不静默失效。 */
        var _wbMemStore = {};
        var _wbStoreBlocked = false;
        function _wbStoreGet(k) {
            try { var v = localStorage.getItem(k); if (v !== null && v !== undefined) return v; } catch (e) {}
            try { var s2 = sessionStorage.getItem(k); if (s2 !== null && s2 !== undefined) return s2; } catch (e) {}
            return Object.prototype.hasOwnProperty.call(_wbMemStore, k) ? _wbMemStore[k] : null;
        }
        function _wbStoreSet(k, v) {
            var ok = false;
            try { localStorage.setItem(k, v); ok = true; } catch (e) {}
            try { sessionStorage.setItem(k, v); } catch (e) {}
            try { _wbMemStore[k] = v; } catch (e) {}
            if (!ok) _wbStoreBlocked = true;
            return ok;
        }
        function _wbStoreDel(k) {
            try { localStorage.removeItem(k); } catch (e) {}
            try { sessionStorage.removeItem(k); } catch (e) {}
            try { delete _wbMemStore[k]; } catch (e) {}
        }
        // 敏感内容专用：只写 sessionStorage（关掉标签页即清除），绝不落 localStorage。
        // 共用电脑 / 换浏览器打开时，不会把上一个人的创意、学校、导师自动铺到表单里。
        var _wbSessMem = {};
        function _wbSessGet(k) {
            try { var v = sessionStorage.getItem(k); if (v !== null && v !== undefined) return v; } catch (e) {}
            return Object.prototype.hasOwnProperty.call(_wbSessMem, k) ? _wbSessMem[k] : null;
        }
        function _wbSessSet(k, v) {
            var ok = false;
            try { sessionStorage.setItem(k, v); ok = true; } catch (e) {}
            try { _wbSessMem[k] = v; } catch (e) {}
            return ok;
        }
        function _wbSessDel(k) {
            try { sessionStorage.removeItem(k); } catch (e) {}
            try { delete _wbSessMem[k]; } catch (e) {}
        }

        // 1×1 透明 GIF：img 的 src 为空时浏览器会把它解析成当前页面 URL 再发一次请求，
        // 白扔一个请求还附带一条资源错误（message 是 undefined、无 stack，极难定位）。
        // 凡是有可能拿不到 url 的 img，一律用这个占位，不要写 src=""。
        var WB_BLANK_IMG = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

        function wbStoreProbe() {
            try {
                localStorage.setItem('__wb_probe__', '1');
                localStorage.removeItem('__wb_probe__');
                return true;
            } catch (e) {
                _wbStoreBlocked = true;
                return false;
            }
        }

        // 手机端上传兼容
        // 微信内置浏览器的 file 选择器只给「图片 / 视频」，选不到 PDF / Word（微信自身限制，改不了），
        // 所以：微信里直接把上传按钮废掉并给明确指引，避免用户反复踩坑；普通手机浏览器展开说明。
        var WB_IN_APP = false;
        (function () {
            var ua = navigator.userAgent || '';
            WB_IN_APP = /MicroMessenger|QQ\//i.test(ua);
            if (WB_IN_APP) { try { document.body.classList.add('in-app'); } catch (e) {} }
            var box = document.getElementById('mobileUploadTip');
            if (box && /iPhone|iPad|iPod|Android|Mobile/i.test(ua)) {
                box.style.display = 'block';
                if (WB_IN_APP) {
                    box.style.borderColor = 'var(--c-b)';
                    box.insertAdjacentHTML('afterbegin',
                        '<div style="color: var(--c-b); font-weight: 600; margin-bottom: 6px;">' +
                        '检测到你在微信/QQ 内置浏览器里，这里只能选到图片和视频。' +
                        '请点右上角 ··· → 用 Safari 打开。</div>');
                }
            }
            if (WB_IN_APP) {
                var banner = document.getElementById('wxBanner');
                if (banner) {
                    banner.style.display = 'block';
                    var lk = document.getElementById('wxLink');
                    if (lk) lk.textContent = location.href;
                }
                var btn = document.getElementById('btnUploadDraft');
                if (btn) {
                    btn.style.background = 'var(--surface-2)';
                    btn.style.color = 'var(--text-mute)';
                    btn.innerHTML = '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-upload"/></svg> 微信里无法上传文件';
                    btn.onclick = function () {
                        wbToast('微信内置浏览器只能选图片和视频', {
                            type: 'warn', ms: 4000,
                            sub: '请点右上角 ··· → 用 Safari 打开；或直接复制文字点「粘贴文本」'
                        });
                    };
                }
            }
        })();

        // 复制网址：方便粘到系统浏览器里打开（微信里读不到文件，只能换浏览器）
        function wbCopyLink() {
            var url = location.href;
            var okFn = function () { wbToast('网址已复制，粘到 Safari 里打开', { type: 'ok', ms: 3000 }); };
            var badFn = function (e) { wbToast('复制失败，请长按上面的网址手动复制', { type: 'error' }); };
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(url).then(okFn, function () { _fallbackCopy(url, okFn, badFn); });
                    return;
                }
            } catch (e) {}
            _fallbackCopy(url, okFn, badFn);
        }

        // 手机端最稳的上传路径：复制文本 → 粘贴（HTTPS 下 clipboard.readText 可用）
        async function wbPasteDraft() {
            var box = document.getElementById('proposal_draft');
            try {
                var txt = await navigator.clipboard.readText();
                if (!txt || !txt.trim()) {
                    wbToast('剪贴板是空的，请先长按复制文字', { type: 'error' });
                    return;
                }
                box.value = (box.value ? box.value + '\n\n' : '') + txt;
                window._wbDraftImported = true;   // 导入过草稿：意图明确，生成时不再弹通路选择
                wbToast('已粘贴 ' + txt.length + ' 字到草稿框，正在自动识别项目信息…');
                // 统一材料框架：粘贴草稿同样自动填充全部输入框
                if (window.wbDraftSmartFill) window.wbDraftSmartFill(txt, {});
            } catch (err) {
                box.focus();
                wbToast('浏览器不让读剪贴板，请在草稿框里长按选择「粘贴」', { type: 'error' });
            }
        }

        // 上传赛事官方文件：抽出的文本直接进 rule_content
        // 后端链路本来就通（app.py 收 rule_content → competition_agents 规则解析 → 写作），
        // 只是前端以前从不传，所以上传了也白传。这里把口子接上。
        document.getElementById('ruleFile').addEventListener('change', async function (e) {
            const file = e.target.files[0];
            if (!file) return;
            var info = document.getElementById('ruleDocInfo');
            if (info) info.textContent = '正在读取：' + file.name;
            try {
                const fd = new FormData();
                fd.append('file', file);
                const res = await _wbFetch('/api/upload_pdf', { method: 'POST', body: fd }, 120000);
                const d = await res.json();
                if (!d || !d.success) {
                    if (info) info.textContent = '读取失败：' + ((d && d.error) || '未知错误');
                    wbToast('读取失败：' + ((d && d.error) || '未知错误'), { type: 'error' });
                    return;
                }
                var txt = String(d.text || '').trim();
                if (!txt) {
                    if (info) info.textContent = '文件里没读到文字（扫描版 PDF 读不出），请换文字版或把要点粘到创意框';
                    wbToast('没读到文字：扫描版 PDF 需要 OCR，请换文字版', { type: 'warn' });
                    return;
                }
                var box = document.getElementById('rules');
                if (box) box.value = txt;
                if (info) {
                    info.innerHTML = '已载入《' + _esc(file.name) + '》· <b style="color: var(--c-a);">' +
                        txt.length + ' 字</b>，生成时会按它的评分标准与章节要求来写';
                }
                var pv = document.getElementById('ruleDocPreview');
                if (pv) {
                    pv.textContent = txt.slice(0, 500) + (txt.length > 500 ? '\n…（预览只显示前 500 字）' : '');
                    pv.style.display = 'block';
                }
                wbToast('已载入赛事规则 ' + txt.length + ' 字，生成会按它来', { type: 'ok', ms: 3000 });
            } catch (err) {
                if (info) info.textContent = '读取失败：连不上服务';
                wbToast('读取失败：连不上服务', { type: 'error' });
            }
        });

        function clearRuleDoc() {
            var box = document.getElementById('rules');
            if (box) box.value = '';
            var pv = document.getElementById('ruleDocPreview');
            if (pv) { pv.textContent = ''; pv.style.display = 'none'; }
            var info = document.getElementById('ruleDocInfo');
            if (info) info.textContent = '未上传。上传官方文件后，将按其评分维度与章节要求生成。';
            wbToast('已清除赛事规则', { type: 'ok' });
        }

        // ============ 实测数据「上传数据文件」+ 智能识别路由（Codex 待办 P0-1）============
        // 后端 /api/upload_file 解析文本后用 LLM 判断 file_type（赛事规则|申报书草稿|实测数据|参考文献|其他），
        // 前端把识别结果摆出来，让用户一键确认路由——不自动写入，避免误覆盖已填内容。
        async function wbUdHandleFile(file) {
            if (!file) return;
            var info = document.getElementById('udFileInfo');
            var ext = (String(file.name).match(/\.[^.]+$/) || [''])[0].toLowerCase();
            if (['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'].indexOf(ext) >= 0) {
                wbToast('图片暂不识别：请导出为 PDF 或文字后再上传', { type: 'warn', ms: 3600 });
                return;
            }
            if (ext === '.doc') {
                wbToast('旧版 .doc 读不了：请在 Word 里「另存为 .docx」再上传', { type: 'warn', ms: 4200 });
                return;
            }
            if (info) { info.style.display = 'block'; info.textContent = '正在识别：' + file.name + ' …'; }
            var d = null;
            try {
                const fd = new FormData();
                fd.append('file', file);
                fd.append('purpose', 'user_data');
                const res = await _wbFetch('/api/upload_file', { method: 'POST', body: fd }, 120000);
                d = await res.json();
            } catch (err) {
                if (info) info.textContent = '识别失败：连不上服务，请稍后重试';
                wbToast('识别失败：连不上服务', { type: 'error' });
                return;
            }
            if (!d || !d.success) {
                var em = (d && d.error) || '未知错误';
                if (info) info.textContent = '识别失败：' + em;
                wbToast('识别失败：' + em, { type: 'error' });
                return;
            }
            var text = String(d.text || '').trim();
            if (!text) {
                if (info) info.textContent = '文件里没读到文字（扫描版读不出），请换文字版或直接把要点粘到上面';
                wbToast('没读到文字：请换文字版文件', { type: 'warn' });
                return;
            }
            wbUdShowRoute(info, file.name, d, text);
        }

        document.getElementById('udFile').addEventListener('change', function (e) {
            var f = e.target.files[0];
            e.target.value = '';   // 清空，允许重复选同一个文件
            if (f) wbUdHandleFile(f);
        });

        // 拖拽上传：拖到佐证区就能接住。只在 .wb-drop 上接管 drag/drop，
        // 页面其它地方保持浏览器默认行为，不会误把文件拖成导航跳转
        (function () {
            var z = document.getElementById('udDrop');
            if (!z) return;
            ['dragenter', 'dragover'].forEach(function (ev) {
                z.addEventListener(ev, function (e) {
                    e.preventDefault(); e.stopPropagation(); z.classList.add('is-over');
                });
            });
            z.addEventListener('dragleave', function (e) {
                e.preventDefault(); e.stopPropagation();
                try { if (z.contains(e.relatedTarget)) return; } catch (err) {}
                z.classList.remove('is-over');
            });
            z.addEventListener('drop', function (e) {
                e.preventDefault(); e.stopPropagation();
                z.classList.remove('is-over');
                var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
                if (f) wbUdHandleFile(f);
            });
            // 键盘可达：聚焦后回车/空格等同点击
            z.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    document.getElementById('udFile').click();
                }
            });
        })();

        // 识别结果卡：类型 + 摘要 + 关键点 + 按类型给出一键路由（第一个按钮是推荐项）
        function wbUdShowRoute(info, fname, d, text) {
            var t = String(d.file_type || '其他');
            var kps = (d.key_points || []).slice(0, 3);
            var routes;
            if (t === '申报书草稿') {
                routes = [{ key: 'draft', label: '填到申报书草稿' }, { key: 'user_data', label: '合并进实测数据' }];
            } else if (t === '赛事规则') {
                routes = [{ key: 'builtin', label: '规则已内置，无需上传（推荐）' }, { key: 'rule', label: '仍要作为官方文件补充' }];
            } else {   // 实测数据 / 参考文献 / 其他 → 默认都进「其它佐证」
                routes = [{ key: 'user_data', label: '合并进实测数据' }, { key: 'draft', label: '填到申报书草稿' }];
            }
            info.innerHTML = '<div style="padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface-2);">'
                + '<div>已识别为 <b style="color: var(--c-a);">' + _esc(t) + '</b>'
                + (d.summary ? '：' + _esc(d.summary) : '')
                + ' <span style="color: var(--text-mute);">（' + _esc(fname) + ' · ' + text.length + ' 字）</span></div>'
                + (kps.length ? '<div style="margin-top: 6px; color: var(--text-dim);">关键点：' + kps.map(function (k) { return _esc(k); }).join('；') + '</div>' : '')
                + '<div style="display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap;">'
                + routes.map(function (r, i) {
                    return '<button type="button" onclick="wbUdApplyRoute(\'' + r.key + '\')" style="padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; '
                        + (i === 0 ? 'background: var(--c-a); color: #fff; border: none;'
                                   : 'background: var(--surface-solid); color: var(--text-dim); border: 1px solid var(--line);') + '">'
                        + r.label + '</button>';
                }).join('')
                + '</div></div>';
            window._wbUdPending = { text: text, fname: fname };
        }

        // 用户确认后的落地动作（结果卡里的按钮是字符串拼的 onclick，显式挂 window 最稳）
        window.wbUdApplyRoute = function (key) {
            var p = window._wbUdPending;
            var info = document.getElementById('udFileInfo');
            if (!p) { if (info) info.style.display = 'none'; return; }
            var destLabel = { rule: '官方文件', draft: '申报书草稿', user_data: '实测数据' };
            if (key === 'builtin') {
                if (info) info.innerHTML = '好的，规则已内置，本次文件不使用。可继续上传其它文件。';
                window._wbUdPending = null;
                return;
            }
            if (key === 'rule') {
                var box = document.getElementById('rules');
                if (box) box.value = p.text;
                wbToast('已作为官方文件载入，生成时会按它的要求来写', { type: 'ok' });
            } else if (key === 'draft') {
                var dr = document.getElementById('proposal_draft');
                if (dr) {
                    dr.value = dr.value.trim() ? dr.value.trim() + '\n\n' + p.text : p.text;
                    dr.dispatchEvent(new Event('change'));
                }
                window._wbDraftImported = true;   // 导入过草稿：意图明确，生成时不再弹通路选择
                wbToast('已填入申报书草稿框（追加，不覆盖已有内容），正在自动识别项目信息…');
                // 统一材料框架：路由到草稿后，其余字段（创意/团队/实测数据分格/关键词）自动填充
                if (window.wbDraftSmartFill) window.wbDraftSmartFill(p.text, {});
            } else {
                var ex = document.getElementById('udExtra');
                if (ex) {
                    var add = '【上传文件：' + p.fname + '】\n' + p.text;
                    ex.value = ex.value.trim() ? ex.value.trim() + '\n\n' + add : add;
                    ex.dispatchEvent(new Event('change'));
                }
                wbToast('已合并进实测数据·其它佐证，正在自动识别试点/样本/指标/成本…');
                // 统一材料框架：只填实测数据四个分格 + 基本信息，不覆盖刚合并进「其它佐证」的原文
                if (window.wbDraftSmartFill) window.wbDraftSmartFill(p.text, {
                    onlyFields: ['competition_name', 'idea', 'team',
                                 'user_data_site', 'user_data_scale',
                                 'user_data_metric', 'user_data_cost', 'keywords']
                });
            }
            if (info) info.innerHTML = '已完成：《' + _esc(p.fname) + '》→ ' + (destLabel[key] || '实测数据') + '。可继续上传其它文件。';
            window._wbUdPending = null;
            wbSaveForm();
        };

        // 导入模板：上传官方/学校的模板文件 → 自动识别章节 → 填进赛事要求卡
        // 复用 /api/upload_pdf 抽文本，前端用正则抽标题，不用新增后端接口
        document.getElementById('tplFile').addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            var tip = document.getElementById('ideaFileName');
            if (tip) tip.innerText = '正在识别模板章节：' + file.name;
            try {
                const fd = new FormData();
                fd.append('file', file);
                const res = await _wbFetch('/api/upload_pdf', { method: 'POST', body: fd }, 120000);
                const d = await res.json();
                if (!d || !d.success) {
                    if (tip) tip.innerText = '模板识别失败：' + ((d && d.error) || '未知错误');
                    wbToast('模板识别失败：' + ((d && d.error) || '未知错误'), { type: 'error' });
                    return;
                }
                var lines = String(d.text || '').split('\n');
                var pats = [/^\s*第?[一二三四五六七八九十]+[章节][、.\s]*.{1,40}$/,
                            /^\s*[一二三四五六七八九十]+、.{1,40}$/,
                            /^\s*（[一二三四五六七八九十]+）.{1,40}$/,
                            /^\s*\d+[、.]\s*.{1,40}$/];
                var secs = [];
                lines.forEach(function (ln) {
                    var t = String(ln).trim();
                    if (!t || t.length > 46) return;
                    for (var i = 0; i < pats.length; i++) {
                        if (pats[i].test(t)) { secs.push(t); break; }
                    }
                });
                if (!secs.length) {
                    if (tip) tip.innerText = '没从模板里认出章节标题，请先确认模板里有「一、xxx」这类标题';
                    wbToast('没认出章节标题，模板里需要有「一、项目概述」这类编号标题', { type: 'warn' });
                    return;
                }
                var c = evCurrent();
                c.sections = secs.slice(0, 20);
                try { _wbStoreSet(c.key, JSON.stringify({ sections: c.sections })); } catch (err) {}
                renderEventCard();
                var card = document.getElementById('eventReqCard');
                if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (tip) tip.innerText = '已按《' + file.name + '》识别 ' + c.sections.length + ' 个章节';
                wbToast('已导入 ' + c.sections.length + ' 个章节，生成会按模板结构写（可在要求卡里改）', { type: 'ok', ms: 3600 });
            } catch (err) {
                if (tip) tip.innerText = '模板识别失败：连不上服务';
                wbToast('模板识别失败：连不上服务', { type: 'error' });
            }
        });

        document.getElementById('ideaFile').addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            // 前端先拦一道：手机容易误选到照片/视频，服务端也会拒，这里给更清楚的提示
            var _n = (file.name || '').toLowerCase();
            if (/\.(jpe?g|png|heic|gif|mp4|mov|avi|webp)$/.test(_n)) {
                document.getElementById('ideaFileName').innerText =
                    '选中的是图片/视频，暂时读不出文字：请在 Safari 里选「浏览」→ 文件 App 里的 PDF/Word，或直接粘贴文本';
                wbToast('不支持图片/视频，请选 PDF / Word / TXT，或用「粘贴文本」', { type: 'error' });
                return;
            }
            // 留住原始文件对象：只有 .docx 才能走「保留原格式只替换内容」的导出
            window._draftFile = file;
            wbRefreshKeepCard();
            document.getElementById('ideaFileName').innerText = '正在上传：' + file.name;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await _wbFetch('/api/upload_pdf', { method: 'POST', body: formData }, 120000);
                const data = await res.json();
                if (data.success) {
                    window._wbDraftImported = true;   // 导入过草稿：意图明确，生成时不再弹通路选择
                    document.getElementById('proposal_draft').value = data.text;
                    // 注意用 innerHTML：innerText 会把 SVG 图标当纯文本显示出来
                    document.getElementById('ideaFileName').innerHTML = '<svg class="wb-ico wb-ico-ok" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-check"/></svg> 上传成功，已填入草稿框，正在自动识别项目信息…';
                    // 统一材料框架：导入草稿 → 一次解析自动填充创意/团队/实测数据/关键词等全部输入框
                    if (window.wbDraftSmartFill) {
                        window.wbDraftSmartFill(data.text, {
                            onDone: function () {
                                document.getElementById('ideaFileName').innerHTML = '<svg class="wb-ico wb-ico-ok" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-check"/></svg> 导入完成：草稿已填入，项目信息已自动填充到各输入框，请核对';
                            },
                            onFail: function (m) {
                                document.getElementById('ideaFileName').innerText = '草稿已填入；' + m + '，可点「从材料识别」重试';
                            }
                        });
                    }
                } else {
                    document.getElementById('ideaFileName').innerText = '上传失败：' + (data.error || '未知错误');
                    wbToast('上传失败：' + (data.error || '未知错误'), { type: 'error' });
                }
            } catch (err) {
                document.getElementById('ideaFileName').innerText = '上传失败：连不上服务';
                wbToast('上传失败：网络连接异常，请稍后刷新重试', { type: 'error' });
            }
        });

        // DOM id -> 生成结果里的字段名（隐藏 tab 的 innerText 会是空串，必须走原始数据）
        var _DOM_TO_KEY = {
            parsedRules: 'parsed_rules', similarityReport: 'similarity_report',
            proposalText: 'proposal', proposalAnalysis: 'proposal_analysis',
            judgeFeedback: 'judge_feedback', competitorAnalysis: 'competitor_analysis',
            businessModel: 'business_model', riskAnalysis: 'risk_analysis',
            techSolution: 'tech_solution', defenseQuestions: 'defense_questions',
            pptOutline: 'ppt_outline',
            // 实施计划：zip 里早就有 12_实施计划.docx，但导出中心一直没有单文件入口
            implementationPlan: 'implementation_plan'
        };
        // ===== 封面信息 / 原格式导出（WorkBuddy）=====
        // 各导出项对应的文档档位：default=申报书 report=报告 analysis=分析 outline=大纲
        var _DOC_TYPE = {
            parsedRules: 'report', similarityReport: 'report', proposalText: 'default',
            proposalAnalysis: 'analysis', judgeFeedback: 'analysis',
            competitorAnalysis: 'analysis', businessModel: 'analysis',
            riskAnalysis: 'analysis', defenseQuestions: 'analysis', pptOutline: 'outline',
            techSolution: 'analysis', implementationPlan: 'analysis'
        };
        function wbMeta() {
            return {
                school: (document.getElementById('wbSchool') || {}).value || '',
                team: (document.getElementById('wbTeam') || {}).value || '',
                advisor: (document.getElementById('wbAdvisor') || {}).value || ''
            };
        }
        // 学校 / 团队 / 指导老师同样属于敏感信息（双盲赛事尤其），只存 sessionStorage
        function wbSaveMeta() {
            try { _wbSessSet('wbDocMeta', JSON.stringify(wbMeta())); } catch (e) {}
            // 旧版本存在 localStorage 里的那份就地清掉
            try { localStorage.removeItem('wbDocMeta'); } catch (e) {}
        }
        function wbLoadMeta() {
            try {
                var m = JSON.parse(_wbSessGet('wbDocMeta') || '{}');
                if (m.school) document.getElementById('wbSchool').value = m.school;
                if (m.team) document.getElementById('wbTeam').value = m.team;
                if (m.advisor) document.getElementById('wbAdvisor').value = m.advisor;
            } catch (e) {}
            try { localStorage.removeItem('wbDocMeta'); } catch (e) {}
        }
        // 只有上传过 .docx 原文件时才显示「原格式导出」卡片（PDF/图片/文本没有版式可保留）
        function wbRefreshKeepCard() {
            var card = document.getElementById('wbKeepCard');
            if (!card) return;
            var f = window._draftFile;
            if (f && /\.docx$/i.test(f.name)) {
                document.getElementById('wbKeepName').textContent = f.name;
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        }
        async function exportOptimized() {
            var f = window._draftFile;
            if (!f) { wbToast('没有上传过的原文件', { type: 'warn' }); return; }
            var text = _txt('proposal', 'proposalText');
            if (!text.trim()) { wbToast('还没有优化后的申报书内容，请先生成', { type: 'warn' }); return; }
            var radio = document.querySelector('input[name=wbKeepMode]:checked');
            var mode = (radio && radio.value) || 'keep';
            var m = wbMeta();
            var fd = new FormData();
            fd.append('original_file', f);
            fd.append('optimized_text', text);
            fd.append('mode', mode);
            fd.append('title', '项目' + WB_DOC_LABEL);
            fd.append('school', m.school);
            fd.append('team', m.team);
            fd.append('advisor', m.advisor);
            var btn = (window.event && window.event.target) || null;
            if (btn) { btn.disabled = true; btn.dataset.old = btn.innerHTML; btn.innerHTML = '导出中...'; }
            try {
                var r = await wbExportFetch('/api/export_original_format', fd);
                if (!r.ok) { await wbExportError('原格式申报书', r); return; }
                var res = r.res;
                var blob = await res.blob();
                wbSaveBlob(blob, (mode === 'reformat' ? '申报书_标准排版.docx' : '优化后的申报书.docx'));
                wbToast('已开始下载', { type: 'ok', ms: 2600 });
            } catch (e) {
                wbToast('导出失败：' + (e && e.message ? e.message : e), { type: 'error' });
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        wbLoadMeta();
        wbRefreshKeepCard();

        /* ---------- 表单自动保存：刷新 / 关掉再打开不丢 ---------- */
        var WB_FORM_KEY = 'wbFormDraft';        // 中性：赛事 / 档位 / 勾选项，可跨会话记住
        var WB_FORM_S_KEY = 'wbFormDraftSens';  // 敏感：只活在当前标签页
        // 中性字段：换设备、换浏览器、别人打开同一台电脑都不会造成信息外泄
        var WB_FORM_SAFE = ['competition'];
        // 敏感字段：项目创意、申报书草稿、自填实测数据——一律不落盘到本地长期存储
        var WB_FORM_SENSITIVE = ['idea', 'proposal_draft', 'keywords',
            'udTeam', 'udSite', 'udScale', 'udMetric', 'udCost', 'udExtra'];
        // 兼容旧引用（清空表单、字数统计等地方都用 WB_FORM_IDS 遍历）
        var WB_FORM_IDS = WB_FORM_SAFE.concat(WB_FORM_SENSITIVE);
        // 勾选项要单独走 checked：混进 WB_FORM_IDS 的话 el.value 恒为 "on"，恢复时会被当成永远勾上
        var WB_CHECK_IDS = ['iterateOpt'];

        var WB_SAVE_OFF = false;   // 清空表单期间抑制自动保存，否则刚删又被写回
        function wbSaveForm() {
            if (WB_SAVE_OFF) return;
            try {
                var safe = { _t: Date.now() }, sens = { _t: Date.now() }, sensHit = 0;
                WB_FORM_SAFE.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el) safe[id] = el.value;
                });
                WB_FORM_SENSITIVE.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (!el) return;
                    sens[id] = el.value;
                    if (String(el.value || '').trim()) sensHit++;
                });
                WB_CHECK_IDS.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el) safe[id] = !!el.checked;
                });
                var r = document.querySelector('input[name=mode]:checked');
                if (r) safe.mode = r.value;
                // 中性字段照旧长期保存；敏感字段只写 sessionStorage，没有内容时连键一起删掉
                _wbStoreSet(WB_FORM_KEY, JSON.stringify(safe));
                if (sensHit) _wbSessSet(WB_FORM_S_KEY, JSON.stringify(sens));
                else _wbSessDel(WB_FORM_S_KEY);
            } catch (e) {}
        }

        // 清空是不可逆的（会连本机草稿一起删），按钮又挪到了显眼位置，必须二次确认
        function wbClearFormAsk() {
            var n = 0;
            try {
                WB_FORM_IDS.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el && String(el.value || '').trim()) n++;
                });
            } catch (e) {}
            var msg = n > 0
                ? '确定清空已填写的 ' + n + ' 项内容？本机草稿也会一起删除，无法恢复。'
                : '确定清空表单并删除本机草稿？';
            if (!window.confirm(msg)) return;
            wbClearForm();
        }

        function wbClearForm() {
            WB_SAVE_OFF = true;   // 清空过程中触发的 change 不要再存一次
            try { _wbStoreDel(WB_FORM_KEY); } catch (e) {}
            try { _wbSessDel(WB_FORM_S_KEY); } catch (e) {}
            WB_FORM_IDS.forEach(function (id) {
                var el = document.getElementById(id);
                if (el) { el.value = ''; el.dispatchEvent(new Event('change')); }
            });
            WB_CHECK_IDS.forEach(function (id) {
                var el = document.getElementById(id);
                if (el) { el.checked = false; el.dispatchEvent(new Event('change')); }
            });
            WB_SAVE_OFF = false;
            var box = document.getElementById('wbRestoreTip');
            if (box) box.style.display = 'none';
            wbToast('已清空表单和本地草稿', { type: 'ok', ms: 2200 });
        }

        // 排查用的「运行日志」页签默认隐藏，URL 带 ?debug=1 才露出来（普通用户不需要，少一个 tab 少一分乱）
        (function () {
            try {
                if (/[?&]debug=1/.test(location.search)) {
                    var t = document.getElementById('logsTab');
                    if (t) t.style.display = '';
                }
            } catch (e) {}
        })();

        // 文风选项只在深度版露出：简洁版不显示，避免用户选了却不起作用（后端也只在深度版处理）
        function wbSyncHumanizeRow() {
            var row = document.getElementById('humanizeRow');
            if (!row) return;
            var m = document.querySelector('input[name=mode]:checked');
            row.style.display = (m && m.value === 'deep') ? 'block' : 'none';
        }

        // 简洁版专属的「低分自动补写」开关：只在选简洁版时露出。
        // 注意：#iterateRow 在 HTML 里初始就是 display:none，所以这里必须显式写 'block'/'none'，
        // 写 '' 会回落到内联的 none，永远不显示（这个坑已经踩过两次）。
        function wbSyncIterateRow() {
            var row = document.getElementById('iterateRow');
            if (!row) return;
            var m = document.querySelector('input[name=mode]:checked');
            row.style.display = (m && m.value === 'fast') ? 'block' : 'none';
        }

        // 今日额度已不在前端展示（用户拍板：数字是全站剩余、不是个人维度，
        // 显眼了反而让用户困惑，也把运营盘子亮给评委）。
        // 后端 /api/quota 接口保留不动，后台运维仍可查。

        // 旧版本把敏感字段也写进了 localStorage：升级后第一件事就是把它们从本地长期存储里抹掉。
        // 独立成一段、放在恢复之前，避免依赖后面的分支是否跑到。
        var _wbPurgedSafe = null;
        function _wbPurgeLegacySensitive() {
            try {
                var raw = localStorage.getItem(WB_FORM_KEY);
                if (!raw) return;
                var o = JSON.parse(raw);
                if (!o || typeof o !== 'object') return;
                var dirty = false, keep = {};
                Object.keys(o).forEach(function (k) {
                    if (WB_FORM_SENSITIVE.indexOf(k) >= 0) { dirty = true; return; }
                    keep[k] = o[k];
                });
                if (dirty) {
                    // 整键删掉、再由 wbSaveForm 按新规则重写一份「只含中性字段」的。
                    // 不做就地改写：改写一旦因为任何原因没落盘，敏感内容就还留在磁盘上
                    _wbPurgedSafe = keep;
                    try { localStorage.removeItem(WB_FORM_KEY); } catch (e2) {}
                    try { sessionStorage.removeItem(WB_FORM_KEY); } catch (e2) {}
                    try { delete _wbMemStore[WB_FORM_KEY]; } catch (e2) {}
                }
            } catch (e) {}
        }

        function wbLoadForm() {
            _wbPurgeLegacySensitive();
            var d = null, ds = null;
            try { d = JSON.parse(_wbStoreGet(WB_FORM_KEY) || 'null'); } catch (e) {}
            try { ds = JSON.parse(_wbSessGet(WB_FORM_S_KEY) || 'null'); } catch (e) {}
            if (!d && !ds) return;
            d = d || {};
            ds = ds || {};
            var safeHit = 0, sensHit = 0;
            // 中性字段：跨会话保留
            WB_FORM_SAFE.forEach(function (id) {
                var el = document.getElementById(id);
                if (el && d[id]) { el.value = d[id]; safeHit++; }
            });
            // 敏感字段：只在同一标签页内恢复（刷新不丢，关掉标签页即清除）
            WB_FORM_SENSITIVE.forEach(function (id) {
                var el = document.getElementById(id);
                if (el && ds[id]) { el.value = ds[id]; sensHit++; }
            });
            WB_CHECK_IDS.forEach(function (id) {
                var el = document.getElementById(id);
                if (el && typeof d[id] === 'boolean') { el.checked = d[id]; }
            });
            // 旧版本把敏感字段也写进了 localStorage：这里就地清掉历史遗留，别留着
            try {
                var dirty = false;
                WB_FORM_SENSITIVE.forEach(function (id) {
                    if (Object.prototype.hasOwnProperty.call(d, id)) { delete d[id]; dirty = true; }
                });
                if (dirty) _wbStoreSet(WB_FORM_KEY, JSON.stringify(d));
            } catch (e) {}
            if (d.mode) {
                var r = document.querySelector('input[name=mode][value="' + d.mode + '"]');
                // 用 click 而不是只改 checked：内联 onclick 还要同步卡片高亮样式
                if (r && !r.checked) r.click();
            }
            if (!safeHit && !sensHit) return;
            try { onCompetitionChange(); } catch (e) {}
            var box = document.getElementById('wbRestoreTip');
            if (box) {
                var tx = document.getElementById('wbRestoreText');
                // 提示里不再出现具体时间：那等于把「你什么时候在这台电脑上写过东西」也告诉了下一个人
                var msg = safeHit && sensHit
                    ? '已恢复上次选择的赛事与档位，本页草稿也还在（关闭标签页后自动清除）'
                    : (safeHit ? '已恢复上次选择的赛事与档位'
                               : '已恢复本页上次填写的草稿（关闭标签页后自动清除）');
                if (tx) tx.textContent = msg;
                box.style.display = 'flex';
            }
        }

        // 输入即存（防抖 400ms），切档位/选赛事立即存
        (function () {
            var t = null;
            var ids = WB_FORM_IDS.concat(['wbSchool', 'wbTeam', 'wbAdvisor']);
            ids.forEach(function (id) {
                var el = document.getElementById(id);
                if (!el) return;
                // 167 轮：400ms 防抖意味着连打一个长句要序列化二三十次（每次都要遍历全表单 + 写 localStorage），
                // 手机上这是实打实的耗电项。改 1s；失焦时再补存一次，内容不会丢。
                el.addEventListener('input', function () { clearTimeout(t); t = setTimeout(wbSaveForm, 1000); });
                el.addEventListener('change', wbSaveForm);
                el.addEventListener('blur', wbSaveForm);
            });
            var radios = document.querySelectorAll('input[name=mode]');
            for (var i = 0; i < radios.length; i++) {
                radios[i].addEventListener('change', wbSaveForm);
                radios[i].addEventListener('change', wbSyncHumanizeRow);
                radios[i].addEventListener('change', wbSyncIterateRow);
            }
            wbSyncHumanizeRow();
            wbSyncIterateRow();
            WB_CHECK_IDS.forEach(function (id) {
                var el = document.getElementById(id);
                if (el) el.addEventListener('change', wbSaveForm);
            });
        })();
        wbLoadForm();
        // 赛事名改成输入框后没有默认值了，这里补回默认（原来 select 默认第一项就是 iCAN），
        // 并顺带把「赛事要求卡」渲染出来
        (function () {
            var el = document.getElementById('competition');
            if (el && !String(el.value || '').trim()) {
                el.value = 'iCAN大学生创新创业大赛';
                try { wbSaveForm(); } catch (e) {}
            }
            try { onCompetitionChange(); } catch (e) {}
        })();
        // 存储被拦时明确说一次：否则「历史是空的」「草稿刷新就没了」对用户全是黑盒
        (function () {
            try {
                if (wbStoreProbe()) return;
                setTimeout(function () {
                    try {
                        wbToast('浏览器限制了本机存储（Tracking Prevention）：草稿与历史只在本次会话保留，'
                            + '换普通浏览器或关掉无痕模式可长期保存', { type: 'warn', ms: 5600 });
                    } catch (e) {}
                }, 1600);
            } catch (e) {}
        })();
        // 首次进入才做交互引导（箭头指向 + 一句话，点一下就走），走完写 localStorage，之后不再出现。
        // 首屏那三步卡片是常驻的，不算打扰；完整说明按需点右上角「这是什么 / 使用说明」。
        (function () {
            var done = false;
            try { done = _wbStoreGet('wbCoachDone') === '1'; } catch (e) {}
            if (!done) { try { done = document.cookie.indexOf('wbCoachDone=1') >= 0; } catch (e) {} }
            if (done) return;
            setTimeout(function () { try { coachStart(); } catch (e) {} }, 900);
        })();
        // 三步引导卡片的打勾状态与折叠（做过的步骤自动打勾，全做完收成一行）
        (function () {
            // 166 轮排查挖出来的真 bug：#wbUaMask 在 index.html 里排在 app.js 之后（1561 → 1576 行之后），
            // 这里同步执行时 getElementById 拿到的是 null，wbUaCheck 走到 `if (!m) return true` 就裸退了，
            // 结果微信/QQ 用户进页面从来没自动收到过这个提示，只有点了上传按钮的那一次才弹。
            // 挪到 DOM 完整之后执行；已经就绪就直接跑（历史回看等二次调用场景）。
            var _uaCheckSoon = function () {
                try { wbUaCheck(); } catch (e) {}
                // 174 轮：开关状态从本机记忆回填（也与 #trainConsent 排在 app.js 之前与否无关，
                // 统一等 DOM 就绪，避免重蹈 166 轮「元素还不存在就初始化」的覆辙）
                try {
                    var _tc = document.getElementById('trainConsent');
                    if (_tc) _tc.checked = wbTrainConsent();
                } catch (e) {}
                // 186 轮：档位卡的实测数字从 /api/stats 现取（拿不到就只显示定性文案）
                try { wbStatsFill(); } catch (e) {}
            };
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', _uaCheckSoon);
            } else {
                _uaCheckSoon();
            }
            try { wbGuideInit(); } catch (e) {}
        })();
        // 顶部固定导出条（滚动时才出现）
        (function () {
            try { wbDockInit(); } catch (e) {}
            try { wbRoadLabel(); } catch (e) {}
        })();

        // 当前赛事名：后端靠它做「按官方章节排序」和「iCAN 双盲隐去学校/导师」，
        // 不传这两件事都不生效。取输入框优先，没有再退回本轮生成时记下的赛事名。
        function wbCompName() {
            var v = (document.getElementById('competition') || {}).value || '';
            if (v && String(v).trim()) return String(v).trim();
            return (window._lastData || {}).competition || '';
        }
        // 「待补充」在网页上是提醒，导出件里就是破绽 —— 评委翻到一页写着
        // 「本次没识别到竞品对比素材」基本直接判死。导出前一律剔除。
        function wbStripTodo(t) {
            if (!t) return t;
            var lines = String(t).split('\n');
            var out = [], skipping = false;
            for (var i = 0; i < lines.length; i++) {
                var ln = lines[i];
                /* 「待替换数据清单」是给作者看的提醒，列出哪些数字还得换实测值。
                   它一旦导出进 Word/PDF，等于主动告诉评委「我的数据是编的」，直接判死。
                   所以整节剔除（从它自己的标题一直到下一个同级标题为止）。 */
                if (/^#{1,6}\s*.*待替换数据清单/.test(ln)) { skipping = true; continue; }
                if (skipping) {
                    if (/^#{1,6}\s/.test(ln)) { skipping = false; }   // 遇到下一个标题 = 这一节结束
                    else { continue; }                                  // 节内正文整段丢掉
                }
                if (String(ln).indexOf('待补充') >= 0) continue;
                out.push(ln);
            }
            return out.join('\n');
        }
        function wbStripDeckTodo(deck) {
            if (!deck || !deck.slides) return deck;
            deck.slides.forEach(function (s) {
                if (!s || typeof s !== 'object') return;
                if (s.bullets) {
                    s.bullets = s.bullets.filter(function (b) { return String(b).indexOf('待补充') < 0; });
                }
                if (s.metrics) {
                    s.metrics = s.metrics.filter(function (m) { return String(m).indexOf('待补充') < 0; });
                }
            });
            return deck;
        }

        // 本轮生成出来的图表（预算饼图 / 市场柱图 / 进度甘特）。
        // 后端 /api/export_word 早就收这个字段并按章节插图，前端以前一直没传，
        // 所以导出的申报书里一张图都没有。
        function wbCharts() {
            return ((window._lastData || {}).rich_charts) || [];
        }

        /* ---------- 导出请求统一入口：失败自动重试 1 次 ----------
           部署/重启 gunicorn 时会做 graceful restart，正好撞上的请求会失败一次，
           用户看到「导出失败」点第二次就好了（第二十轮 #1 实测：重试即成功）。
           让用户在演示现场手动重试既不专业也容易以为网站坏了 —— 这里自动补一次。
           4xx 是内容/参数问题，重试多少次结果都一样，直接返回不浪费时间。 */
        async function wbExportFetch(url, payload) {
            var last = null;
            for (var attempt = 0; attempt < 2; attempt++) {
                try {
                    // 原格式导出走 FormData（带上传的原文件），不能设 Content-Type，
                    // 否则边界串丢了后端解不出文件
                    var isFd = (typeof FormData !== 'undefined') && (payload instanceof FormData);
                    var opt = { method: 'POST', body: isFd ? payload : JSON.stringify(payload) };
                    if (!isFd) opt.headers = { 'Content-Type': 'application/json' };
                    var res = await fetch(url, opt);
                    if (res.ok) return { ok: true, res: res };
                    last = { ok: false, res: res };
                    if (res.status >= 400 && res.status < 500) return last;
                } catch (e) {
                    last = { ok: false, err: e };
                }
                if (attempt === 0) await new Promise(function (r) { setTimeout(r, 900); });
            }
            return last || { ok: false };
        }

        // 导出失败的统一文案：能拿到后端 error 就照实说，拿不到就是服务端抖动/重启窗口
        async function wbExportError(label, bad) {
            var msg = '', j = null;
            if (bad && bad.res) {
                // clone 一次拿 JSON：响应体只能读一次，后面还要用 res 判断状态码
                try { j = await bad.res.clone().json(); msg = (j && (j.error || j.hint)) || ''; } catch (e) {}
            }
            // 122/123 轮：被「系统默认评委」打分门打回。后端把具体扣分项放在 reasons 里，
            // 只弹「导出失败」的话，用户分不清是自己内容不行还是网站坏了，会一直重复点。
            if (j && j.code === 'quality_fail') {
                var rs = (j.reasons && j.reasons.length) ? j.reasons.slice(0, 3).join('；') : '';
                wbToast(label + '未通过内容质检，暂时不导出', {
                    type: 'warn', ms: 9000,
                    sub: (rs ? '主要问题：' + rs + '。' : '')
                        + '内容还在页面上，改完或重新生成后再点导出即可，不用重头再来'
                });
                return;
            }
            // 417 轮：PDF 超页数/超大小被打回时，光说「未达标」用户不知道删哪。
            // 后端在 suggestions 里给了带数字的删减条目，这里原样列出来。
            if (j && j.code === 'export_quality_fail' && j.suggestions && j.suggestions.length) {
                var _ips = j.suggestions.slice(0, 4).join('；');
                wbToast(label + '超出该赛事提交要求，已取消导出', {
                    type: 'warn', ms: 11000,
                    sub: (msg ? msg + '。' : '') + '怎么改：' + _ips
                });
                return;
            }
            if (msg) { wbToast(label + '导出失败：' + msg, { type: 'error', ms: 6000 }); return; }
            wbToast(label + '没导出成功，服务正在重启或网络抖动', {
                type: 'error', ms: 6000,
                sub: '已自动重试过一次；页面内容和生成结果都还在，稍后再点一次即可，不用重新生成'
            });
        }

        // 导出成功带的非阻断提醒（X-Export-Warnings 响应头，URL-encoded JSON 数组）：文件照常下载，提醒逐条弹 warn
        function wbShowExportWarnings(res) {
            try {
                var raw = res && res.headers && res.headers.get('X-Export-Warnings');
                if (!raw) return;
                var arr = JSON.parse(decodeURIComponent(raw));
                if (!Array.isArray(arr)) return;
                arr.slice(0, 5).forEach(function (w) {
                    var m = String(w || '').trim();
                    if (m) wbToast(m, { type: 'warn', ms: 8000 });
                });
            } catch (e) {}
        }

        async function exportOne(id, name) {
            const text = wbStripTodo(_txt(_DOM_TO_KEY[id] || '', id));
            if (!text.trim()) { wbToast('「' + name + '」没有内容，请先生成', { type: 'warn' }); return; }
            var btn = (window.event && window.event.target) || null;
            var _qcTimer = 0;
            if (btn) {
                btn.disabled = true; btn.dataset.old = btn.innerHTML;
                // 122/127 轮：后端导出前先跑系统默认评委打分门（≤3 秒）再生成文件。
                // 按钮如实分两段说：先「质检中」，1.5 秒还没好说明已进生成阶段。
                // 一直写「生成中」的话，用户被质检打回时会以为是网站坏了
                btn.innerHTML = '质检中…';
                _qcTimer = setTimeout(function () { if (btn) btn.innerHTML = '生成文件…'; }, 1500);
            }
            try {
                var m = wbMeta();
                var payload = {title: name, text: text,
                        doc_type: _DOC_TYPE[id] || 'report',
                        competition_name: wbCompName(),
                        project_name: ((window._lastData || {}).one_liner || (window._lastData || {}).idea || ''),
                        // 后端原文兜底：页面 DOM 在并发生成/断网时可能被串台或半截渲染污染，
                        // 传 task_id/history_id 让后端用库里的 proposal 原文覆盖。
                        // 只对申报书传——后端该分支取的就是 proposal，传给别的文档会串内容。
                        task_id: (_DOM_TO_KEY[id] === 'proposal') ? (window._currentTaskId || null) : null,
                        history_id: (_DOM_TO_KEY[id] === 'proposal') ? (window._lastHistoryId || null) : null,
                        // 只有申报书/分析这类主文档配图表，规则解析等不适合插图
                        charts: (id === 'proposalText' || _DOC_TYPE[id] === 'analysis') ? wbCharts() : [],
                        // 171 轮：把用户在「高级参数」里选的图表配色带过去，
                        // 后端接上后导出的图表 PNG 与前台同色（未接上也不影响，后端忽略未知字段）
                        chart_theme: wbChartThemeKey(),
                        // 2026-10-01：带上本次生成模式，后端质量门按 fast 标准评 fast 稿
                        mode: (window._lastGenMode || 'deep'),
                        school: m.school, team: m.team, advisor: m.advisor};
                var r = await wbExportFetch('/api/export_word', payload);
                if (!r.ok) { await wbExportError('Word', r); return; }
                const res = r.res;
                wbShowExportWarnings(res);
                const blob = await res.blob();
                wbSaveBlob(blob, name + ".docx");
                wbToast('「' + name + '」已开始下载', { type: 'ok', ms: 2600 });
            } catch (e) {
                wbToast('导出失败：' + (e && e.message ? e.message : e), { type: 'error' });
            } finally {
                if (_qcTimer) clearTimeout(_qcTimer);
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        /* ---------- 结果页用户打分 ---------- */
        var wbRateVal = 0;
        var WB_RATE_TXT = ['', '很差，没帮上忙', '一般，还得大改', '还行，能用', '不错，省了事', '很好，直接用'];
        function wbRateSet(v) {
            wbRateVal = v;
            var bs = document.querySelectorAll('#wbRateStars .wb-rate-star');
            for (var i = 0; i < bs.length; i++) {
                var bv = parseInt(bs[i].getAttribute('data-v'), 10);
                if (bv <= v) bs[i].classList.add('on'); else bs[i].classList.remove('on');
            }
            var lb = document.getElementById('wbRateLabel');
            if (lb) lb.textContent = (WB_RATE_TXT[v] || '') + '（' + v + ' 星）';
        }
        function wbRateSubmit() {
            if (!wbRateVal) { wbToast('先点一个星星再提交', { type: 'warn' }); return; }
            var btn = document.getElementById('wbRateBtn');
            var txt = (document.getElementById('wbRateInput') || {}).value || '';
            if (btn) { btn.disabled = true; btn.textContent = '提交中…'; }
            var comp = '';
            try { comp = (document.getElementById('competition') || {}).value || ''; } catch (e) {}
            // 后端 /api/feedback 只收 content（+ history_id），星级拼进文本里一起入库
            var line = '评分 ' + wbRateVal + ' 星（' + (WB_RATE_TXT[wbRateVal] || '') + '）'
                     + (txt ? '｜' + txt : '')
                     + (comp ? '｜赛事：' + comp : '');
            fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: line,
                                       history_id: (window._lastHistoryId || null) })
            }).then(function (r) { return r.ok ? r.json() : null; })
              .then(function (j) {
                  if (j && j.success === false) throw new Error(j.error || '提交失败');
                  var d = document.getElementById('wbRateDone');
                  // 第八十九轮【低】：用户反馈「打分完没任何回应，体验干」。
                  // ① 显式写 'block'（写 '' 会回落到样式表/内联的 none，本项目已踩过两次）；
                  // ② 1.5s 后自动收起，不长期占着结果页底部。
                  if (d) {
                      d.style.display = 'block';
                      if (d._t) clearTimeout(d._t);
                      d._t = setTimeout(function () { d.style.display = 'none'; }, 1500);
                  }
                  if (btn) btn.textContent = '已提交';
                  wbToast('感谢你的反馈，我们会持续改进！', { type: 'ok' });
                  try { _wbStoreSet('wbRatedV', String(wbRateVal)); } catch (e) {}
              })
              .catch(function () {
                  if (btn) { btn.disabled = false; btn.textContent = '提交反馈'; }
                  wbToast('没提交成功，网络问题', { type: 'error' });
              });
        }
        async function exportOnePDF(id, name) {
            /* iCAN 官方交的就是 PDF（≤20页），这里必须和 Word 一样先清洗，
               否则「待补充」「待替换数据清单」会原样进 PDF */
            const text = wbStripTodo(_txt(_DOM_TO_KEY[id] || '', id));
            if (!text.trim()) { wbToast('「' + name + '」没有内容，请先生成', { type: 'warn' }); return; }
            var btn = (window.event && window.event.target) || null;
            var _qcTimer = 0;
            if (btn) {
                btn.disabled = true; btn.dataset.old = btn.innerHTML;
                // 122/127 轮：后端导出前先跑系统默认评委打分门（≤3 秒）再生成文件。
                // 按钮如实分两段说：先「质检中」，1.5 秒还没好说明已进生成阶段。
                // 一直写「生成中」的话，用户被质检打回时会以为是网站坏了
                btn.innerHTML = '质检中…';
                _qcTimer = setTimeout(function () { if (btn) btn.innerHTML = '生成文件…'; }, 1500);
            }
            try {
                var r = await wbExportFetch('/api/export_pdf', {title: name, text: text,
                        competition_name: wbCompName(),
                        // 与 Word 导出同理：只对申报书传，让后端用库里原文覆盖被污染的 DOM 文本
                        task_id: (_DOM_TO_KEY[id] === 'proposal') ? (window._currentTaskId || null) : null,
                        history_id: (_DOM_TO_KEY[id] === 'proposal') ? (window._lastHistoryId || null) : null,
                        chart_theme: wbChartThemeKey()});
                if (!r.ok) { await wbExportError('PDF', r); return; }
                const res = r.res;
                wbShowExportWarnings(res);
                const blob = await res.blob();
                wbSaveBlob(blob, name + ".pdf");
                // 官方硬性上限校验（iCAN 应用方案 ≤20 页 / ≤50MB）
                var _pg = parseInt(res.headers.get('X-PDF-Pages') || '0', 10);
                var _mb = parseFloat(res.headers.get('X-PDF-MB') || '0');
                var _lim = parseInt(res.headers.get('X-PDF-Limit') || '0', 10);
                if (_lim && _pg > _lim) {
                    wbToast('共 ' + _pg + ' 页，超出官方 ' + _lim + ' 页上限，建议压缩「使用说明」截图或合并功能清单', { type: 'warn', ms: 5200 });
                } else if (_mb > 50) {
                    wbToast('文件 ' + _mb + 'MB，超出 50MB 上限，请压缩图片后重导', { type: 'warn', ms: 5200 });
                } else {
                    wbToast('「' + name + '」PDF已开始下载' + (_pg ? '（' + _pg + ' 页）' : ''), { type: 'ok', ms: 2600 });
                }
            } catch (e) {
                wbToast('导出失败：' + (e && e.message ? e.message : e), { type: 'error' });
            } finally {
                if (_qcTimer) clearTimeout(_qcTimer);
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        // 取文本：优先用生成结果的原始数据（隐藏的 tab 用 innerText 会读到空串），DOM 仅兜底
        function _txt(key, domId) {
            var rd = window._lastData || {};
            var v = rd[key];
            if (v && String(v).trim()) return String(v);
            var el = document.getElementById(domId);
            if (!el) return '';
            return el.innerText || el.textContent || '';
        }
        async function exportAll() {
            var rd = window._lastData || {};
            var _m = wbMeta();
            var deck = rd.rich_deck || null;
            // 与「下载 PPT」同一套结构：打包里的 PPT 也走固定 8 页 + 申报书回填
            if (deck && wbRoadshowOn()) { try { deck = wbRoadshowDeck(rd); } catch (e) { deck = rd.rich_deck; } }
            deck = wbStripDeckTodo(deck);
            var tk = (document.getElementById('deckTheme') || {}).value;
            var vk = (document.getElementById('deckVariant') || {}).value;
            const data = {
                parsed_rules: _txt('parsed_rules', 'parsedRules'),
                similarity_report: _txt('similarity_report', 'similarityReport'),
                proposal: _txt('proposal', 'proposalText'),
                proposal_analysis: _txt('proposal_analysis', 'proposalAnalysis'),
                judge_feedback: _txt('judge_feedback', 'judgeFeedback'),
                competitor_analysis: _txt('competitor_analysis', 'competitorAnalysis'),
                business_model: _txt('business_model', 'businessModel'),
                risk_analysis: _txt('risk_analysis', 'riskAnalysis'),
                defense_questions: _txt('defense_questions', 'defenseQuestions'),
                ppt_outline: _txt('ppt_outline', 'pptOutline'),
                // 后端 12:42 那版已支持打包这两个模块，但前端一直没传 → zip 里永远没有它们。
                // 「后端有功能前端没传 = 等于没有」，这里补上。
                tech_solution: _txt('tech_solution', 'techSolution'),
                implementation_plan: _txt('implementation_plan', 'implementationPlan'),
                // 富媒体三件套：不带上就没有 13_项目数据图表.docx 和 14_路演PPT.pptx
                rich_charts: rd.rich_charts || [],
                rich_tables: rd.rich_tables || [],
                rich_deck: deck,
                idea: rd.idea || (document.getElementById('idea') || {}).value || '',
                // 打包里的 Word 同样要按赛事章节排序 / 走 iCAN 双盲，漏了就退化成默认顺序
                competition_name: wbCompName(),
                // 页面上手动选过主题/模板时覆盖自动推断值，和「下载 PPT」保持一致
                theme: tk || (deck && deck.theme) || null,
                variant: vk || (deck && deck.variant) || null,
                chart_theme: wbChartThemeKey(),
                school: _m.school, team: _m.team, advisor: _m.advisor
            };
            var btn = (window.event && window.event.target) || null;
            if (btn) { btn.disabled = true; btn.dataset.old = btn.innerHTML; btn.innerHTML = '打包中...'; }
            try {
                // 以前直接 res.blob() 存盘：后端 400 返回的是 JSON 错误体，会被原样存成 .zip，
                // 用户拿到「内容是错误信息的坏压缩包」，页面还提示「已打包，去下载吧」——
                // 虚假成功比明确报错更糟，必须先把非 2xx 拦死
                var r = await wbExportFetch('/api/export_zip', data);
                if (!r.ok) { await wbExportError('打包', r); return; }
                const res = r.res;
                const blob = await res.blob();
                wbSaveBlob(blob, "科创赛事项目材料包.zip");
                wbToast('已打包，去下载吧', { type: 'ok', ms: 3000 });
            } catch (e) {
                wbToast('打包失败：' + (e && e.message ? e.message : e), { type: 'error' });
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        function _fallbackCopy(text, done, fail) {
            // 非 HTTPS 或旧浏览器下 clipboard API 不可用时的兜底
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                var ok = document.execCommand('copy');
                document.body.removeChild(ta);
                ok ? done() : fail(new Error('execCommand 返回 false'));
            } catch (e) { fail(e); }
        }
        function copyText(id) {
            var el = document.getElementById(id);
            if (!el) return;
            // 优先复制渲染后的干净文本；隐藏的 tab innerText 为空时回退原始数据
            var text = (el.innerText || '').trim() || _txt(_DOM_TO_KEY[id] || '', id);
            if (!String(text).trim()) { wbToast('没有可复制的内容', { type: 'warn' }); return; }
            var okFn = function () {
                wbToast('已复制 ' + String(text).trim().length + ' 字到剪贴板', { type: 'ok', ms: 2200 });
            };
            var badFn = function (e) {
                wbToast('复制失败，请手动选中文本按 Ctrl+C', {
                    type: 'error', sub: String((e && e.message) || e || '')
                });
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(okFn).catch(function () {
                    _fallbackCopy(text, okFn, badFn);
                });
            } else {
                _fallbackCopy(text, okFn, badFn);
            }
        }
        function _esc(s) {
            return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
        }
        /* 2026-09-30 人眼审查：接口挂掉时把英文原始错误（Unexpected end of JSON input /
           Failed to fetch）直接甩给用户，评委看到很减分。统一转成中文人话，未知错误仍原样透出 */
        function _friendlyErr(e) {
            var m = (e && e.message) || String(e || '');
            if (/Unexpected end of JSON|invalid JSON|JSON/i.test(m)) return '服务暂时无响应，请稍后重试';
            if (/Failed to fetch|NetworkError|Load failed|net::/i.test(m)) return '网络连接失败，请检查网络后重试';
            if (/timeout|Timed out|aborted/i.test(m)) return '请求超时，请稍后重试';
            return m;
        }
        // ---- 全局提示 Toast（替代 alert，所有反馈统一走这里）----
        var _toastSeq = 0;
        function wbToast(title, opt) {
            opt = opt || {};
            var box = document.getElementById('wbToast');
            if (!box) { window.alert(title); return; }
            var type = opt.type || 'info';
            var ms = (opt.ms == null) ? (type === 'error' ? 8000 : 4000) : opt.ms;
            var icon = (type === 'error' || type === 'warn') ? 'wb-i-warn'
                     : (type === 'ok') ? 'wb-i-check' : 'wb-i-bulb';
            window.__wbLastToastAt = Date.now();   // 兜底拦截器据此判断调用方是否已提示，避免重复弹
            var id = 'wbtoast' + (++_toastSeq);
            var el = document.createElement('div');
            el.className = 'wb-toast t-' + type;
            el.id = id;
            el.innerHTML =
                '<svg class="wb-toast-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#' + icon + '"/></svg>' +
                '<div class="wb-toast-main">' +
                    '<div class="wb-toast-title">' + _esc(title) + '</div>' +
                    (opt.sub ? '<div class="wb-toast-sub">' + _esc(opt.sub) + '</div>' : '') +
                '</div>' +
                '<svg class="wb-toast-x" viewBox="0 0 24 24" aria-hidden="true" onclick="wbToastClose(\'' + id + '\')"><use href="#wb-i-cross"/></svg>';
            box.appendChild(el);
            while (box.children.length > 4) box.removeChild(box.firstChild);   // 最多 4 条，避免刷屏
            if (ms > 0) setTimeout(function () { wbToastClose(id); }, ms);
            return id;
        }
        function wbToastClose(id) {
            var el = document.getElementById(id);
            if (!el || el.classList.contains('is-out')) return;
            el.classList.add('is-out');
            setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 240);
        }

        /* ---------- 赛事要求卡：跟着赛事名自动换文档类型与章节结构 ---------- */
        // 数据与 data/event_requirements.json 同源（改那边记得同步这里）
        var EVENT_REQ = {
            "iCAN大学生创新创业大赛": {
                label: "应用方案", doc_type: "应用方案（PDF，不超过 20 页 / 50MB）",
                alias: ["ican", "ican大赛", "ican大学生", "创新创业", "AI应用创新挑战赛", "iCAN AI挑战赛"],
                sections: ["一、项目背景与痛点", "二、需求分析与目标用户", "三、开发工具与技术选型",
                           "四、技术方案与系统架构", "五、功能说明与 AI 核心作用",
                           "六、使用说明", "七、应用前景与商业模式", "八、团队分工与知识产权"],
                // 官方口径（与 data/competition_profiles.json 一致）：创新性30/商业性25/技术方案25/产品介绍20
                scoring: [["创新性", 30], ["商业性", 25], ["技术方案", 25], ["产品介绍", 20]],
                deduct: "扣分点：智能能力只做套壳点缀 / 无可运行 Demo / 技术细节空洞 / 缺少使用说明 / 硬件赛道交渲染图",
                // 官方提交物（AI 应用创新挑战赛）：应用方案 PDF + 演示视频 + 可运行程序
                submit: ["应用方案 PDF（≤20页、≤50MB）", "演示视频 MP4（≤5分钟）",
                         "可运行程序链接或源码", "硬件赛道另交：硬件设计说明 + 实物原型照片"]
            },
            "挑战杯全国大学生课外学术科技作品竞赛": {
                label: "申报书", doc_type: "申报书（学术论文 / 科技发明类）",
                alias: ["挑战杯", "课外学术科技作品"],
                sections: ["一、项目概述", "二、国内外研究现状", "三、研究内容与方法",
                           "四、创新点与成果", "五、应用前景与社会价值", "六、团队与进度安排"],
                scoring: [["创新性", 30], ["可行性", 30], ["科学性与先进性", 20], ["综合答辩与展示", 20]],
                deduct: "扣分点：缺少文献综述 / 创新点不清晰 / 无数据或实验支撑"
            },
            "中国国际互联网+大学生创新创业大赛": {
                label: "商业计划书", doc_type: "商业计划书",
                alias: ["互联网+", "互联网+大赛", "中国国际大学生创新大赛"],
                sections: ["一、项目概述", "二、市场分析", "三、产品与技术方案", "四、商业模式",
                           "五、财务预测与融资计划", "六、团队与教育维度", "七、社会价值"],
                scoring: [["教育维度", 25], ["创新维度", 30], ["团队维度", 20], ["商业与社会价值维度", 25]],
                deduct: "扣分点：商业模式不成立 / 财务数据拍脑袋 / 缺少教育维度"
            }
        };
        var EV_DEFAULT = {
            label: "申报书", doc_type: "申报书（通用科创赛事结构）",
            sections: ["一、项目概述", "二、项目背景与痛点分析", "三、解决方案与技术方案",
                       "四、核心创新点", "五、应用场景与市场分析", "六、商业模式",
                       "七、团队介绍与分工", "八、社会价值与应用前景"],
            scoring: [["创新性", 30], ["实用性", 25], ["技术难度", 20], ["团队展示", 15], ["社会价值", 10]],
            deduct: "通用结构：可在上方卡片里增删改章节，生成会按你改的来"
        };

        // 当前文档名词（申报书 / 应用方案 / 商业计划书，按比赛官方提交物为准），全站文案跟着它走
        var WB_DOC_LABEL = '申报书';

        // ---- 赛事官方资料索引：选比赛就立刻看到真实资料，不等生成 ----
        // 后端 knowledge/data/*.txt（15 个赛事）解析成的结构化索引，落在 /static/competition_index.json。
        // 页面加载时拉一次并缓存进 localStorage，之后选赛事纯本地查表 —— 0 延迟，不占生成时间。
        var WB_COMP_INDEX = null;
        var WB_COMP_IDX_KEY = 'wbCompIndexV1';

        function wbLoadCompIndex() {
            // 先读缓存，让首屏就能立刻匹配（哪怕这次 fetch 还没回来）
            try {
                var c = JSON.parse(_wbStoreGet(WB_COMP_IDX_KEY) || 'null');
                if (c && c.items && c.items.length) WB_COMP_INDEX = c;
            } catch (e) {}
            _wbFetch('/static/competition_index.json', { cache: 'no-cache' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (!d || !d.items || !d.items.length) return;
                    var oldV = WB_COMP_INDEX && WB_COMP_INDEX.version;
                    WB_COMP_INDEX = d;
                    try { _wbStoreSet(WB_COMP_IDX_KEY, JSON.stringify(d)); } catch (e) {}
                    // 候选清单可能已缓存过（当时索引还没到），让它下次重新算，把索引里的新赛事并进来
                    _compOpts = null;
                    // 版本变了说明后端资料更新过，重画一次要求卡
                    if (oldV !== d.version) { try { renderEventCard(); } catch (e) {} }
                })
                .catch(function () { /* 拉不到就用缓存，再不行回落内置规则 */ });
        }

        /* ---------- 赛事结构化配置（后端 data/competition_profiles.json） ----------
           15 个比赛的官方章节顺序 / 评分重点 / 赛事侧重 / 是否双盲都在这一份里。
           前端拉一次缓存起来，赛事卡与评分展示优先用它，避免后端改了 JSON 前端还写死旧口径。
           优先级：知识库资料索引（真实资料）> 本配置 > 前端内置 EVENT_REQ。 */
        var WB_COMP_PROFILES = null;
        var WB_COMP_PROF_KEY = 'wbCompProfilesV1';

        function wbLoadProfiles() {
            try {
                var c = JSON.parse(_wbStoreGet(WB_COMP_PROF_KEY) || 'null');
                if (c && c.length) WB_COMP_PROFILES = c;
            } catch (e) {}
            _wbFetch('/api/competition_profiles', { cache: 'no-cache' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (!d || !d.success || !d.competitions || !d.competitions.length) return;
                    WB_COMP_PROFILES = d.competitions;
                    try { _wbStoreSet(WB_COMP_PROF_KEY, JSON.stringify(d.competitions)); } catch (e) {}
                    try { renderEventCard(); } catch (e) {}
                })
                .catch(function () { /* 拉不到就用缓存 / 回落到内置规则 */ });
        }

        function wbMatchProfile(name) {
            if (!WB_COMP_PROFILES || !WB_COMP_PROFILES.length) return null;
            var n = String(name || '').toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
            if (!n) return null;
            var best = null, bs = 0;
            WB_COMP_PROFILES.forEach(function (it) {
                var keys = [it.name].concat(it.aliases || []);
                var s = 0;
                keys.forEach(function (k) {
                    var kk = String(k || '').toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
                    if (!kk) return;
                    if (n === kk) s = Math.max(s, 100);
                    else if (n.indexOf(kk) >= 0 || kk.indexOf(n) >= 0) s = Math.max(s, 80);
                });
                if (s > bs) { bs = s; best = it; }
            });
            return bs >= 80 ? best : null;
        }

        // 从索引匹配赛事：keys 完全相等优先，其次互相包含；取最优命中，避免「挑战杯」串到小挑
        function wbMatchIndex(name) {
            if (!WB_COMP_INDEX || !WB_COMP_INDEX.items) return null;
            var n = String(name || '').toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
            if (!n) return null;
            var best = null, bs = 0;
            WB_COMP_INDEX.items.forEach(function (it) {
                var s = 0;
                (it.keys || []).forEach(function (k) {
                    var kk = String(k).toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
                    if (!kk) return;
                    if (n === kk) s = Math.max(s, 100);
                    else if (n.indexOf(kk) >= 0 || kk.indexOf(n) >= 0) s = Math.max(s, 80);
                });
                if (s > bs) { bs = s; best = it; }
            });
            return bs >= 80 ? best : null;
        }

        // 评分项里有没有真实的百分比数字（null / undefined / 空串都不算）
        function _wbPctOf(x) {
            if (!x || x.length < 2) return null;
            var w = x[1];
            return (typeof w === 'number' && isFinite(w)) ? w : null;
        }
        function _wbScoringHasPct(arr) {
            if (!arr || !arr.length) return false;
            for (var i = 0; i < arr.length; i++) if (_wbPctOf(arr[i]) !== null) return true;
            return false;
        }
        // 一份 scoring 里最长的条目名有多长——用来判断它是不是"整段规则原文"
        function _wbScoringMaxLen(arr) {
            var m = 0;
            if (!arr || !arr.length) return 0;
            for (var i = 0; i < arr.length; i++) {
                var n = String((arr[i] && arr[i][0]) || '');
                if (n.length > m) m = n.length;
            }
            return m;
        }

        // 官方资料 + 内置规则合并：官方优先，官方缺哪块就用内置的补哪块
        function wbMergeEvent(idx, req, prof) {
            var base = req || EV_DEFAULT;
            // 章节：官方资料 > 结构化配置 > 内置规则 > 通用结构
            var sec = null;
            if (idx && idx.sections && idx.sections.length) sec = idx.sections;
            else if (prof && prof.chapters && prof.chapters.length) sec = prof.chapters;
            else sec = base.sections;
            // 评分：先看哪份里真有百分比。
            // 2026-09-28 实测：官方资料索引里国创/蓝桥杯的 scoring 是「规则原文 + null」
            // （11 条长文本，weight 全 null），按老逻辑 idx 优先 → 页面直接渲染出 null%
            // 和一大段规则原文。所以：① 有真实百分比的优先；② 都没有就选条目最短的那份
            // （profiles 的「立项评审 / 结题验收」比索引的整段原文干净得多）。
            var sco = null;
            // 只在「官方两份」里挑：内置 EVENT_REQ 的别名匹配很宽（"创新创业"会命中 iCAN），
            // 让它参与"有百分比就优先"的竞争，会把国创的权重显示成 iCAN 的（2026-09-28 实测踩到）。
            // 内置那份只在官方两份都没有时才兜底。
            var _cands = [];
            if (idx && idx.scoring && idx.scoring.length) _cands.push(idx.scoring);
            if (prof && prof.scoring && prof.scoring.length) _cands.push(prof.scoring);
            for (var _ci = 0; _ci < _cands.length; _ci++) {
                if (_wbScoringHasPct(_cands[_ci])) { sco = _cands[_ci]; break; }
            }
            if (!sco && _cands.length) {
                sco = _cands.slice().sort(function (p1, p2) {
                    return _wbScoringMaxLen(p1) - _wbScoringMaxLen(p2);
                })[0];
            }
            if (!sco) sco = base.scoring;
            return {
                label: (idx && idx.doc_type) || base.label,
                doc_type: (idx && idx.doc_type) || base.doc_type,
                sections: sec.slice(),
                scoring: sco,
                deduct: (idx && idx.deduct) || base.deduct,
                _idx: idx || null,
                _prof: prof || null,
                _src: idx ? 'index' : (prof ? 'profile' : (req ? 'builtin' : 'default'))
            };
        }

        function wbMatchEvent(name) {
            var n = String(name || '').toLowerCase().replace(/[""'']/g, '');
            if (!n) return null;
            // 先查官方资料索引（后端知识库解析来的，是真资料）
            var idx = wbMatchIndex(name);
            // 再查前端内置规则，只用来补官方资料的缺口
            var builtin = null;
            for (var k in EVENT_REQ) {
                if (n === k.toLowerCase()) { builtin = EVENT_REQ[k]; break; }
                var al = EVENT_REQ[k].alias || [];
                for (var i = 0; i < al.length; i++) {
                    if (n.indexOf(al[i]) >= 0 || al[i].indexOf(n) >= 0) { builtin = EVENT_REQ[k]; break; }
                }
                if (builtin) break;
            }
            var prof = wbMatchProfile(name);
            if (!idx && !prof && !builtin) return null;
            return wbMergeEvent(idx, builtin, prof);
        }

        function evCurrent() {
            var name = (document.getElementById('competition') || {}).value || '';
            var req = wbMatchEvent(name);
            var base = req || EV_DEFAULT;
            var key = 'wbEventReq_' + (req ? (req.label + name) : name);
            var custom = null;
            try { custom = JSON.parse(_wbStoreGet(key) || 'null'); } catch (e) {}

            // 赛道：只有知识库真写了「## 赛道设置」的赛事才有。
            // 默认选中第一个（iCAN 是创新赛道——它的禁忌是「别写学校/导师」，
            // 这条对任何赛道都无害，反而是不选才容易漏掉商业模式这类硬要求）
            var tracks = (base._idx && base._idx.tracks) || [];
            var tk = null;
            if (tracks.length) {
                var tkey = (custom && custom.track) || '';
                tk = tracks.filter(function (t) { return t.key === tkey; })[0] || tracks[0];
            }

            var sections;
            if (custom && custom.sections && custom.sections.length) sections = custom.sections;
            else if (tk && tk.sections && tk.sections.length) sections = tk.sections.slice();
            else sections = base.sections.slice();

            return { label: base.label, doc_type: base.doc_type, sections: sections,
                     scoring: base.scoring, deduct: base.deduct, key: key,
                     _idx: base._idx || null, _prof: base._prof || null,
                     _src: base._src || 'default',
                     _track: tk, _tracks: tracks };
        }

        // 选赛道：切换后章节跟着换成该赛道的结构（用户手动改过的章节优先保留）
        function evSetTrack(tkey) {
            var c = evCurrent();
            if (!c._tracks || !c._tracks.length) return;
            var tk = c._tracks.filter(function (t) { return t.key === tkey; })[0];
            if (!tk) return;
            var saved = null;
            try { saved = JSON.parse(_wbStoreGet(c.key) || 'null'); } catch (e) {}
            // 已有自定义章节 → 只换赛道标记，不动用户改过的结构
            var keep = (saved && saved.sections && saved.sections.length) ? saved.sections : null;
            try {
                _wbStoreSet(c.key, JSON.stringify({
                    sections: keep || [], track: tkey
                }));
            } catch (e) {}
            renderEventCard();
            wbSaveForm();
        }

        // 赛道规则拼成给 AI 看的约束文本（走 rule_content 链路，后端不用改）
        function evTrackRule() {
            var c = evCurrent();
            var tk = c._track;
            if (!tk) return '';
            var L = [];
            L.push('【赛道】' + tk.name + '：' + tk.desc);
            if (tk.ban && tk.ban.length) {
                L.push('【硬性禁忌】以下内容严禁出现：' + tk.ban.join('、') +
                       (tk.ban_note ? '。' + tk.ban_note : ''));
            }
            if (tk.focus && tk.focus.length) L.push('【必须写到】' + tk.focus.join('；'));
            if (tk.avoid && tk.avoid.length) L.push('【不要写】' + tk.avoid.join('；'));
            return L.join('\n');
        }

        function evSave() {
            var c = evCurrent();
            var boxes = document.querySelectorAll('#evSections input.ev-sec');
            var arr = [];
            for (var i = 0; i < boxes.length; i++) {
                var v = boxes[i].value.trim();
                if (v) arr.push(v);
            }
            c.sections = arr;
            try { _wbStoreSet(c.key, JSON.stringify({ sections: arr })); } catch (e) {}
        }

        function evAddSection() {
            evSave();
            var c = evCurrent();
            c.sections.push('新章节 ' + (c.sections.length + 1));
            try { _wbStoreSet(c.key, JSON.stringify({ sections: c.sections })); } catch (e) {}
            renderEventCard();
        }

        function evDelSection(i) {
            evSave();
            var c = evCurrent();
            c.sections.splice(i, 1);
            try { _wbStoreSet(c.key, JSON.stringify({ sections: c.sections })); } catch (e) {}
            renderEventCard();
        }

        function evReset() {
            var c = evCurrent();
            try { _wbStoreDel(c.key); } catch (e) {}
            renderEventCard();
        }

        // 赛事卡默认只给重点（文档类型 / 章节前 6 / 评分权重 / 双盲），细节按需展开。
        // 一屏十几行的话用户根本不看，等于白做。
        var _evSecAll = false;
        function evToggleSections() {
            _evSecAll = !_evSecAll;
            renderEventCard();
        }
        function evToggleMore() {
            var m = document.getElementById('evMore');
            var a = document.getElementById('evMoreArrow');
            if (!m) return;
            var open = m.style.display === 'none';
            m.style.display = open ? 'block' : 'none';
            if (a) a.textContent = open ? '▴' : '▾';
        }

        function renderEventCard() {
            var card = document.getElementById('eventReqCard');
            if (!card) return;
            var c = evCurrent();
            // 文档名换了 → 全站文案跟着换
            WB_DOC_LABEL = c.label || '申报书';
            wbApplyDocName();

            var dt = document.getElementById('evDocType');
            if (dt) dt.textContent = c.doc_type || WB_DOC_LABEL;

            var box = document.getElementById('evSections');
            if (box) {
                var LIM = 6;
                var hasExtra = c.sections.length > LIM;
                var rows = c.sections.map(function (s, i) {
                    var hide = (hasExtra && !_evSecAll && i >= LIM);
                    // 序号做成圆点徽章：原来只是一个灰色「1.」，整列看起来就是一排灰字
                    return '<div class="wb-sec-row" style="display: ' + (hide ? 'none' : 'flex') +
                        '; gap: 8px; align-items: center; margin-bottom: 5px;">' +
                        '<span class="wb-sec-no" aria-hidden="true">' + (i + 1) + '</span>' +
                        '<input class="ev-sec" value="' + _esc(s) + '" onchange="evSave()" aria-label="第 ' + (i + 1) + ' 章" style="flex: 1; height: 34px; padding: 0 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface-2); color: var(--text); font-size: 13px;">' +
                        '<button onclick="evDelSection(' + i + ')" class="wb-textbtn" style="flex: 0 0 auto; padding: 4px 9px; font-size: 12px;" title="删除第 ' + (i + 1) + ' 章">删</button>' +
                        '</div>';
                }).join('');
                if (hasExtra) {
                    rows += '<div onclick="evToggleSections()" style="margin-top: 2px; font-size: 12.5px; ' +
                        'color: var(--c-a); cursor: pointer; user-select: none;">' +
                        (_evSecAll ? '收起章节' : '展开全部 ' + c.sections.length + ' 章') +
                        ' <span>' + (_evSecAll ? '▴' : '▾') + '</span></div>';
                }
                box.innerHTML = rows;
            }

            var sc = document.getElementById('evScoring');
            if (sc) {
                var _arr = c.scoring || [];
                // 上方赛道细则里已经有「官方原文」的评分侧重，这里再列一套百分比，
                // 两条挨着容易被当成「官方给了两套互相矛盾的权重」——必须标出来源
                var _srcNote = c._idx ? '（来源：官方原文）' : '（来源：通用模板，本赛事未收录官方权重）';
                if (!_arr.length) {
                    sc.innerHTML = '<b style="color: var(--text-dim);">评分权重：</b>按官方规则评定';
                } else if (!_wbScoringHasPct(_arr)) {
                    // 国创 / 蓝桥杯这类：官方是定性评审或机器评分，本来就没有固定百分比，
                    // 别把规则原文逐条列出来吓人，也绝不能显示 null%
                    sc.innerHTML = '<b style="color: var(--text-dim);">评分权重' + _srcNote + '：</b>' +
                        '按官方规则评定（该赛事为定性评审 / 机器评分，官方无固定百分比）';
                } else {
                    sc.innerHTML = '<b style="color: var(--text-dim);">评分权重' + _srcNote + '：</b>' +
                        _arr.map(function (x) {
                            var _w = _wbPctOf(x);
                            var _nm = String((x && x[0]) || '');
                            if (_nm.length > 24) _nm = _nm.slice(0, 24) + '…';
                            return _esc(_nm) + ' ' + (_w === null ? '按官方规则评定' : _w + '%');
                        }).join(' · ');
                }
            }
            // 赛事结构化配置带来的两条硬信息：双盲（iCAN 封面不能出现学校/导师）与官方侧重
            var pf = document.getElementById('evProfileTip');
            if (pf) {
                var p = c._prof, h = '';
                if (p && p.double_blind) {
                    h += '<div style="margin-top: 6px; color: var(--danger, #C0392B); font-weight: 600;">' +
                         '⚠ 本赛事双盲评审：导出封面自动隐去学校 / 单位 / 指导老师，只保留团队信息</div>';
                }
                if (p && p.focus) {
                    h += '<div style="margin-top: 4px; color: var(--text-dim);">赛事侧重：' + _esc(p.focus) + '</div>';
                }
                pf.innerHTML = h;
                pf.style.display = h ? 'block' : 'none';
            }
            // 赛道选择：无赛道数据的赛事整块隐藏，不留空壳
            var tb = document.getElementById('evTrackBox');
            if (tb) {
                var tks = c._tracks || [];
                if (tks.length) {
                    tb.style.display = 'block';
                    var chips = document.getElementById('evTrackChips');
                    if (chips) {
                        chips.innerHTML = tks.map(function (t) {
                            var on = c._track && t.key === c._track.key;
                            return '<button onclick="evSetTrack(\'' + t.key + '\')" ' +
                                'title="' + _esc(t.desc) + '" ' +
                                'style="padding: 6px 12px; font-size: 12.5px; border-radius: 999px; cursor: pointer; ' +
                                'border: 1px solid ' + (on ? 'var(--c-a)' : 'var(--line)') + '; ' +
                                'background: ' + (on ? 'var(--c-a)' : 'var(--surface-solid)') + '; ' +
                                'color: ' + (on ? '#fff' : 'var(--text-dim)') + '; ' +
                                'font-weight: ' + (on ? '600' : '400') + ';">' + _esc(t.name) + '</button>';
                        }).join('');
                    }
                    // 赛道细则：禁忌用红色，必须写/不要写用普通色；
                    // focus/avoid/sections 是我们按赛道定位推导的，不是官方原文，必须标注清楚
                    var ti = document.getElementById('evTrackInfo');
                    if (ti && c._track) {
                        var t = c._track, h = '';
                        // 来源徽章：官方原文 / 知识库整理 / 建议——学生得知道自己在看什么级别的东西
                        var sm = { official: ['官方原文', '#0E9F6E', '#E7F7F1'],
                                   kb: ['知识库整理', '#6B7280', '#F3F4F6'],
                                   derived: ['建议', '#B45309', '#FEF3C7'] }[t.src || 'kb'];
                        h += '<div style="margin-bottom: 4px;">' +
                             '<span style="display:inline-block; padding: 1px 7px; border-radius: 4px; font-size: 11px; ' +
                             'background: ' + sm[2] + '; color: ' + sm[1] + '; font-weight: 600;">' +
                             sm[0] + '</span></div>';
                        h += '<div style="color: var(--text-dim);">' + _esc(t.desc) + '</div>';
                        if (t.ban && t.ban.length) {
                            h += '<div style="margin-top: 5px; color: var(--danger, #C0392B); font-weight: 600;">' +
                                 '⚠ 不能出现：' + _esc(t.ban.join('、')) +
                                 (t.ban_note ? '<span style="font-weight:400;">（' + _esc(t.ban_note) + '）</span>' : '') +
                                 '</div>';
                        }
                        // derived=true 表示 focus/avoid/sections 是我们按赛道定位推导的建议，
                        // 不是官方原文——必须标出来，不然学生会当成官方要求照抄
                        var tag = t.derived
                            ? '<span style="color: var(--warn-text); font-size: 11.5px;">（以下为建议，非官方要求）</span>'
                            : '';
                        if (t.focus && t.focus.length) {
                            h += '<div style="margin-top: 4px; color: var(--text-dim);">要写到' + tag + '：' +
                                 _esc(t.focus.join('；')) + '</div>';
                        }
                        if (t.avoid && t.avoid.length) {
                            h += '<div style="margin-top: 4px; color: var(--text-mute);">别写：' +
                                 _esc(t.avoid.join('；')) + '</div>';
                        }
                        if (t.sections && t.sections.length) {
                            h += '<div style="margin-top: 4px; color: var(--text-mute); font-size: 12px;">' +
                                 '（下面章节' + (t.derived ? '是我们按该赛道给的建议结构，' : '') +
                                 '可直接改）</div>';
                        }
                        ti.innerHTML = h;
                        ti.style.display = 'block';
                    }
                } else {
                    // 没赛道数据，但官方介绍里明明提到了赛道划分
                    // （蓝桥杯「软件类/电子类」、西门子杯「工程设计/创新研发」、计算机设计「11 大类」）。
                    // 这种情况必须说清楚：不然学生以为该比赛没有赛道，或者以为我们给的就是按赛道来的。
                    var intro = (c._idx && c._idx.intro) || '';
                    var mentioned = /赛道|大类|类（|软件类|电子类/.test(intro);
                    if (mentioned) {
                        tb.style.display = 'block';
                        var chips2 = document.getElementById('evTrackChips');
                        if (chips2) chips2.innerHTML = '';
                        var ti2 = document.getElementById('evTrackInfo');
                        if (ti2) {
                            ti2.innerHTML =
                                '<div style="color: var(--warn-text);">⚠ 这个比赛按官方划分是有赛道的，' +
                                '但我们还没收录各赛道的差异规则 —— 现在按<b>通用要求</b>生成。</div>' +
                                '<div style="margin-top: 4px; color: var(--text-mute); font-size: 12px;">' +
                                _esc(intro) + '</div>' +
                                '<div style="margin-top: 4px; color: var(--text-mute); font-size: 12px;">' +
                                '赛道选错容易偏题，建议上传本赛事官方文件后再生成。</div>';
                            ti2.style.display = 'block';
                        }
                    } else {
                        tb.style.display = 'none';
                    }
                }
            }

            var dd = document.getElementById('evDeduct');
            if (dd) dd.textContent = c.deduct || '';

            // 匹配状态：这份要求到底是官方知识库来的、还是通用兜底——必须让学生看见，
            // 否则他会以为「官方资料」四个字适用于任何比赛，选个没收录的也照信不误
            var mb = document.getElementById('evMatchBar');
            if (mb) {
                var idx = c._idx;
                if (idx) {
                    // 匹配上了就别报流水账（资料标题 + 字数 + 来源），那是内部信息。
                    // 只有「官方资料缺东西」这一条对用户有影响，值得说一句。
                    if (idx.gaps && idx.gaps.length) {
                        mb.style.display = 'block';
                        mb.innerHTML = '<div style="padding: 7px 10px; border-radius: 6px; background: var(--warn-bg); ' +
                            'color: var(--text-dim); font-size: 12px; line-height: 1.6;">' +
                            '官方资料缺 ' + _esc(idx.gaps.join('、')) + '，已用通用规则补齐</div>';
                    } else {
                        mb.style.display = 'none';
                        mb.innerHTML = '';
                    }
                } else {
                    // 没收录：只留一句「按通用标准 + 可上传官方文件」，不展开解释
                    mb.style.display = 'block';
                    mb.innerHTML = '<div style="padding: 7px 10px; border-radius: 6px; background: var(--warn-bg); ' +
                        'color: var(--text-dim); font-size: 12.5px; line-height: 1.6;">' +
                        '<b style="color: var(--warn-text);">未收录官方资料</b>，按通用标准生成；' +
                        '上传官方文件会更准。</div>';
                }
            }

            // 评委偏好：官方知识库里有，之前前端没地方显示，白白浪费
            var pf = document.getElementById('evPref');
            if (pf) {
                var pref = (c._idx && c._idx.preference) ? c._idx.preference : [];
                if (pref.length) {
                    pf.innerHTML = '<b style="color: var(--text-dim);">评委偏好：</b>' + _esc(pref.join('；'));
                    pf.style.display = 'block';
                } else {
                    pf.innerHTML = '';
                    pf.style.display = 'none';
                }
            }

            // 一行摘要：卡片默认收起，标题后面直接说清「几章 / 几个评分维度 / 是否双盲」，
            // 用户不展开也知道这份要求大概是什么，展开了才是全文
            var sm = document.getElementById('evSummary');
            if (sm) {
                var bits = [];
                bits.push((c.sections || []).length + ' 章');
                var _sc = (c.scoring || []).filter(function (x) { return _wbPctOf(x) !== null; });
                bits.push(_sc.length ? (_sc.length + ' 个评分维度') : '按官方规则评定');
                if (c._prof && c._prof.double_blind) bits.push('双盲');
                sm.textContent = ' · ' + bits.join(' · ');
            }

            card.style.display = 'block';
        }

        // 全站把「申报书」替换成当前文档名：文本节点 + 内联属性（onclick 里的导出名等）
        // 只换文本节点够不到 onclick="exportOne(...,'项目申报书全文')" 这类属性里的字符串，
        // 所以属性也要扫一遍。原文都备份过，切回「申报书」时回得来。
        var _WB_SWAP_ATTRS = ['onclick', 'title', 'placeholder', 'aria-label', 'alt'];
        function wbApplyDocName() {
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
            var nodes = [];
            while (walker.nextNode()) nodes.push(walker.currentNode);
            nodes.forEach(function (n) {
                if (n._wbOrig === undefined) n._wbOrig = n.nodeValue;
                if (n._wbOrig.indexOf('申报书') >= 0) {
                    n.nodeValue = n._wbOrig.replace(/申报书/g, WB_DOC_LABEL);
                }
            });
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                for (var j = 0; j < _WB_SWAP_ATTRS.length; j++) {
                    var a = _WB_SWAP_ATTRS[j];
                    if (!el.hasAttribute || !el.hasAttribute(a)) continue;
                    var key = '_wbAttrOrig_' + a;
                    if (el[key] === undefined) el[key] = el.getAttribute(a);
                    var o = el[key] || '';
                    if (o.indexOf('申报书') >= 0) {
                        el.setAttribute(a, o.replace(/申报书/g, WB_DOC_LABEL));
                    }
                }
            }
        }

        /* ---------- 分步引导：箭头指向按钮 + 一句话，点一下就走 ---------- */
        var COACH_STEPS = [
            // 刻意用「先选 / 再填 / 最后」的顺序词，不用「第 N 步」：
            // 表单的阿拉伯步骤号已随统一材料框架重排（第 1 步=导入材料、第 2 步=赛事、第 3 步=创意），
            // 气泡里再写「第一步选赛事」会和表单第 1 步撞号，用户分不清说的是哪一步。
            { id: 'competition', text: '先选参赛赛事：系统将按该赛事的官方评分标准与章节要求组织内容；未收录的赛事按通用标准生成。有现成申报书/材料的话，先回顶部第 1 步导入，会自动填好这里。' },
            { id: 'idea', text: '再填项目创意：用一两句话说明目标用户、解决的核心问题与技术路径，描述越具体，产出越贴合评审视角。已经写过草稿的，用第 1 步导入即可，不用在这里手抄。' },
            { id: 'startBtn', text: '最后选生成档位并开始：简洁版出稿快、字数精；深度版内容更全，含图表与路演 PPT。两档的实际字数与用时见档位卡上的实测统计。' }
        ];
        var _coachIdx = 0;
        var _coachEnded = false;
        var _coachRaf = 0;
        // 2026-10-01 错位根治（用户二报）：定位只算一次的话，手机地址栏收起（视口高度突变）、
        // #startBar sticky 重新吸附、字体加载回流、用户滚动，都会让 fixed 气泡和目标脱节——
        // 桌面探针三步几何全对、真机仍错位，差的就是这层动态跟踪。引导期间 rAF 节流持续重算。
        function _coachTrack() {
            if (_coachRaf) return;
            _coachRaf = window.requestAnimationFrame(function () {
                _coachRaf = 0;
                try { coachRepos(); } catch (e) {}
            });
        }

        function _coachClear() {
            var olds = document.querySelectorAll('.wb-coach-target');
            for (var i = 0; i < olds.length; i++) olds[i].classList.remove('wb-coach-target');
            var veil = document.getElementById('wbCoachVeil');
            if (veil && veil.parentNode) veil.parentNode.removeChild(veil);
            var tip = document.getElementById('coachTip');
            if (tip && tip.parentNode) tip.parentNode.removeChild(tip);
            // 跟踪监听随引导清理，防泄漏
            try { window.removeEventListener('scroll', _coachTrack); } catch (e) {}
            try { window.removeEventListener('resize', _coachTrack); } catch (e) {}
            try { if (window.visualViewport) window.visualViewport.removeEventListener('resize', _coachTrack); } catch (e) {}
            if (_coachRaf) { try { window.cancelAnimationFrame(_coachRaf); } catch (e) {} _coachRaf = 0; }
        }

        function _coachEsc(e) { if (e && e.key === 'Escape') coachEnd(); }

        function coachStart() {
            _coachIdx = 0;
            _coachEnded = false;
            try { document.addEventListener('keydown', _coachEsc); } catch (e) {}
            coachShow();
        }

        function coachShow() {
            _coachClear();
            if (_coachIdx >= COACH_STEPS.length) { coachEnd(); return; }
            var step = COACH_STEPS[_coachIdx];
            var el = document.getElementById(step.id);
            if (!el) { _coachIdx++; coachShow(); return; }
            // instant 而非 smooth：smooth 动画中 getBoundingClientRect 拿到中间态，380ms 后 coachRepos 按它定位就会错位（根因）
            try { el.scrollIntoView({ behavior: 'instant', block: 'center' }); }
            catch (e) { try { el.scrollIntoView({ block: 'center' }); } catch (e2) {} }
            setTimeout(function () {
                // 竞态守卫：scrollIntoView 的延迟窗口内用户可能已打开使用说明/历史等弹窗
                //（showIntro 里的 coachEnd 会清场），此时不能再重建遮罩——否则气泡压在弹窗上、
                // 指向错位（2026-09-30 截图实测撞车）。
                if (_coachEnded) return;
                if (!document.getElementById('wbCoachVeil')) {
                    var veil = document.createElement('div');
                    veil.id = 'wbCoachVeil';
                    // 遮罩盖住整屏，用户第一次点顶栏（背景/历史/使用说明）会被它吃掉，
                    // 体感就是「点了没反应」。这里做穿透：先临时让遮罩不接收事件，
                    // 看落点底下是不是顶栏里的按钮 —— 是就结束引导并把这个点击转给它。
                    veil.addEventListener('click', function (ev) {
                        var under = null;
                        try {
                            veil.style.pointerEvents = 'none';
                            under = document.elementFromPoint(ev.clientX, ev.clientY);
                        } catch (e) {}
                        finally { veil.style.pointerEvents = ''; }
                        try {
                            if (under && under !== veil && under.closest && under.closest('#wbTopTools')) {
                                coachEnd();
                                under.click();
                                return;
                            }
                        } catch (e) {}
                        coachEnd();
                    });
                    document.body.appendChild(veil);
                }
                el.classList.add('wb-coach-target');
                var tip = document.createElement('div');
                tip.id = 'coachTip';
                tip.innerHTML =
                    '<div>' + step.text + '</div>' +
                    '<div style="margin-top: 10px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">' +
                        '<span style="font-size: 12.5px; color: #aab8de; flex: none;">' +
                            (_coachIdx + 1) + ' / ' + COACH_STEPS.length + '</span>' +
                        '<button onclick="coachNext()" style="padding: 6px 14px; background: var(--c-a); color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; flex: none;">知道了</button>' +
                        '<span onclick="coachEnd()" style="font-size: 12.5px; color: #cdd6f2; cursor: pointer; flex: none;">跳过</span>' +
                        '<span style="font-size: 12px; color: #aab8de; flex: 1 1 100%;">点暗处或按 Esc 也可退出</span>' +
                    '</div>';
                document.body.appendChild(tip);
                coachRepos();
                // 引导期间持续跟踪：滚动/视口变化（地址栏收起）/sticky 重新吸附都实时重算
                window.addEventListener('scroll', _coachTrack, { passive: true });
                window.addEventListener('resize', _coachTrack);
                try { if (window.visualViewport) window.visualViewport.addEventListener('resize', _coachTrack); } catch (e) {}
                el.addEventListener('click', function _once() {
                    el.removeEventListener('click', _once);
                    coachNext();
                });
            }, 380);
        }

        function coachRepos() {
            var tip = document.getElementById('coachTip');
            if (!tip) return;
            var step = COACH_STEPS[_coachIdx];
            var el = step && document.getElementById(step.id);
            if (!el) return;
            var r = el.getBoundingClientRect();
            var th = tip.offsetHeight || 90, tw = tip.offsetWidth || 260;
            var below = true;
            var top = r.bottom + 10;
            var vh = (typeof wbViewportHeight === 'function') ? wbViewportHeight() : window.innerHeight;
            if (top + th > vh - 12) { top = r.top - th - 10; below = false; }
            if (top < 8) top = 8;
            var left = Math.max(10, Math.min(r.left, window.innerWidth - tw - 10));
            tip.style.top = top + 'px';
            tip.style.left = left + 'px';
            tip.className = below ? 'coach-below' : 'coach-above';
        }

        function coachNext() { _coachIdx++; coachShow(); }

        function coachEnd() {
            _coachClear();
            _coachEnded = true;
            try { document.removeEventListener('keydown', _coachEsc); } catch (e) {}
            try { _wbStoreSet('wbCoachDone', '1'); } catch (e) {}
            // cookie 兜底：微信/QQ 内置浏览器、隐私模式下 localStorage 可能不持久，
            // 导致引导每次都弹。cookie 多一层保障，任一命中就不再弹。
            try { document.cookie = 'wbCoachDone=1; max-age=31536000; path=/'; } catch (e) {}
        }

        /* ---------- 首页三步引导（常驻卡片，不是弹窗） ---------- */
        // 「① 输创意 ② 选档位 ③ 点生成」三步写在首屏，点一步就跳到对应位置；
        // 做到了自动打勾，三步都做完折叠成一行，记进 localStorage，老用户不再占地方。
        var WB_GUIDE_KEY = 'wbGuideDone';
        var WB_GUIDE_SEL = ['#idea', '.version-card', '#startBtn'];
        var _wbGuide = [false, false, false];

        function _wbGuideSave() { try { _wbStoreSet(WB_GUIDE_KEY, JSON.stringify(_wbGuide)); } catch (e) {} }

        function wbGuidePaint() {
            for (var i = 0; i < 3; i++) {
                var el = document.getElementById('wbGuideStep' + i);
                if (el) el.classList.toggle('is-done', !!_wbGuide[i]);
            }
        }
        function wbGuideDone(i) {
            if (_wbGuide[i]) return;
            _wbGuide[i] = true;
            wbGuidePaint();
            _wbGuideSave();
            if (_wbGuide[0] && _wbGuide[1] && _wbGuide[2]) {
                setTimeout(function () { wbGuideCollapse(); }, 1400);
            }
        }
        function wbGuideCollapse() {
            var g = document.getElementById('wbGuide'), b = document.getElementById('wbGuideBar');
            if (g) g.style.display = 'none';
            if (b) b.style.display = 'flex';
        }
        // 手机上默认收起三步引导：实测它占掉首屏 546px，把创意输入框挤到
        // 屏幕外（要滚 760px 才看得见）。评委进来要一眼看到输入区，不是先看教程。
        // 收起后 wbGuideBar 那一行还留着「展开三步」，想看随时能展开。
        (function () {
            try {
                if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches
                    && !_wbStoreGet('wbGuideKeep')) {
                    wbGuideCollapse();
                }
            } catch (e) {}
        })();
        function wbGuideExpand() {
            var g = document.getElementById('wbGuide'), b = document.getElementById('wbGuideBar');
            if (g) g.style.display = '';
            if (b) b.style.display = 'none';
            _wbGuide = [false, false, false];
            wbGuidePaint();
            _wbGuideSave();
        }
        // 点引导卡片：滚到对应位置并让目标闪一下（用背景闪烁而不是外发光，
        // 因为 .card 是 overflow:hidden，外发光会被裁掉看不见）
        function wbGuideGo(i) {
            var el = document.querySelector(WB_GUIDE_SEL[i]);
            if (!el) return;
            try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
            el.classList.remove('wb-guide-flash');
            void el.offsetWidth;
            el.classList.add('wb-guide-flash');
            setTimeout(function () { el.classList.remove('wb-guide-flash'); }, 1700);
            if (i === 0) { try { document.getElementById('idea').focus(); } catch (e) {} }
        }
        /* ---------- 微信 / QQ 内置浏览器：打开就提示，不等用户踩坑 ---------- */
        // 这些内核：不支持上传文件、复制、下载。必须一进页面就说清楚 + 给复制网址的出口，
        // 否则用户会一直卡在"传不了 / 下不了"，还以为是我们坏了。
        function wbUaKind() {
            var ua = navigator.userAgent || '';
            if (/micromessenger/i.test(ua)) return 'wechat';
            if (/\bqq\//i.test(ua) || (/mqqbrowser/i.test(ua) && !/micromessenger/i.test(ua))) return 'qq';
            if (/\bweibo/i.test(ua)) return 'weibo';
            if (/dingtalk/i.test(ua)) return 'dingtalk';
            return '';
        }
        function wbUaCheck() {
            var k = wbUaKind();
            if (!k) return false;
            try { if (sessionStorage.getItem('wbUaTip') === '1') return true; } catch (e) {}
            var m = document.getElementById('wbUaMask');
            if (!m) return true;
            var who = {wechat: '微信', qq: 'QQ', weibo: '微博', dingtalk: '钉钉'}[k] || '内置浏览器';
            var el = document.getElementById('wbUaWho');
            // 166 轮：这里原来列「这三件事做不了：」再配三条清单，弹窗一屏塞不下。
            // 现在只留一行说清后果，细节折进「查看详细说明」
            if (el) el.textContent = who + '里上传只能选图片/视频，Word、PDF、PPT 也下载不下来';
            var t = document.getElementById('wbUaMaskTitle');
            if (t) t.textContent = who + '里用不了上传和下载';
            m.className = 'on';
            return true;
        }
        // 166 轮：三个行动之一。微信里 JS 跳不出去（scheme 会被拦），所以只做「指引 + 兜底复制」：
        // 把右上角箭头晃一下让人知道点哪，同时把网址复制好，切换浏览器后可直接粘贴
        function wbUaOpenBrowser() {
            var ar = document.querySelector('#wbUaMask .wb-ua-arrow');
            if (ar) {
                ar.style.transition = 'transform .18s';
                var n = 0;
                var iv = setInterval(function () {
                    n++;
                    ar.style.transform = n % 2 ? 'scale(1.25)' : 'scale(1)';
                    if (n >= 6) { clearInterval(iv); ar.style.transform = 'scale(1)'; }
                }, 180);
            }
            wbUaCopy();
            wbToast('请点右上角 ··· → 在浏览器打开；网址已复制好', { type: 'warn', ms: 4200 });
        }
        // 166 轮：不换浏览器也能继续——直接把已有材料文字贴进来，绕开上传限制
        function wbUaPaste() {
            wbUaClose();
            try { wbMatOpen(); } catch (e) {}
            setTimeout(function () {
                var ta = document.getElementById('wbMatText');
                if (ta) { ta.focus(); try { ta.scrollIntoView({ block: 'center' }); } catch (e2) {} }
            }, 260);
        }
        function wbUaClose() {
            var m = document.getElementById('wbUaMask');
            if (m) m.className = '';
            try { sessionStorage.setItem('wbUaTip', '1'); } catch (e) {}
        }
        function wbUaCopy() {
            var url = location.href;
            function ok() { wbToast('网址已复制，去浏览器里粘贴打开', {type: 'ok', ms: 3200}); }
            function fallback() {
                try {
                    var ta = document.createElement('textarea');
                    ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
                    document.body.appendChild(ta); ta.select();
                    document.execCommand('copy'); document.body.removeChild(ta); ok();
                } catch (e) { wbToast('复制失败，请手动长按地址栏复制网址', {type: 'warn', ms: 3600}); }
            }
            // 微信里 navigator.clipboard 常常不可用，必须留 execCommand 兜底
            if (navigator.clipboard && navigator.clipboard.writeText) {
                try { navigator.clipboard.writeText(url).then(ok, fallback); } catch (e) { fallback(); }
            } else { fallback(); }
        }
        // 供下载逻辑判断：内置浏览器里点了下载只会"没反应"，要弹提示而不是静默失败
        function wbInApp() { return !!wbUaKind(); }

        // 上传兜底：点「上传」之前先判能不能用。命中内置浏览器就别让用户白选一轮文件，
        // 命中旧版 .doc 也提前说清（后端只读 pdf/docx/txt/md，选 .doc 必然失败）。
        function wbUploadGuard(inputId) {
            var el = document.getElementById(inputId);
            if (!el) return;
            el.addEventListener('click', function (ev) {
                var k = wbUaKind();
                if (!k) return;
                ev.preventDefault();
                ev.stopPropagation();
                wbUaCheck();
            }, true);
            el.addEventListener('change', function (ev) {
                var f = ev.target.files && ev.target.files[0];
                if (!f) return;
                var nm = String(f.name || '');
                var ext = (nm.match(/\.[^.]+$/) || [''])[0].toLowerCase();
                if (ext === '.doc') {
                    ev.target.value = '';
                    wbToast('旧版 .doc 读不了：请在 Word 里「另存为 .docx」再上传，或直接粘贴文字', {type: 'warn', ms: 4200});
                }
            });
        }

        function wbGuideInit() {
            var g = document.getElementById('wbGuide');
            if (!g) return;
            try {
                var s = JSON.parse(_wbStoreGet(WB_GUIDE_KEY) || 'null');
                if (s && s.length === 3) _wbGuide = [!!s[0], !!s[1], !!s[2]];
            } catch (e) {}
            wbGuidePaint();
            if (_wbGuide[0] && _wbGuide[1] && _wbGuide[2]) wbGuideCollapse();
            // 做过的动作自动打勾：不靠用户回来点
            var idea = document.getElementById('idea');
            if (idea) idea.addEventListener('input', function () {
                if (String(idea.value || '').trim().length >= 4) wbGuideDone(0);
            });
            var draft = document.getElementById('proposal_draft');
            if (draft) draft.addEventListener('input', function () {
                if (String(draft.value || '').trim().length >= 4) wbGuideDone(0);
            });
            var f = document.getElementById('ideaFile');
            if (f) f.addEventListener('change', function () { wbGuideDone(0); });
            var radios = document.querySelectorAll('input[name="mode"]');
            for (var i = 0; i < radios.length; i++) {
                radios[i].addEventListener('change', function () { wbGuideDone(1); });
            }
            var sb = document.getElementById('startBtn');
            if (sb) sb.addEventListener('click', function () { wbGuideDone(2); });
        }

        /* ---------- 一键回到生成内容 ---------- */
        // 结果区很长（评分 / 自查 / 校验 / 正文 / 图表…），读到一半想换栏目得手动往上滑很久。
        // 这个按钮直接切到「申报与评审」并滚回结果区顶部的栏目栏。
        function wbBackToResult() {
            var t = document.getElementById('proposalTab');
            if (t) { try { t.click(); } catch (e) {} }
            var head = document.getElementById('resultTabs') || document.getElementById('resultArea');
            if (!head) return;
            try { head.scrollIntoView({behavior: 'smooth', block: 'start'}); }
            catch (e) { window.scrollTo(0, 0); }
            try { if (document.getElementById('wbFab').className.indexOf('open') >= 0) wbFabToggle(); } catch (e) {}
        }

        /* ---------- 悬浮导出按钮 ---------- */
        // 顶部的导出条滚过去就看不见了，这个按钮跟着页面走，随时能点
        function wbFabToggle() {
            var f = document.getElementById('wbFab');
            if (f) f.classList.toggle('open');
        }
        function wbFabShow(hasPpt) {
            var f = document.getElementById('wbFab');
            if (!f) return;
            f.style.display = 'flex';
            var p = document.getElementById('wbFabPpt');
            if (p) p.style.display = hasPpt ? '' : 'none';
            if (window.wbDockSync) { try { window.wbDockSync(); } catch (e) {} }
        }
        function wbFabHide() {
            var f = document.getElementById('wbFab');
            if (!f) return;
            f.style.display = 'none';
            f.classList.remove('open');
        }
        // 顶部固定导出条：结果区顶部那条一滚出视口就贴上来（翻到哪都能点），
        // 滚回去或者没生成结果时自动收起，不挡内容
        function wbDockInit() {
            var bar = document.getElementById('quickExportBar');
            var dock = document.getElementById('wbExportDock');
            if (!bar || !dock) return;
            var sync = function () {
                var ra = document.getElementById('resultArea');
                var hasResult = !!ra && ra.style.display !== 'none';
                if (!hasResult || window._wbGenerating) { dock.style.display = 'none'; return; }
                var out;
                if (bar.offsetParent !== null) {          // 顶部那条正常显示时，看它有没有滚出去
                    out = bar.getBoundingClientRect().bottom < 8;
                } else {
                    // 顶部那条没显示（隐藏 / 换皮肤）时按结果区顶部算，
                    // 保证任何赛事、任何档位都有顶部导出，不会某个比赛下就消失
                    out = ra.getBoundingClientRect().top < 8;
                }
                dock.style.display = out ? 'flex' : 'none';
            };
            window.addEventListener('scroll', sync, { passive: true });
            window.addEventListener('resize', sync);
            if ('IntersectionObserver' in window) {
                try { new IntersectionObserver(sync, { threshold: 0 }).observe(bar); } catch (e) {}
            }
            window.wbDockSync = sync;      // 生成完 / 打开历史后要手动刷一次
            sync();
        }
        // 结果区顶部「PPT / 分项下载 →」：直接切到导出中心页签
        function wbGoExport() {
            var t = document.getElementById('exportTab');
            if (t) t.click();
            var ra = document.getElementById('resultArea');
            if (ra) { try { ra.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {} }
        }

        /* ---------- 智能识别：从项目创意反推该报哪个赛事 ---------- */
        // 用户抱怨「要拉列表找半天」，最省事的做法是他写完创意我们就猜一个。
        // 关键词取长不取短：命中「数学建模」就不该被「建模」盖过去。
        var WB_IDEA_COMP = [
            {name: 'iCAN大学生创新创业大赛', kw: ['ican', '物联网', '智能硬件', '传感器', '可穿戴']},
            {name: '中国国际互联网+大学生创新创业大赛', kw: ['互联网+', '互联网＋', '商业计划', '融资', '路演', '商业模式']},
            {name: '全国大学生数学建模竞赛', kw: ['数学建模', '数模', '数学模', '优化模型', '预测模型', '评价体系']},
            {name: '全国大学生电子设计竞赛', kw: ['电子设计', '电赛', '单片机', '电路设计', '嵌入式', '硬件设计']},
            {name: '挑战杯全国大学生课外学术科技作品竞赛', kw: ['大挑', '课外学术科技', '学术作品', '调研报告', '社会调查']},
            {name: '挑战杯中国大学生创业计划竞赛（小挑）', kw: ['小挑', '创业计划竞赛']},
            {name: '国家级大学生创新创业训练计划', kw: ['国创', '大创', '创新创业训练']},
            {name: '全国大学生广告艺术大赛', kw: ['大广赛', '广告艺术', '品牌策划', '视觉传达', '海报设计']},
            {name: '中国大学生服务外包创新创业大赛', kw: ['服务外包']},
            {name: '蓝桥杯全国软件和信息技术专业人才大赛', kw: ['蓝桥杯', '算法竞赛', '程序设计竞赛']},
            {name: '全国大学生信息安全竞赛', kw: ['信息安全', '网安', '网络安全', '攻防', '漏洞']},
            {name: '中国大学生计算机设计大赛', kw: ['计算机设计', '软件作品', '应用系统']},
            {name: 'RoboMaster全国大学生机器人大赛', kw: ['robomaster', '机器人', '机甲', '机械臂']},
            {name: '西门子杯中国智能制造挑战赛', kw: ['西门子', '智能制造', '工业自动化', '产线']}
        ];
        // 只在赛事框空着时自动填：用户已经选过就别自作主张改掉
        function wbAutoComp() {
            var el = document.getElementById('competition');
            var idea = document.getElementById('idea');
            if (!el || !idea) return;
            if (String(el.value || '').trim()) return;
            var t = String(idea.value || '').toLowerCase();
            if (t.replace(/\s/g, '').length < 10) return;      // 太短猜不准，别乱填
            var best = '', bestLen = 0;
            WB_IDEA_COMP.forEach(function (m) {
                (m.kw || []).forEach(function (k) {
                    var kk = String(k).toLowerCase();
                    if (kk.length >= 2 && t.indexOf(kk) >= 0 && kk.length > bestLen) {
                        bestLen = kk.length; best = m.name;
                    }
                });
            });
            if (!best) return;
            el.value = best;
            wbCompInput();
            onCompetitionChange();
            wbSaveForm();
            var tip = document.getElementById('compAutoTip');
            if (tip) {
                tip.style.display = 'block';
                tip.innerHTML = '按你的创意自动选为 <b style="color: var(--text);">' + _esc(best) +
                    '</b>，不对就点右边 × 改。';
            }
        }

        /* ---------- 赛事选择：输入即过滤 + 一键清空 ---------- */
        var _compOpts = null;
        // 同一个赛事在不同来源里写法不一样：datalist 是「RoboMaster全国大学生机器人大赛」，
        // 知识库索引的 title 是「RoboMaster 全国大学生机器人大赛」，还有带引号的
        // 「"挑战杯" 中国大学生创业计划竞赛（小挑）」和带副标题后缀的「…（高教社杯）」。
        // 不去归一化的话下拉里会出现两条看着一样的赛事。尾部括号后缀一并剥掉
        // （「…（小挑）」与「…」指的是同一个比赛，但括号在中间时不剥）。
        function _compNorm(s) {
            var t = String(s || '').replace(/\s+/g, '').replace(/[""''「」《》]/g, '').toLowerCase();
            var prev;
            do { prev = t; t = t.replace(/[（(][^（()）]*[）)]$/, ''); } while (t !== prev);
            return t;
        }
        function wbCompOptions() {
            if (_compOpts) return _compOpts;
            var os = document.querySelectorAll('#competitionList option');
            _compOpts = Array.prototype.map.call(os, function (o) { return o.value; });
            // 知识库索引里收录的赛事也算候选（后端 data/*.txt 加了新赛事，下拉要能选到）。
            // 两个坑：① WB_COMP_INDEX 是 {version, items}，不是数组，直接 forEach 会抛错被 catch 吞掉，
            // 结果索引里的赛事一个都进不来；② item 的赛事名在 title 字段（没有 name）。
            // 另外 title 常带空格（"RoboMaster 全国…"）而 datalist 不带，必须去空格后去重，
            // 否则下拉里会出现两条看着一样的赛事。
            try {
                var idx = window.WB_COMP_INDEX;
                var arr = (idx && idx.items) ? idx.items : (Object.prototype.toString.call(idx) === '[object Array]' ? idx : []);
                var have = {};
                _compOpts.forEach(function (n) { have[_compNorm(n)] = 1; });
                arr.forEach(function (it) {
                    var nm = it && (it.name || it.title);
                    if (!nm) return;
                    var k = _compNorm(nm);
                    if (!k || have[k]) return;
                    have[k] = 1;
                    _compOpts.push(nm);
                });
            } catch (e) {}
            // 数量明示（第八十四轮催办）：写死数字迟早和清单脱节，直接回填真实条数。
            // 卡片是懒渲染的，此刻 #compCountNum 可能还没进 DOM，所以取不到就跳过、不报错。
            var _cn = document.getElementById('compCountNum');
            if (_cn) _cn.textContent = String(_compOpts.length);
            return _compOpts;
        }
        function wbCompHits(q) {
            q = String(q || '').trim().toLowerCase();
            var all = wbCompOptions();
            // 不再截断：原来 slice(0,8) 把 15 个内置赛事砍掉 7 个，
            // 空查询时下拉里永远看不到后面的比赛（P1-3「后面的比赛选不到」的另一个根因）。
            // 候选框本身 max-height 264px + 纵向滚动，全量列出不会撑破页面
            if (!q) return all;
            return all.filter(function (n) {
                return String(n).toLowerCase().indexOf(q) >= 0;
            });
        }
        // 聚焦就全选：选错了不用一个个删字，直接打字就整体替换掉旧赛事名。
        // 不直接清空 value 是因为那样一点进去内容就没了，误触会丢已填的东西。
        function wbCompFocus() {
            var el = document.getElementById('competition');
            if (el && String(el.value || '').trim()) {
                try { el.select(); } catch (e) {}
            }
            wbCompOpen();
        }
        /* 空查询时按「类型」分组：15 项一长条在小屏上滚不到底也分不清性质，
           分组头只作视觉分隔、不可点，点击行为仍在赛事名上（wbCompFill）。
           类型以后端 data/competition_profiles.json 的 type 为准；
           配置还没拉到 / 只有一类 / 正在搜索时，回落成原来的平铺，行为不变。 */
        var WB_COMP_TYPE_ORDER = ['工程创新类', '创新创业类', '学术类', '创新训练类', '建模类', '工科类', '经管类'];
        // 不用 wbMatchProfile：它对「挑战杯」这类 3 字泛称只取第一个命中，
        // 会把「小挑（创业计划）」分进「学术类（大挑）」——大挑小挑性质完全不同，
        // 分错类比不分更误导。这里改成「取最长覆盖」：短别名（<4 字）一律不参与。
        function wbCompTypeOf(name) {
            var n = String(name || '').toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
            if (!n) return '';
            var best = null, bs = 0;
            (WB_COMP_PROFILES || []).forEach(function (it) {
                var keys = [it.name].concat(it.aliases || []);
                keys.forEach(function (k) {
                    var kk = String(k || '').toLowerCase().replace(/[""'']/g, '').replace(/\s+/g, '');
                    if (kk.length < 4) return;
                    var s = 0;
                    if (n === kk) s = 1000;
                    else if (n.indexOf(kk) >= 0 || kk.indexOf(n) >= 0) s = Math.min(kk.length, n.length);
                    if (s > bs) { bs = s; best = it; }
                });
            });
            return (best && best.type) ? String(best.type) : '';
        }
        function wbCompGroups(hits) {
            var buckets = {}, seen = [];
            hits.forEach(function (n) {
                var t = wbCompTypeOf(n) || '其它';
                if (!buckets[t]) { buckets[t] = []; seen.push(t); }
                buckets[t].push(n);
            });
            seen.sort(function (a, b) {
                var ia = WB_COMP_TYPE_ORDER.indexOf(a), ib = WB_COMP_TYPE_ORDER.indexOf(b);
                return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
            });
            return seen.map(function (t) { return { type: t, items: buckets[t] }; });
        }
        // 赛事简称：15 个赛事各一个，做视觉锚点帮快速识别。
        // 键故意取「有区分度的片段」而不是泛称——「挑战杯」三个字大挑小挑都含，
        // 用它当键会把「小挑（创业计划）」错配成大挑。
        // 原先这里是 emoji（第十七轮 #1 全站去 emoji）：老安卓/微信内置内核里
        // emoji 会显示成豆腐块，一眼看上去像页面没做完，改用文字简称更稳。
        var WB_COMP_SHORT = [
            ['ican', 'iCAN'],
            ['互联网', '互联网+'],
            ['课外学术科技作品', '大挑'],
            ['创业计划', '小挑'],
            ['创新创业训练计划', '国创'],
            ['数学建模', '数模'],
            ['电子设计', '电赛'],
            ['西门子', '西门子杯'],
            ['计算机设计', '计算机设计'],
            ['蓝桥杯', '蓝桥杯'],
            ['robomaster', 'RoboMaster'],
            ['信息安全', '信安'],
            ['服务外包', '服务外包'],
            ['广告艺术', '大广赛'],
            ['金砖', '金砖']
        ];
        function wbCompShort(name) {
            var n = String(name || '').toLowerCase().replace(/[\s""'']/g, '');
            if (!n) return '';
            if (n.indexOf('国创') >= 0) return '国创';
            var best = '', bl = 0;
            WB_COMP_SHORT.forEach(function (p) {
                if (n.indexOf(p[0]) >= 0 && p[0].length > bl) { bl = p[0].length; best = p[1]; }
            });
            return best;
        }

        function wbCompItemHtml(n, cur) {
            var on = (String(n).trim() === String(cur || '').trim());
            return '<div data-wbcomp="' + _esc(n) + '" ontouchstart="" onclick="wbCompFill(this.getAttribute(\'data-wbcomp\'))" ' +
                'style="padding: 9px 12px; font-size: 13px; cursor: pointer; border-bottom: 1px solid var(--line); ' +
                'color: ' + (on ? 'var(--c-a)' : 'var(--text)') + '; ' +
                'background: ' + (on ? 'var(--surface-2)' : 'transparent') + ';">'
                // 下拉项显示赛事全名（用户要按全名确认），不再拼 emoji/简称前缀
                + _esc(n) + '</div>';
        }
        // forceAll：忽略输入框当前内容，列出全部赛事。
        // 「全部赛事 ▾」必须走这条路——否则输入框里已填了赛事时，点它只会列出匹配当前值的
        // 那 1 条，用户想要"看看都有啥比赛"反而看不到（第三十二轮刺的另一半根因）。
        function wbCompOpen(forceAll) {
            var el = document.getElementById('competition');
            var box = document.getElementById('compSuggest');
            if (!el || !box) return;
            var hits = wbCompHits(forceAll ? '' : el.value);
            if (!hits.length) { box.style.display = 'none'; return; }
            var q = forceAll ? '' : String(el.value || '').trim();
            var gs = (q || !WB_COMP_PROFILES || !WB_COMP_PROFILES.length) ? null : wbCompGroups(hits);
            if (gs && gs.length >= 2) {
                box.innerHTML = gs.map(function (g) {
                    // 第八十五轮【低】刺：分组头原来用 var(--muted)——全站没定义这个变量，
                    // 颜色声明非法被静默丢弃，分组头就继承了正文色，看着跟赛事条目一模一样。
                    // 顺手把它做成真正的「分组标题」：加粗 + 字距 + 吸顶，与可点条目明显分层。
                    return '<div data-wbgroup="1" style="position: sticky; top: 0; padding: 8px 12px 4px; font-size: 11px; font-weight: 700; letter-spacing: 1px; ' +
                        'color: var(--text-mute); background: var(--surface-2); border-bottom: 1px solid var(--line); cursor: default;">' +
                        _esc(g.type) + ' · ' + g.items.length + ' 个</div>' +
                        g.items.map(function (n) { return wbCompItemHtml(n, q); }).join('');
                }).join('');
            } else {
                box.innerHTML = hits.map(function (n) { return wbCompItemHtml(n, q); }).join('');
            }
            box.style.display = 'block';
            var clr = document.getElementById('compClear');
            if (clr) clr.style.display = String(el.value || '').trim() ? 'block' : 'none';
        }
        function wbCompClose() {
            var box = document.getElementById('compSuggest');
            if (box) box.style.display = 'none';
        }
        function wbCompInput() {
            var el = document.getElementById('competition');
            var clr = document.getElementById('compClear');
            if (clr && el) clr.style.display = String(el.value || '').trim() ? 'block' : 'none';
            wbCompOpen();
        }
        function wbCompFill(name) {
            var el = document.getElementById('competition');
            if (!el) return;
            el.value = name || '';
            wbCompClose();
            wbCompInput();
            onCompetitionChange();
            wbSaveForm();
        }
        function wbCompClear() {
            var el = document.getElementById('competition');
            if (!el) return;
            // 误触治理：#compClear 是赛事标签区里一个紧跟标签的小控件，手指滑动很容易带倒，
            // 清掉的是「所选赛事 + 依赖它的规则/章节配置」，代价比看起来大 → 加一道确认。
            var _cur = String(el.value || '').trim();
            if (_cur && !window.confirm('确定清空已选赛事「' + _cur + '」？\n\n清空后需要重新选择赛事。')) return;
            el.value = '';
            wbCompClose();
            var clr = document.getElementById('compClear');
            if (clr) clr.style.display = 'none';
            var tip = document.getElementById('compAutoTip');
            if (tip) { tip.style.display = 'none'; tip.innerHTML = ''; }
            onCompetitionChange();
            wbSaveForm();
            try { el.focus(); } catch (e) {}
        }
        // 「全部赛事 ▾」：把完整 15 项下拉拉出来（datalist 在微信/QQ 内核不可靠，走自绘候选）
        function wbCompAll() {
            var el = document.getElementById('competition');
            if (!el) return;
            try { el.focus(); } catch (e) {}
            try { el.select(); } catch (e) {}
            wbCompOpen(true);   // 传 true：列全部 15 项，而不是只列匹配当前输入的那些
        }
        // 第三十二轮刺：按钮 onclick 调 wbCompAll，但函数只存在于 IIFE 里没挂 window
        // → ReferenceError，点了完全没反应（和 switchScoreTab 同一个坑，已踩第三次）。
        // 顺手把这一簇赛事交互函数全部显式挂出去，避免下一个又漏。
        window.wbCompAll = wbCompAll;
        window.wbCompOpen = wbCompOpen;
        window.wbCompClose = wbCompClose;
        window.wbCompInput = wbCompInput;
        window.wbCompKey = wbCompKey;
        window.wbPickComp = wbPickComp;
        function wbCompKey(e) {
            if (e.key === 'Escape') { wbCompClose(); return; }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                var box = document.getElementById('compSuggest');
                if (!box || box.style.display === 'none') { wbCompOpen(); return; }
                // 只遍历可点的赛事名，分组头（data-wbgroup）跳过，否则上下键会停在分隔条上
                var items = box.querySelectorAll('[data-wbcomp]');
                var cur = -1;
                for (var i = 0; i < items.length; i++) {
                    if (items[i].style.background && items[i].style.background !== 'transparent') cur = i;
                }
                var nxt = (e.key === 'ArrowDown') ? cur + 1 : cur - 1;
                if (nxt < 0) nxt = items.length - 1;
                if (nxt >= items.length) nxt = 0;
                for (var j = 0; j < items.length; j++) {
                    items[j].style.background = (j === nxt) ? 'var(--surface-2)' : 'transparent';
                }
            }
        }
        // 点页面别处关闭；延时是因为 blur 会先于候选项的 click 触发
        document.addEventListener('click', function (e) {
            var box = document.getElementById('compSuggest');
            var el = document.getElementById('competition');
            if (!box || !el) return;
            if (box.contains(e.target) || el.contains(e.target)) return;
            // 「全部赛事 ▾」就在输入框外面，它那一次 click 会冒泡到这里：
            // 于是 wbCompAll 刚把下拉打开、这里立刻 wbCompClose 关掉，用户看到的就是
            // 「点了完全没反应」（第三十二轮刺的根因，不是没绑函数）。
            // 这个按钮是专门用来展开下拉的，必须放行。
            // 106-3：数量说明行（compCountHint）整行也可点展开，同属放行名单——
            // 不放行的话点它就是「开了又被这里关掉」，等于没加。
            var _trig = ['wbCompAllBtn', 'compCountHint'];
            for (var _ti = 0; _ti < _trig.length; _ti++) {
                var _t = document.getElementById(_trig[_ti]);
                if (_t && (_t === e.target || _t.contains(e.target))) return;
            }
            wbCompClose();
        });

        // 点热门赛事 chip 填入，并触发一次知识库状态刷新
        /* ---- 常用赛事置顶（第一百零二/一百零四轮）----
           用户用得最多的赛事应该排在快捷标签最前面，而不是写死 iCAN 第一。
           次数记 localStorage（本机记忆，不上传），无记录时保持页面原有顺序。
           「全部赛事 ▾」是兜底入口，永远排最后，不参与排序。 */
        function wbCompUsage() {
            try { return JSON.parse(_wbStoreGet('wbCompUsage') || '{}') || {}; } catch (e) { return {}; }
        }
        function wbCompUse(name) {
            if (!name) return;
            var u = wbCompUsage();
            u[name] = (u[name] || 0) + 1;
            try { _wbStoreSet('wbCompUsage', JSON.stringify(u)); } catch (e) {}
        }
        function wbCompReorderChips() {
            var row = document.getElementById('compQuickRow');
            if (!row) return;
            var chips = Array.prototype.slice.call(row.children);
            var pinned = null, pickable = [], others = [];
            chips.forEach(function (c) {
                if (c.id === 'wbCompAllBtn') { pinned = c; return; }   // 兜底入口永远殿后
                if (c.getAttribute('data-comp')) pickable.push(c); else others.push(c);
            });
            if (!pinned || pickable.length < 2) return;
            var u = wbCompUsage();
            var base = pickable.map(function (c, i) { return { el: c, i: i, n: u[c.getAttribute('data-comp')] || 0 }; });
            base.sort(function (a, b) { return (b.n - a.n) || (a.i - b.i); });   // 次数降序，同次数保持原序
            base.forEach(function (o) { row.appendChild(o.el); });
            others.forEach(function (c) { row.appendChild(c); });
            row.appendChild(pinned);
        }

        function wbPickComp(name) {
            var el = document.getElementById('competition');
            if (!el) return;
            el.value = name;
            wbCompUse(name);            // 记一次使用，下次这个标签自动排到最前
            wbCompReorderChips();
            try { el.dispatchEvent(new Event('change')); } catch (e) {}
            onCompetitionChange();
            wbSaveForm();
        }

        // ---- 知识库状态面板（数据来源 /api/knowledge_status）----
        var _kbState = null;                    // 原始返回，避免重复请求
        async function loadKnowledgeStatus() {
            try {
                const res = await _wbFetch('/api/knowledge_status');
                const d = await res.json();
                if (d && d.success) _kbState = d;
            } catch (e) { _kbState = null; }
            renderKbStatus();
            return _kbState;
        }
        // 与后端 get_competition_knowledge 保持一致：文件名与赛事名互为子串即命中
        function _kbMatch(fname, comp) {
            return !!comp && (String(comp).indexOf(fname) >= 0 || String(fname).indexOf(comp) >= 0);
        }
        // 逐个下拉选项算出命中的知识库文件
        function _kbHitList() {
            var files = ((_kbState && _kbState.files) || []).map(function (f) { return f.name; });
            var sel = document.querySelectorAll('#competition option');
            return Array.prototype.map.call(sel, function (o) {
                var comp = o.value;
                return { comp: comp, hit: files.filter(function (n) { return _kbMatch(n, comp); }) };
            });
        }
        function _kbFileByName(name) {
            return ((_kbState && _kbState.files) || []).filter(function (x) { return x.name === name; })[0] || {};
        }
        function renderKbStatus() {
            var cov = document.getElementById('kbCoverage');
            var cur = document.getElementById('kbCurrent');
            if (!cov || !cur) return;
            if (!_kbState) {
                cov.textContent = '读取失败';
                cov.style.color = 'var(--warn-text)';
                cur.innerHTML = '<span style="color:var(--warn-text);">知识库读取失败，请稍后刷新重试</span>';
                return;
            }
            var list = _kbHitList();
            var okN = list.filter(function (x) { return x.hit.length; }).length;
            cov.textContent = okN + '/' + list.length + ' 赛事已收录资料';
            cov.style.color = okN === list.length ? 'var(--ok)' : 'var(--info-text)';
            var me = (document.getElementById('competition') || {}).value || '';
            var row = list.filter(function (x) { return x.comp === me; })[0] || {hit: []};
            if (row.hit.length) {
                var f = _kbFileByName(row.hit[0]);
                var tail = f.ok
                    ? '<span style="color:var(--ok);">资料格式完整（' + (f.chars || 0) + ' 字）</span>'
                    : '<span style="color:var(--info-text);">已收录，部分章节待补充：' + (f.missing || []).map(_esc).join('、') + '</span>';
                cur.innerHTML = '本次赛事：<b style="color:var(--text);">' + _esc(me) + '</b> → 命中《' + _esc(row.hit[0]) + '》' + tail;
            } else {
                cur.innerHTML = '本次赛事：<b style="color:var(--text);">' + _esc(me) + '</b> → <span style="color:var(--info-text);">未匹配内置知识库，将按通用标准评审</span>';
            }
            renderKbDetail();
        }
        function renderKbDetail() {
            var box = document.getElementById('kbDetail');
            if (!box || !_kbState) return;
            var rows = _kbHitList().map(function (x) {
                var badge, tip;
                if (x.hit.length) {
                    var f = _kbFileByName(x.hit[0]);
                    badge = f.ok
                        ? '<span style="color:var(--ok);">完整</span>'
                        : '<span style="color:var(--info-text);">待补充 ' + (f.missing || []).map(_esc).join('、') + '</span>';
                    tip = '《' + _esc(x.hit[0]) + '》' + (f.chars || 0) + ' 字';
                } else {
                    badge = '<span style="color:var(--text-mute);">未收录</span>';
                    tip = '<span style="color:var(--text-mute);">data/ 下无同名文件</span>';
                }
                return '<div style="display:flex; gap:8px; padding:5px 0; border-bottom:1px dashed var(--line);">' +
                    '<span style="flex:1 1 44%; min-width:0; color:var(--text-dim);">' + _esc(x.comp) + '</span>' +
                    '<span style="flex:0 0 auto;">' + badge + '</span>' +
                    '<span style="flex:1 1 38%; min-width:0; text-align:right; color:var(--text-mute);">' + tip + '</span></div>';
            }).join('');
            var miss = (_kbState.missing || []).map(_esc).join('、');
            box.innerHTML =
                '<div style="color:var(--text-dim); margin-bottom:8px; line-height:1.7;">' +
                '后端统计覆盖率：<b style="color:var(--text);">' + _esc(_kbState.coverage || '-') + '</b>' +
                (miss ? '<br>后端标记缺失：' + miss : '') + '</div>' +
                '<div style="color:var(--text-mute); margin-bottom:8px; line-height:1.6;">' +
                '命中规则：知识库文件名与下拉赛事名<b>互为连续子串</b>才生效（如「iCAN大赛.txt」匹配不上「iCAN大学生创新创业大赛」，须改名「iCAN.txt」）</div>' +
                rows;
        }
        function toggleKbDetail() {
            var box = document.getElementById('kbDetail');
            var ar = document.getElementById('kbArrow');
            if (!box) return;
            var show = box.style.display === 'none';
            box.style.display = show ? 'block' : 'none';
            if (ar) ar.textContent = show ? '▴' : '▾';
        }
        // 赛事 quick-pick 横排 chip 高亮：当前选中的赛事对应 chip 亮成主色，其余保持灰
        function wbSyncCompChips() {
            var cur = String((document.getElementById('competition') || {}).value || '').trim();
            var el = document.getElementById('competition');
            var row = document.getElementById('compQuickRow');
            if (row) {
                var chips = row.children;
                for (var i = 0; i < chips.length; i++) {
                    var sp = chips[i];
                    var m = /wbPickComp\('([^']*)'\)/.exec(sp.getAttribute('onclick') || '');
                    var name = m ? m[1] : '';
                    // 非快捷 chip（末尾「全部赛事 ▾」走 wbCompAll，没有 wbPickComp）
                    // 跳过，否则会把它的虚线强调样式刷成普通灰底
                    if (!name) continue;
                    var on = !!name && name === cur;
                    sp.setAttribute('data-on', on ? '1' : '0');
                    sp.style.background = on ? 'var(--c-a)' : 'var(--surface-2)';
                    sp.style.color = on ? '#fff' : 'var(--text)';
                    sp.style.borderColor = on ? 'var(--c-a)' : 'var(--line)';
                    sp.style.fontWeight = on ? '600' : '400';
                }
            }
            // 输入框本身也给一个「已匹配」描边，选中状态更明显
            if (el) {
                var matched = false;
                try { matched = !!(evCurrent() || {})._idx; } catch (e) {}
                if (matched) el.classList.add('wb-matched'); else el.classList.remove('wb-matched');
            }
        }

        // 页脚赛事名跟着当前赛事走（原来写死 iCAN，切赛事不联动）
        function wbSyncFooterComp() {
            var el = document.getElementById('wbFooterComp');
            var n = wbCompName();
            var s = wbCompShort(n) || String(n || '').trim();
            if (el) el.textContent = s ? (' · 当前赛事：' + s) : '';
            // 结果卡片底部那句感谢（第八十九轮【低】）与页脚同源回填，避免两处各写一份赛事名
            var th = document.getElementById('wbThanksLine');
            if (th) th.textContent = s ? ('感谢使用，祝 ' + s + ' 备赛顺利') : '感谢使用，祝你备赛顺利';
        }
        function onCompetitionChange() {
            wbSyncCompChips();
            wbSyncFooterComp();
            renderKbStatus();
            try { renderEventCard(); } catch (e) {}   // 换赛事 → 要求卡自动换成该赛事的文档类型与章节
            // 换赛事 → 主题重新推荐 + 页序说明/状态条跟着变（数学建模会多两页）
            try { wbRoadLabel(); } catch (e) {}
            try { wbApplyCompTheme(); } catch (e) {}
            if (window._lastData && window._lastData.rich_deck) {
                try { renderRich(window._lastData, true); } catch (e) {}
            }
        }
        window.wbSyncFooterComp = wbSyncFooterComp;
        // 页脚在 app.js 之后才渲染（脚本位于 body 中部），首次同步必须等 DOM 就绪
        (function () {
            var run = function () { try { wbSyncFooterComp(); } catch (e) {} };
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
            else run();
        })();

        // ---- 申报书章节完整性提示（数据来源 generate 返回的 completeness）----
        function renderCompleteness(comp) {
            var box = document.getElementById('completenessBox');
            if (!box) return;
            // 可交付度指标（替代「正文字数」当卖点）：数据支撑点越多越好、待补占位越少越好
            var dp = document.getElementById('dpCount');
            if (dp) dp.innerText = (comp && typeof comp.data_points === 'number') ? comp.data_points : '暂无';
            var ph = document.getElementById('phCount');
            if (ph) {
                var phn = (comp && typeof comp.placeholders === 'number') ? comp.placeholders : null;
                ph.innerText = (phn === null) ? '暂无' : phn;
                ph.style.color = (phn > 0) ? 'var(--warn-text)' : 'var(--ok)';
                ph.title = (phn > 0) ? '正文还有「待补充」占位，导出前必须换成真实数据' : '正文无待补占位';
            }
            var miss = (comp && comp.missing) || [];
            _wbCheckIssues.miss = miss.length;
            wbScoreTabBadge();
            if (!miss.length) { box.style.display = 'none'; return; }
            box.style.display = 'block';
            box.style.background = 'var(--err-bg)';
            box.style.border = '1px solid var(--err-line)';
            box.style.color = 'var(--err-text)';
            box.innerHTML = '<b>⚠ 申报书缺少以下章节：</b>' + miss.map(_esc).join('、') +
                '<br><span style="color:var(--text-mute); font-size:12.5px;">可据此人工补写，或把草稿粘回输入框用深度版重跑一轮（当前正文 ' + (comp.chars || 0) + ' 字）</span>';
        }

        // ---- 字数统计：去掉 Markdown 标记后统计，避免符号把篇幅算虚高 ----
        function plainLen(s) {
            if (!s) return 0;
            return String(s).replace(/[#*`\-\|>\[\]（）()\s]/g, '').length;
        }
        // 在产物标题（content-block 的前一个 h3）旁挂字数标签
        function tagWordCount(divId, text) {
            var box = document.getElementById(divId);
            if (!box) return;
            var h3 = box.previousElementSibling;
            if (!h3 || h3.tagName !== 'H3') return;
            var old = h3.querySelector('.wb-count');
            if (old) old.remove();
            // 口径必须和「复制」「导出 Word」取的是同一份文本，否则标题旁写 1583、
            // 导出出来 7774，用户会以为内容被截断了。渲染后的 innerText 是导出真正用的文本，
            // 优先用它；隐藏 tab 拿不到 innerText 时才回退到原始 Markdown。
            var live = String((box.innerText || '')).trim();
            var n = live ? live.length : plainLen(text);
            if (!n) return;
            var sp = document.createElement('span');
            sp.className = 'wb-count';
            sp.textContent = n + ' 字';
            h3.appendChild(sp);
        }

        // ---- 多专家模拟评审面板（深度版专属，简洁版为空自动隐藏）----
        function _erColor(s) {
            s = Number(s) || 0;
            if (s >= 85) return 'var(--ok)';
            if (s >= 75) return 'var(--c-a)';
            if (s >= 60) return 'var(--c-b)';
            return 'var(--warn-text)';
        }

        function _erBar(score) {
            var s = Math.max(0, Math.min(100, Number(score) || 0));
            return '<span style="display:inline-block; width:74px; height:5px; border-radius:3px; ' +
                'background:var(--line); vertical-align:middle; overflow:hidden;">' +
                '<span style="display:block; width:' + s + '%; height:100%; border-radius:3px; background:' + _erColor(s) + ';"></span></span>';
        }

        // 评分维度明细：judge_scores 带权重，把「86 分」拆成「创新性 30% × 86 → 25.8」。
        // 评委视角最在意「这分数怎么来的」，光一个总数没有说服力。
        // 后端正则解析失败时 score 是 null，显示「—」而不是 0——显示 0 会让学生以为自己拿了零分
        function renderJudgeScores(list) {
            var box = document.getElementById('judgeScoresBox');
            var ul = document.getElementById('judgeScoresList');
            if (!box || !ul) return;
            if (!Array.isArray(list) || !list.length) {
                box.style.display = 'none';
                ul.innerHTML = '';
                return;
            }
            var h = '', sum = 0, wsum = 0;
            list.forEach(function (it) {
                var name = it.name || '维度';
                var w = Number(it.weight) || 0;
                var sc = (it.score === null || it.score === undefined || it.score === '') ? null : Number(it.score);
                if (sc !== null && isNaN(sc)) sc = null;
                var contrib = (sc === null) ? null : sc * w / 100;
                if (contrib !== null) { sum += contrib; wsum += w; }
                var col = (sc === null) ? 'var(--text-mute)' : _erColor(sc);
                h += '<div style="display:flex; align-items:center; gap:10px; margin-bottom:9px; flex-wrap:wrap;">' +
                     '<span style="flex:0 0 88px; font-size:12.5px; color:var(--text-dim);">' + _esc(name) + '</span>' +
                     '<span style="flex:0 0 40px; font-size:11.5px; color:var(--text-mute); text-align:right;">' +
                        (w ? _esc(String(w)) + '%' : '') + '</span>' +
                     '<span style="flex:1; min-width:70px;">' + _erBar(sc === null ? 0 : sc) + '</span>' +
                     '<span style="flex:0 0 34px; text-align:right; font-size:13px; font-weight:700; color:' + col + ';">' +
                        (sc === null ? '<span style="font-weight:400; color:var(--text-mute);">—</span>' : _esc(String(sc))) + '</span>' +
                     '<span style="flex:0 0 60px; text-align:right; font-size:11.5px; color:var(--text-mute);">' +
                        (contrib === null ? '' : '→ ' + contrib.toFixed(1)) + '</span>' +
                     '</div>';
            });
            if (wsum > 0) {
                h += '<div style="margin-top:9px; padding-top:9px; border-top:1px dashed var(--line); ' +
                     'font-size:12px; color:var(--text-mute);">加权合计 ' +
                     '<b style="color:var(--text-dim); font-size:14px;">' + Math.round(sum) + '</b>' +
                     '<span style="margin-left:6px;">（权重合计 ' + _esc(String(wsum)) + '%）</span></div>';
            }
            // 14 个维度平铺出来是一堵墙，一眼看不到重点。
            // 用原生 <details> 折叠：不依赖 JS，最坏情况也只是默认展开，不会失效。
            ul.innerHTML = '<details style="margin-top: 2px;">' +
                '<summary style="cursor: pointer; user-select: none; font-size: 12.5px; color: var(--text-dim);">' +
                '展开 ' + list.length + ' 个评审维度（权重 × 得分 → 加权）</summary>' +
                '<div style="margin-top: 10px;">' + h + '</div></details>';
            box.style.display = 'block';
        }

        // 创意五维雷达图（纯 SVG，不依赖 ECharts）：只看创意本身的强弱。
        // scores = {innovation:{name,score,weight}, feasibility:..., market:..., barrier:..., social:...}
        function renderIdeaRadar(scores, ideaScore) {
            var box = document.getElementById('ideaRadarBox');
            var el = document.getElementById('ideaRadar');
            if (!box || !el) return;
            var dims = [['创新性', 'innovation'], ['可行性', 'feasibility'], ['市场价值', 'market'],
                        ['技术壁垒', 'barrier'], ['社会价值', 'social']];
            var vals = [];
            var any = false;
            dims.forEach(function (d) {
                var o = (scores && scores[d[1]]) || {};
                var sc = (o.score === null || o.score === undefined || o.score === '') ? null : Number(o.score);
                if (sc !== null && isNaN(sc)) sc = null;
                if (sc !== null) { any = true; sc = Math.max(0, Math.min(100, sc)); }
                vals.push({ name: d[0], score: sc });
            });
            if (!any) { box.style.display = 'none'; return; }

            // 184 轮【P1】：画布从 400 加宽到 470、圆心右移到 235。
            // 原尺寸下「可行性 78」这类两位数标签从 x≈354 以 anchor=start 向右画，右端到 409，
            // 超出 viewBox(400) 被 SVG 默认 overflow:hidden 切掉末位字符——用户看到的是
            // 「可行性 7」，评委以为项目可行性只有 7 分。左右各留 35px 余量 + 下面再做边界收拢。
            var W = 470, H = 400, cx = 235, cy = 205, R = 132, N = 5;
            function pt(i, r) {
                var a = -Math.PI / 2 + i * 2 * Math.PI / N;
                return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
            }
            function poly(radius, stroke, fill, sw) {
                var pts = [];
                for (var i = 0; i < N; i++) { var p = pt(i, radius); pts.push(p[0].toFixed(1) + ',' + p[1].toFixed(1)); }
                return '<polygon points="' + pts.join(' ') + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"/>';
            }
            // overflow:visible 兜底：万一标签仍探出 viewBox，也不再被硬裁（数字完整性优先于留白）
            var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block;overflow:visible;" xmlns="http://www.w3.org/2000/svg">';
            // 网格（5 层） + 轴线
            for (var g = 5; g >= 1; g--) {
                svg += poly(R * g / 5, 'rgba(148,163,184,.25)', (g === 5 ? 'rgba(148,163,184,.04)' : 'none'), 1);
            }
            for (var k = 0; k < N; k++) {
                var p0 = pt(k, 0), p1 = pt(k, R);
                svg += '<line x1="' + p0[0] + '" y1="' + p0[1] + '" x2="' + p1[0] + '" y2="' + p1[1] + '" stroke="rgba(148,163,184,.25)" stroke-width="1"/>';
            }
            // 数据多边形
            var dp = [];
            for (var q = 0; q < N; q++) {
                var sc = vals[q].score;
                var r = (sc === null) ? 0 : R * sc / 100;
                var pp = pt(q, r);
                dp.push(pp[0].toFixed(1) + ',' + pp[1].toFixed(1));
            }
            svg += '<polygon points="' + dp.join(' ') + '" fill="rgba(34,211,238,.28)" stroke="#22d3ee" stroke-width="2" stroke-linejoin="round"/>';
            // 顶点 + 标签
            for (var z = 0; z < N; z++) {
                var vp = pt(z, R);
                var vd = pt(z, (vals[z].score === null ? 0 : R * vals[z].score / 100));
                svg += '<circle cx="' + vd[0] + '" cy="' + vd[1] + '" r="3.5" fill="#22d3ee"/>';
                // 标签位置：沿半径外推一点
                var lp = pt(z, R + 30);
                var anchor = 'middle';
                var lx = lp[0];
                // 184 轮：标签先收进安全区再判 anchor——原来只按未收拢的 lx 判断，
                // 靠边的标签会一路画到画布外被切掉末位数字。
                var PAD = 42;                       // 左右各留这么多，够放「可行性 78」
                lx = Math.min(Math.max(lx, PAD), W - PAD);
                if (Math.abs(lx - cx) < 30) anchor = 'middle';
                else if (lx < cx) anchor = 'end';
                else anchor = 'start';
                var scTxt = (vals[z].score === null) ? '—' : Math.round(vals[z].score);
                svg += '<text x="' + lx + '" y="' + (lp[1] + 4) + '" text-anchor="' + anchor + '" font-size="12.5" style="fill:var(--text-dim)">' + vals[z].name + ' ' + scTxt + '</text>';
            }
            svg += '</svg>';
            el.innerHTML = svg;
            var ft = document.getElementById('ideaRadarFoot');
            if (ft) {
                // 第二十三/二十四/三十一轮反复刺：这里原来还挂一个「创意结构分 66 / 100」，
                // 和上方「系统模拟自评 86」形成两个总分，评委不知道信哪个。
                // 现在只做维度分解——五个维度的分都在图上，不再汇总出第二个总分。
                ft.innerHTML = '创新性 30% · 可行性 25% · 市场价值 20% · 技术壁垒 15% · 社会价值 10%'
                    + '<div style="margin-top: 5px;">这五个维度看的是<b>创意本身</b>的强弱，仅作分解参考，'
                    + '不另设总分；页面唯一评分是上方「系统模拟自评（文档质量）」。</div>';
            }
            box.style.display = 'block';
        }

        function renderExpertReview(er) {
            var panel = document.getElementById('expertReviewPanel');
            var box = document.getElementById('expertReviewContent');
            if (!panel || !box) return;

            // 后端可能给 dict，也可能给 JSON 字符串（解析失败时是空串）
            var d = null;
            if (er && typeof er === 'object') d = er;
            else if (typeof er === 'string' && er.trim()) {
                try { d = JSON.parse(er); } catch (e) { d = null; }
            }
            if (!d || !Array.isArray(d.experts) || !d.experts.length) {
                panel.style.display = 'none';
                box.innerHTML = '';
                return;
            }

            var h = '';
            // 顶部：综合分 + 结论
            h += '<div style="display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:14px;">' +
                 '<span style="font-size:30px; font-weight:800; color:' + _erColor(d.overall_score) + '; line-height:1;">' +
                 _esc(d.overall_score) + '</span>' +
                 '<span style="font-size:13px; color:var(--text-dim);">/ 100 综合分</span>' +
                 (d.verdict ? '<span style="padding:3px 12px; border-radius:20px; font-size:12.5px; font-weight:600; ' +
                  'background:var(--c-a-soft); color:var(--c-a);">' + _esc(d.verdict) + '</span>' : '') +
                 '</div>';

            // 三位专家卡片
            h += '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px,1fr)); gap:12px;">';
            (d.experts || []).forEach(function (exp) {
                h += '<div style="border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--surface-2);">';
                h += '<div style="display:flex; justify-content:space-between; align-items:baseline; gap:8px;">' +
                     // role 现在是具体身份（如「某高校自动化学院副教授，研究方向…」），比原来的「技术视角」长得多，
                     // 给 flex:1 让它换行，不跟右边的分数抢位置
                     '<b style="font-size:14.5px; flex:1; line-height:1.45;">' + _esc(exp.role || '专家') + '</b>' +
                     '<span style="font-size:16px; font-weight:700; color:' + _erColor(exp.score) + ';">' + _esc(exp.score) + '</span></div>';
                if (exp.focus) h += '<div style="font-size:12px; color:var(--text-mute); margin:4px 0 10px;">关注：' + _esc(exp.focus) + '</div>';

                // 分维度打分
                var dims = exp.dimensions || [];
                if (dims.length) {
                    h += '<div style="margin-bottom:10px;">';
                    dims.forEach(function (dm) {
                        h += '<div style="margin-bottom:7px;">' +
                             '<div style="display:flex; justify-content:space-between; align-items:center; gap:8px; font-size:12.5px;">' +
                             '<span>' + _esc(dm.name || '') + '</span>' +
                             '<span style="display:flex; align-items:center; gap:6px;">' + _erBar(dm.score) +
                             '<b style="color:' + _erColor(dm.score) + ';">' + _esc(dm.score) + '</b></span></div>' +
                             (dm.comment ? '<div style="font-size:12px; color:var(--text-dim); line-height:1.55; margin-top:2px;">' + _esc(dm.comment) + '</div>' : '') +
                             '</div>';
                    });
                    h += '</div>';
                }

                // 优点
                var sts = exp.strengths || [];
                if (sts.length) {
                    h += '<div style="font-size:12.5px; margin-bottom:8px;"><b style="color:var(--ok);">优点</b>' +
                         '<ul style="margin:4px 0 0 16px; color:var(--text-dim); line-height:1.6;">';
                    sts.forEach(function (s) { h += '<li>' + _esc(s) + '</li>'; });
                    h += '</ul></div>';
                }

                // 逐条批注
                var iss = exp.issues || [];
                if (iss.length) {
                    h += '<div style="font-size:12.5px;"><b style="color:var(--warn-text);">待改进</b>';
                    iss.forEach(function (it) {
                        h += '<div style="margin:8px 0 0; padding:8px 10px; border-left:3px solid var(--warn-text); background:var(--surface-solid); border-radius:0 6px 6px 0;">';
                        if (it.quote) h += '<div style="font-size:12px; color:var(--text-mute); font-style:italic; margin-bottom:4px;">“' + _esc(it.quote) + '”</div>';
                        if (it.problem) h += '<div style="color:var(--text-dim); line-height:1.6;">问题：' + _esc(it.problem) + '</div>';
                        if (it.suggestion) h += '<div style="color:var(--text); line-height:1.6; margin-top:3px;">建议：' + _esc(it.suggestion) + '</div>';
                        h += '</div>';
                    });
                    h += '</div>';
                }
                h += '</div>';
            });
            h += '</div>';

            // 共识 / 分歧
            var cons = d.consensus || [], dive = d.divergence || [];
            if (cons.length || dive.length) {
                h += '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:12px; margin-top:14px;">';
                if (cons.length) {
                    h += '<div style="padding:12px; border-radius:8px; background:var(--info-bg-2);">' +
                         '<b style="font-size:13px; color:var(--ok);">专家共识</b><ul style="margin:6px 0 0 16px; font-size:12.5px; color:var(--text-dim); line-height:1.65;">';
                    cons.forEach(function (c) { h += '<li>' + _esc(c) + '</li>'; });
                    h += '</ul></div>';
                }
                if (dive.length) {
                    h += '<div style="padding:12px; border-radius:8px; background:var(--surface-2); border:1px solid var(--line);">' +
                         '<b style="font-size:13px; color:var(--warn-text);">存在分歧</b><ul style="margin:6px 0 0 16px; font-size:12.5px; color:var(--text-dim); line-height:1.65;">';
                    dive.forEach(function (c) { h += '<li>' + _esc(c) + '</li>'; });
                    h += '</ul></div>';
                }
                h += '</div>';
            }

            // 优先改进清单（带理由）
            var acts = d.priority_actions || [];
            if (acts.length) {
                h += '<div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--line);">' +
                     '<b style="font-size:13.5px;">优先改进清单</b>';
                acts.slice().sort(function (a, b) { return (Number(a.priority) || 0) - (Number(b.priority) || 0); })
                    .forEach(function (a, i) {
                        h += '<div style="display:flex; gap:10px; margin-top:10px;">' +
                             '<span style="flex:0 0 22px; height:22px; border-radius:50%; background:var(--c-a); color:#fff; ' +
                             'font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center;">' +
                             _esc(a.priority || (i + 1)) + '</span>' +
                             '<div style="font-size:12.5px; line-height:1.65;">' +
                             '<div>' + _esc(a.action || '') + '</div>' +
                             (a.reason ? '<div style="color:var(--text-mute); font-size:12px; margin-top:2px;">理由：' + _esc(a.reason) + '</div>' : '') +
                             '</div></div>';
                    });
                h += '</div>';
            }

            // 底部免责声明：专家身份是虚构的，必须写明，否则学生可能以为真有这三位评委审过
            var dcl = d.disclaimer
                || '本评审由系统模拟多位专家视角生成，专家身份为虚构，仅供备赛参考，不代表真人评审意见。';
            h += '<div style="margin-top:14px; padding:10px 12px; border-radius:6px; ' +
                 'background:var(--surface-2); border:1px dashed var(--line); ' +
                 'font-size:12px; color:var(--text-mute); line-height:1.6;">' +
                 '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-warn"/></svg> ' +
                 _esc(dcl) + '</div>';

            box.innerHTML = h;
            panel.style.display = 'block';
        }

        // ---- AI 富媒体渲染：图表 / 表格 / PPT 预览 ----
        function renderRich(rd, isDeep) {
            var charts = rd.rich_charts || [];
            var tables = rd.rich_tables || [];
            var deck = rd.rich_deck;
            // 开关开着时预览与导出都用重排后的 8 页 deck，做到"所见即所下载"
            var showDeck = deck;
            if (deck && deck.slides && deck.slides.length && wbRoadshowOn()) {
                try { showDeck = wbRoadshowDeck(rd); } catch (e) { showDeck = deck; }
            }
            var rcw = document.getElementById('richChartsWrap');
            var dcw = document.getElementById('demoChartsWrap');
            if (!rcw || !dcw) return;
            if (isDeep && charts.length) {
                rcw.style.display = 'block'; dcw.style.display = 'none';
            } else {
                rcw.style.display = 'none'; dcw.style.display = 'block';
            }
            // 存一份索引，放大弹窗按序号取原图，避免把 url 拼进 onclick 造成引号/转义问题
            window.__chartItems = charts;
            document.getElementById('richCharts').innerHTML = charts.map(function (c, i) {
                return '<div style="background: var(--surface-2); border-radius: 10px; padding: 14px; border: 1px solid var(--line);">' +
                    '<div style="position:relative;">' +
                    // src 为空时浏览器会把它解析成当前页面 URL 再请求一次（白扔一个请求 + 一条资源错误）
                    '<img src="' + (_esc(c.url) || WB_BLANK_IMG) + '" data-ci="' + i + '" onclick="openChartById(this.dataset.ci)" ' +
                    'title="点击放大查看" alt="' + _esc(c.title) + '" ' +
                    'style="width:100%; border-radius:6px; background:#fff; cursor:zoom-in; display:block;">' +
                    '<div style="position:absolute; right:8px; bottom:8px; padding:3px 8px; border-radius:6px; ' +
                    'font-size:11px; background:rgba(3,6,20,.72); color:#e9eefc; pointer-events:none;">' +
                    '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true" style="width:11px;height:11px;vertical-align:-1px;"><use href="#wb-i-search"/></svg> 点击放大</div>' +
                    '</div>' +
                    '<div style="margin-top:10px; font-size:13px; color:var(--text); font-weight:600;">' + _esc(c.title) + '</div>' +
                    (c.caption ? '<div style="font-size:12px; color:var(--text-mute); margin-top:3px;">' + _esc(c.caption) + '</div>' : '') +
                    (c.source ? '<div style="font-size:11.5px; color:var(--text-mute); margin-top:6px; opacity:.85;">' +
                        '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true" style="width:11px;height:11px;vertical-align:-1px;"><use href="#wb-i-book"/></svg> 数据来源：' + _esc(c.source) + '</div>' : '') +
                    '</div>';
            }).join('');
            document.getElementById('richTables').innerHTML = tables.map(t => {
                var th = '<thead><tr>' + (t.header || []).map(h => '<th>' + _esc(h) + '</th>').join('') + '</tr></thead>';
                var trs = (t.rows || []).map(r =>
                    '<tr>' + r.map(c => '<td>' + _esc(c) + '</td>').join('') + '</tr>').join('');
                return '<div style="background: var(--surface-2); border-radius: 10px; padding: 16px; border: 1px solid var(--line);">' +
                    '<div style="font-size:13px; color:var(--text); font-weight:600; margin-bottom:10px;">' + _esc(t.title) + '</div>' +
                    '<div class="rich-table-wrap"><table class="rich-table">' + th + '<tbody>' + trs + '</tbody>' +
                    (t.caption ? '<caption>' + _esc(t.caption) + '</caption>' : '') +
                    '</table></div></div>';
            }).join('');
            var dw = document.getElementById('deckWrap');
            if (isDeep && deck && deck.slides && deck.slides.length) {
                dw.style.display = 'block';
                var typeLabel = {cover:'封面', section:'章节', bullets:'要点', metrics:'数据', chart:'图表', table:'表格', closing:'结尾'};
                // 图表 / 表格索引：slide 里只存 id，卡片要还原出真实内容
                var chartsById = {};
                charts.forEach(function (c) { if (c.id) chartsById[c.id] = c; if (c.title) chartsById[c.title] = c; });
                var tablesById = {};
                tables.forEach(function (t) { if (t.id) tablesById[t.id] = t; if (t.title) tablesById[t.title] = t; });
                // "**重点**：说明" 里的加粗标记转成 <b>
                function _md(s) { return _esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
                function bulletsHtml(bs, n, dark) {
                    var arr = (bs || []).filter(function (x) { return String(x == null ? '' : x).trim(); });
                    var color = dark ? 'rgba(255,255,255,.84)' : 'var(--text-dim)';
                    var bar = dark ? '#22B8CF' : 'var(--c-a)';
                    var h = arr.slice(0, n).map(function (b) {
                        return '<div class="dc-li" style="color:' + color + '; --dc-bar:' + bar + ';">' + _md(b) + '</div>';
                    }).join('');
                    if (arr.length > n) {
                        h += '<div style="font-size:9.5px; color:' + (dark ? '#8A93D8' : 'var(--text-mute)') + '; margin-top:2px;">+' + (arr.length - n) + ' 条…</div>';
                    }
                    return h;
                }
                function miniTable(tb) {
                    if (!tb || !tb.header || !tb.header.length) return '';
                    var head = '<tr>' + tb.header.slice(0, 5).map(function (h) { return '<th>' + _esc(h) + '</th>'; }).join('') + '</tr>';
                    var rows = (tb.rows || []).slice(0, 4).map(function (r) {
                        return '<tr>' + r.slice(0, 5).map(function (c) { return '<td>' + _esc(c) + '</td>'; }).join('') + '</tr>';
                    }).join('');
                    var more = (tb.rows || []).length > 4
                        ? '<div style="font-size:9.5px; color:var(--text-mute); margin-top:3px;">共 ' + tb.rows.length + ' 行</div>' : '';
                    return '<table class="dc-mini">' + head + rows + '</table>' + more;
                }
                document.getElementById('deckPreview').innerHTML = showDeck.slides.map((s, i) => {
                    var t = String(s.type || 'bullets').toLowerCase();
                    var isDark = (t === 'cover' || t === 'section' || t === 'closing');
                    var label = typeLabel[t] || t;
                    var title = s.title || label;
                    var body = '';
                    if (t === 'cover') {
                        body = '<div style="font-size:10.5px; line-height:1.55; color:#C6CFEF;">' + _md(showDeck.one_liner || s.note || '') + '</div>' +
                               bulletsHtml(s.bullets, 2, true);
                    } else if (t === 'closing') {
                        body = '<div style="font-size:10.5px; line-height:1.55; color:#C6CFEF;">' + _md(showDeck.one_liner || '') + '</div>' +
                               bulletsHtml(s.bullets, 2, true);
                    } else if (t === 'metrics' || (s.metrics && s.metrics.length)) {
                        body = '<div class="dc-chips">' + (s.metrics || []).slice(0, 4).map(function (m) {
                            var mm = String(m).match(/^\s*([\d.]+\s*[^\s：:、]*)\s*[：:、]\s*(.+)$/);
                            return '<span class="dc-chip">' + (mm ? '<i>' + _esc(mm[1]) + '</i> ' + _esc(mm[2]) : _esc(m)) + '</span>';
                        }).join('') + '</div>' + bulletsHtml(s.bullets, 3, isDark);
                    } else if (t === 'table' || (s.table && typeof s.table === 'object')) {
                        var tb = (s.table && typeof s.table === 'object') ? s.table : tablesById[s.table];
                        body = miniTable(tb) + (s.note ? '<div class="dc-li" style="color:var(--text-mute);">' + _md(s.note) + '</div>' : '');
                    } else {
                        var img = s.chart ? (chartsById[s.chart] || {}) : {};
                        if (img.url) {                       // 左文右图，和真 PPT 版式一致
                            body = '<div style="display:flex; gap:8px; height:100%; align-items:flex-start;">' +
                                   '<div style="flex:1 1 52%; min-width:0;">' + bulletsHtml(s.bullets, 4, isDark) + '</div>' +
                                   '<div style="flex:0 0 46%;"><img class="dc-img" src="' + _esc(img.url) + '" alt=""></div></div>';
                        } else {
                            body = bulletsHtml(s.bullets, 5, isDark);
                        }
                    }
                    var bg = isDark ? 'linear-gradient(135deg,#0F1535,#232E6A)' : 'var(--surface-2)';
                    var barColor = isDark ? '#22B8CF' : 'var(--c-a)';
                    var muteColor = isDark ? '#8A93D8' : 'var(--text-mute)';
                    var titleColor = isDark ? '#FFFFFF' : 'var(--text)';
                    return '<div class="deck-card" style="background:' + bg + ';">' +
                        '<div class="dc-bar" style="background:' + barColor + ';"></div>' +
                        '<div class="dc-badge" style="color:' + muteColor + ';">P' + (i + 1) + ' · ' + label + '</div>' +
                        (s.kicker ? '<div class="dc-kicker" style="color:' + (isDark ? '#22B8CF' : 'var(--c-a)') + ';">' + _esc(s.kicker) + '</div>' : '') +
                        '<div class="dc-title" style="color:' + titleColor + ';">' + _esc(title) + '</div>' +
                        '<div class="dc-body">' + body + '</div>' +
                        '<div class="dc-foot" style="color:' + muteColor + ';">' + _esc(showDeck.project || '') + '</div>' +
                        '</div>';
                }).join('');
                try { wbRoadLabel(); } catch (e) {}
                wbRenderRoadPlan(showDeck);
            } else {
                dw.style.display = 'none';
            }
        }
        // ============ 标准路演结构：基础 8 页 + 赛事专项页 + 申报书回填 ============
        // 为什么在前端做：deck 本来就是前端拿去 POST 给 /api/export_pptx 的，
        // 在下载前重排一次，"下载 PPT" 和"一键打包"两条路同时生效，后端不用改。
        // 基础 8 页。kicker 不写死，按最终页序动态编号 —— 赛事专项页插进来后序号要跟着变
        var WB_ROAD_PAGES = [
            {key: 'cover',    type: 'cover',   name: '封面',     kw: [], strong: []},
            {key: 'pain',     type: 'bullets', name: '项目痛点',
             kw: ['痛点', '问题', '现状', '背景', '需求', '挑战', '难点', '困难', '刚需', '为什么'],
             strong: ['痛点', '难点', '难以', '无法', '不足', '缺失', '缺少', '成本高', '效率低', '信息不对称']},
            {key: 'solution', type: 'bullets', name: '解决方案',
             kw: ['解决方案', '方案', '技术', '原理', '思路', '路径', '方法', '路线', '架构', '创新点', '实现'],
             strong: ['采用', '通过', '本方案', '本平台', '架构', '算法', '机制', '实现']},
            {key: 'feature',  type: 'bullets', name: '核心功能',
             kw: ['功能', '产品', '模块', '特性', '亮点', '优势', '服务', '场景', '形态'],
             strong: ['功能', '模块', '支持', '提供', '一键', '自动', '可查', '可追溯']},
            {key: 'data',     type: 'metrics', name: '落地数据',
             kw: ['数据', '成果', '验证', '落地', '试点', '效果', '指标', '市场', '规模', '财务', '营收', '用户', '测试', '进展'],
             strong: ['试点', '测试', '验证', '覆盖', '累计', '准确率', '提升', '降低', '增长']},
            {key: 'compete',  type: 'table',   name: '竞品对比',
             kw: ['竞品', '对比', '竞争', '差异化', '对手', '同类', '友商'],
             strong: ['竞品', '对比', '相比', '同类', '友商', '优于', '差异', '领先']},
            {key: 'team',     type: 'bullets', name: '团队介绍',
             kw: ['团队', '成员', '分工', '指导', '师资', '负责人', '年级', '专业'],
             strong: ['团队成员', '成员', '分工', '指导教师', '团队由', '专业年级']},
            {key: 'thanks',   type: 'closing', name: '致谢',     kw: [], strong: []}
        ];
        // 赛事专项页：插在 after 那一页之后。数学建模讲模型、广告艺术讲视觉，
        // 通用 8 页里没有这两块，硬塞进"解决方案"会又长又乱，所以单独成页。
        var WB_EXTRA_PAGES = {
            math: [
                {key: 'assume',  type: 'bullets', name: '模型假设', after: 'solution',
                 kw: ['假设', '前提', '符号', '变量', '约定', '符号说明', '假定'],
                 strong: ['假设', '假定', '不妨设', '符号说明', '记为', '忽略', '不考虑']},
                {key: 'formula', type: 'bullets', name: '公式推导', after: 'assume',
                 kw: ['公式', '推导', '求解', '目标函数', '约束', '模型建立', '算法', '求解过程', '灵敏度', '检验'],
                 strong: ['公式', '推导', '由', '可得', '代入', '目标函数', '约束条件', '求解', '迭代']}
            ],
            art: [
                {key: 'sketch', type: 'bullets', name: '创意草图', after: 'feature',
                 kw: ['创意', '草图', '构思', '概念', '灵感', '脚本', '分镜', '文案', '主题'],
                 strong: ['创意', '构思', '草图', '脚本', '分镜', '创意点', '概念来源', '灵感']},
                // 不放泛化的"效果"：落地数据页的关键词里也有它，两边都认就会串页
                {key: 'visual', type: 'bullets', name: '视觉效果', after: 'sketch',
                 kw: ['视觉', '画面', '呈现', '配色', '版式', '海报', '物料', 'KV'],
                 strong: ['视觉', '配色', '版式', '画面', '海报', '呈现', '物料', '字体', '构图']}
            ]
        };
        // 赛事类型 → 推荐主题（主题 key 用 15 套精品里的，不再指向旧模板）。
        // 顺序即优先级：iCAN 最先命中，数学建模 / 广告艺术 比泛化的"科技"更具体，排前面。
        var WB_COMP_TYPES = [
            {type: 'ican',  name: 'iCAN 大赛', theme: 'star',
             kw: ['iCAN', 'ican', 'Ican']},
            {type: 'math',  name: '数学建模类', theme: 'math',
             rename: {feature: '模型应用', compete: '方法对比'},
             kw: ['数学建模', '数模', '建模', '运筹', '统计建模']},
            {type: 'art',   name: '艺术设计类', theme: 'morandi',
             // 不放泛化的"设计大赛"：中国大学生计算机设计大赛是软件类赛事，
             // 被它命中就会推成设计风，反而错
             kw: ['广告艺术', '大广赛', '视觉传达', '艺术设计', '数字媒体', '动画', '影视', '文创']},
            {type: 'eng',   name: '工程硬件类', theme: 'star',
             kw: ['电子设计', '电赛', '蓝桥杯', '机器人', '智能制造', '西门子', '机械', '嵌入式',
                  '单片机', '硬件', '电路', '自动化', 'RoboMaster', '工程训练', '智能车']},
            // 国创/大创计划名称里带"创业"两字（创新创业训练计划），但它是科研训练类，
            // 排在经管类前面先命中，不然会被推成商务灰
            {type: 'acad',  name: '学术科研类', theme: 'paper',
             kw: ['创新创业训练', '国创计划', '大创']},
            {type: 'biz',   name: '经管商业类', theme: 'flat',
             kw: ['互联网+', '互联网＋', '创业', '小挑', '服务外包', '商业', '经管', '金融',
                  '供应链', '市场', '营销', '电商', '财务']},
            {type: 'it',    name: '软件信息类', theme: 'star',
             kw: ['信息安全', '计算机设计', '软件', '程序', '算法', '网络', '大数据', '人工智能',
                  '信息技术', '金砖', '技能']},
            {type: 'acad',  name: '学术科研类', theme: 'academic',
             kw: ['挑战杯', '课外学术', '国创', '创新创业训练', '科研', '论文', '学术']}
        ];
        // 赛事 → 模板：15 个赛事逐个钉死一套，用户不用自己挑风格。
        // 顺序即优先级（先命中的赢），两个坑：
        //   ① "创业计划/小挑" 必须排在 "挑战杯" 前面，否则小挑会被大挑的红金吃掉；
        //   ② "服务外包" 必须排在 "创业" 前面（服务外包大赛名字里也带"创新创业"）。
        // 最后一档是类型兜底，给"用户手输赛事名"的场合用。
        // 主题全部落在 15 套精品上：科技星空 star/cyber、扁平商务 flat/biz/capital、
        // 简洁学术 paper/math/academic、莫兰迪 morandi/clay、红金 redgold/blackgold、
        // 清新文艺 verdant/literary、中国风 ink。
        // 传统文化必须排在"文创"前面：非遗项目名字里也带"文创"，被文创吃掉就成了清新绿。
        var WB_COMP_THEME = [
            {kw: ['ican'], theme: 'star'},
            {kw: ['传统文化', '非遗', '非物质文化', '国学', '汉服', '书法', '中医药',
                  '国风', '文物', '戏曲', '古籍', '民俗', '汉字', '中医药'], theme: 'ink'},
            {kw: ['绘本', '书籍', '出版', '展览', '书店', '文艺'], theme: 'literary'},
            {kw: ['文创', '文旅', '手作', '博物馆', '文化创', '乡村振兴'], theme: 'verdant'},
            {kw: ['互联网+', '互联网＋'], theme: 'flat'},
            {kw: ['服务外包'], theme: 'biz'},
            {kw: ['创业计划', '小挑'], theme: 'blackgold'},
            {kw: ['课外学术科技作品', '大挑'], theme: 'redgold'},
            {kw: ['挑战杯'], theme: 'redgold'},
            {kw: ['创新创业训练', '国创计划', '大创'], theme: 'paper'},
            {kw: ['数学建模', '数模', '建模'], theme: 'math'},
            {kw: ['电子设计', '电赛', '嵌入式', '单片机', '电路'], theme: 'star'},
            {kw: ['西门子', '智能制造', '机械', '自动化', '工程训练', '智能车'], theme: 'star'},
            {kw: ['蓝桥杯', '计算机设计', '软件', '程序', '算法'], theme: 'star'},
            {kw: ['广告艺术', '大广赛', '视觉传达', '艺术设计', '数字媒体', '动画', '影视'], theme: 'morandi'},
            {kw: ['包装', '平面', '品牌', '海报', '展陈', '文创产品'], theme: 'clay'},
            {kw: ['信息安全', '网安', '网络安全', '攻防', '漏洞'], theme: 'cyber'},
            {kw: ['机器人', 'robomaster', '人工智能', '深度学习', '机器学习', '神经网络'], theme: 'cyber'},
            {kw: ['金砖', '技能发展', '青年创客'], theme: 'capital'},
            {kw: ['创业', '商业', '融资', '创投', '经管', '金融', '供应链', '市场', '营销', '电商', '财务'], theme: 'biz'},
            {kw: ['论文', '科研', '结题', '开题', '学术'], theme: 'academic'}
        ];
        // 赛事名来源：输入框 + 已生成结果里的赛事名（历史回看时输入框可能已被清空）
        function wbCompText() {
            var el = document.getElementById('competition');
            return (_wbT(el && el.value) + ' ' + _wbT((window._lastData || {}).competition) +
                    ' ' + _wbT((window._lastData || {}).competition_name)).toLowerCase();
        }
        function wbRecoTheme() {
            var low = wbCompText();
            for (var i = 0; i < WB_COMP_THEME.length; i++) {
                var t = WB_COMP_THEME[i];
                for (var j = 0; j < t.kw.length; j++) {
                    if (low.indexOf(String(t.kw[j]).toLowerCase()) >= 0) return t.theme;
                }
            }
            return 'star';
        }
        // 赛事名 → 类型（找不到就 general）。类型是"页面结构"用（专项页/改名词），
        // 主题由 wbRecoTheme 单独定（同类型下不同赛事可以推不同模板）
        function wbCompType() {
            var low = wbCompText();
            for (var i = 0; i < WB_COMP_TYPES.length; i++) {
                var t = WB_COMP_TYPES[i];
                for (var j = 0; j < t.kw.length; j++) {
                    if (low.indexOf(String(t.kw[j]).toLowerCase()) >= 0) {
                        return {type: t.type, name: t.name, rename: t.rename, kw: t.kw, theme: wbRecoTheme()};
                    }
                }
            }
            return {type: 'general', name: '通用', theme: wbRecoTheme(), kw: []};
        }
        // 最终页序：基础 8 页 + 该赛事类型的专项页（插在指定页之后）
        function wbRoadPages() {
            var ct = wbCompType();
            var rn = ct.rename || {};
            var out = WB_ROAD_PAGES.map(function (p) {
                if (!rn[p.key]) return p;
                // 数学建模谈"核心功能"很怪，按赛事换一个说法（kw 不变，回填逻辑照旧）
                return {key: p.key, type: p.type, name: rn[p.key], kw: p.kw, strong: p.strong};
            });
            var ex = WB_EXTRA_PAGES[ct.type] || [];
            if (!ex.length) return out;
            ex.forEach(function (p) {
                var at = -1;
                for (var i = 0; i < out.length; i++) { if (out[i].key === p.after) { at = i; break; } }
                if (at < 0) at = out.length - 2;               // 兜底：插在致谢前
                out.splice(at + 1, 0, p);
            });
            return out;
        }
        // 内容页编号：封面/致谢不编号，其余按 01 02 03… 走
        function wbRoadKicker(pages, i) {
            var p = pages[i];
            if (p.type === 'cover' || p.type === 'closing') return '';
            var n = 0;
            for (var j = 0; j <= i; j++) {
                if (pages[j].type !== 'cover' && pages[j].type !== 'closing') n++;
            }
            return (n < 10 ? '0' : '') + n + ' / ' + p.name;
        }
        // 后端 metrics 卡片的数字单位只认这些（见 pptx_builder._metrics_body 的正则），
        // 其余单位（人/家/台/次…）塞进标签里，不然整串会被当成"大号数字"排版
        var WB_METRIC_UNITS = ['%', '％', '万', '亿', '倍', '年', '个', '天', '元', '周',
                               '人', '家', '台', '套', '项', '次', '所', '校'];
        function wbRoadshowOn() {
            var el = document.getElementById('chkRoadshow');
            return !el || el.checked;                        // 元素还没渲染时默认开
        }
        function _wbT(v) { return String(v == null ? '' : v); }
        function _wbOne(s) { return _wbT(s).replace(/\s+/g, ' ').trim(); }
        function _wbTrim(s, n) { s = _wbOne(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
        function _wbClean(s) {
            return _wbT(s).replace(/^#{1,6}\s*/gm, '').replace(/\*\*/g, '')
                          .replace(/^\s*[-*•·]\s*/gm, '').replace(/^\s*\d+[.、)]\s*/gm, '')
                          .replace(/`/g, '').replace(/\s+/g, ' ').trim();
        }
        function _wbSentences(t) {
            return _wbOne(t).split(/[。；;！!？?\n]/).map(function (x) { return x.trim(); })
                            .filter(function (x) { return x.length >= 8; });
        }
        // 申报书按标题切段：## xxx / **xxx** / 1. xxx / 一、xxx
        function _wbSections(text) {
            var out = [], cur = {h: '', body: []};
            _wbT(text).split(/\r?\n/).forEach(function (raw) {
                var l = _wbOne(raw);
                if (!l) return;
                var m = l.match(/^#{1,6}\s*(.+)$/) || l.match(/^\*\*(.+?)\*\*\s*$/) ||
                        l.match(/^[（(]?([一二三四五六七八九十]+|\d+)[）).、]\s*(.+)$/);
                if (m && l.length <= 40) {
                    if (cur.h || cur.body.length) out.push(cur);
                    cur = {h: _wbClean(m[2] ? m[2] : m[1]), body: []};
                    return;
                }
                cur.body.push(_wbClean(l));
            });
            if (cur.h || cur.body.length) out.push(cur);
            return out;
        }
        function _wbPush(arr, seen, s, limit) {
            if (arr.length >= (limit || 99)) return;
            var k = s.slice(0, 16);
            if (seen[k]) return;
            seen[k] = 1; arr.push(s);
        }
        // 这段标题归哪一页（用于回填时不抢别人的章节）。
        // 走动态页序：数学建模的"模型假设"段不能被"解决方案"页抢走
        // 取"命中最长的那个关键词"所属页，而不是先遍历到的页：
        // "落地效果" 同时含数据页的"落地"和视觉页的"效果"，按页序会判给先出现的那页，
        // 按长度能在两页各有更专的词时判得更准（"视觉效果"→视觉，"落地效果"→数据）
        function _wbOwner(h) {
            var pages = wbRoadPages();
            var best = '', bl = 0;
            for (var i = 1; i < pages.length - 1; i++) {
                var p = pages[i];
                for (var j = 0; j < p.kw.length; j++) {
                    if (h.indexOf(p.kw[j]) >= 0 && p.kw[j].length > bl) { bl = p.kw[j].length; best = p.key; }
                }
            }
            return best;
        }
        // 先按"标题命中"取整段；不够再用强关键词全文扫。两条约束都是踩坑换来的：
        // ① 强关键词必须窄——用宽词（服务/同类）扫时，痛点句被塞进"核心功能"页、竞品页；
        // ② 别人的章节不能抢——"竞品对比"段的句子再像也不许进"核心功能"页。
        // 串页比缺内容更糟，宁可留空让用户自己补。
        function _wbFill(sections, key, limit) {
            var p = null;
            // 走动态页序：赛事专项页（模型假设 / 创意草图…）不在基础 8 页里，
            // 查静态表会返回空，专项页就永远只剩"待补充"
            wbRoadPages().forEach(function (x) { if (x.key === key) p = x; });
            if (!p) return [];
            var out = [], seen = {};
            sections.forEach(function (sec) {
                // 标题命中也不许抢别人的章节：数据页的关键词里有"效果"，
                // 会把广告艺术的"视觉效果"整段搬进落地数据页
                var own0 = _wbOwner(sec.h);
                if (own0 && own0 !== key) return;
                var hit = false;
                for (var i = 0; i < p.kw.length; i++) { if (sec.h.indexOf(p.kw[i]) >= 0) { hit = true; break; } }
                if (!hit) return;
                sec.body.forEach(function (b) {
                    _wbSentences(b).forEach(function (s) { _wbPush(out, seen, s, limit); });
                });
            });
            if (out.length < 2) {
                sections.forEach(function (sec) {
                    var own = _wbOwner(sec.h);
                    if (own && own !== key) return;
                    sec.body.forEach(function (b) {
                        _wbSentences(b).forEach(function (s) {
                            for (var i = 0; i < p.strong.length; i++) {
                                if (s.indexOf(p.strong[i]) >= 0) { _wbPush(out, seen, s, limit); return; }
                            }
                        });
                    });
                });
            }
            return out;
        }
        // 关键数字：抽成 "数字：说明" 的数据卡。
        // 必须走清洗后的段落：直接扫原文的话，"## 四、落地数据" 会和正文粘成一句，
        // 标签就变成"落地数据 已在三甲医院试点"这种读不通的东西。
        function _wbMetrics(sections, limit) {
            var res = [], seen = {};
            var re = /(\d+(?:\.\d+)?)\s*(%|％|个百分点|亿元|万元|万|亿|倍|年|个月|天|周|小时|分钟|秒|元|人|家|台|套|项|个|次|篇|所|校|米|kg)/g;
            sections.forEach(function (sec) {
                // 数据/成果/市场类章节里的数字优先，别的章节靠后
                var hw = /数据|成果|验证|落地|试点|效果|指标|市场|规模|财务|营收|进展|测试/.test(sec.h) ? 2 : 0;
                sec.body.forEach(function (b) {
                    _wbSentences(b).forEach(function (s) {
                        var m, picked = 0;
                        re.lastIndex = 0;
                        while ((m = re.exec(s)) !== null && picked < 2) {   // 一句最多取 2 个，免得 4 张卡全是同一句
                            picked++;
                            var num = m[1], unit = m[2], key = num + unit;
                            if (seen[key]) continue;
                            if (unit === '年' && /^(19|20)\d{2}$/.test(num)) continue;   // 2026 年这种年份不算指标
                            var sw = /提升|提高|降低|减少|增长|准确率|覆盖率|转化|节省|缩短|效率|成本|收入|用户|满意度|覆盖|试点|累计/.test(s) ? 1 : 0;
                            if (!hw && !sw) continue;                       // 既不在数据章节、也没结果词的数字不上卡
                            var own = _wbOwner(sec.h);
                            if (!hw && own && own !== 'data') continue;     // 团队/痛点章节里的人数、比例不算"落地数据"
                            seen[key] = 1;
                            // 说明取数字所在的那个小分句（逗号/顿号切开），去掉数字本身；
                            // "1200 人次" 这种双字单位会剩一个"次"挂在尾巴上，一并抹掉
                            var clause = s;
                            var parts = s.split(/[，,、；;：:（(]/);
                            for (var pi = 0; pi < parts.length; pi++) {
                                if (parts[pi].indexOf(m[0]) >= 0) { clause = parts[pi]; break; }
                            }
                            var at2 = clause.indexOf(m[0]);
                            var tail = clause.slice(at2 + m[0].length).replace(/^[次秒米个项套台篇所校家天周]/, '');
                            var label = (clause.slice(0, at2) + tail).replace(/\s+/g, '')
                                            .replace(/^(19|20)\d{2}年/, '').trim();
                            label = _wbTrim(label, 14) || '项目关键数据';
                            var shown = num + (WB_METRIC_UNITS.indexOf(unit) >= 0 ? (unit === '％' ? '%' : unit) : '');
                            res.push({raw: shown + '：' + label, w: hw + sw});
                        }
                    });
                });
            });
            res.sort(function (a, b) { return b.w - a.w; });
            return res.slice(0, limit || 4);
        }
        // 亮点句：带数字 + 有结果动词（提升/准确率/覆盖…），给"落地数据"页当要点
        function _wbHighlights(sections, limit) {
            var out = [], seen = {};
            sections.forEach(function (sec) {
                // 属于专项页的章节（模型假设 / 创意草图 / 视觉效果）不算"落地数据"，
                // 不然广告艺术的数据页会冒出"分镜脚本共 6 幕"这种不是数据的句子
                var own = _wbOwner(sec.h);
                if (own && own !== 'data') return;
                sec.body.forEach(function (b) {
                    _wbSentences(b).forEach(function (s) {
                        if (!/\d/.test(s)) return;
                        if (!/提升|提高|降低|减少|增长|准确率|覆盖率|转化|节省|缩短|效率|成本|收入|用户|满意度|完成|覆盖|验证|落地|合作/.test(s)) return;
                        _wbPush(out, seen, _wbTrim(s, 58), limit);
                    });
                });
            });
            return out;
        }
        // AI 给的页归到哪一页：标题命中权重高于正文命中（走动态页序，含赛事专项页）
        function _wbBucket(s) {
            var pages = wbRoadPages();
            var head = (String(s.title || '') + ' ' + String(s.kicker || '')).toLowerCase();
            var body = ((s.bullets || []).concat(s.metrics || []).join(' ')).toLowerCase();
            var best = 'feature', bs = 0;
            for (var i = 1; i < pages.length - 1; i++) {
                var p = pages[i], sc = 0;
                for (var j = 0; j < p.kw.length; j++) {
                    if (head.indexOf(p.kw[j]) >= 0) sc += 3;
                    if (body.indexOf(p.kw[j]) >= 0) sc += 1;
                }
                if (sc > bs) { bs = sc; best = p.key; }
            }
            if (bs > 0) return best;
            if (s.table) return 'compete';
            if (s.metrics && s.metrics.length) return 'data';
            return 'feature';
        }
        // 把 AI 生成的 deck 重排成标准路演结构：基础 8 页 + 该赛事类型的专项页，
        // 并用申报书回填空页。页数不再写死 8 页 —— 数学建模会多出「模型假设 / 公式推导」，
        // 广告艺术会多出「创意草图 / 视觉效果」。
        function wbRoadshowDeck(rd) {
            rd = rd || {};
            var src = rd.rich_deck || {};
            var slides = src.slides || [];
            var pages = wbRoadPages();
            var acc = {}, cover = null, closing = null;
            pages.forEach(function (p) { acc[p.key] = {bullets: [], metrics: [], table: null, chart: null, note: ''}; });
            slides.forEach(function (s) {
                if (!s || typeof s !== 'object') return;
                var ty = String(s.type || 'bullets').toLowerCase();
                if (ty === 'cover' || ty === 'title') { if (!cover) cover = s; return; }
                if (ty === 'closing' || ty === 'thanks' || ty === 'end') { if (!closing) closing = s; return; }
                var a = acc[_wbBucket(s)];
                (s.bullets || []).forEach(function (b) {
                    b = _wbTrim(b, 58);
                    if (b && a.bullets.indexOf(b) < 0 && a.bullets.length < 8) a.bullets.push(b);
                });
                (s.metrics || []).forEach(function (m) {
                    m = _wbOne(m);
                    if (m && a.metrics.indexOf(m) < 0 && a.metrics.length < 6) a.metrics.push(m);
                });
                if (!a.table && s.table) a.table = s.table;
                if (!a.chart && s.chart) a.chart = s.chart;
                if (!a.note && s.note) a.note = _wbOne(s.note);
            });
            // 回填素材：申报书全文 + 各分析模块（方案/竞品/商业/落地计划）
            var docs = _wbT(rd.proposal) || _wbT(rd.proposalText);
            var extra = [_wbT(rd.tech_solution), _wbT(rd.competitor_analysis), _wbT(rd.project_summary),
                         _wbT(rd.social_value), _wbT(rd.business_model), _wbT(rd.implementation_plan)].join('\n');
            var secs = _wbSections(docs).concat(_wbSections(extra));
            var fill = {};
            pages.forEach(function (p) {
                if (!p.kw.length) return;
                fill[p.key] = _wbFill(secs, p.key, 6);
            });
            var nums = _wbMetrics(secs, 4);
            var hl = _wbHighlights(secs, 4);

            function merge(key, cap) {
                var a = acc[key] || {bullets: []};
                var arr = a.bullets.slice(0, cap);
                (fill[key] || []).forEach(function (s) {
                    if (arr.length >= cap) return;
                    var dup = false;
                    for (var i = 0; i < arr.length; i++) { if (arr[i].slice(0, 10) === s.slice(0, 10)) { dup = true; break; } }
                    if (!dup) arr.push(_wbTrim(s, 58));
                });
                return arr;
            }
            var proj = _wbOne(src.project || _wbTrim(rd.idea, 24) || '科创项目');
            var one = _wbOne(src.one_liner || rd.one_liner || '');
            var out = [];
            pages.forEach(function (p, idx) {
                var kicker = wbRoadKicker(pages, idx);
                var a = acc[p.key] || {bullets: []};

                if (p.type === 'cover') {
                    out.push({type: 'cover', title: (cover && cover.title) || proj,
                              bullets: (cover && cover.bullets && cover.bullets.length) ? cover.bullets.slice(0, 2) : (one ? [one] : []),
                              note: (cover && cover.note) || ''});
                    return;
                }
                if (p.type === 'closing') {
                    out.push({type: 'closing', title: (closing && closing.title) || '谢谢聆听',
                              bullets: (closing && closing.bullets && closing.bullets.length)
                                       ? closing.bullets.slice(0, 2)
                                       : [one || '欢迎各位评委老师批评指正']});
                    return;
                }
                // 落地数据：先 AI 给的指标卡，不够再用申报书里挖出来的数字补到 4 张
                if (p.key === 'data') {
                    var dm = (a.metrics || []).slice(0, 4);
                    nums.forEach(function (m) { if (dm.length < 4) dm.push(m.raw); });
                    var dbullets = merge('data', 4);
                    hl.forEach(function (s) {
                        if (dbullets.length >= 4) return;
                        // merge 里已经可能从同一章节取过同一句，追加前查重，别让数据页出现两行一模一样的话
                        for (var hi = 0; hi < dbullets.length; hi++) {
                            if (dbullets[hi].slice(0, 10) === s.slice(0, 10)) return;
                        }
                        dbullets.push(s);
                    });
                    var chartId = a.chart || '';
                    if (!chartId) {
                        var ids = (rd.rich_charts || []).map(function (c) { return _wbT(c.id); });
                        if (ids.indexOf('market') >= 0) chartId = 'market';
                        else if (ids.indexOf('timeline') >= 0) chartId = 'timeline';
                    }
                    out.push({type: 'metrics', kicker: kicker, title: p.name,
                              metrics: dm, bullets: dbullets, chart: chartId || ''});
                    return;
                }
                // 竞品对比：有表用表，没表退回文字要点，绝不留一张空表格页
                // AI 的 slide.table 可能只是个 id 字符串（"t1"），也可能已经是实体对象，两种都要还原
                if (p.key === 'compete') {
                    var ts = rd.rich_tables || [];
                    var tb = null, rid = a.table;
                    if (typeof rid === 'string') {
                        for (var ti = 0; ti < ts.length; ti++) {
                            if (ts[ti].id === rid || ts[ti].title === rid) { tb = ts[ti]; break; }
                        }
                    } else if (rid && rid.header && rid.rows) {
                        tb = rid;
                    }
                    if (!tb) {
                        for (var tj = 0; tj < ts.length; tj++) {
                            if (/竞品|对比|竞争|差异化|同类|友商/.test(_wbT(ts[tj].title))) { tb = ts[tj]; break; }
                        }
                        if (!tb && ts.length) tb = ts[0];
                    }
                    if (tb && tb.header && tb.rows) {
                        out.push({type: 'table', kicker: kicker, title: p.name,
                                  table: {header: tb.header, rows: tb.rows}, note: a.note || ''});
                    } else {
                        var cb = merge('compete', 5);
                        if (!cb.length) cb = ['**待补充**：本次没识别到竞品对比素材，建议在申报书里补一段与同类方案的维度对比'];
                        out.push({type: 'bullets', kicker: kicker, title: p.name, bullets: cb, note: a.note || ''});
                    }
                    return;
                }
                // 团队：申报书 + 页面上填的学校/团队/指导教师
                if (p.key === 'team') {
                    var tbs = merge('team', 5);
                    var meta = (typeof wbMeta === 'function') ? wbMeta() : {};
                    if (meta.team) tbs.unshift('**团队成员**：' + _wbTrim(meta.team, 40));
                    if (meta.advisor) tbs.unshift('**指导教师**：' + _wbTrim(meta.advisor, 30));
                    if (meta.school) tbs.unshift('**所属院校**：' + _wbTrim(meta.school, 30));
                    if (!tbs.length) tbs = ['**待补充**：团队成员、专业分工与指导教师'];
                    out.push({type: 'bullets', kicker: kicker, title: p.name, bullets: tbs.slice(0, 5)});
                    return;
                }
                // 通用要点页（含数学建模 / 广告艺术插进来的专项页）。
                // 带指标卡时正文容量是 4 条（后端 MAX_BLOCKS_WITH_METRICS），给 5 条会多出一张"（续）"页
                var ms = (a.metrics || []).slice(0, 2);
                var bs = merge(p.key, ms.length ? 4 : 5);
                if (!bs.length) bs = ['**待补充**：申报书里没识别到「' + p.name + '」相关内容，建议在对应章节补一段'];
                var sl = {type: 'bullets', kicker: kicker, title: p.name, bullets: bs};
                if (ms.length) sl.metrics = ms;
                if (a.note) sl.note = a.note;
                out.push(sl);
            });
            return {
                project: proj, one_liner: one,
                competition: _wbOne(src.competition || rd.competition || ''),
                theme: src.theme || 'star', variant: src.variant || 'v1',
                slides: out
            };
        }
        // 页序说明 + 状态条：每页几条内容，空的标出来，导出前就知道哪页要补。
        // 页数随赛事类型变（数学建模 10 页、广告艺术 10 页），所以标题和流程说明都由 JS 填
        function wbRoadLabel() {
            var pages = wbRoadPages();
            var t = document.getElementById('roadTitle');
            if (t) t.textContent = '按标准路演结构导出（固定 ' + pages.length + ' 页）';
            var f = document.getElementById('roadFlow');
            if (f) {
                var ct = wbCompType();
                f.textContent = pages.map(function (p) { return p.name; }).join(' → ') +
                                '，缺内容的页自动从申报书补' +
                                (WB_EXTRA_PAGES[ct.type] ? '（' + ct.name + '额外加了专项页）' : '');
            }
        }
        function wbRenderRoadPlan(deck) {
            var el = document.getElementById('deckRoadPlan');
            if (!el) return;
            if (!wbRoadshowOn()) {
                el.innerHTML = '<div style="font-size:12px; color:var(--text-mute);">已关闭：按系统原始结构导出（页数与顺序不固定）。</div>';
                return;
            }
            if (!deck || !deck.slides) { el.innerHTML = ''; return; }
            var pages = wbRoadPages();
            el.innerHTML = deck.slides.map(function (s, i) {
                var n = (s.bullets || []).length + (s.metrics || []).length +
                        (s.table ? (s.table.rows || []).length : 0) + (s.chart ? 1 : 0);
                var dark = (s.type === 'cover' || s.type === 'closing');
                // 占位提示不算"有内容"，否则每页都不会显示待补
                var real = (s.bullets || []).filter(function (b) { return String(b).indexOf('**待补充**') < 0; }).length;
                var empty = !dark && (n === 0 || (real === 0 && !(s.metrics || []).length && !s.table && !s.chart));
                var nm = (pages[i] && pages[i].name) || ('P' + (i + 1));
                return '<span style="display:inline-flex; align-items:center; gap:5px; padding:4px 9px; border-radius:12px; font-size:11.5px;' +
                       ' background:' + (empty ? 'var(--c-b-soft, #FDECEC)' : 'var(--surface-solid, #fff)') + ';' +
                       ' border:1px solid ' + (empty ? 'var(--c-b, #D9534F)' : 'var(--line)') + ';' +
                       ' color:' + (empty ? 'var(--c-b, #D9534F)' : 'var(--text-dim)') + ';">' +
                       '<b style="font-weight:600;">' + (i + 1) + '. ' + _esc(nm) + '</b>' +
                       (dark ? '' : '<span style="opacity:.75;">' + (empty ? '待补' : n + ' 条') + '</span>') +
                       (s.chart ? '<span style="opacity:.75;">·图</span>' : '') +
                       '</span>';
            }).join('');
        }
        function wbRoadToggle() {
            var rd = window._lastData;
            if (!rd || !rd.rich_deck) return;
            try { renderRich(rd, true); } catch (e) {}   // 预览区同步换成新结构，所见即所下载
        }

        // ---- PPT 主题 / 模板选择 ----
        // 缩略图配色表：只作兜底，正常走后端 list_themes 回传的 colors（新增主题自动生效）
        var WB_THEME_COLORS = {
            tech:     { deep: '#0F1535', deep2: '#3B2170', primary: '#4A55B8', accent: '#22B8CF', deco: ['#22B8CF', '#F59E0B', '#DB3F72'] },
            ink:      { deep: '#1B1B1B', deep2: '#4A4A4A', primary: '#8B2E2E', accent: '#B98A3C', deco: ['#8B2E2E', '#B98A3C', '#4A5D4E'] },
            medical:  { deep: '#09332F', deep2: '#0E6B60', primary: '#0E9E8C', accent: '#34D3B5', deco: ['#34D3B5', '#F5C86B', '#2E86C1'] },
            edu:      { deep: '#4A2410', deep2: '#8A4B1F', primary: '#E2803A', accent: '#F0B429', deco: ['#F0B429', '#E2803A', '#D45B5B'] },
            agri:     { deep: '#1E3D1A', deep2: '#3E6B2A', primary: '#4E8C3A', accent: '#C9A227', deco: ['#C9A227', '#7BA05B', '#E08A3C'] },
            finance:  { deep: '#0C1A33', deep2: '#1F3864', primary: '#1F3864', accent: '#B8860B', deco: ['#B8860B', '#C99700', '#40607A'] },
            craft:    { deep: '#1F2A30', deep2: '#3D4C55', primary: '#5C6B73', accent: '#E08A38', deco: ['#E08A38', '#A63A2F', '#7A8B5A'] },
            social:   { deep: '#4A2320', deep2: '#8A3F33', primary: '#D46A5C', accent: '#E4A03C', deco: ['#E4A03C', '#D46A5C', '#5E8C7E'] },
            academic: { deep: '#00254D', deep2: '#003F88', primary: '#002FA7', accent: '#2E75B6', deco: ['#2E75B6', '#5B8C5A', '#8B6914'] },
            cyber:    { deep: '#160826', deep2: '#3B2170', primary: '#7C3AED', accent: '#22D3EE', deco: ['#22D3EE', '#A855F7', '#F472B6'] },
            ican:     { deep: '#072C55', deep2: '#0F5C9E', primary: '#0E5EA8', accent: '#2AA9E0', deco: ['#2AA9E0', '#7FC4EE', '#0E5EA8'] },
            biz:      { deep: '#1E242C', deep2: '#3A4654', primary: '#374151', accent: '#6B7280', deco: ['#9AA5B1', '#6B7280', '#C0C8D2'] },
            studio:   { deep: '#111318', deep2: '#2C303C', primary: '#C2185B', accent: '#00ACC1', deco: ['#FF4D6D', '#00E5C0', '#FFC94D'] },
            // 15 套精品（后端会回传 colors，这里是接口拿不到时的兜底）
            star:     { deep: '#06152F', deep2: '#123A6B', primary: '#1F6FB2', accent: '#3FBFEA', deco: ['#3FBFEA', '#7CC4F5', '#1F6FB2'] },
            flat:     { deep: '#0F4C9E', deep2: '#2E7BD6', primary: '#1B6AC9', accent: '#FFB020', deco: ['#FFB020', '#2E9E6B', '#E4572E'] },
            morandi:  { deep: '#3E4C55', deep2: '#6B7A83', primary: '#7C95A6', accent: '#B08C7A', deco: ['#9DAE9E', '#B08C7A', '#A8998C'] },
            clay:     { deep: '#5A4A46', deep2: '#8A736A', primary: '#B08C7A', accent: '#9C8AA5', deco: ['#9C8AA5', '#7D8F69', '#C0A090'] },
            verdant:  { deep: '#EDF4EE', deep2: '#D6E7DA', primary: '#4C9A8A', accent: '#E0A46B', deco: ['#4C9A8A', '#7BA05B', '#E0A46B'] },
            literary: { deep: '#F6EFE2', deep2: '#E8DCC8', primary: '#3E5C6B', accent: '#C87F4A', deco: ['#3E5C6B', '#C87F4A', '#8C7BA6'] },
            ink:      { deep: '#F7F3E8', deep2: '#E8DFC9', primary: '#9E2B25', accent: '#B08D57', deco: ['#9E2B25', '#2F4858', '#B08D57'] }
        };
        function wbHex(c) { c = String(c || ''); return c && c.charAt(0) !== '#' ? '#' + c : c; }
        function wbThemeColors(t) {
            var c = t && t.colors;
            if (c && c.deep) {
                return {deep: wbHex(c.deep), deep2: wbHex(c.deep2), primary: wbHex(c.primary),
                        accent: wbHex(c.accent), deco: (c.deco || []).map(wbHex)};
            }
            return WB_THEME_COLORS[t && t.key] || WB_THEME_COLORS.tech;
        }
        // 画一张迷你封面：底色/构图按这套的 cover 版式（整页渐变 / 左色块 / 顶部色带 / 白底），
        // 页眉样式体现在顶条或左竖条，正文按 cards / 序号 / 极简三种画法 ——
        // 缩略图之间能看出结构差异，而不是 15 张只是颜色不同的方块
        function wbThemeThumb(c, lay) {
            lay = lay || {};
            var cov = lay.cover || 'gradient';
            var light = (cov === 'split' || cov === 'band' || cov === 'paper' || cov === 'orient' ||
                         (cov === 'center' && lay.light_cover));
            var bg;
            if (cov === 'split')      bg = 'linear-gradient(90deg,' + c.deep + ' 0%,' + c.deep2 + ' 40%,#fff 40%,#fff 100%)';
            else if (cov === 'band')  bg = 'linear-gradient(180deg,' + c.primary + ' 0%,' + c.deep2 + ' 42%,#fff 42%,#fff 100%)';
            else if (cov === 'paper') bg = 'linear-gradient(90deg,' + c.primary + ' 0 7%,#fff 7% 100%)';
            else if (cov === 'orient') bg = 'linear-gradient(90deg,#fff 0 86%,' + c.primary + ' 86% 100%)';
            else if (cov === 'star')  bg = 'radial-gradient(circle at 76% 14%, ' + c.deep2 + ' 0%, ' + c.deep + ' 62%)';
            else                      bg = 'linear-gradient(135deg,' + c.deep + ' 0%,' + c.deep2 + ' 100%)';
            var bar = light ? c.primary : '#FFFFFF';
            var line = light ? 'rgba(20,35,61,.30)' : 'rgba(255,255,255,.55)';
            var blk = light ? 'rgba(20,35,61,.07)' : 'rgba(255,255,255,.14)';
            var cls = 'wb-theme-thumb' + (lay.header === 'sidebar' ? ' sidebar'
                                          : (lay.header === 'rule' ? ' nobar' : ''));
            var h = '<div class="' + cls + '" style="background:' + bg + '; --t-primary:' + c.primary +
                    '; --t-accent:' + c.accent + '; --t-bar:' + bar + '; --t-line:' + line + ';">';
            h += '<div class="wb-theme-bar" style="left:12%; top:24%; width:52%;"></div>';
            var body = lay.body || 'cards';
            if (body === 'numbered') {
                h += '<div class="wb-theme-sq" style="background:' + c.accent + '; left:12%; top:44%;"></div>' +
                     '<div class="wb-theme-line" style="left:26%; top:46%; width:46%;"></div>' +
                     '<div class="wb-theme-sq" style="background:' + c.accent + '; left:12%; top:64%;"></div>' +
                     '<div class="wb-theme-line" style="left:26%; top:66%; width:34%;"></div>';
            } else if (body === 'minimal') {
                h += '<div class="wb-theme-dot" style="background:' + c.accent + '; left:12%; top:45%; bottom:auto;"></div>' +
                     '<div class="wb-theme-line" style="left:26%; top:46%; width:54%;"></div>' +
                     '<div class="wb-theme-dot" style="background:' + c.accent + '; left:12%; top:65%; bottom:auto;"></div>' +
                     '<div class="wb-theme-line" style="left:26%; top:66%; width:38%;"></div>';
            } else {
                // cards：两条带底色的卡片块，左侧一条强调色竖条
                h += '<div class="wb-theme-cardblk" style="left:12%; top:42%; width:74%; height:13px; background:' + blk + ';"></div>' +
                     '<div class="wb-theme-sq" style="background:' + c.accent + '; left:13%; top:44%; width:3px; height:9px;"></div>' +
                     '<div class="wb-theme-line" style="left:18%; top:45%; width:56%;"></div>' +
                     '<div class="wb-theme-cardblk" style="left:12%; top:62%; width:74%; height:13px; background:' + blk + ';"></div>' +
                     '<div class="wb-theme-sq" style="background:' + c.accent + '; left:13%; top:64%; width:3px; height:9px;"></div>' +
                     '<div class="wb-theme-line" style="left:18%; top:65%; width:40%;"></div>';
            }
            if (!light) {
                for (var i = 0; i < (c.deco || []).length && i < 3; i++) {
                    h += '<div class="wb-theme-dot" style="background:' + c.deco[i] + '; right:' + (8 + i * 12) + 'px;"></div>';
                }
            }
            // 星空封面：缩略图上也撒几颗星，一眼能和"整页渐变"区分开
            if (cov === 'star') {
                var st = [[14, 16, 2], [40, 10, 1.6], [72, 20, 2], [104, 9, 1.4], [52, 54, 1.6], [96, 40, 1.8]];
                for (var s = 0; s < st.length; s++) {
                    h += '<div style="position:absolute; left:' + st[s][0] + 'px; top:' + st[s][1] +
                         'px; width:' + st[s][2] + 'px; height:' + st[s][2] +
                         'px; border-radius:50%; background:rgba(255,255,255,.9);"></div>';
                }
            }
            // 中国风：右上角朱红竖条 + 左上角朱印方块
            if (cov === 'orient') {
                h += '<div style="position:absolute; left:8px; top:26px; width:8px; height:8px; background:' + c.primary + ';"></div>';
            }
            h += '</div>';
            return h;
        }
        function wbThemeCard(t, cur, reco) {
            var lb = String(t.label || t.key);
            var name = lb, sub = '';
            var p = lb.indexOf('（');
            if (p > 0) { name = lb.slice(0, p); sub = lb.slice(p).replace(/[（）]/g, ''); }
            var isReco = (t.key === reco);
            return '<div class="wb-theme-card' + (t.key === cur ? ' on' : '') + '" data-key="' + _esc(t.key) + '"' +
                   ' onclick="wbPickTheme(\'' + _esc(t.key) + '\')" title="' + _esc(lb) + '">' +
                   (isReco ? '<span style="position:absolute; top:6px; left:6px; z-index:2; padding:1px 6px; border-radius:8px;' +
                             ' font-size:10.5px; background:var(--c-a); color:#fff;">推荐</span>' : '') +
                   wbThemeThumb(wbThemeColors(t), t.layout) +
                   '<div class="wb-theme-name">' + _esc(name) +
                   (sub ? '<div style="font-weight: 400; color: var(--text-mute); font-size: 11px; margin-top: 2px;">' + _esc(sub) + '</div>' : '') +
                   '</div></div>';
        }
        function renderThemeGrid(themes, cur) {
            var g = document.getElementById('deckThemeGrid');
            if (!g) return;
            var reco = wbCompType().theme;
            themes = themes || [];
            var premium = themes.filter(function (t) { return t.tier === 'premium'; });
            var extra = themes.filter(function (t) { return t.tier !== 'premium'; });
            var show = premium.length ? premium : themes;
            var cnt = document.getElementById('deckThemeCount');
            if (cnt) cnt.textContent = show.length;
            // 按风格族分组：15 套一屏排下来没有分类等于没排，用户看不出"哪套适合我"
            var html = '', fam = '';
            show.forEach(function (t) {
                if ((t.family || '') !== fam) {
                    fam = t.family || '';
                    html += '<div style="grid-column:1/-1; display:flex; align-items:center; gap:8px; margin:8px 0 0;">' +
                            '<span style="font-size:12px; font-weight:600;">' + _esc(fam || '内置模板') + '</span>' +
                            '<span style="flex:1; height:1px; background:currentColor; opacity:.16;"></span></div>';
                }
                html += wbThemeCard(t, cur, reco);
            });
            g.innerHTML = html;
            // 旧主题折叠：不删（历史记录可能引用），但不占主视觉
            var eg = document.getElementById('deckThemeExtraGrid');
            if (eg) eg.innerHTML = extra.map(function (t) { return wbThemeCard(t, cur, reco); }).join('');
            var btn = document.getElementById('deckThemeMoreBtn');
            if (btn) btn.style.display = extra.length ? '' : 'none';
            wbRenderReco(reco, cur);
        }
        function wbToggleExtraThemes() {
            var w = document.getElementById('deckThemeExtraWrap');
            var b = document.getElementById('deckThemeMoreBtn');
            if (!w) return;
            var on = w.style.display === 'none';
            w.style.display = on ? 'block' : 'none';
            if (b) b.textContent = on ? '收起备选风格' : '展开更多备选风格';
        }
        // 选中态要在两个网格里同步（精品区 + 备选区各有一批卡片）
        function wbSyncThemeCards(k) {
            var cards = document.querySelectorAll('#deckThemeGrid .wb-theme-card, #deckThemeExtraGrid .wb-theme-card');
            for (var i = 0; i < cards.length; i++) {
                cards[i].classList.toggle('on', cards[i].getAttribute('data-key') === k);
            }
        }
        // 推荐语：说清楚"按哪个赛事推荐、现在用的哪套、能改"，别让用户以为是锁死的
        function wbRenderReco(reco, cur) {
            var el = document.getElementById('deckThemeReco');
            if (!el) return;
            var t = (_themeLib || []).filter(function (x) { return x.key === reco; })[0];
            var curT = (_themeLib || []).filter(function (x) { return x.key === cur; })[0];
            var nm = function (x) {
                var s = String((x && x.label) || '');
                var p = s.indexOf('（');
                return p > 0 ? s.slice(0, p) : (s || '');
            };
            var comp = _wbT((document.getElementById('competition') || {}).value) ||
                       _wbT((window._lastData || {}).competition);
            var head = comp ? '已按 <b>' + _esc(_wbTrim(comp, 22)) + '</b> 推荐 ' : '推荐 ';
            el.innerHTML = head + '<b>' + _esc(nm(t) || reco) + '</b>' +
                           (curT && cur !== reco ? '（当前用的是 ' + _esc(nm(curT)) + '）' : '') +
                           '；点任意一套即可覆盖，换赛事会重新推荐。每套的封面/正文/页眉版式都已定好，不用再单独选。';
        }
        var _themeManual = false;            // 用户手动点过主题后，不再自动改
        // 换赛事时重新按类型推荐主题（用户手动点过就以手动为准）
        function wbApplyCompTheme() {
            if (_themeManual) return;
            var sel = document.getElementById('deckTheme');
            if (!sel || !(_themeLib || []).length) return;
            var reco = wbCompType().theme;
            var has = (_themeLib || []).filter(function (x) { return x.key === reco; })[0];
            if (!has) return;
            sel.value = reco;
            wbSyncThemeCards(reco);
            onThemeChange();
        }
        function wbPickTheme(k) {
            _themeManual = true;
            var sel = document.getElementById('deckTheme');
            if (sel) sel.value = k;
            wbSyncThemeCards(k);
            onThemeChange();
        }

        var _themeLib = null;                       // 后端返回的 {themes:[{key,label,variants:[...]}]}
        async function loadThemeLib() {
            if (_themeLib) return _themeLib;
            try {
                const res = await _wbFetch('/api/ppt_themes');
                const d = await res.json();
                if (d && d.success) _themeLib = d.themes || [];
            } catch (e) { _themeLib = []; }
            return _themeLib || [];
        }
        function _fillSelect(el, items, value) {
            if (!el) return;
            el.innerHTML = items.map(function (it) {
                return '<option value="' + _esc(it.key) + '"' + (it.key === value ? ' selected' : '') + '>' + _esc(it.name || it.label) + '</option>';
            }).join('');
        }
        async function initDeckThemeSelect() {
            const themes = await loadThemeLib();
            if (!themes.length) {
                // 主题清单拿不到时明说，别留一个「0 套」的空框让人以为是功能没做
                var g0 = document.getElementById('deckThemeGrid');
                if (g0) g0.innerHTML = '<div style="grid-column: 1 / -1; font-size: 12.5px; color: var(--text-mute);">' +
                    '主题清单加载失败，刷新页面重试；不影响下载（会用默认主题）。</div>';
                return;
            }
            const rd = window._lastData || {};
            // 主题：优先顶层 theme（后端若提供），回退 rich_deck.theme（当前实际版本）。
            // 版式不再由 variant 决定 —— 15 套模板各自带 layout，前端不提供版式下拉。
            var cur = rd.theme || (rd.rich_deck && rd.rich_deck.theme) || 'star';
            // 按赛事推荐模板：iCAN→蓝白科技、电赛→电路蓝、互联网+→商务灰、
            // 数模→白底建模、挑战杯→红金、广告艺术→海报撞色…用户手动点过就不再动
            if (!_themeManual) {
                var reco = wbCompType().theme;
                if (themes.filter(function (x) { return x.key === reco; }).length) cur = reco;
            }
            _fillSelect(document.getElementById('deckTheme'),
                        themes.map(function (t) { return {key: t.key, name: t.label}; }), cur);
            renderThemeGrid(themes, cur);
            onThemeChange();
        }
        function onThemeChange() {
            const tk = document.getElementById('deckTheme') && document.getElementById('deckTheme').value;
            if (window._lastData && window._lastData.rich_deck) {
                window._lastData.rich_deck.theme = tk;
            }
            previewDeckStyle();
        }
        // 版式的中文说明：告诉用户这套"长什么样"，而不是让他自己拼
        function wbLayoutDesc(t) {
            var L = (t && t.layout) || {};
            var cov = {gradient: '整页渐变封面', split: '左色块封面', band: '顶部色带封面',
                       center: '居中留白封面', paper: '白底学术封面',
                       star: '星空封面', orient: '中国风宣纸封面'}[L.cover] || '';
            var body = {cards: '卡片正文', minimal: '极简条目', numbered: '大号序号'}[L.body] || '';
            var out = [cov, body].filter(Boolean).join(' · ');
            return out || '';
        }
        function previewDeckStyle() {
            // 把选择写回 deck，下载时后端据此渲染
            if (!window._lastData || !window._lastData.rich_deck) return;
            const tk = document.getElementById('deckTheme') && document.getElementById('deckTheme').value;
            const vk = document.getElementById('deckVariant') && document.getElementById('deckVariant').value;
            window._lastData.rich_deck.theme = tk;
            window._lastData.rich_deck.variant = vk;
            if (vk) window._lastData.rich_deck.variant = vk;
            const t = (_themeLib || []).find(function (x) { return x.key === tk; });
            const hint = document.getElementById('deckThemeHint');
            if (hint) {
                var nm = String((t && t.label) || tk);
                var p = nm.indexOf('（');
                if (p > 0) nm = nm.slice(0, p);
                var d = wbLayoutDesc(t);
                hint.style.display = 'block';
                hint.innerHTML = '当前：<b>' + _esc(nm) + '</b>' + (d ? '（' + _esc(d) + '）' : '') +
                                 '　字体：微软雅黑；切换后点"下载 PPT"即生效，不必重新生成';
            }
        }
        // ---- 下载 AI 生成的路演 PPT ----
        async function exportPptx() {
            var rd = window._lastData || {};
            if (!rd.rich_deck) { wbToast('请先用深度版生成一次，才有自动排版的 PPT', { type: 'warn' }); return; }
            previewDeckStyle();
            // 固定路演结构 + 申报书回填：开关开着时导出重排后的 8 页 deck
            var deck = rd.rich_deck;
            if (wbRoadshowOn()) { try { deck = wbRoadshowDeck(rd); } catch (e) { deck = rd.rich_deck; } }
            deck = wbStripDeckTodo(deck);
            var btn = (window.event && window.event.target) || null;
            var _qcTimer = 0;
            if (btn) {
                btn.disabled = true; btn.dataset.old = btn.innerHTML;
                // 122/127 轮：后端导出前先跑系统默认评委打分门（≤3 秒）再生成文件。
                // 按钮如实分两段说：先「质检中」，1.5 秒还没好说明已进生成阶段。
                // 一直写「生成中」的话，用户被质检打回时会以为是网站坏了
                btn.innerHTML = '质检中…';
                _qcTimer = setTimeout(function () { if (btn) btn.innerHTML = '生成文件…'; }, 1500);
            }
            try {
                // 417 轮：把大纲原文一起发给后端，后端据此校验「PPT 页数 == 大纲页数」。
                // 之前后端只拿到重排后的 deck，无从判断页数对不对，等于校验形同虚设。
                var r = await wbExportFetch('/api/export_pptx', {deck: deck, charts: rd.rich_charts || [], tables: rd.rich_tables || [], idea: rd.idea || '', one_liner: rd.one_liner || '',
                                          ppt_outline: rd.ppt_outline || '',
                                          theme: deck.theme, variant: deck.variant, chart_theme: wbChartThemeKey()});
                if (!r.ok) { await wbExportError('路演 PPT', r); return; }
                const res = r.res;
                var blob = await res.blob();
                wbSaveBlob(blob, '路演PPT.pptx');
                wbToast('路演 PPT 已开始下载', { type: 'ok', ms: 3000 });
            } catch (e) {
                wbToast('PPT 导出失败：' + _friendlyErr(e), { type: 'error' });
            } finally {
                if (_qcTimer) clearTimeout(_qcTimer);
                if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old; }
            }
        }
        // 导出中心「路演 PPT」单文件入口：常驻显示（原先挂 deep-only，简洁版整行藏起来，
        // 用户只在打包 zip 里见过 PPT，以为没有单文件入口 —— 第二十轮 #3）。
        // 简洁版没有 rich_deck，直接进 exportPptx 只会弹一句「请先用深度版生成」，
        // 用户不知道下一步怎么办，所以这里给带路径的引导。
        function wbPptDownload() {
            var rd = window._lastData || {};
            if (!rd.rich_deck) {
                wbToast('路演 PPT 是深度完整版专属', {
                    type: 'warn',
                    sub: '把档位切到「深度完整版」重跑一次，就能导出自动排版的 8 页路演 PPT（打包 zip 里也有一份）'
                });
                return;
            }
            exportPptx();
        }
        window.wbPptDownload = wbPptDownload;

        // 结果渲染后同步 PPT 行的档位提示：简洁版把按钮标成「深度版可用」，
        // 避免用户点了才被告知不可用（点了才知道 = 白点一次）
        function wbSyncPptRow() {
            var rd = window._lastData || {};
            var hint = document.getElementById('wbPptModeHint');
            var btn = document.getElementById('wbPptBtn');
            if (!hint || !btn) return;
            // 还没出结果时（生成中/刚打开页面）不给「不可用」的暗示，保持「下载 PPT」，
            // 点了由 wbPptDownload 判断并引导；有结果且确认没 rich_deck 才标「深度版可用」
            var decided = !!window._lastData;
            var noDeck = decided && !rd.rich_deck;
            hint.textContent = noDeck ? '（深度版）' : '';
            btn.textContent = noDeck ? '深度版可用' : '下载 PPT';
        }
        window.wbSyncPptRow = wbSyncPptRow;

        // 统一保存入口：内置浏览器里点了下载只会"没反应"，这里弹提示而不是静默失败；
        // 正常手机浏览器把 a 挂到 DOM 上再点（部分内核不触发游离元素的 click），
        // iOS 对 blob 下载的兼容也一般，补一句兜底提示。
        function wbSaveBlob(blob, name) {
            if (wbInApp()) {
                wbUaCheck();
                wbToast('微信 / QQ 里下载不了文件，请点右上角 ··· 用浏览器打开', {type: 'warn', ms: 4200});
                return;
            }
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url; a.download = name; a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(function () { URL.revokeObjectURL(url); try { document.body.removeChild(a); } catch (e) {} }, 4000);
            if (/iP(hone|ad|od)/.test(navigator.userAgent || '')) {
                setTimeout(function () {
                    wbToast('没弹出下载的话：长按文件 → 选「存储到文件」', {type: 'info', ms: 5000});
                }, 1200);
            }
        }

        function exportSection(id, name) {
            var text = document.getElementById(id).innerText;
            var blob = new Blob([text], {type: "text/plain"});
            wbSaveBlob(blob, name + ".txt");
            wbToast('「' + name + '」已开始下载', { type: 'ok', ms: 2200 });
        }
        // 开始生成
        // ================= 分块流式渲染 =================
        // 后端每跑完一个 LangGraph 节点就把产出的字段塞进 partial，
        // /api/status 一起返回，这里把已有内容先渲染出来，用户不再干等进度条。
        var _STREAM_MAP = [
            ['parsed_rules',        'parsedRules',        'analysis'],
            ['similarity_report',   'similarityReport',   'analysis'],
            ['idea_feedback',       'ideaFeedback',       'analysis'],
            ['competitor_analysis', 'competitorAnalysis', 'deep'],
            ['business_model',      'businessModel',      'deep'],
            ['risk_analysis',       'riskAnalysis',       'deep'],
            ['tech_solution',       'techSolution',       'deep'],
            ['implementation_plan', 'implementationPlan', 'deep'],
            ['social_value',        'socialValue',        'deep'],
            ['project_summary',     'projectSummary',     'analysis'],
            ['proposal_outline',    'proposalOutline',    'proposal'],
            ['proposal',            'proposalText',       'proposal'],
            ['judge_feedback',      'judgeFeedback',      'proposal'],
            ['proposal_analysis',   'proposalAnalysis',   'proposal'],
            ['defense_questions',   'defenseQuestions',   'defense'],
            ['ppt_outline',         'pptOutline',         'defense'],
            ['speech_script',       'speechScript',       'defense']
        ];
        // 必须挂到 window：打字机 twSet 在 index.html 的另一个 script 块里，
        // 它靠 _STREAM_MAP 找字段对应的 DOM id。不挂全局的话 fieldMeta() 永远拿到 undefined，
        // twSet 每次直接 return —— 流式草稿从来没真正渲染过（生成中看不到内容，结束才整页蹦出来）。
        window._STREAM_MAP = _STREAM_MAP;
        var _streamLen = {};          // 字段 -> 已渲染字数，用于判断是否有新增
        var _streamAccum = {};        // 字段 -> 已累积全文（配合后端 cursor 增量，只拉新增后缀）
        var _streamShown = false;     // 结果区是否已因流式内容提前展开
        var _streamTotal = 0;         // 已产出总字数（给进度条显示，裸 length 口径）
        var _streamCjk = 0;           // 徽章专用：只累计 proposal 正文有效字数（剥 Markdown 符号，口径对齐后端 _cjk_len）。speech/deck 等其他字段不计入，避免「已生成 4.7 万字」和正文 1.2 万字对不上
        // 与后端 competition_agents._cjk_len 同一口径：# * ` - | > ( ) （ ） [ ] 和空白都不算字，
        // 否则进度条上写「已生成 3000 字」，实际正文只有 2400 字，用户按字数估算篇幅会被带偏
        function wbCjkLen(text) {
            return (text || '').replace(/[#*`\-\|>()\[\]（）()\s]/g, '').length;
        }

        function streamReset() {
            _streamLen = {}; _streamAccum = {}; _streamShown = false; _streamTotal = 0; _streamCjk = 0;
            window._wbCjkLen = 0;
            document.querySelectorAll('.content-block.streaming').forEach(function (el) {
                el.classList.remove('streaming');
            });
            document.querySelectorAll('.tab.has-stream').forEach(function (el) {
                el.classList.remove('has-stream');
            });
        }

        // 生成开始时给每个区块铺「生成中…」占位，内容一到就替换
        // 传 mode 是为了让深度版提前把 deep-only 区块露出来，
        // 否则实施计划/社会价值/项目简介要等全部跑完才显示，流式阶段白等。
        function streamPrepare(mode) {
            streamReset();
            var _isDeep = mode === 'deep';
            document.querySelectorAll('.deep-only').forEach(function (el) {
                el.style.display = _isDeep ? 'block' : 'none';
            });
            _STREAM_MAP.forEach(function (p) {
                var el = document.getElementById(p[1]);
                if (el) el.innerHTML = '<div class="stream-wait">内容正在生成，将实时流出…</div>';
            });
            var ol = document.getElementById('oneLiner');
            if (ol) ol.innerHTML = '<span style="color:var(--text-mute);font-size:13px;">正在提炼一句话定位…</span>';
        }

        // 刷新占位符统计条：正文里高亮了几处【待你填写：xxx】
        /* ---------- 结果区渲染队列：分帧补画，别让主线程一次锁死 ----------
           15 个板块一起 marked.parse 会把低端机卡住（微信/夸克内核尤其明显：
           卡顿、白屏、渲染到一半内容丢失）。这里按优先级排队，每帧只干 8ms，
           干不完下一帧继续 —— 用户能立刻看到当前 tab，其余在后台慢慢补上。 */
        function wbPaintQueue(q) {
            if (!q || !q.length) return;
            q.sort(function (a, b) { return a[0] - b[0]; });
            var i = 0;
            var raf = window.requestAnimationFrame ||
                      function (f) { return setTimeout(f, 16); };
            function now() {
                return (window.performance && performance.now) ? performance.now() : Date.now();
            }
            function step() {
                var t0 = now();
                while (i < q.length) {
                    try { q[i][1](); } catch (e) { /* 单个板块出错不能连累整份结果 */ }
                    i++;
                    if (now() - t0 > 8) break;   // 本帧时间用完了，剩下的下一帧
                }
                if (i < q.length) raf(step);
            }
            step();
        }

        function wbRefreshPhBar() {
            var bar = document.getElementById('wbPhBar');
            var cnt = document.getElementById('wbPhCount');
            if (!bar || !cnt) return;
            var n = (window.wbCountPlaceholders ? window.wbCountPlaceholders() : 0);
            cnt.textContent = n;
            bar.style.display = n > 0 ? 'block' : 'none';
            wbRefreshBanBar();
            wbScoreTabBadge();   // 占位符数量变了，自评面板标签上的红点要跟着更新
        }

        // 赛道禁忌扫描：只对「有明文禁令」的赛道生效（目前只有 iCAN 创新赛道）。
        // 规则写进 prompt 模型也可能漏，所以成品再扫一遍兜底——这类漏写是真扣分，不是体验问题。
        var WB_BAN_WORDS = ['大学', '学院', '学校', '指导教师', '指导老师', '导师', '教授', '副教授', '讲师'];
        function wbRefreshBanBar() {
            var bar = document.getElementById('wbBanBar');
            var cntEl = document.getElementById('wbBanCount');
            var listEl = document.getElementById('wbBanList');
            if (!bar) return;
            var tk = null;
            try { tk = (evCurrent() || {})._track; } catch (e) {}
            // 没选赛道、或该赛道没有明文禁令 → 不扫描（避免对创业/挑战赛道误报）
            if (!tk || !tk.ban || !tk.ban.length) { bar.style.display = 'none'; return; }

            var root = document.getElementById('results') || document.getElementById('resultArea') || document.body;
            var txt = (root.innerText || root.textContent || '');
            // 「大学」会命中「大学生」——这是大学生赛事，正文必然出现，属于误报，先剥掉再扫
            txt = txt.replace(/大学生/g, '');
            var hits = [];
            for (var i = 0; i < WB_BAN_WORDS.length; i++) {
                var w = WB_BAN_WORDS[i];
                var p = 0, n = 0;
                while ((p = txt.indexOf(w, p)) >= 0) { n++; p += w.length; }
                if (n > 0) hits.push(w + '×' + n);
            }
            if (!hits.length) { bar.style.display = 'none'; return; }
            if (cntEl) cntEl.textContent = hits.length;
            if (listEl) listEl.textContent = '命中：' + hits.join('、') +
                '（也可能命中「大学生」等正常用词，自己核一眼）';
            bar.style.display = 'block';
        }

        // 把后端返回的 partial 渲染进页面；返回本次是否产出了新内容
        function paintPartial(partial) {
            if (!partial || typeof partial !== 'object' || !window.marked) return false;
            var fresh = 0;
            _STREAM_MAP.forEach(function (p) {
                var key = p[0], id = p[1], tab = p[2];
                var txt = partial[key];
                if (!txt) return;
                var el = document.getElementById(id);
                if (!el) return;
                var prev = _streamLen[key] || 0;
                if (txt.length <= prev) return;      // 没有新增就别重渲染，省掉闪烁
                _streamLen[key] = txt.length;
                fresh += txt.length - prev;
                if (key === 'proposal') {
                    _streamCjk += wbCjkLen(txt.slice(prev));   // 只算正文本次新增片段的有效字数
                }
                twSet(key, txt);          // 交给打字机逐字揭示，不再整块覆盖
                el.classList.add('streaming');
                // 该区块所属 Tab 打上脉冲点（提示用户在别的页签有内容流入）
                var tb = document.querySelector('.tab[onclick*="' + tab + '"]');
                if (tb) {
                    if (tab === 'defense') tb.style.display = 'block';   // 答辩页签一有内容就露出
                    if (!tb.classList.contains('active')) tb.classList.add('has-stream');
                }
            });
            if (fresh > 0) wbRefreshPhBar();
            var olTxt = partial.one_liner;
            if (olTxt) {
                var ol = document.getElementById('oneLiner');
                if (ol && ol.innerText !== olTxt) ol.innerText = olTxt;
                // 关键：更新已见长度，否则 cursor 里永远没有 one_liner，
                // 后端每轮都回全量、前端每轮都追加，导致「一句话定位」越滚越长
                _streamLen['one_liner'] = olTxt.length;
            }
            if (fresh > 0) {
                _streamTotal += fresh;
                window._wbCjkLen = _streamCjk;   // 给等待区的「已生成 X 字」徽章取数
                // 第一次有内容就把骨架屏换成真实结果区
                if (!_streamShown) {
                    _streamShown = true;
                    // 113 轮自查：骨架屏→结果区原来是 display 瞬间硬切，两块高度差一大
                    // 就是「闪一下」。这里让骨架屏先淡出再撤，结果区同时淡入，平滑过渡。
                    var _sk = document.getElementById('skeletonArea');
                    if (_sk) {
                        _sk.style.transition = 'opacity .26s ease';
                        _sk.style.opacity = '0';
                        setTimeout(function () { try { _sk.style.display = 'none'; } catch (e) {} }, 280);
                    }
                    var _ra = document.getElementById('resultArea');
                    if (_ra) {
                        _ra.style.display = 'block';
                        _ra.style.transition = 'opacity .26s ease';
                        _ra.style.opacity = '0';
                        // 取一帧再置 1，否则起始值和目标值在同一帧里浏览器直接跳到终态
                        requestAnimationFrame(function () {
                            requestAnimationFrame(function () { _ra.style.opacity = '1'; });
                        });
                    } else {
                        document.getElementById('resultArea').style.display = 'block';
                    }
                    // 生成中先给局部提示条，下载条等 done 再出（历史打开时 _wbGenerating 为 false，不会误亮）
                    if (window._wbGenerating) {
                        var _pnS = document.getElementById('wbPartialNote');
                        if (_pnS) _pnS.style.display = 'block';
                    }
                }
            }
            return fresh > 0;
        }

        // 生成结束：撤掉光标与脉冲点
        function streamFinish() {
            document.querySelectorAll('.content-block.streaming').forEach(function (el) {
                el.classList.remove('streaming');
            });
            document.querySelectorAll('.tab.has-stream').forEach(function (el) {
                el.classList.remove('has-stream');
            });
            document.querySelectorAll('.stream-wait').forEach(function (w) { w.remove(); });
        }

        var _currentTaskId = null;
        function cancelGeneration() {
            if (!_currentTaskId) return;
            // 误触治理：终止是这一页代价最高的操作（深度版要重跑 4~5 分钟），
            // 而它就挨在进度条旁边，手指一滑就点到 → 必须二次确认。
            if (!window.confirm('确定终止本次生成？\n\n已写出的内容会保留，但要拿到完整材料需要重新生成一次（深度版约 4~5 分钟）。')) return;
            fetch('/api/cancel/' + _currentTaskId, { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d && d.success) {
                        wbToast('已请求终止，正在停止…', { type: 'warn' });
                    }
                })
                .catch(function () {});
        }
        /* ---- 系统模拟自评：面板内二级标签 ---- */
        var WB_SUB_TABS = [['score', 'wbSubTabScore'], ['judge', 'wbSubTabJudge'], ['check', 'wbSubTabCheck']];
        function switchScoreTab(ev, name) {
            WB_SUB_TABS.forEach(function (t) {
                // ⚠️ 必须显式写 block/none：写 '' 会回落到样式表里的 none，面板永远不会显示
                var p = document.getElementById('wbSubPanel-' + t[0]);
                if (p) p.style.display = (t[0] === name) ? 'block' : 'none';
                var b = document.getElementById(t[1]);
                if (b) {
                    b.classList.toggle('active', t[0] === name);
                    if (t[0] === name) wbScrollTabIntoView(b);
                }
            });
        }
        // 挂到 window：app.js 整体在 IIFE 里，函数不外露，
        // 而 index.html 的二级 tab 是内联 onclick 调用——不挂就是 ReferenceError，
        // 表现是「点了自查 tab 没反应，还停在评分依据」（第十七轮 #3 的真正根因）
        window.switchScoreTab = switchScoreTab;
        // 自查面板默认不在眼前，未处理项要显示在标签上，否则重要提醒等于被藏起来
        var _wbCheckIssues = { ph: 0, ban: 0, miss: 0 };
        function wbScoreTabBadge() {
            try {
                var phBar = document.getElementById('wbPhBar'), phEl = document.getElementById('wbPhCount');
                _wbCheckIssues.ph = (phBar && phEl && phBar.style.display !== 'none')
                    ? (parseInt(phEl.textContent, 10) || 0) : 0;
                var banEl = document.getElementById('wbBanBar');
                _wbCheckIssues.ban = (banEl && banEl.style.display === 'block') ? 1 : 0;
            } catch (e) {}
            var n = _wbCheckIssues.ph + _wbCheckIssues.ban + _wbCheckIssues.miss;
            var dot = document.getElementById('wbSubCheckDot');
            var tab = document.getElementById('wbSubTabCheck');
            if (dot) dot.textContent = n;
            if (tab) tab.classList.toggle('has-issue', n > 0);
        }

        // ---- 实测数据：拼给后端的 user_data（纯文本，后端按最高优先级事实来源注入 prompt）----
        // 后端是 str(ud)[:3000] 直接进 prompt，所以这里拼成「字段名：值」的自然文本，别传对象（会被 str() 成字典样子）
        var WB_UD_FIELDS = [
            ['udSite', '试点单位/落地场景'], ['udScale', '测试用户数/样本量'],
            ['udMetric', '实测指标'], ['udCost', '成本']
        ];
        function wbUserDataText() {
            var lines = [];
            // 团队信息放最前：后端已改成「有真实团队成员就原样写进团队章节」，
            // 它是评委判断「是不是真有人在做」的第一依据，别混在其它佐证后面被截断
            var tm = document.getElementById('udTeam');
            if (tm && String(tm.value || '').trim()) lines.push('团队成员：' + String(tm.value || '').trim());
            WB_UD_FIELDS.forEach(function (f) {
                var el = document.getElementById(f[0]);
                var v = el ? String(el.value || '').trim() : '';
                if (v) lines.push(f[1] + '：' + v);
            });
            var ex = document.getElementById('udExtra');
            if (ex && String(ex.value || '').trim()) lines.push('其它佐证：' + String(ex.value || '').trim());
            return lines.join('\n');
        }

        /* ---------- 从材料识别：POST /api/parse_material → 自动填充 ----------
           统一材料框架（2026-10-01）：后端 profile 扩展为 12 字段——
           material_type（材料类型）/ competition_name / idea / team /
           实测数据四个分格（site/scale/metric/cost）+ extra（其它佐证）/
           keywords / sections（官方模板章节）。
           填充原则是「建议不是覆盖」：目标框已有内容就先问一句，不偷偷改用户写过的东西。 */
        var WB_MAT_MAP = [
            ['competition_name', 'competition', '赛事'],
            ['idea', 'idea', '创意'],
            ['team', 'udTeam', '团队成员'],
            ['user_data_site', 'udSite', '试点单位'],
            ['user_data_scale', 'udScale', '样本量'],
            ['user_data_metric', 'udMetric', '实测指标'],
            ['user_data_cost', 'udCost', '成本'],
            ['user_data_extra', 'udExtra', '其它佐证'],
            ['keywords', 'keywords', '关键词']
        ];
        // 折叠区与输入框的对应关系：填了哪个框，就把它的折叠区展开，否则填了也看不见
        var WB_MAT_FOLD = {
            udTeam: 'teamBody', udSite: 'userDataBody', udScale: 'userDataBody',
            udMetric: 'userDataBody', udCost: 'userDataBody', udExtra: 'userDataBody',
            keywords: 'advParamBody'
        };
        function wbMatOpen() {
            var m = document.getElementById('wbMatMask'), p = document.getElementById('wbMatPanel');
            // CSS 里初始是 display:none，这里必须显式写具体值（写 '' 会回落到 none，永远不显示）
            if (m) m.style.display = 'block';
            if (p) p.style.display = 'block';
        }
        function wbMatClose() {
            var m = document.getElementById('wbMatMask'), p = document.getElementById('wbMatPanel');
            if (m) m.style.display = 'none';
            if (p) p.style.display = 'none';
        }
        function wbMatGo() {
            var txt = document.getElementById('wbMatText');
            var fin = document.getElementById('wbMatFile');
            var btn = document.getElementById('wbMatGo');
            var text = txt ? String(txt.value || '').trim() : '';
            var file = (fin && fin.files && fin.files[0]) ? fin.files[0] : null;
            if (!text && !file) { wbToast('先粘贴材料文字，或选一个文件', { type: 'warn' }); return; }
            var oldHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> 识别中…';
            var req;
            var _do = (typeof _wbFetch === 'function') ? _wbFetch : fetch;
            if (file) {
                var fd = new FormData();
                fd.append('file', file);
                req = _do('/api/parse_material', { method: 'POST', body: fd }, 120000);
            } else {
                req = _do('/api/parse_material', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text })
                }, 60000);
            }
            req.then(function (r) { return r.json(); })
                .then(function (d) {
                    btn.disabled = false; btn.innerHTML = oldHtml;
                    if (!d || !d.success || !d.profile) {
                        wbToast('没识别出内容：' + ((d && d.error) || '接口没返回画像'), { type: 'warn', ms: 3200 });
                        return;
                    }
                    wbMatApply(d.profile);
                })
                .catch(function (e) {
                    btn.disabled = false; btn.innerHTML = oldHtml;
                    wbToast('识别失败：' + (e && e.message ? e.message : '网络异常'), { type: 'warn', ms: 3200 });
                });
        }
        function wbMatApply(p, opts) {
            opts = opts || {};
            var only = opts.onlyFields || null;
            p = p || {};
            // 旧版 user_data 兜底：四个分格都没识别出来、但汇总 user_data 有值 → 填进「其它佐证」
            var _splitEmpty = ['user_data_site', 'user_data_scale', 'user_data_metric',
                'user_data_cost', 'user_data_extra'].every(function (k) {
                    return !String(p[k] || '').trim();
                });
            if (_splitEmpty && String(p.user_data || '').trim() && (!only || only.indexOf('user_data_extra') >= 0)) {
                p.user_data_extra = p.user_data;
            }
            var empty = [], conflict = [], missed = [], filledIds = [];
            WB_MAT_MAP.forEach(function (m) {
                if (only && only.indexOf(m[0]) < 0) return;
                var v = String(p[m[0]] || '').trim();
                if (!v) { missed.push(m[2]); return; }
                var el = document.getElementById(m[1]);
                if (!el) return;
                if (String(el.value || '').trim()) conflict.push([m, v]); else empty.push([m, v]);
            });
            var hit = empty.length + conflict.length;
            // 官方模板章节：识别出 sections 就写进赛事要求卡（生成时按模板结构写）。
            // 必须放在 hit 早退之前——纯模板材料（只有章节、没别的字段）也要入库，不能被「没找到可填的字段」挡掉
            var secsMsg = '';
            if (!only && String(p.sections || '').trim() && typeof evCurrent === 'function') {
                try {
                    var secs = String(p.sections).split('|').map(function (s) { return s.trim(); })
                        .filter(function (s) { return s && s.length <= 46; });
                    if (secs.length >= 2) {
                        var c0 = evCurrent();
                        c0.sections = secs.slice(0, 20);
                        _wbStoreSet(c0.key, JSON.stringify({ sections: c0.sections }));
                        renderEventCard();
                        secsMsg = '、模板章节 ' + c0.sections.length + ' 个';
                    }
                } catch (e) {}
            }
            if (!hit && !secsMsg) { wbToast('材料里没找到可填的字段，请手动填写', { type: 'warn', ms: 3000 }); return; }
            var doConflict = true;
            if (conflict.length) {
                var names = conflict.map(function (c) { return c[0][2]; }).join('、');
                doConflict = window.confirm('这些框已经有你写过的内容：' + names + '。\n\n点「确定」用识别结果覆盖它们，点「取消」只填还空着的框。');
            }
            empty.forEach(function (c) { document.getElementById(c[0][1]).value = c[1]; filledIds.push(c[0][1]); });
            if (doConflict) conflict.forEach(function (c) { document.getElementById(c[0][1]).value = c[1]; filledIds.push(c[0][1]); });
            try { onCompetitionChange(); } catch (e) {}
            // 填了哪个框，就展开它所在的折叠区（填了看不见等于没填）
            Object.keys(WB_MAT_FOLD).forEach(function (id) {
                if (filledIds.indexOf(id) < 0) return;
                var fold = document.getElementById(WB_MAT_FOLD[id]);
                if (fold && fold.style.display === 'none') {
                    try { wbAdvToggle(WB_MAT_FOLD[id]); } catch (e) { fold.style.display = ''; }
                }
            });
            wbSaveForm();
            wbMatClose();
            var msg = filledIds.length
                ? ('已填充 ' + filledIds.length + ' 项：识别自材料，请核对' + secsMsg)
                : ('已从材料识别' + secsMsg.replace('、', '') + '，请核对');
            if (missed.length) msg += '（未识别：' + missed.join('、') + '）';
            wbToast(msg, { type: 'ok', ms: 4200 });
        }

        /* ---------- 统一材料框架入口：任何导入（上传草稿 / 粘贴文本 / 佐证文件路由）→
           /api/parse_material 一次解析 → wbMatApply 自动填充所有对应输入框。
           识别失败不打断主流程（草稿原文已经填进框里），只提示可重试。
           opts.onlyFields: 只填充指定 profile 字段（如佐证文件路由只填实测数据分格）。 */
        function wbDraftSmartFill(text, opts) {
            opts = opts || {};
            var t = String(text || '').trim();
            if (t.length < 20) {
                if (opts.onFail) opts.onFail('文本太短，没有可识别的信息');
                return;
            }
            var _do = (typeof _wbFetch === 'function') ? _wbFetch : fetch;
            _do('/api/parse_material', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: t.slice(0, 20000) })
            }, 60000).then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d && d.success && d.profile) {
                        try { wbMatApply(d.profile, opts); } catch (e) {}
                        if (opts.onDone) opts.onDone(d.profile);
                    } else {
                        if (opts.onFail) opts.onFail('自动识别没返回结果');
                        else wbToast('自动识别没返回结果，可点「从材料识别」重试', { type: 'warn', ms: 3600 });
                    }
                })
                .catch(function () {
                    if (opts.onFail) opts.onFail('自动识别失败');
                    else wbToast('自动识别失败（不影响已填入的内容），可点「从材料识别」重试', { type: 'warn', ms: 3600 });
                });
        }
        // 第六十九轮【高】的死按钮根因：wbMatOpen / wbMatClose / wbMatGo 都定义在本 IIFE 内，
        // 而「从材料识别」按钮和弹层里的按钮走的是内联 onclick（外层作用域）→ ReferenceError，
        // 点了完全没反应。这是本项目第 N 次踩同一个坑，所以这一簇必须显式挂出去。
        // 校验方式：全仓库 grep 'window.wbMat' 必须命中 3 处，否则按钮必死。
        window.wbMatOpen = wbMatOpen;
        window.wbMatClose = wbMatClose;
        window.wbMatGo = wbMatGo;
        // wbDraftSmartFill 要被前一个 IIFE 里的 ideaFile / wbPasteDraft / wbUdApplyRoute 调用，同样必须挂出去
        window.wbDraftSmartFill = wbDraftSmartFill;

        /* ===== 等待期趣味增强（Codex P3）=====
           只动「生成等待期」的文案，正文 / 表单 / 导出 / 评分权重一律不碰。
           阶段中文名的单一真相源是后端 stage_reporter.STAGE_META（/api/status 的 stage_label），
           这里只额外补一句有温度的话，不覆盖、不替换，避免两边中文打架。 */
        // 全部改成纯文字（第十七轮 #1「全站去 emoji」）：等待期文案挂在进度条下面，
        // emoji 在部分安卓/老 Chromium 上会显示成豆腐块，反而显得页面没做完
        var WB_STAGE_WORD = {
            start:          '开工，先把手头的材料理一理…',
            parsing_rules:  '正在读你们赛事的评分标准…',
            similarity:     '看看有没有人写过一模一样的…',
            idea_scoring:   '给你的创意找一句能记住的定位…',
            analysis:       '把赛题和你的方案对上对…',
            rich_assets:    '先把图表和 PPT 的素材备好…',
            writing:        '正在把创意变成能交的稿子…',
            judging:        '先让系统自己当一次评委…',
            expert_review:  '换几位专家轮流挑毛病…',
            diagnosis:      '找出最容易扣分的地方…',
            revision:       '按挑出来的毛病改一遍…',
            defense:        '猜评委待会儿会问你什么…',
            ppt:            '正在排路演 PPT 的骨架…',
            speech:         '写一份能照着念的路演稿…',
            queued:         '正在给你安排生成引擎…',
            done:           '收个尾，马上就好…',
            error:          '这一步卡住了，正在收尾…'
        };
        // 等待文案轮换：原来是一句永远不变的「正在生成内容…」，等 4 分钟看久了像卡死。
        // 按已耗时轮换（跟着轮询走，不额外起定时器），4 句循环，不刷屏。
        var WB_WAIT_LINE = [
            '正在生成，可以先去做别的事',
            '评委正在挑刺，系统替你先挨一轮批',
            '图表和 PPT 在排队，快了',
            '快了，再等半分钟就好'
        ];
        function wbStageWord(code) {
            return (code && WB_STAGE_WORD[code]) || '';
        }
        // 阶段短标签：进度按钮上那行「正在生成 2% · xxx」挂的是后端 stage code，
        // queued/running 这类英文直出很出戏。这里给一份短中文，按钮上放得下。
        // 后端偶尔会传回中文 stage_label（比如下面的'等待中'），那种原样返回即可。
        var WB_STAGE_SHORT = {
            start: '准备中', parsing_rules: '读评分标准', similarity: '查重比对',
            idea_scoring: '定位创意', analysis: '赛题分析', rich_assets: '备图表素材',
            writing: '写正文', judging: '自评打分', expert_review: '专家评审',
            diagnosis: '找扣分点', revision: '改写润色', defense: '答辩预测',
            ppt: '排 PPT', speech: '写演讲稿', queued: '排队中', running: '生成中',
            pending: '准备中', done: '收尾', finished: '收尾', error: '收尾中', failed: '收尾中'
        };
        function wbStageShort(s) {
            var k = String(s || '').trim();
            if (!k) return '';
            if (WB_STAGE_SHORT[k]) return WB_STAGE_SHORT[k];
            // 未收录但仍是纯英文 code（后端新增阶段时前端还没同步）→ 兜底给「生成中」，
            // 总比把 queued2 这种裸 code 甩给用户强；中文标签原样透传
            return /^[a-z_]+$/.test(k) ? '生成中' : k;
        }
        // 里程碑彩蛋：整个生成过程只弹 2 次（正文完成 / 全部完成），多了就是骚扰
        var _wbMile = {};
        function wbMileOnce(key, msg, type) {
            if (_wbMile[key]) return;
            _wbMile[key] = 1;
            try { wbToast(msg, { type: type || 'ok', ms: 3000 }); } catch (e) {}
        }
        function wbMileReset() {
            for (var k in _wbMile) { if (Object.prototype.hasOwnProperty.call(_wbMile, k)) delete _wbMile[k]; }
        }

        // 团队分工智能建议：按赛事性质给一套「能直接改」的分工骨架。
        // 只是起点，不做任何真实性承诺——学生必须换成自己队友的真名真事，
        // 否则就是给评委送一个「团队是编的」的把柄。
        var WB_TEAM_TPL = {
            '工程创新类': '队长（计算机 / 自动化学院）：统筹进度 + 核心算法\n' +
                          '硬件 / 结构：样机设计与加工、可靠性测试\n' +
                          '软件 / 算法：模型训练与接口开发\n' +
                          '调研 / 文档：用户调研、数据采集与材料撰写',
            '创新创业类': '负责人：整体统筹 + 对外对接\n' +
                          '技术：产品原型与技术实现\n' +
                          '市场：用户调研、渠道与定价\n' +
                          '运营 / 财务：成本测算、收支与落地推进',
            '学术类': '第一作者：研究设计与论文主笔\n' +
                      '实验：数据采集与实验验证\n' +
                      '分析：数据处理与结果分析\n' +
                      '文献：文献综述与格式校对',
            '建模类': '建模：模型假设与建立\n' +
                      '求解：算法实现与编程\n' +
                      '写作：论文撰写与排版',
            'default': '队长：统筹进度 + 核心模块\n' +
                       '技术：原型开发与测试\n' +
                       '调研：用户调研与数据\n' +
                       '文档：材料撰写与排版'
        };
        function wbTeamSuggest() {
            var ta = document.getElementById('udTeam');
            if (!ta) return;
            if (String(ta.value || '').trim() &&
                !window.confirm('已经填过团队成员了，用建议模板覆盖？\n\n点「确定」覆盖，点「取消」保留你写的。')) return;
            var tpl = WB_TEAM_TPL['default'];
            try {
                var nm = (document.getElementById('competition') || {}).value || '';
                var tp = (typeof wbCompTypeOf === 'function') ? wbCompTypeOf(nm) : '';
                if (tp && WB_TEAM_TPL[tp]) tpl = WB_TEAM_TPL[tp];
            } catch (e) {}
            ta.value = tpl;
            // 展开这一块，不然填完了看不见，用户会以为没生效
            var b = document.getElementById('teamBody');
            if (b) { b.style.display = 'block'; var ar = document.getElementById('teamBodyArrow'); if (ar) ar.textContent = '▾'; }
            try { ta.focus(); } catch (e) {}
            try { wbSaveForm(); } catch (e) {}
            wbToast('已填入一套分工模板，请改成你队友的真实姓名与分工', { type: 'ok', ms: 4200 });
        }
        window.wbTeamSuggest = wbTeamSuggest;

        /* 双通路选择弹窗（2026-10-01）：创意框和草稿框都有内容时弹出，
           用户点选本次走哪条通路，避免草稿静默劫持创意输入。
           一次性选择：选完重新走 startWork，_wbPathChoice 用后即清。 */
        function wbPathDialog() {
            var old = document.getElementById('wbPathDlg');
            if (old) old.remove();
            var veil = document.createElement('div');
            veil.id = 'wbPathDlg';
            veil.style.cssText = 'position:fixed;inset:0;z-index:1900;background:rgba(8,12,30,.55);display:flex;align-items:center;justify-content:center;padding:20px;';
            veil.innerHTML =
                '<div style="max-width:420px;width:100%;background:var(--card,#fff);border:1px solid var(--line,#e3e8f5);border-radius:14px;padding:22px 20px;box-shadow:0 18px 48px rgba(0,0,0,.28);">' +
                    '<div style="font-size:16px;font-weight:700;color:var(--text,#1a2340);margin-bottom:6px;">本次按哪条通路生成？</div>' +
                    '<div style="font-size:13px;color:var(--text-mute,#4a5575);line-height:1.7;margin-bottom:16px;">检测到「项目创意」和「申报书草稿」都填了内容，两者不会同时使用，请指定本次的输入来源（另一个不受影响）。</div>' +
                    '<div style="display:flex;gap:10px;flex-wrap:wrap;">' +
                        '<button id="wbPathIdea" style="flex:1;min-width:150px;padding:10px 14px;border:none;border-radius:9px;cursor:pointer;background:var(--c-a,#3b82f6);color:#fff;font-size:14px;">从创意生成</button>' +
                        '<button id="wbPathDraft" style="flex:1;min-width:150px;padding:10px 14px;border:1px solid var(--line,#e3e8f5);border-radius:9px;cursor:pointer;background:transparent;color:var(--text,#1a2340);font-size:14px;">优化我的草稿</button>' +
                    '</div>' +
                    '<div style="margin-top:12px;text-align:right;"><span id="wbPathCancel" style="font-size:12.5px;color:var(--text-mute,#4a5575);cursor:pointer;">取消</span></div>' +
                '</div>';
            document.body.appendChild(veil);
            var close = function () { veil.remove(); };
            veil.addEventListener('click', function (e) { if (e.target === veil) close(); });
            document.getElementById('wbPathCancel').onclick = close;
            document.getElementById('wbPathIdea').onclick = function () {
                window._wbPathChoice = 'idea'; close(); try { startWork(); } catch (e) {}
            };
            document.getElementById('wbPathDraft').onclick = function () {
                window._wbPathChoice = 'draft'; close(); try { startWork(); } catch (e) {}
            };
        }
        window.wbPathDialog = wbPathDialog;

        function startWork() {
            const idea = document.getElementById('idea').value.trim();
            const proposal_draft = document.getElementById('proposal_draft').value.trim();
            const competition = document.getElementById('competition').value;
            const mode = document.querySelector('input[name="mode"]:checked').value;

            // 双通路显式选择（2026-10-01）：创意和草稿都填了时，让用户指定本次走哪条通路。
            // 之前 proposal_draft 有字就静默切「优化」模式、创意被忽略——两条通路不是并行是草稿劫持。
            // 例外：本会话从第 1 步导入过草稿（上传/粘贴/佐证路由）的，意图明确是「优化我的草稿」——
            // 此时创意框的内容本来就是系统从草稿里识别填充的，再弹窗问一遍属于自找麻烦，直接走草稿。
            // 想改走创意：把草稿框清空即可（草稿为空时自然走创意通路）。
            if (idea && proposal_draft && !window._wbPathChoice && !window._wbDraftImported) { wbPathDialog(); return; }
            var _useDraft = (window._wbPathChoice === 'draft') ? true
                          : (window._wbPathChoice === 'idea') ? false
                          : proposal_draft.length > 0;
            window._wbPathChoice = null;   // 一次性选择，下次再弹
            const isOptimize = _useDraft;
            var draftOut = _useDraft ? proposal_draft : '';   // 创意通路：草稿留在框里但本次不参与

            window._wbGenerating = true;   // 下载条/吸附 dock 以此为准：done 前一律不出
            window._lastGenMode = mode;    // 导出质量门按真实模式评分（fast 不按 deep 标准误杀）
            // 赛事是必填项：后端会返回 400「请先选择赛事」，但等到那时候用户已经点了按钮、
            // 看到进度条再弹回，体验上是「网站故障」。这里当场拦下并把赛事框标出来
            var _ceEl = document.getElementById('competition');
            var _ceVal = _ceEl ? String(_ceEl.value || '').trim() : '';
            if (!_ceVal) {
                window._wbGenerating = false;
                wbToast('请先选择或填写赛事名称', { type: 'warn', sub: '不同赛事的评审侧重不同，选了才能对准评分点写' });
                if (_ceEl) {
                    if (_ceEl.focus) try { _ceEl.focus(); } catch (e) {}
                    _ceEl.classList.remove('wb-shake-hl');
                    void _ceEl.offsetWidth;
                    _ceEl.classList.add('wb-shake-hl');
                    setTimeout(function () { _ceEl.classList.remove('wb-shake-hl'); }, 1600);
                }
                return;
            }
            if (!idea && !proposal_draft) {
                window._wbGenerating = false;
                wbToast('请先填写项目创意，或粘贴一段申报书草稿', { type: 'warn' });
                var _ie = document.getElementById('idea');
                if (_ie) {
                    if (_ie.focus) _ie.focus();
                    // 红框抖两下：光标聚焦在手机上不够显眼，加上视觉标记才能一眼定位
                    _ie.classList.remove('wb-shake-hl');
                    void _ie.offsetWidth;   // 重启动画
                    _ie.classList.add('wb-shake-hl');
                    setTimeout(function () { _ie.classList.remove('wb-shake-hl'); }, 1600);
                }
                return;
            }

            const btn = document.getElementById('startBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> 系统正在' + (isOptimize ? '优化' : '生成') + '，请耐心等待...';
            document.getElementById('progressSteps').style.display = 'block';
            document.getElementById('cancelWrap').style.display = 'block';
            try { wbHideRetry(); } catch (e) {}
            var _eb0 = document.getElementById('etaBadge');
            if (_eb0) { _eb0.style.display = 'inline-block'; _eb0.innerText = '预计 --'; }
            document.getElementById('skeletonArea').style.display = 'block';
            document.getElementById('resultArea').style.display = 'none';
            wbFabHide();   // 重新生成期间旧结果的导出按钮先收起来
            _currentTaskId = null;
            streamPrepare(mode);   // 铺「生成中…」占位，等后端 partial 一到就逐块替换成真内容

            // ★ 真实进度：走异步接口 + 轮询 /api/status，百分比来自后端 stage
            // 注意：后端前几个节点是并行跑的，stage 会乱序跳变，所以百分比只涨不跌
            let _maxPct = 0;
            var _curStageLabel = '';
            var _curStageCode = '';
            wbMileReset();   // 每次生成重置，里程碑彩蛋一轮只弹 2 次
            // 进度条在页面 y≈1500px 处（移动端实测），光更新它用户根本看不到——
            // 视口里只有顶上那条 sticky 的开始按钮。所以同一个百分比/阶段也写进按钮文案，
            // 用户不滚动也能看到「正在推进」（深度版要等 3 分半，看不到反馈会以为卡死）。
            const _setBar = (pct, label, stageText) => {
                if (pct > _maxPct) _maxPct = pct;
                document.getElementById('fastProgress').style.width = Math.max(_maxPct, 0) + '%';
                document.getElementById('fastProgressText').innerText = label;
                var _b = document.getElementById('startBtn');
                if (_b && _b.disabled) {
                // 169 轮：sticky 按钮上的百分比必须写明是「整体进度」，
                // 否则它会和下方智能体面板的「环节 2/9」被当成同一个指标前后打架。
                // 阶段名不再挂按钮后面（太挤），统一给 fastProgressText 那行显示
                _b.innerHTML = '<span class="spinner"></span> ' +
                    (isOptimize ? '正在优化' : '正在生成') + ' · 整体 ' + Math.max(_maxPct, 0) + '%';
                }
                // 126 轮：已用时间。惰性初始化而不是读外层 t0——_setBar 定义在 t0 之前，
                // 直接引用会踩 let 的 TDZ（首次调用时 t0 还没初始化，直接 ReferenceError）。
                var _eb = document.getElementById('elapsedBadge');
                if (_eb) {
                    if (!window._wbGenT0) window._wbGenT0 = Date.now();
                    var _es = Math.round((Date.now() - window._wbGenT0) / 1000);
                    _eb.style.display = 'inline-block';
                    _eb.innerText = _es >= 60
                        ? ('已用 ' + Math.floor(_es / 60) + ' 分 ' + (_es % 60) + ' 秒')
                        : ('已用 ' + _es + ' 秒');
                }
                // 等待期人话副标题：只补在进度条下面，不动上面那行准确文案。
                // 用 textContent 而不是 innerHTML：文案是写死的常量，没必要开 HTML 口子
                var _sw = document.getElementById('wbStageWord');
                if (_sw) {
                    var _w = wbStageWord(_curStageCode);
                    _sw.textContent = _w;
                    _sw.style.display = _w ? 'block' : 'none';
                }
            };
            _setBar(2, '正在提交任务…');
            // 生成一开始就把进度区带进视野：移动端实测进度条在 y≈1500px，不滚过去等于没有。
            setTimeout(function () {
                var _ps = document.getElementById('progressSteps');
                if (!_ps) return;
                try { _ps.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
                // 平滑滚动在微信 / 夸克内核里经常不动（实测 headless 下也是 0），
                // 700ms 后检查一次：还在视野外就直接定位，保证用户一定看得到进度条。
                setTimeout(function () {
                    try {
                        var r = _ps.getBoundingClientRect();
                        var vh = window.innerHeight || 600;
                        if (r.top > vh * 0.85 || r.bottom < 60) {
                            var delta = r.top - vh / 2 + r.height / 2;
                            // 页面是 body{overflow-y:auto} 的自滚动容器，window.scrollTo 对它无效，
                            // 必须同时驱动 scrollingElement 和 body，少一个就滚不动
                            try { window.scrollBy(0, delta); } catch (e) {}
                            try {
                                var sc = document.scrollingElement || document.documentElement;
                                sc.scrollTop += delta;
                            } catch (e) {}
                            try { document.body.scrollTop += delta; } catch (e) {}
                        }
                    } catch (e) {}
                }, 700);
            }, 60);

            fetch('/api/generate_async', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    competition_name: competition,
                    idea: idea,
                    proposal_draft: draftOut,
                    mode: mode,
                    // 文风：standard=标准 / strong=去 AI 味。
                    // 与 Codex 约定：只在深度版生效，简洁版一律按 standard 传，避免和「短而准」冲突
                    humanize: (mode === 'deep'
                        ? ((document.querySelector('input[name=humanize]:checked') || {}).value || 'standard')
                        : 'standard'),
                    keywords: (document.getElementById('keywords') || {}).value || '',
                    // 简洁版「低分自动补写」：后端 should_iterate_fast 只在显式收到 true 时才返工一轮，
                    // 默认 false 保持「50 秒出稿」。深度版迭代由后端自行控制，这里统一传 false 不干扰。
                    iterate: !!(mode === 'fast'
                        && document.getElementById('iterateOpt')
                        && document.getElementById('iterateOpt').checked),
                    // 用户实测数据：后端注入为最高优先级事实来源，给了的数字原文使用并标「实测值」，
                    // 没给的才用测算值。全空就传空串，后端 _user_data_ref 返回空、不影响原有链路
                    user_data: wbUserDataText(),
                    // 赛事官方文件：后端已有 rule_content 链路，这里把前端口子接上
                    // 官方文件文本 + 赛道规则：后端 rule_content 直接进 prompt，不用改后端
                    rule_content: (function () {
                        var up = (document.getElementById('rules') || {}).value || '';
                        var tr = '';
                        try { tr = evTrackRule(); } catch (e) {}
                        return [up, tr].filter(function (x) { return x; }).join('\n\n');
                    })(),
                    theme: (document.getElementById('deckTheme') || {}).value || null,
                    // 171 轮：图表配色主题。后端 rich_pipeline 已有 pick_theme/render_chart(theme=)，
                    // 接上这个字段后，深度版生成的图表 PNG 就与前台所选配色一致（后端未接则忽略）
                    chart_theme: wbChartThemeKey(),
                    // 赛事要求卡：后端收到就按这个结构生成（不认识该字段会自动忽略，不影响旧链路）
                    doc_type: (evCurrent() || {}).doc_type || null,
                    // 与 Codex 约定：章节定制只对深度版生效，简洁版保持「短而准」的精简五章
                    outline_requirement: (mode === 'deep' ? ((evCurrent() || {}).sections || []) : []),
                    scoring_weights: ((evCurrent() || {}).scoring || []).filter(function (x) { return _wbPctOf(x) !== null; })
                })
            })
            .then(res => res.json().catch(function () { return {}; }).then(function (j) {
                // 原来直接 res.json()：后端 400/500 时被当正常响应往下走，错误体里真正的
                // 原因（如「请先选择赛事」）被泛化文案盖掉。这里先把 HTTP 状态和后端 error 捞出来
                if (!res.ok || (j && j.success === false)) {
                    var e0 = new Error((j && (j.error || j.message)) || ('服务返回 ' + res.status));
                    e0.httpStatus = res.status;
                    e0.code = (j && j.code) || null;
                    e0.isCreateFail = true;
                    throw e0;
                }
                return j;
            }))
            .then(start => {
                if (!start.success || !start.task_id) {
                    var e1 = new Error(start.error || '任务创建失败');
                    e1.isCreateFail = true;
                    throw e1;
                }
                _currentTaskId = start.task_id;
                // 暴露给导出用：导出申报书时连同 task_id 一起提交，后端可回库取干净原文
                window._currentTaskId = start.task_id;
                let t0 = Date.now();
                let _hiddenAt = 0;
                document.addEventListener('visibilitychange', function () {
                    if (document.hidden) { _hiddenAt = Date.now(); }
                    else if (_hiddenAt) { t0 += Date.now() - _hiddenAt; _hiddenAt = 0; }
                });
                // 看门狗：fast 5 分钟 / deep 12 分钟（深度版实测 4~5 分钟、产出约 1.2 万字，负载高时更久，
                // 5 分钟看门狗会在后端还在正常跑时误报「等待超时」）；
                // queued 再统一放宽到 15 分钟。
                const WATCHDOG_MS = (mode === 'deep' ? 12 : 5) * 60 * 1000;
                let _queuedSeen = false;
                return new Promise((resolve, reject) => {
                    // 167 轮：原来是每 800ms 打一次 /api/status（还外加 speech_stream），
                    // 手机上连续几分钟的高频请求 + 重渲染是发烫主因之一。改为：
                    //   ① 前台 2s 一次（流式预览仍然连贯）；② 页面切到后台完全不请求；
                    //   ③ 回到前台立刻补拉一次，不用等下一个 tick。
                    const _poll = () => {
                        // 切后台/锁屏时彻底停手：省电、省流量，也不给后端添无意义负载
                        if (document.hidden) return;
                        if (Date.now() - t0 > (_queuedSeen ? 15 * 60 * 1000 : WATCHDOG_MS)) {
                            clearInterval(tick);
                            reject(new Error('等待超时（' + (WATCHDOG_MS / 60000) + ' 分钟未完成）。可能是服务重启过或任务被中断，请重新生成'));
                            return;
                        }
                        fetch('/api/status/' + start.task_id + '?cursor=' + encodeURIComponent(JSON.stringify(_streamLen)))
                            .then(r => r.json())
                            .then(res2 => {
                                if (!res2.success) {
                                    clearInterval(tick);
                                    reject(new Error((res2.error || '任务已失效') +
                                        (res2.detail ? '（' + res2.detail + '）' : '')));
                                    return;
                                }
                                if (res2.status === 'queued') {
                                    // 排队兜底（并发 16 路正常永远碰不到）：默认只说「正在安排」，
                                    // 超过 20 秒还没轮到才诚实显示位次；queued 期间放宽看门狗到 15 分钟
                                    _queuedSeen = true;
                                    var _qp = res2.queue_position || 1;
                                    var _qw = res2.queue_wait_seconds || 0;
                                    var _qmsg = (Date.now() - t0 > 20000 && _qp > 1)
                                        ? ('生成需求较多，你前面还有 ' + (_qp - 1) + ' 人，预计 ' +
                                           (_qw >= 60 ? Math.ceil(_qw / 60) + ' 分钟' : _qw + ' 秒') + '内开始，无需操作')
                                        : '生成需求较多，正在为你安排引擎，马上开始，无需操作';
                                    _curStageLabel = '等待中';
                                    _curStageCode = 'queued';
                                    _setBar(2, _qmsg, '等待中');
                                    try { wbAgentStage('queued', '等待中'); } catch (e) {}
                                    return;
                                }
                                if (res2.status === 'running') {
                                    const sec = Math.round((Date.now() - t0) / 1000);
                                    // ★ 分块流式：后端每跑完一个节点就返回已产出内容，这里立刻渲染
                                    // cursor 增量：后端只回每个字段「新增后缀」，这里累加成全文再渲染
                                    var _p = res2.partial || {};
                                    Object.keys(_p).forEach(function (f) {
                                        _streamAccum[f] = (_streamAccum[f] || '') + (_p[f] || '');
                                    });
                                    paintPartial(_streamAccum);
                                    try { wbAgentStage(res2.stage, res2.stage_label); } catch (e) {}
                                    if (res2.stage_label) _curStageLabel = String(res2.stage_label);
                                    if (res2.stage) _curStageCode = String(res2.stage);
                                    // 里程碑 1/2：正文写完、评委接手。其余阶段不弹，避免刷屏
                                    if (res2.stage === 'judging' || res2.stage === 'expert_review' ||
                                        res2.stage === 'diagnosis' || res2.stage === 'revision') {
                                        wbMileOnce('body', '正文完成，模拟评委开始挑刺…');
                                    }
                                    var _eta = parseInt(res2.eta_seconds || 0, 10);
                                    // 剩余时间单独挂徽章，混在长句里没人看得见
                                    var _eb = document.getElementById('etaBadge');
                                    if (_eb) {
                                        if (_eta > 0) {
                                            _eb.style.display = 'inline-block';
                                            _eb.innerText = '还需 ' + (_eta >= 60 ? (Math.ceil(_eta / 60) + ' 分钟') : (_eta + ' 秒'));
                                        } else {
                                            // 前几个节点并行跑时后端还没算出 eta，此时给档位经验值，别让徽章消失造成"没反馈"
                                            _eb.style.display = 'inline-block';
                                            _eb.innerText = isOptimize ? '预计 2-3 分钟'
                                                : (mode === 'deep' ? '预计 4~5 分钟' : '预计约 1 分钟');
                                        }
                                    }
                                    // 档位名原来写死「深度版」，选简洁版非优化时会把用户说成在跑深度版
                                    var _tierName = isOptimize ? '优化' : (mode === 'deep' ? '深度版' : '简洁版');
                    // 等待文案轮换：每 12 秒换一句，等几分钟不至于一直盯着同一句话
                    var _waitLine = WB_WAIT_LINE[Math.floor(sec / 12) % WB_WAIT_LINE.length];
                    // 169 轮：这行原来把「预计还需 / 当前阶段 / 已产出字数 / 终止提示」全拼成一句长句，
                    // 窄屏下被右侧徽章挤成 160px 竖条。现在按「谁已经有专门位置」拆分：
                    //   剩余时间 → etaBadge；已用时间 → elapsedBadge；字数 → lenBadge（唯一口径）
                    // 本行只留「档位 · 阶段 · 一句温度话」，短句 + 居中 + 自动换行，不再溢出
                    var _stageShort = wbStageShort(res2.stage_label || _curStageLabel);
                    var _barLine = _tierName + (_stageShort ? ' · ' + _esc(_stageShort) : '') +
                        ' · ' + _waitLine;
                    _setBar(res2.pct || 0, _barLine, res2.stage_label || _curStageLabel);
                    // 超时安抚塞副标题行（12.5px 小字），不占主行宽度
                    if (sec >= 240) {
                        var _swT = document.getElementById('wbStageWord');
                        if (_swT) {
                            _swT.textContent = '等得久了可以点下方「终止生成」重来，已跑的不浪费，可再用同样的内容重跑';
                            _swT.style.display = 'block';
                        }
                    }
                                    // 演讲稿流式预览：stage 到 speech 时，实时显示已生成字数
                                    if (res2.stage === 'speech') {
                                        fetch('/api/speech_stream/' + start.task_id)
                                            .then(function (r) { return r.json(); })
                                            .then(function (ss) {
                                                if (ss && ss.success && ss.text) {
                                                    _setBar(res2.pct || 0,
                                                        // 169 轮：带上「演讲稿」前缀——同屏还有 lenBadge 的「正文 N 字」，
                                                        // 不标明的话又变成两个无标注字数
                                                        '正在撰写演讲稿 · 演讲稿 ' + ss.text.length +
                                                        ' 字（预计 2-3 分钟，无需等待，可以先去做别的事）');
                                                }
                                            })
                                            .catch(function () {});
                                    }
                                    return;
                                }
                                clearInterval(tick);
                                if (res2.status === 'error') {
                                    window._wbGenerating = false;
                                    var _pnE = document.getElementById('wbPartialNote'); if (_pnE) _pnE.style.display = 'none';
                                    // 后端 /api/status 会给 error + detail，detail 才是原始报错。
                                    // 只弹 error 的话用户看到的是「生成失败」四个字，等于没说，
                                    // 也没法判断是自己网络问题还是服务挂了
                                    reject(new Error((res2.error || '生成失败') +
                                        (res2.detail ? '（' + res2.detail + '）' : '')));
                                } else if (res2.status === 'cancelled') {
                                    window._wbGenerating = false;
                                    var _pnC = document.getElementById('wbPartialNote'); if (_pnC) _pnC.style.display = 'none';
                                    reject({ cancelled: true });
                                } else {
                                    resolve({ success: true, data: res2.data });
                                }
                            })
                            .catch(e => { clearInterval(tick); reject(e); });
                    };
                    const tick = setInterval(_poll, 2000);
                    document.addEventListener('visibilitychange', function () {
                        if (!document.hidden) { try { _poll(); } catch (e) {} }
                    });
                });
            })
            .then(data => {
                streamFinish();   // 撤掉流式光标与脉冲点，交由最终渲染统一覆盖
                try { wbAgentFinish(true); } catch (e) {}
                window._wbGenerating = false;
                // 整轮跑完才亮出下载条；生成中的局部提示撤掉
                try {
                    var _qeb = document.getElementById('quickExportBar');
                    var _pn = document.getElementById('wbPartialNote');
                    if (data && data.success) {
                        if (_pn) _pn.style.display = 'none';
                        if (_qeb) _qeb.style.display = 'flex';
                    } else {
                        if (_pn) _pn.style.display = 'none';
                    }
                } catch (e) {}
                window._lastMode = mode;   // 档位单一真相源：结果页徽章、历史打开都读它
                // 里程碑 2/2：整轮只弹这一次收尾彩蛋
                wbMileOnce('all', mode === 'deep' ? '搞定，三件套已生成'
                                                  : '搞定，申报书已生成');
                document.getElementById('fastProgress').style.width = '100%';
                setTimeout(() => {
                    document.getElementById('progressSteps').style.display = 'none';
                    document.getElementById('cancelWrap').style.display = 'none';
                    _currentTaskId = null;
                    btn.disabled = false;
                    btn.innerHTML = '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-rocket"/></svg> 开始' + (proposal_draft.length > 0 ? '优化' : '生成');
                    if (data.success) {
                        document.getElementById('skeletonArea').style.display = 'none';
                        document.getElementById('resultArea').style.display = 'block';
                        // 默认直接看「申报与评审」（正文），不把规则解析/评委打分糊在用户脸上
                        try { switchTab(null, 'proposal'); } catch (e) {}
                        // ===== 结果渲染：入队分帧，不一把梭 =====
                        // 微信 / 夸克 / 百度App 的内核在手机上一次性跑 15 个板块的
                        // marked.parse + innerHTML 会锁死主线程：卡顿、白屏、甚至渲染到一半丢内容。
                        // 改成按优先级入队、每帧限时补画；依赖 DOM 的判断全排到渲染之后。
                        window._lastData = data.data;
                        const isDeep = mode === 'deep';
                        var _Q = [];
                        function _P(prio, fn) { _Q.push([prio, fn]); }

                        // ---- 0：分数，第一眼要看到的 ----
                        _P(0, function () {
                            document.getElementById('scoreNum').innerText = data.data.score;
                            // 174 轮：分数出来才知道够不够入库门槛（≥85），顺手同步「沉淀」入口
                            try {
                                window._wbLastScore = parseInt(data.data.score, 10) || 0;
                                wbTrainArchiveSync(window._wbLastScore);
                            } catch (e) {}
                        });
                        _P(0, function () {
                            var si = document.getElementById('simInfo');
                            if (si) {
                                var s = data.data.similarity || {};
                                // 空值一律「暂无」：显示「—」用户分不清是「没数据」还是「加载坏了」
                                si.innerText = (typeof s.percent === 'number') ? (Math.round(s.percent * 10) / 10) + '%' : '暂无';
                                si.title = (s.checked ? '与本地 ' + s.checked + ' 条范文对比（本地初检，非知网正式查重）' : '本地初检，非正式查重');
                            }
                        });
                        // ---- 1：当前 tab（默认「前期分析」）里的板块先画 ----
                        _P(1, function () { document.getElementById('parsedRules').innerHTML = wbRenderMD(data.data.parsed_rules); });
                        _P(1, function () { document.getElementById('similarityReport').innerHTML = wbRenderMD(data.data.similarity_report); });
                        // ---- 2~5：核心内容 ----
                        if (data.data.proposal_outline) _P(2, function () { document.getElementById('proposalOutline').innerHTML = wbRenderMD(data.data.proposal_outline); });
                        _P(2, function () {
                            var sc = document.getElementById('proposalSelfcheck');
                            if (sc && data.data.proposal_selfcheck) {
                                sc.textContent = data.data.proposal_selfcheck;
                                sc.style.display = 'block';
                            }
                        });
                        _P(3, function () { document.getElementById('proposalText').innerHTML = wbRenderMD(data.data.proposal); });
                        _P(3, function () { document.getElementById('judgeFeedback').innerHTML = wbRenderMD(data.data.judge_feedback); });
                        _P(4, function () { renderExpertReview(data.data.expert_review); });
                        _P(4, function () { renderJudgeScores(data.data.judge_scores); });
                        _P(4, function () { renderIdeaRadar(data.data.scores, data.data.idea_score); });
                        _P(5, function () { document.getElementById('proposalAnalysis').innerHTML = wbRenderMD(data.data.proposal_analysis); });
                        // ---- 6~8：深度版专属板块 ----
                        if (data.data.competitor_analysis) _P(6, function () { document.getElementById('competitorAnalysis').innerHTML = wbRenderMD(data.data.competitor_analysis); });
                        if (data.data.business_model) _P(6, function () { document.getElementById('businessModel').innerHTML = wbRenderMD(data.data.business_model); });
                        if (data.data.risk_analysis) _P(6, function () { document.getElementById('riskAnalysis').innerHTML = wbRenderMD(data.data.risk_analysis); });
                        if (data.data.tech_solution) _P(7, function () { document.getElementById('techSolution').innerHTML = wbRenderMD(data.data.tech_solution); });
                        // 实施计划：深度版独立产出，之前前端缺展示块，内容白白浪费
                        if (data.data.implementation_plan) _P(7, function () { document.getElementById('implementationPlan').innerHTML = wbRenderMD(data.data.implementation_plan); });
                        // 社会价值 / 项目简介：后端已返回，之前漏了往这两个 div 写内容，导致一直空白
                        if (data.data.social_value) _P(7, function () { document.getElementById('socialValue').innerHTML = wbRenderMD(data.data.social_value); });
                        if (data.data.project_summary) _P(7, function () { document.getElementById('projectSummary').innerHTML = wbRenderMD(data.data.project_summary); });
                        if (data.data.defense_questions) _P(8, function () { document.getElementById('defenseQuestions').innerHTML = wbRenderMD(data.data.defense_questions); });
                        if (data.data.ppt_outline) _P(8, function () { document.getElementById('pptOutline').innerHTML = wbRenderMD(data.data.ppt_outline); });
                        // ---- 9：富媒体（图表 / 表格 / deck），DOM 最重，放最后 ----
                        _P(9, function () { renderRich(data.data, isDeep); });

                        // ---- 20：以下都要读已渲染的 DOM，必须排在所有渲染任务之后 ----
                        _P(20, function () {
                            // T2 深度版专属板块：显示时加高亮（左侧主题色竖条 + 浅底 + 「深度版专属」标签）
                            let deepN = 0;
                            document.querySelectorAll('.deep-only').forEach(el => {
                                el.style.display = isDeep ? 'block' : 'none';
                                if (isDeep) {
                                    const cb = el.querySelector('.content-block');
                                    if (cb && cb.innerHTML.trim().length > 20) deepN++;
                                    el.classList.add('deep-hl');
                                } else {
                                    el.classList.remove('deep-hl');
                                }
                            });
                            // auto-show 区块：简化版后台也产出的模块，有内容就显示（所见即所得）
                            document.querySelectorAll('.auto-show').forEach(el => {
                                const cb = el.querySelector('.content-block');
                                el.style.display = (cb && cb.innerHTML.trim().length > 20) ? 'block' : 'none';
                                if (cb && cb.innerHTML.trim().length > 20) deepN++;
                            });
                            try { wbSyncPptRow(); } catch (e) {}
                            // 答辩/PPT Tab：两档都显示（简化版同样生成答辩问题与 PPT 大纲）
                            document.getElementById('defenseTab').style.display = 'block';
                            // 简化版升级钩子：关键模块底部提示深度版能多给什么（产品分层：够用 → 想升级）
                            if (!isDeep) {
                                const UPSELL = [
                                    ['proposalText', '升级深度版：申报书扩写至 <b>12000 字级 / 12 章</b>（实测字数见档位卡统计），自动配数据图表'],
                                    ['judgeFeedback', '升级深度版：<b>3 位专家模拟评审</b>，逐条批注 + 优先改进清单'],
                                    ['defenseQuestions', '升级深度版：<b>智能路演 PPT</b>，按大纲自动排版，可下载 .pptx'],
                                    ['competitorAnalysis', '升级深度版：<b>竞品对比表 + 竞争力四象限图</b>']
                                ];
                                UPSELL.forEach(p => {
                                    const el = document.getElementById(p[0]);
                                    const box = el && el.parentElement;
                                    if (!box || box.querySelector('.deep-upsell')) return;
                                    const tip = document.createElement('div');
                                    tip.className = 'deep-upsell';
                                    tip.innerHTML = '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-bolt"/></svg> ' + p[1];
                                    box.appendChild(tip);
                                });
                            } else {
                                document.querySelectorAll('.deep-upsell').forEach(el => el.remove());
                            }
                            // T1 结果区顶部档位标识
                            const badge = document.getElementById('tierBadge');
                            if (badge) {
                                badge.innerHTML = wbTierBadgeHtml(mode, competition,
                                    '深度完整版 · 已生成 ' + deepN + ' 个模块', '简洁版');
                            }
                            // T3 共享产物标题旁标字数（去 Markdown 标记后统计，两档长短一眼可比）
                            [['parsedRules', data.data.parsed_rules],
                             ['similarityReport', data.data.similarity_report],
                             ['proposalText', data.data.proposal],
                             ['judgeFeedback', data.data.judge_feedback],
                             ['proposalAnalysis', data.data.proposal_analysis]].forEach(p => tagWordCount(p[0], p[1]));
                            // 占位符 / 赛道禁忌扫描：扫的是渲染后的正文，必须等画完再扫，
                            // 否则扫到半截内容会漏报
                            wbRefreshPhBar();
                        });
                        // 锚点条要等板块都画完（才知道哪些有内容）再生成
                        _P(21, function () { wbRenderAnchorBar(); });
                        // 错别字扫描必须排在正文画完之后（扫的是渲染好的 DOM）
                        _P(22, function () {
                            try { wbTypoScan(); } catch (e) {}
                            try { wbDataTodoScan(); } catch (e) {}
                        });

                        // 不依赖渲染结果的：同步执行
                        // 分享需要知道这条结果对应哪条历史记录
                        window._lastHistoryId = (data.data && data.data.history_id) || window._lastHistoryId || null;
                        // 生成完就存一份在本机：后端历史按 uid 隔离，手机端 uid 存不住时
                        // 只剩这份能保证「刷新后还能打开刚才那版」
                        try {
                            if (window._lastHistoryId) {
                                wbLocalHistPush({
                                    id: window._lastHistoryId,
                                    competition_name: competition || '',
                                    idea: idea || proposal_draft || '',
                                    time: _wbNowStr(),
                                    score: (data.data || {}).score,
                                    data: data.data
                                });
                            }
                        } catch (e) {}
                        wbHideRetry();
                        wbFabShow(!!(data.data && data.data.rich_deck));
                        renderCompleteness(data.data.completeness);
                        initDeckThemeSelect();
                        document.getElementById('chartsTab').style.display = isDeep ? 'block' : 'none';
                        wbPaintQueue(_Q);
                        // 接口说成功但一个字都没有：多半是某一步 LLM 静默失败。
                        // 不提示的话用户就对着一堆空板块发呆，以为是自己的问题
                        var _got = ['parsed_rules', 'proposal', 'judge_feedback', 'project_summary']
                            .some(function (k) { return !!(data.data[k] && String(data.data[k]).trim()); });
                        if (!_got) {
                            wbToast('生成结束但没拿到内容，建议再生成一次', {
                                type: 'warn', ms: 6000,
                                sub: '若反复出现，请把「运行日志」里的报错发给我们'
                            });
                        }
                        // 初始化可视化图表（有 AI 真图时不再画示例图）
                        if (isDeep && !(data.data.rich_charts || []).length) {
                            setTimeout(async () => {
                                // echarts 是按需加载的：这里等它到位再画（首屏不再为它买单）
                                await wbLoadEcharts();
                                // 两条路都没拉到 → 摆错误态，别让三个空白框挂在那儿
                                if (window.echarts.__noop) { wbEchartsDown(); return; }
                                await window.__wbDemoChartDraw();
                            }, 100);
                                // 171 轮：整套配色从所选主题取；CA 的跨端约束已收进 WB_CHART_THEMES.tech，
                                // 选中「科技蓝紫」时仍与后端 chart_renderer_pro 的 tech 主题完全同色。
                                // 整段抽成闭包挂 window：切主题时直接重绘，不必重新生成内容。
                                window.__wbDemoChartDraw = async function () {
                                var _T = WB_CHART_THEMES[wbChartThemeKey()] || WB_CHART_THEMES.soft;
                                var _dark = !(document.body && document.body.classList.contains('light'));
                                var _bgPair = _dark ? _T.bgD : _T.bgL;
                                const CA_BG = { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                                    colorStops: [{ offset: 0, color: _bgPair[0] }, { offset: 1, color: _bgPair[1] }] };
                                const CA = _T.series.slice();
                                const CBAR = { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                                    colorStops: [{ offset: 0, color: _T.bar[0] }, { offset: 1, color: _T.bar[1] }] };
                                const CTX = _T.text, CAX = _T.axis, CSPLIT = _T.split;
                                const CTIP = { backgroundColor: _T.tip[0], borderColor: _T.tip[1], textStyle: { color: _T.tip[2] } };
                                // 预算构成饼图（重复生成时先销毁旧实例，避免叠加）
                                const budgetEl = document.getElementById('budgetChart');
                                const oldBudget = echarts.getInstanceByDom(budgetEl);
                                if (oldBudget) oldBudget.dispose();
                                const budgetChart = echarts.init(budgetEl);
                                budgetChart.setOption({
                                    backgroundColor: CA_BG,
                                    color: CA,
                                    textStyle: { color: CTX },
                                    tooltip: Object.assign({ trigger: 'item' }, CTIP),
                                    legend: { bottom: 0, textStyle: { color: CTX } },
                                    series: [{
                                        type: 'pie',
                                        radius: ['40%', '70%'],
                                        data: [
                                            {value: 40, name: '研发成本'},
                                            {value: 25, name: '硬件采购'},
                                            {value: 20, name: '市场推广'},
                                            {value: 15, name: '运营备用'}
                                        ]
                                    }]
                                });
                                // 市场规模柱状图
                                const marketEl = document.getElementById('marketChart');
                                const oldMarket = echarts.getInstanceByDom(marketEl);
                                if (oldMarket) oldMarket.dispose();
                                const marketChart = echarts.init(marketEl);
                                marketChart.setOption({
                                    backgroundColor: CA_BG,
                                    color: CA,
                                    textStyle: { color: CTX },
                                    tooltip: Object.assign({}, CTIP),
                                    xAxis: { data: ['2024', '2025', '2026', '2027', '2028'], axisLine: { lineStyle: { color: CAX } }, axisLabel: { color: CTX } },
                                    yAxis: { splitLine: { lineStyle: { color: CSPLIT } }, axisLabel: { color: CTX } },
                                    series: [{
                                        type: 'bar', data: [120, 280, 560, 980, 1500],
                                        itemStyle: { borderRadius: [6, 6, 0, 0], color: CBAR }
                                    }]
                                });
                                // 时间线
                                const timelineEl = document.getElementById('timelineChart');
                                const oldTimeline = echarts.getInstanceByDom(timelineEl);
                                if (oldTimeline) oldTimeline.dispose();
                                const timelineChart = echarts.init(timelineEl);
                                timelineChart.setOption({
                                    backgroundColor: CA_BG,
                                    color: CA,
                                    textStyle: { color: CTX },
                                    tooltip: Object.assign({}, CTIP),
                                    xAxis: { type: 'category', data: ['需求调研', '原型开发', '测试迭代', '上线运营', '推广拓展'], axisLine: { lineStyle: { color: CAX } }, axisLabel: { color: CTX } },
                                    yAxis: { type: 'value', splitLine: { lineStyle: { color: CSPLIT } }, axisLabel: { color: CTX } },
                                    series: [{ type: 'line', data: [10, 30, 55, 80, 100], smooth: true, areaStyle: { color: _T.area }, itemStyle: { color: _T.line } }]
                                });
                                // 窗口变化时自动重绘（只注册一次，避免每次生成都叠加监听器）
                                if (!window.__chartsResizeBound) {
                                    window.__chartsResizeBound = true;
                                    window.addEventListener('resize', () => {
                                        ['budgetChart', 'marketChart', 'timelineChart'].forEach(id => {
                                            const inst = echarts.getInstanceByDom(document.getElementById(id));
                                            if (inst) inst.resize();
                                        });
                                    });
                                }
                                // 示例图表同样支持单击放大：把 echarts 实例导出成高清图再塞进弹窗
                                const demoChartTitles = {budgetChart: '预算构成', marketChart: '市场规模', timelineChart: '项目实施时间线'};
                                ['budgetChart', 'marketChart', 'timelineChart'].forEach(id => {
                                    const el = document.getElementById(id);
                                    if (!el || el.dataset.zoomBound) return;
                                    el.dataset.zoomBound = '1';
                                    el.style.cursor = 'zoom-in';
                                    el.title = '点击放大查看';
                                    el.addEventListener('click', () => {
                                        const inst = echarts.getInstanceByDom(el);
                                        if (!inst) return;
                                        try {
                                            openChartModal(
                                                inst.getDataURL({pixelRatio: 2, backgroundColor: '#ffffff'}),
                                                demoChartTitles[id] || '示例图表',
                                                '示例数据绘制，正式使用请按实际情况替换');
                                        } catch (err) {
                                            /* 导出失败就不放大，不能影响主流程 */
                                        }
                                    });
                                });
                            };
                        }
                        document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth' });
                    } else {
                        // 后端返回的友好错误（余额不足 / 超时 / 鉴权失败等），detail 是原始报错
                        wbToast(data.error || '生成失败，请稍后重试', {
                            type: 'error',
                            sub: (data.detail ? ('原始报错：' + data.detail + '　') : '') +
                                 '已填的内容都还在，点「重新生成」再来一次',
                            ms: 10000
                        });
                    }
                }, 500);
            })
            .catch(err => {
                // 注意：这里的 timer 变量已随真实进度改造移除，别再清 interval
                streamFinish();   // 失败/取消也要撤掉流式光标和「生成中」占位
                try { wbAgentFinish(false); } catch (e) {}
                document.getElementById('skeletonArea').style.display = 'none';
                document.getElementById('cancelWrap').style.display = 'none';
                document.getElementById('progressSteps').style.display = 'none';
                // 失败/取消后把残留进度条清零，避免下次进来还挂着旧百分比
                document.getElementById('fastProgress').style.width = '0%';
                document.getElementById('fastProgressText').innerText = '';
                var _eb2 = document.getElementById('etaBadge');
                if (_eb2) _eb2.style.display = 'none';
                // 被用户主动终止的不弹重试（他自己按的，不需要提示）
                if (!(err && err.cancelled)) {
                    var _rw = document.getElementById('retryWrap');
                    var _ps = document.getElementById('progressSteps');
                    if (_rw) { _rw.style.display = 'block'; }
                    if (_ps) { _ps.style.display = 'block'; }
                }
                _currentTaskId = null;
                window._wbGenerating = false;   // 必须复位：泄漏会让之后打开历史记录时下载 dock 永久被抑制
                btn.disabled = false;
                btn.innerHTML = '<svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-rocket"/></svg> 开始生成';
                if (err && err.cancelled) {
                    wbToast('已终止生成', { type: 'warn' });
                } else if (err && err.code === 'quota_exceeded') {
                    wbToast('今日生成次数已达上限，请明天再试', {
                        type: 'warn',
                        sub: '已填内容都还在，明天再来就能继续生成',
                        ms: 8000
                    });
                } else if (err && err.isCreateFail) {
                    // 任务根本没建立起来：不是生成质量问题，别让人去改创意
                    wbToast('生成服务暂不可用：' + (err.message || '未知原因') + '，请重试', {
                        type: 'error',
                        sub: (err.httpStatus ? ('HTTP ' + err.httpStatus + ' · ') : '') + '已填内容都还在，改好后点「开始生成」即可'
                    });
                } else {
                    var _net = String((err && err.message) || err || '');
                    var _isNet = _net.indexOf('Failed to fetch') >= 0 || _net.indexOf('NetworkError') >= 0;
                    // 同理心放在标题上，原始报错降级到副标题：用户先看到「人话」，
                    // 排查时仍能拿到真实原因（不能为了好听把报错吞掉）
                    wbToast(_isNet
                        ? '这次没生成成功，可能是网络抖了一下'
                        : '这次没生成成功，换个创意或稍后再试', {
                        type: 'error',
                        sub: _isNet ? '网络似乎断了一下，恢复后点「重新生成」即可，已填的内容都还在'
                                    : ('原始信息：' + _net).slice(0, 120)
                    });
                }
            });
        }

        /* 手机浮动生成按钮 #wbMobileGen（元素/样式由 index.html / style.css 提供，.wb-gen-show 控制显隐）：
           滚动超约一屏且吸底入口条 #startBar 不在视野时显示；点击触发 startWork()。元素可能晚于本脚本插入，每次现查 DOM，查不到静默返回。 */
        function _wbFabCheck() {
            var fab = document.getElementById('wbMobileGen');
            if (!fab) return;
            var bar = document.getElementById('startBar');
            var vis = false;
            if (bar) { var r = bar.getBoundingClientRect(); vis = (r.bottom > 0 && r.top < (window.innerHeight || 0)); }
            fab.classList.toggle('wb-gen-show', (window.scrollY || window.pageYOffset || 0) > (window.innerHeight || 0) && !vis);
        }
        window.addEventListener('scroll', _wbFabCheck, { passive: true });
        window.addEventListener('resize', _wbFabCheck, { passive: true });
        document.addEventListener('click', function (e) {   // 事件委托：按钮晚插入也能点上
            var fab = document.getElementById('wbMobileGen');
            if (fab && e.target && fab.contains(e.target)) { try { startWork(); } catch (err) {} }
        });
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wbFabCheck);
        else _wbFabCheck();

        // 档位徽章（结果区头部）：赛事固定 emoji 做视觉锚点，一眼认出是哪场比赛
        function wbTierBadgeHtml(mode, compName, deepTxt, fastTxt) {
            var isDeep = (mode === 'deep');
            // 赛事名徽章常驻：未收录赛事没有简称时退回全名截断，不再因为「没有图标」就整块消失
            var short = wbCompShort(compName) || _esc(String(compName || '').slice(0, 22));
            var tag = isDeep
                ? '<span class="tier-tag tier-tag-deep"><span class="wb-dot"></span>' + deepTxt + '</span>'
                : '<span class="tier-tag">' + fastTxt + '</span>';
            if (!short) return tag;
            return '<span class="tier-tag" style="background: var(--surface-solid); border: 1px solid var(--line);">'
                + _esc(short) + '</span>' + tag;
        }

        // 卡片选择
        function selectMode(type) {
            if (type === 'fast') {
                document.getElementById('fastCard').style.border = '2px solid var(--c-a)';
                document.getElementById('fastCard').style.background = 'var(--c-a-soft)';
                document.getElementById('deepCard').style.border = '2px solid var(--line)';
                document.getElementById('deepCard').style.background='var(--surface-solid)';
                document.querySelector('input[value="fast"]').checked = true;
            } else {
                document.getElementById('deepCard').style.border = '2px solid var(--c-a)';
                document.getElementById('deepCard').style.background = 'var(--c-a-soft)';
                document.getElementById('fastCard').style.border = '2px solid var(--line)';
                document.getElementById('fastCard').style.background='var(--surface-solid)';
                document.querySelector('input[value="deep"]').checked = true;
            }
        }

        // 手机上一排放不下 5 个栏目，容器虽然能横滑，但默认激活的「申报与评审」排在第四位、
        // 刚好落在屏外——内容切过去了，高亮的标签却看不见，看着像被挤没了。
        // 所以每次切栏目都把当前标签滚到可视区中央；面板宽度够、不用滑时直接跳过。
        function wbScrollTabIntoView(btn) {
            if (!btn) return;
            var box = btn.parentNode;
            while (box && box !== document.body &&
                   String(box.className || '').indexOf('tabs') < 0) box = box.parentNode;
            if (!box || box === document.body) return;
            if (!box.scrollWidth || box.scrollWidth <= box.clientWidth + 1) return;
            var br = box.getBoundingClientRect(), tr = btn.getBoundingClientRect();
            if (!tr.width) return;
            var delta = (tr.left - br.left) - (br.width - tr.width) / 2;
            var max = box.scrollWidth - box.clientWidth;
            var left = Math.max(0, Math.min(max, box.scrollLeft + delta));
            // ⚠️ 这里刻意不用 behavior:'smooth'。实测（Edge headless + 多视口）发现：
            // 带 smooth 的写法在部分内核里会被静默忽略 —— 不报错、不抛异常、但 scrollLeft 一动不动，
            // 结果就是「激活的标签停在屏幕外」。宁可瞬间跳到位，也不要悄悄失效。
            // 标签条是短距离横向滚动，瞬时跳转几乎不违和，可靠性优先。
            try {
                box.scrollTo({ left: left });
            } catch (e) {
                box.scrollLeft = left;   // 老内核（QQ/夸克）不认 options 对象
            }
            // 个别内核的 scrollTo 实现有偏差，同步校准一次（不依赖定时器）
            if (Math.abs(box.scrollLeft - left) > 4) box.scrollLeft = left;
        }

        // tab切换
        // 栏目按钮 id 表：锚点条要能不带 event 直接切栏目（原来是靠 event.currentTarget，
        // 程序化调用时没有 event，会直接报错）
        var WB_TAB_BTN = { export: 'exportTab', analysis: 'analysisTab', deep: 'deepTab',
                           proposal: 'proposalTab', charts: 'chartsTab', defense: 'defenseTab',
                           kb: 'kbTab', logs: 'logsTab' };

        function switchTab(event, tabName) {
            // 隐藏所有tab
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            // 去掉所有tab的active样式
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            // 显示当前tab
            document.getElementById('tab-' + tabName).classList.add('active');
            var _btn = (event && event.currentTarget) ||
                       document.getElementById(WB_TAB_BTN[tabName] || '');
            if (_btn) { _btn.classList.add('active'); wbScrollTabIntoView(_btn); }
            if (tabName === 'kb') { kbLoadTags(); kbList(); }
            if (tabName === 'logs') { loadLogs(); loadLessons(); }
        }


        /* ---------- 板块快速定位（结果区锚点条） ----------
           结果区动辄上万字，看完一块要翻很久才到下一块。锚点条只列「当前真的有内容」
           的板块，点一下自动切栏目 + 平滑滚过去。 */
        var WB_ANCHORS = [
            {n: '规则解析', t: 'analysis', id: 'parsedRules'},
            {n: '查重',     t: 'analysis', id: 'similarityReport'},
            {n: '项目简介', t: 'proposal', id: 'projectSummary'},
            {n: '申报书',   t: 'proposal', id: 'proposalText'},
            {n: '诊断',     t: 'proposal', id: 'proposalAnalysis'},
            {n: '评审意见', t: 'proposal', id: 'judgeFeedback'},
            {n: '竞品',     t: 'deep',     id: 'competitorAnalysis'},
            {n: '商业',     t: 'deep',     id: 'businessModel'},
            {n: '风险',     t: 'deep',     id: 'riskAnalysis'},
            {n: '技术方案', t: 'deep',     id: 'techSolution'},
            {n: '实施计划', t: 'deep',     id: 'implementationPlan'},
            {n: '社会价值', t: 'deep',     id: 'socialValue'},
            {n: '图表',     t: 'charts',   id: 'tab-charts'},
            {n: '答辩',     t: 'defense',  id: 'defenseQuestions'},
            {n: 'PPT大纲',  t: 'defense',  id: 'pptOutline'},
            {n: '导出',     t: 'export',   id: 'tab-export'}
        ];

        function wbRenderAnchorBar() {
            var bar = document.getElementById('wbAnchorBar');
            var box = document.getElementById('wbAnchorScroll');
            if (!bar || !box) return;
            var h = '';
            WB_ANCHORS.forEach(function (a) {
                var el = document.getElementById(a.id);
                if (!el) return;
                // 整块被隐藏（简洁版没有深度板块）或压根没内容 → 不给锚点，
                // 否则点过去是一片空白，反而更迷路
                var wrap = el.closest ? (el.closest('.deep-only, .auto-show') || el) : el;
                if (wrap.offsetParent === null && el.offsetParent === null) return;
                var isPanel = (a.id.indexOf('tab-') === 0);
                if (!isPanel && !(el.textContent || '').trim()) return;
                h += '<button class="wb-anchor-btn" onclick="wbGoAnchor(\'' + a.t +
                     '\',\'' + a.id + '\')">' + a.n + '</button>';
            });
            if (!h) { bar.style.display = 'none'; return; }
            box.innerHTML = h;
            bar.style.display = 'block';
        }

        function wbGoAnchor(tab, id) {
            var btn = document.getElementById(WB_TAB_BTN[tab] || '');
            if (btn && !btn.classList.contains('active')) {
                try { switchTab(null, tab); } catch (e) {}
            }
            setTimeout(function () {
                var el = document.getElementById(id);
                if (!el) return;
                // 滚到带标题的整块（content-block 的父 div），而不是光秃秃的正文块
                var target = (el.closest && el.closest('div')) || el;
                // 让开吸顶的导出条，不然标题被压在下面看不见
                target.style.scrollMarginTop = '76px';
                try {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } catch (e) {
                    target.scrollIntoView();   // 老内核（QQ/夸克）不支持 smooth 的兜底
                }
                // ⚠️ 平滑滚动可能「认下参数却不跑动画」——标签栏那次实测就撞上了：
                // 同为 scroll 系 API 的 behavior:'smooth' 不报错、scrollLeft 却纹丝不动。
                // 锚点条要是也这样，就是「点了没反应」。这里延后核对一次：
                // 既没滚动、目标又还离得远，才补一次即时滚动；正常情况下完全不触发。
                var _y0 = window.pageYOffset;
                setTimeout(function () {
                    try {
                        var _top = target.getBoundingClientRect().top;
                        if (Math.abs(window.pageYOffset - _y0) < 2 && Math.abs(_top - 76) > 60) {
                            target.scrollIntoView();
                        }
                    } catch (e) {}
                }, 450);
                // 闪一下边框，让用户知道跳到哪了
                try {
                    var old = target.style.boxShadow;
                    target.style.boxShadow = '0 0 0 2px var(--c-a)';
                    setTimeout(function () { target.style.boxShadow = old; }, 1200);
                } catch (e) {}
            }, 60);
        }

        /* ---------- 首次进入引导：手机与电脑两套内容 ---------- */
        // 端判断全自动：UA + 屏幕宽度 + 触屏能力三者综合，不让用户自己选
        // （只看 UA 会漏掉 iPad 桌面模式、安卓平板；只看宽度会漏掉横屏手机）
        var WB_IS_MOBILE = (function () {
            var ua = navigator.userAgent || '';
            var byUa = /iPhone|iPod|Android|Mobile|BlackBerry|Opera Mini|IEMobile/i.test(ua);
            var byPad = /iPad/.test(ua) || (/Macintosh/.test(ua) && (navigator.maxTouchPoints || 0) > 1);
            var byWidth = false;
            try { byWidth = window.matchMedia('(max-width: 820px)').matches; } catch (e) {}
            return !!(byUa || byPad || byWidth);
        })();

        function _introSteps() {
            return [
                ['① 填创意', WB_IS_MOBILE
                    ? '一句话说清「解决什么问题 + 怎么做」，越具体生成越好'
                    : '一句话说清「解决什么问题 + 怎么做」；有草稿可上传 Word / PDF / TXT'],
                ['② 选档位', WB_IS_MOBILE
                    ? '简洁版约 1~2 分钟出 2000~4000 字；深度版约 3~5 分钟，多出竞品/商业/风险分析 + 图表 + PPT'
                    : '简洁版出稿快、字数精；深度版约 4 分钟出 12 章 + 图表 + PPT + 多专家模拟评审（实测字数与用时见档位卡）'],
                ['③ 点生成', '内容实时流出，不用盯着空白页等；生成完直接导出'],
            ];
        }

        function introHTML() {
            var m = WB_IS_MOBILE;
            var wx = /MicroMessenger|QQ\//i.test(navigator.userAgent || '');
            var btn = m ? 'padding: 14px 20px; font-size: 16px;' : 'padding: 10px 22px; font-size: 14px;';
            var h = '';

            h += '<h2 style="margin-bottom: 6px;"><svg class="wb-ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#wb-i-rocket"/></svg> 科创赛事申报材料智能生成助手</h2>';
            h += '<div style="color: var(--text-dim); font-size: 13.5px; line-height: 1.8; margin-bottom: 16px;">' +
                 '把你的项目创意变成一整套参赛材料：规则解析、申报书正文、评委打分、竞品与商业分析、图表、路演 PPT、答辩预测。</div>';

            // 手机端：先说清楚在手机上怎么用，避免踩微信的坑
            if (m) {
                h += '<div style="padding: 12px 14px; border-radius: 10px; border: 1px solid var(--c-b); background: var(--surface-2); margin-bottom: 16px;">' +
                     '<div style="font-weight: 700; color: var(--c-b); margin-bottom: 6px;">手机上请注意</div>' +
                     '<div style="color: var(--text-dim); font-size: 13px; line-height: 1.8;">' +
                     '文字建议<b>复制后粘贴</b>到创意框（长按复制 → 长按输入框粘贴）。' +
                     (wx ? '<br><b style="color: var(--c-b);">你现在在微信里，上传只能选到图片和视频</b>，' +
                           '要传 Word / PDF 请点右上角 ··· → 用 Safari 打开。'
                         : '<br>要传 Word / PDF，在 Safari 里点「浏览」选文件 App 里的文件。') +
                     '</div></div>';
            }

            h += '<div style="font-weight: 600; margin: 0 0 10px; color: var(--text);">怎么用（三步）</div>';
            h += '<div style="margin-bottom: 18px;">';
            _introSteps().forEach(function (s) {
                h += '<div style="display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line); align-items: flex-start;">' +
                     '<span style="flex: 0 0 74px; font-weight: 700; color: var(--c-a);">' + s[0] + '</span>' +
                     '<span style="flex: 1; color: var(--text-dim); font-size: 13px; line-height: 1.7;">' + s[1] + '</span>' +
                     '</div>';
            });
            h += '</div>';

            if (!m) {
                h += '<div style="font-weight: 600; margin: 0 0 10px; color: var(--text);">还能干什么</div>';
                h += '<div style="color: var(--text-dim); font-size: 13px; line-height: 1.9; margin-bottom: 18px;">' +
                     '· <b>范文库</b>：加示范范文片段，生成时自动参考同类写法（关键词检索，不是微调）<br>' +
                     '· <b>导出中心</b>：Word / PDF / PPT / 一键打包，申报书按标准格式排版<br>' +
                     '· <b>原格式导出</b>：上传学校模板 .docx，优化后保留你原来的版式<br>' +
                     '· <b>历史记录</b>：之前生成的随时打开回看，可继续导出' +
                     '</div>';
            }

            // 上传入口说明（最容易传错的地方，写清楚；规则上传已降级为折叠可选，不再单列）
            h += '<div style="font-weight: 600; margin: 0 0 8px; color: var(--text);">上传入口，别传错</div>';
            h += '<div style="font-size: 12.5px; color: var(--text-dim); line-height: 1.8; margin-bottom: 16px;">' +
                 '<div style="padding: 6px 0; border-bottom: 1px dashed var(--line);">' +
                 '· <b>上传数据文件</b>（实测数据区）：测试报告/调研数据，系统自动识别并填到对应位置</div>' +
                 '<div style="padding: 6px 0; border-bottom: 1px dashed var(--line);">' +
                 '· <b>上传草稿</b>（创意框下方）：你已经写好的内容，在原文上优化</div>' +
                 '<div style="padding: 6px 0; border-bottom: 1px dashed var(--line);">' +
                 '· <b>导入模板</b>（草稿区）：学校/官方模板，自动识别章节按它写</div>' +
                 '<div style="padding: 6px 0;">' +
                 '· <b>补充规则</b>（折叠区，一般不用）：评分标准已内置 15 个赛事，只有官方最新文件有特殊要求才传</div>' +
                 '<div style="margin-top: 6px; color: var(--text-mute);">支持 PDF / Word / TXT / Markdown；' +
                 '图片和扫描版 PDF 读不出文字。</div>' +
                 '</div>';

            // 常见问题
            h += '<div style="font-weight: 600; margin: 0 0 8px; color: var(--text);">常见问题</div>';
            h += '<div style="font-size: 12.5px; color: var(--text-dim); line-height: 1.8; margin-bottom: 16px;">' +
                 '· 页面看着是旧的 → 刷新一下（电脑 Ctrl+F5）<br>' +
                 '· 微信里只能选图片 → 换 Safari 打开，或直接复制文字粘贴<br>' +
                 '· 深度版约 4~5 分钟属正常，卡住可点「终止生成」<br>' +
                 '· 只有深度版才有 PPT 和图表<br>' +
                 '· 出问题看「运行日志」页签，点「复制报告」发给开发' +
                 '</div>';

            h += '<div style="padding: 10px 12px; border-radius: 10px; background: var(--surface-2); color: var(--text-mute); font-size: 12.5px; line-height: 1.7; margin-bottom: 16px;">' +
                 '创意与草稿仅用于本次生成，不做模型训练、不外传；生成内容归你所有。' +
                 '生成的内容请自行核对数据、按真实情况修改后再提交。</div>';

            h += '<div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">' +
                 '<button onclick="closeIntro(true)" style="' + btn + ' background: var(--c-a); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; flex: 1 1 140px;">开始使用</button>' +
                 '<label style="display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text-mute); cursor: pointer;">' +
                 '<input type="checkbox" id="introNoMore" checked style="width: 15px; height: 15px;"> 下次不再自动弹出</label>' +
                 '</div>';
            return h;
        }

        // 真实视口高度：移动端不能用 vh 单位（地址栏收起时 vh 会比实际高，
        // 蒙层/背景就会盖不满或溢出，出现色带错位）
        function wbViewportHeight() {
            return window.innerHeight || document.documentElement.clientHeight || 640;
        }
        (function () {
            function refit() {
                var box = document.getElementById('introBox');
                var modal = document.getElementById('introModal');
                if (!box || !modal || modal.style.display !== 'flex') return;
                if (typeof WB_IS_MOBILE !== 'undefined' && WB_IS_MOBILE) {
                    box.style.height = wbViewportHeight() + 'px';
                }
            }
            window.addEventListener('resize', refit);
            window.addEventListener('orientationchange', function () { setTimeout(refit, 300); });
        })();

        function showIntro(force) {
            // 同「背景」按钮：引导遮罩还在时先把引导收掉，别让用户点了没反应
            try {
                if (typeof coachEnd === 'function') coachEnd(); // 无条件收引导：veil 有 380ms 创建延迟，只查 veil 会漏掉窗口期
            } catch (e) {}
            var modal = document.getElementById('introModal');
            var box = document.getElementById('introBox');
            var body = document.getElementById('introBody');
            if (!modal || !box || !body) return;
            if (!force) {
                try { if (_wbStoreGet('wbIntroSeen') === '1') return; } catch (e) {}
            }
            body.innerHTML = introHTML();
            if (WB_IS_MOBILE) {
                // 手机做成全屏引导页：大按钮、可滚动。
                // ⚠️ 别用 100vh：移动端地址栏一收，vh 就和真实视口差几十像素，
                // 蒙层盖不满，底部露出下层渐变 —— 就是用户说的「界面上下颜色分层」。
                // 这里按 innerHeight 实测，转屏 / 地址栏变化时再量一次。
                box.style.maxWidth = 'none';
                box.style.width = '100%';
                box.style.maxHeight = 'none';
                box.style.height = wbViewportHeight() + 'px';
                box.style.borderRadius = '0';
                box.style.overflowY = 'auto';
            }
            modal.style.display = 'flex';
        }

        // Esc 关闭使用说明弹窗：点暗处已支持，键盘党/桌面端习惯 Esc（待验收清单一#3）
        try {
            document.addEventListener('keydown', function (e) {
                if (e.key !== 'Escape') return;
                var md = document.getElementById('introModal');
                if (md && md.offsetParent !== null) closeIntro();
            });
        } catch (e) {}

        function closeIntro(remember) {
            var modal = document.getElementById('introModal');
            if (modal) modal.style.display = 'none';
            var noMore = document.getElementById('introNoMore');
            var skip = (!noMore || noMore.checked);
            if (remember !== false && skip) {
                try { _wbStoreSet('wbIntroSeen', '1'); } catch (e) {}
            }
            // 手机端：关掉引导直接进输入区并唤起键盘
            // （focus 必须在点击的同一个调用栈里同步执行，iOS 才认这是用户手势，
            //   放进 setTimeout 会丢手势上下文，键盘弹不出来）
            if (WB_IS_MOBILE) {
                // 聚焦输入区第一个字段（赛事名）：既唤起键盘，也让视口落在输入区顶部。
                // 不要用 preventScroll —— iOS 自己会把焦点元素滚到可见处，拦掉反而滚错。
                // 键盘弹出动画（约 300ms）会改变视口高度，所以延迟后再校正两次位置。
                var el = document.getElementById('competition');
                if (el) {
                    try { el.focus(); } catch (e) {}
                    var card = el.closest ? el.closest('.card') : null;
                    var fix = function () {
                        try { (card || el).scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
                    };
                    setTimeout(fix, 350);
                    setTimeout(fix, 900);
                }
            }
        }

        /* ---------- 运行日志（只读排查面板，数据来自 /api/logs） ---------- */
        var _LOG_COLOR = { 'ERROR': 'var(--err-text)', 'WARN': '#d97706', 'INFO': 'var(--text-mute)' };
        async function loadLogs() {
            var box = document.getElementById('logList');
            if (!box) return;
            var lv = (document.getElementById('logLevel') || {}).value || '';
            box.innerHTML = '<div style="color: var(--text-mute);">加载中…</div>';
            try {
                var r = await fetch('/api/logs?limit=100' + (lv ? '&level=' + encodeURIComponent(lv) : ''));
                var d = await r.json();
                if (!d || !d.success) throw new Error((d && d.error) || '加载失败');
                var items = d.logs || [];
                var cnt = document.getElementById('logCount');
                var ecnt = document.getElementById('logErrorCount');
                if (cnt) cnt.textContent = items.length;
                if (ecnt) ecnt.textContent = (d.error_count == null ? 0 : d.error_count);
                if (!items.length) {
                    box.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-mute);">暂无日志记录' +
                        (lv ? '（当前只看 ' + _esc(lv) + '）' : '') + '</div>';
                    return;
                }
                box.innerHTML = items.slice().reverse().map(function (x) {
                    var c = _LOG_COLOR[x.level] || 'var(--text-dim)';
                    return '<div style="display: flex; gap: 10px; padding: 8px 10px; border-bottom: 1px solid var(--line); align-items: flex-start; flex-wrap: wrap;">' +
                        '<span style="flex: 0 0 62px; font-weight: 700; color: ' + c + ';">' + _esc(x.level) + '</span>' +
                        '<span style="flex: 0 0 148px; color: var(--text-mute);">' + _esc(x.time || '') + '</span>' +
                        '<span style="flex: 0 0 76px; color: var(--text-dim);">' + _esc(x.source || '') + '</span>' +
                        '<span style="flex: 1 1 240px; color: var(--text-dim); word-break: break-all;">' + _esc(x.message || '') + '</span>' +
                        '</div>';
                }).join('');
            } catch (e) {
                box.innerHTML = '<div style="color: var(--err-text);">加载失败：' + _esc(_friendlyErr(e)) + '</div>';
            }
        }

        async function copyLogReport() {
            try {
                var r = await fetch('/api/logs/report');
                var d = await r.json();
                if (!d || !d.success) throw new Error((d && d.error) || '生成失败');
                var okFn = function () { wbToast('报告已复制，可直接发给开发排查', { type: 'ok', ms: 3000 }); };
                var badFn = function () { wbToast('复制失败，请手动选中后复制', { type: 'error' }); };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(d.report).then(okFn, function () { _fallbackCopy(d.report, okFn, badFn); });
                } else {
                    _fallbackCopy(d.report, okFn, badFn);
                }
            } catch (e) {
                wbToast('获取报告失败：' + _friendlyErr(e), { type: 'error' });
            }
        }

        async function loadLessons() {
            var box = document.getElementById('lessonList');
            if (!box) return;
            var q = (document.getElementById('lessonSearch') || {}).value || '';
            try {
                var r = await fetch('/api/lessons?q=' + encodeURIComponent(q));
                var d = await r.json();
                if (!d || !d.success) throw new Error((d && d.error) || '加载失败');
                var items = d.lessons || [];
                var c = document.getElementById('lessonCount');
                if (c) c.textContent = items.length;
                if (!items.length) {
                    box.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-mute);">没有匹配的踩坑记录</div>';
                    return;
                }
                box.innerHTML = items.map(function (l) {
                    return '<div style="padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface-solid); margin-bottom: 8px;">' +
                        '<div style="font-weight: 600; color: var(--text); margin-bottom: 4px;">' + _esc(l.title || '') +
                        ' <span style="font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--surface-2); color: var(--text-mute); font-weight: 400;">' +
                        _esc(l.category || '') + '</span></div>' +
                        '<div style="color: var(--text-dim); font-size: 12.5px; line-height: 1.7;">' + _esc(l.summary || '') + '</div>' +
                        '</div>';
                }).join('');
            } catch (e) {
                box.innerHTML = '<div style="color: var(--err-text);">加载失败：' + _esc(_friendlyErr(e)) + '</div>';
            }
        }

        /* ---------- 范文库 ---------- */
        // 标签词表：后端 /api/kb/tags 本来就按 module/track/feature 分好维度，
        // 但旧代码把三组摊平进一个 flex 容器，上百个标签全混在一起（第三十五轮刺）。
        // 现在按维度分块渲染，并支持搜索过滤。
        var _kbTagGroups = [];
        function kbTagChipHtml(t) {
            return '<span onclick="kbAddTag(\'' + String(t).replace(/'/g, "\\'") + '\')" ' +
                'style="padding:4px 10px; background:var(--surface-2); color:var(--text); ' +
                'border:1px solid var(--line); border-radius:12px; cursor:pointer; font-size:12px;">' +
                _esc(t) + '</span>';
        }
        function kbRenderTags(filter) {
            var wrap = document.getElementById('kbChipWrap');
            if (!wrap) return;
            var q = String(filter || '').trim().toLowerCase();
            var html = '';
            _kbTagGroups.forEach(function (g) {
                var list = (g[1] || []).filter(function (t) {
                    return !q || String(t).toLowerCase().indexOf(q) >= 0;
                });
                if (!list.length) return;
                html += '<div style="margin-bottom: 9px;">'
                    + '<div style="font-size: 11px; color: var(--text-mute); margin-bottom: 5px;">'
                    + _esc(g[0]) + ' · ' + list.length + '</div>'
                    + '<div style="display: flex; flex-wrap: wrap; gap: 6px;">'
                    + list.map(kbTagChipHtml).join('') + '</div></div>';
            });
            wrap.innerHTML = html
                || ('<span style="font-size:12px;color:var(--text-mute);">'
                    + (q ? '没有匹配「' + _esc(q) + '」的标签，也可以直接手填' : '（标签词表未加载）') + '</span>');
        }
        function kbFilterTags() {
            var el = document.getElementById('kbTagFilter');
            kbRenderTags(el ? el.value : '');
        }
        window.kbFilterTags = kbFilterTags;
        function kbLoadTags() {
            fetch('/api/kb/tags')
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d || !d.success) return;
                    _kbTagGroups = [['文档模块', d.module || []], ['赛道方向', d.track || []], ['项目特征', d.feature || []]];
                    kbRenderTags((document.getElementById('kbTagFilter') || {}).value || '');
                })
                .catch(function () {});
        }

        // 内容关键词 -> 建议标签（队友不一定熟悉标签体系，靠内容自动推荐降低打错标签的概率）
        var KB_TAG_RULES = [
            ['文化文旅', ['文旅', '苏轼', '景区', '文化旅游', '游客', '博物馆', '传统文化']],
            ['非遗', ['非遗', '传承人', '刺绣', '苏绣', '绣娘', '手艺', '非物质文化']],
            ['人工智能', ['AI', '人工智能', '识别', '模型', '算法', '深度学习', '视觉', '机器学习']],
            ['web网站', ['网站', '网页', 'web', '小程序', '平台', '线上', 'APP', 'APP']],
            ['校园服务', ['校园', '学生', '高校', '大学', '宿舍', '食堂', '图书馆', '同学']],
            ['乡村振兴', ['乡村', '农业', '农户', '种植', '农村', '振兴', '县域', '农产品']],
            ['项目简介', ['项目简介', '项目概述', '本项目', '我们做', '项目是']],
            ['社会价值', ['社会价值', '社会意义', '公益', '带动', '文化自信']],
            ['商业模式', ['商业模式', '收入', '盈利', '收费', '付费', '成本', '变现', '定价', '订阅']],
            ['风险分析', ['风险', '局限', '不足', '挑战', '困难', '尚未', '误报']],
            ['创新点', ['创新', '与众不同', '首次', '独特', '突破']],
            ['实践过程', ['实践', '阶段', '进度', '实施', '落地', '试点', '下一步', '计划']]
        ];

        function kbContentHint() {
            var el = document.getElementById('kbContent');
            var hint = document.getElementById('kbLenHint');
            if (!el || !hint) return;
            var n = (el.value || '').trim().length;
            var txt, color;
            if (!n) { hint.innerHTML = ''; }
            else if (n < 150) { txt = '偏短，建议补充到 300 字以上，太短的片段参考价值有限'; color = 'var(--c-warn, #d97706)'; }
            else if (n < 300) { txt = '可以，但 300-600 字效果更好'; color = 'var(--text-mute)'; }
            else if (n <= 700) { txt = '长度合适 ✓'; color = '#22c55e'; }
            else if (n <= 1500) { txt = '偏长，建议按章节拆成多个片段分别入库'; color = 'var(--c-warn, #d97706)'; }
            else { txt = '太长！建议拆成多个片段——检索到它会占满参考额度，反而挤掉其它范文'; color = '#ef4444'; }
            hint.innerHTML = n ? ('<b>' + n + ' 字</b> · ' + txt) : '';
            if (n && color) hint.style.color = color;

            // 标签建议
            var wrap = document.getElementById('kbTagSuggestWrap');
            var box = document.getElementById('kbTagSuggest');
            if (!wrap || !box) return;
            var cur = (document.getElementById('kbTags') || {}).value || '';
            var chosen = cur.split(/[,，]/).map(function (s) { return s.trim(); }).filter(Boolean);
            var sugg = [];
            KB_TAG_RULES.forEach(function (r) {
                if (chosen.indexOf(r[0]) >= 0) return;
                var hit = false;
                r[1].forEach(function (w) { if (el.value.indexOf(w) >= 0) hit = true; });
                if (hit) sugg.push(r[0]);
            });
            if (!sugg.length) { wrap.style.display = 'none'; return; }
            wrap.style.display = 'block';
            box.innerHTML = sugg.map(function (t) {
                return '<span onclick="kbAddTag(\'' + t + '\')" style="cursor:pointer;padding:3px 10px;background:var(--c-a-soft);color:var(--c-a);border-radius:10px;font-size:11px;">+ ' + _esc(t) + '</span>';
            }).join(' ');
        }

        function kbAddTag(tag) {
            var el = document.getElementById('kbTags');
            if (!el) return;
            var cur = el.value.split(/[,，]/).map(function (s) { return s.trim(); }).filter(Boolean);
            if (cur.indexOf(tag) >= 0) return;
            cur.push(tag);
            el.value = cur.join(', ');
        }

        // 范文库上传：只把文件解析成文本填进输入框，存不存由用户点「添加」决定。
        // 走 purpose=draft，后端不会把内容塞进共享知识库（别人的作品不该被动入库）
        window.kbFileUpload = function (input) {
            var f = input && input.files && input.files[0];
            if (!f) return;
            var fd = new FormData();
            fd.append('file', f);
            fd.append('purpose', 'draft');
            try { wbToast('正在解析文件…', { type: 'ok', ms: 1800 }); } catch (e) {}
            fetch('/api/upload_file', { method: 'POST', body: fd })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d || !d.success) {
                        wbToast('解析失败：' + ((d && d.error) || '未知错误'), { type: 'error' });
                        return;
                    }
                    var t = String(d.text || '').trim();
                    if (!t) {
                        wbToast('这份文件没解析出文字（可能是扫描件图片），请手动粘贴', { type: 'warn', ms: 4200 });
                        return;
                    }
                    // 范文讲究精炼，超长片段反而会占满生成时的参考额度
                    if (t.length > 3000) t = t.slice(0, 3000);
                    var el = document.getElementById('kbContent');
                    if (el) el.value = (String(el.value || '').trim() ? el.value.trim() + '\n\n' : '') + t;
                    kbContentHint();
                    wbToast('已解析 ' + t.length + ' 字，确认后点「添加到范文库」', { type: 'success', ms: 3600 });
                })
                .catch(function () { wbToast('解析失败：连不上服务', { type: 'error' }); })
                .then(function () { try { input.value = ''; } catch (e) {} });
        };
        function kbAdd() {
            var content = (document.getElementById('kbContent') || {}).value || '';
            var tagsRaw = (document.getElementById('kbTags') || {}).value || '';
            content = content.trim();
            if (!content) { wbToast('请先粘贴范文内容', { type: 'warn' }); return; }
            var tags = tagsRaw.split(/[,，]/).map(function (s) { return s.trim(); }).filter(Boolean);
            if (!tags.length) { wbToast('至少填一个标签', { type: 'warn' }); return; }
            fetch('/api/kb/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: content, tags: tags })
            })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.success) {
                    var sc = d.score, tp = d.type || '材料';
                    if (d.duplicate) {
                        wbToast('库里已经有这段了（内容重复，未重复添加）', { type: 'warn', ms: 3500 });
                    } else if (sc !== undefined && sc !== null) {
                        // 后端已自动打分：>=75 归「范文」才会被生成采纳，要让队友看得见
                        var msg = '已添加 · 评分 ' + sc + ' 分';
                        if (sc >= 75) {
                            msg += '，归为「范文」，生成时会作为参考';
                            wbToast(msg, { type: 'success', ms: 4000 });
                        } else {
                            msg += '，未达 75 分归为「材料」，生成时不会采纳。建议补充数据化表述（具体数字、试点范围、真实局限）';
                            wbToast(msg, { type: 'warn', ms: 6000 });
                        }
                    } else {
                        wbToast('已添加到范文库', { type: 'success' });
                    }
                    document.getElementById('kbContent').value = '';
                    document.getElementById('kbTags').value = '';
                    kbContentHint();
                    kbList();
                } else {
                    wbToast('添加失败：' + ((d && d.error) || '未知错误'), { type: 'error' });
                }
            })
            .catch(function () { wbToast('添加失败：连不上服务', { type: 'error' }); });
        }

        function kbList() {
            fetch('/api/kb/list')
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    var box = document.getElementById('kbList');
                    var cnt = document.getElementById('kbCount');
                    if (!box) return;
                    var items = (d && d.items) || [];
                    if (cnt) cnt.innerText = items.length;
                    if (!items.length) {
                        box.innerHTML = '<div style="color:var(--text-mute);padding:16px;background:var(--surface-2);border-radius:8px;">范文库还是空的。在上面粘贴一段示范片段并打上标签即可。</div>';
                        return;
                    }
                    var html = '';
                    items.forEach(function (it) {
                        var tags = (it.tags || []).map(function (t) {
                            return '<span style="padding:2px 8px;background:var(--c-a-soft);color:var(--c-a);border-radius:10px;font-size:11px;">' + _esc(t) + '</span>';
                        }).join(' ');
                        // type 徽章：范文=绿，其它（材料/模板）=灰
                        var tname = it.type || '材料';
                        var isFan = (tname === '范文');
                        var badge = '<span style="padding:2px 8px;border-radius:10px;font-size:11px;' +
                            (isFan ? 'background:rgba(34,197,94,.14);color:#22c55e;'
                                   : 'background:var(--surface-2);color:var(--text-mute);') +
                            '">' + _esc(tname) + '</span>';
                        // 评分：>=75 加 ★（与后端"范文"判定线一致）
                        var sc = (it.score === null || it.score === undefined) ? null : Number(it.score);
                        var scoreTxt = '';
                        if (sc !== null && !isNaN(sc)) {
                            scoreTxt = '<span style="color:var(--text-mute);font-size:11px;">' +
                                '质检 ' + sc + ' 分</span>';
                        }
                        // 摘要优先，没有则回退正文前 60 字
                        var brief = (it.summary && String(it.summary).trim())
                            ? String(it.summary)
                            : (it.content || '').slice(0, 60);
                        html += '<div style="padding:12px;background:var(--surface-solid);border:1px solid var(--line);border-radius:8px;margin-bottom:10px;">' +
                            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">' +
                            '<div style="flex:1;min-width:0;">' +
                            '<div style="margin-bottom:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">' + tags + badge + scoreTxt + '</div>' +
                            '<div style="color:var(--text-dim);line-height:1.6;">' + _esc(brief) + '…</div>' +
                            '</div>' +
                            '<button onclick="kbDelete(' + it.id + ')" style="padding:4px 10px;background:var(--surface-2);color:var(--text-dim);border:1px solid var(--line);border-radius:4px;cursor:pointer;font-size:12px;white-space:nowrap;">删除</button>' +
                            '</div></div>';
                    });
                    box.innerHTML = html;
                })
                .catch(function () {});
        }

        function kbDelete(id) {
            if (!confirm('确定删除这条范文？')) return;
            fetch('/api/kb/delete/' + id, { method: 'DELETE' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d && d.success) { wbToast('已删除', { type: 'success' }); kbList(); }
                    else { wbToast('删除失败', { type: 'error' }); }
                })
                .catch(function () { wbToast('删除失败：连不上服务', { type: 'error' }); });
        }

        function kbSearch() {
            var q = (document.getElementById('kbSearchInput') || {}).value || '';
            var out = document.getElementById('kbSearchResult');
            if (!out) return;
            if (!q.trim()) { out.innerHTML = '<span style="color:var(--text-mute);">请输入关键词</span>'; return; }
            out.innerHTML = '检索中…';
            fetch('/api/kb/search?keywords=' + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d || !d.success) {
                        out.innerHTML = '<span style="color:var(--text-mute);">检索失败</span>';
                        return;
                    }
                    var kws = (d.keywords || []).map(function (k) {
                        return '<span style="padding:2px 8px;background:var(--c-a-soft);color:var(--c-a);border-radius:10px;font-size:11px;">' + k + '</span>';
                    }).join(' ');
                    if (!d.hits) {
                        out.innerHTML = '识别到的标签：' + (kws || '（无）') +
                            '<div style="margin-top:6px;color:var(--text-mute);">没有命中任何范文。换个说法，或先添加带这些标签的范文。</div>';
                        return;
                    }
                    out.innerHTML = '识别到的标签：' + (kws || '（无）') +
                        '<div style="margin-top:8px;padding:10px;background:var(--surface-2);border-radius:8px;color:var(--text-dim);line-height:1.7;max-height:260px;overflow:auto;">' +
                        (d.ref || '').slice(0, 600) + (d.hits > 600 ? '…' : '') +
                        '</div><div style="margin-top:6px;color:var(--text-mute);">共命中 ' + d.hits + ' 字，生成时会作为参考上下文注入。</div>';
                })
                .catch(function () { out.innerHTML = '<span style="color:var(--text-mute);">检索失败：连不上服务</span>'; });
        }

    /* ===================== 错别字扫描 + 一键修正 ===================== */
    /* 只收「几乎必错」的词，宁可漏报也不误报——误报会让用户不信任整个功能。
       主力是 AI 写中文时高频犯的繁体残留词（软体/硬体/网路/资讯…）和形近错字。 */
    var TYPO_RULES = [
        ['软体', '软件'], ['硬体', '硬件'], ['网路', '网络'], ['资讯', '信息'],
        ['介面', '界面'], ['程式', '程序'], ['数位', '数字'], ['效能', '性能'],
        ['模版', '模板'], ['图象', '图像'], ['帐户', '账户'], ['做为', '作为'],
        ['按装', '安装'], ['布署', '部署'], ['复盖', '覆盖'], ['重迭', '重叠'],
        ['缺限', '缺陷'], ['惟一', '唯一'], ['登陆', '登录'], ['藉由', '借助'],
        ['部份', '部分'], ['萤幕', '屏幕']
    ];
    /* 连续重复字：只收「叠着写基本就是手误」的虚词，
       爸/妈/渐/慢这类常见叠词用字刻意不在集合里，避免误报。 */
    var DUP_CHARS = '的了是在和与及或就都也很再把被让向从对为以于这那其着过';

    function typoFindInText(t) {
        var hits = [];
        TYPO_RULES.forEach(function (r) {
            var i = 0, at;
            while ((at = t.indexOf(r[0], i)) >= 0) {
                hits.push({ at: at, len: r[0].length, from: r[0], to: r[1] });
                i = at + r[0].length;
            }
        });
        var re = new RegExp('([' + DUP_CHARS + '])\\1+', 'g');
        var m;
        while ((m = re.exec(t)) !== null) {
            hits.push({ at: m.index, len: m[0].length, from: m[0], to: m[0][0] });
        }
        hits.sort(function (a, b) { return a.at - b.at; });
        // 去掉重叠区间（前面的命中已覆盖）
        var out = [], last = -1;
        hits.forEach(function (h) {
            if (h.at >= last) { out.push(h); last = h.at + h.len; }
        });
        return out;
    }

    /* 在渲染好的正文里标红。用 TreeWalker 只碰文本节点，
       绝不改 HTML 标签——直接字符串替换 innerHTML 会把 markdown 渲染结果搞坏。 */
    window.wbTypoScan = function () {
        var el = document.getElementById('proposalText');
        var bar = document.getElementById('typoBar');
        if (!el || !bar) return 0;
        el.querySelectorAll('mark.wb-typo').forEach(function (mk) {
            var p = mk.parentNode;
            p.replaceChild(document.createTextNode(mk.textContent), mk);
            p.normalize();
        });
        var total = 0, sample = [];
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
        var nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(function (node) {
            var t = node.nodeValue || '';
            if (t.length < 1) return;
            var hits = typoFindInText(t);
            if (!hits.length) return;
            total += hits.length;
            var frag = document.createDocumentFragment();
            var pos = 0;
            hits.forEach(function (h) {
                if (h.at > pos) frag.appendChild(document.createTextNode(t.slice(pos, h.at)));
                var mk = document.createElement('mark');
                mk.className = 'wb-typo';
                mk.setAttribute('data-fix', h.to);
                mk.textContent = h.from;
                mk.title = '疑似错别字，建议改为「' + h.to + '」';
                frag.appendChild(mk);
                pos = h.at + h.len;
                if (sample.length < 3 && sample.indexOf(h.from + '→' + h.to) < 0) {
                    sample.push(h.from + '→' + h.to);
                }
            });
            if (pos < t.length) frag.appendChild(document.createTextNode(t.slice(pos)));
            node.parentNode.replaceChild(frag, node);
        });
        var cnt = document.getElementById('typoCount');
        var smp = document.getElementById('typoSample');
        if (total > 0) {
            if (cnt) cnt.textContent = total;
            if (smp) smp.textContent = sample.length ? ('（' + sample.join('、') + '）') : '';
            /* CSS 初始 display:none，这里必须显式写 block，写 '' 会回落到样式表的 none */
            bar.style.display = 'block';
        } else {
            bar.style.display = 'none';
        }
        return total;
    };

    window.wbTypoFix = function () {
        var el = document.getElementById('proposalText');
        if (!el) return;
        var marks = el.querySelectorAll('mark.wb-typo');
        var n = marks.length;
        if (!n) { wbToast('没有需要修正的地方', { type: 'ok' }); return; }
        marks.forEach(function (mk) {
            mk.parentNode.replaceChild(document.createTextNode(mk.getAttribute('data-fix') || mk.textContent), mk);
        });
        el.normalize();
        document.getElementById('typoBar').style.display = 'none';
        // 字数标签要跟着改（导出取的就是 DOM 文本，改完 DOM 导出自动生效）
        try {
            if (typeof tagWordCount === 'function') {
                tagWordCount('proposalText', _txt('proposalText'));
            }
        } catch (e) {}
        wbToast('已修正 ' + n + ' 处', { type: 'ok' });
    };

    window.wbTypoDismiss = function () {
        var el = document.getElementById('proposalText');
        if (el) {
            el.querySelectorAll('mark.wb-typo').forEach(function (mk) {
                var p = mk.parentNode;
                p.replaceChild(document.createTextNode(mk.textContent), mk);
                p.normalize();
            });
        }
        document.getElementById('typoBar').style.display = 'none';
    };

    /* ===================== 图表数据真实性提醒 ===================== */
    /* 后端会在文末生成「待替换数据清单」章节，网页上要提醒作者去补真实数据；
       但它绝不能出现在导出件里（见 wbStripTodo）。 */
    window.wbDataTodoScan = function () {
        var bar = document.getElementById('dataTodoBar');
        var cnt = document.getElementById('dataTodoCount');
        var el = document.getElementById('proposalText');
        if (!bar || !el) return 0;
        var txt = el.innerText || el.textContent || '';
        var at = txt.indexOf('待替换数据清单');
        if (at < 0) {
            /* 兜底：后端字段名可能变化，改用更宽松的判据 */
            if (txt.indexOf('需替换为实测') < 0 && txt.indexOf('待替换') < 0) {
                bar.style.display = 'none';
                return 0;
            }
        }
        /* 数一下清单里列了几条（行首 - 或 数字. 的行） */
        var seg = at >= 0 ? txt.slice(at, at + 2000) : txt;
        var n = (seg.match(/(^|\n)\s*[-*·]\s*\S/g) || []).length;
        if (!n) { n = (seg.match(/(^|\n)\s*\d+[.、)]\s*\S/g) || []).length; }
        if (n > 40) n = 0;   // 明显是误判就干脆不显示数字
        /* 193 轮：数不出条数时原来填「若干」，页面就成了「有 若干 项数据需要替换」——
           这是占位词残留（L7），评委会当成没做完。改为：数得出来就报数，数不出来就说定性结论。 */
        var head = document.getElementById('dataTodoHead');
        if (head) {
            head.innerHTML = n
                ? '有 <b id="dataTodoCount">' + n + '</b> 项数据需要替换成真实值'
                : '清单里有数据需要替换成真实值（按正文里的标记逐条核对）';
        } else if (cnt) {
            cnt.textContent = n || '';
        }
        bar.style.display = 'block';
        return n;
    };
    window.wbDataTodoJump = function () {
        var el = document.getElementById('proposalText');
        if (!el) return;
        var heads = el.querySelectorAll('h1,h2,h3,h4,h5,h6,strong,p');
        for (var i = 0; i < heads.length; i++) {
            var t = (heads[i].innerText || heads[i].textContent || '');
            if (t.indexOf('待替换数据清单') >= 0) {
                heads[i].scrollIntoView({ behavior: 'smooth', block: 'center' });
                return;
            }
        }
        wbToast('没定位到清单，请手动往下翻', { type: 'warn' });
    };

    /* ===================== 分享：生成 7 天有效的只读链接 ===================== */
    function wbShareModal(url, expires) {
        var old = document.getElementById('wbShareModal');
        if (old) old.remove();
        var d = document.createElement('div');
        d.id = 'wbShareModal';
        d.className = 'modal-overlay';
        d.style.display = 'flex';
        /* _esc 在主 script 里，这里兜个底，拿不到就自己转义 */
        var safeUrl = (typeof _esc === 'function') ? _esc(url) : url.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        d.innerHTML = '<div style="background: var(--surface-solid); border: 1px solid var(--line); border-radius: 14px; padding: 20px; width: 92%; max-width: 460px;">' +
            '<div style="font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px;">分享链接已生成</div>' +
            '<div style="font-size: 12.5px; color: var(--text-mute); margin-bottom: 12px;">链接有效期至 ' +
            (expires ? _esc(String(expires)) : '7 天后') + '，对方打开只能看，不能改。</div>' +
            '<input id="wbShareUrl" readonly value="' + safeUrl + '" style="width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface-2); color: var(--text); font-size: 13px; box-sizing: border-box;">' +
            '<div style="display: flex; gap: 8px; margin-top: 12px;">' +
            '<button onclick="wbShareCopy()" style="flex: 1; padding: 11px; background: linear-gradient(135deg, var(--c-a) 0%, var(--c-b) 100%); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;">复制链接</button>' +
            '<button onclick="document.getElementById(\'wbShareModal\').remove()" style="padding: 11px 18px; background: var(--btn-ghost); color: var(--text); border: 1px solid var(--line); border-radius: 8px; cursor: pointer; font-size: 14px;">关闭</button>' +
            '</div></div>';
        d.addEventListener('click', function (e) { if (e.target === d) d.remove(); });
        document.body.appendChild(d);
        var inp = document.getElementById('wbShareUrl');
        if (inp) { inp.focus(); inp.select(); }
    }
    window.wbShareCopy = function () {
        var inp = document.getElementById('wbShareUrl');
        if (!inp) return;
        var txt = inp.value;
        var done = function () { wbToast('链接已复制', { type: 'ok' }); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txt).then(done, wbShareFallback);
        } else {
            wbShareFallback();
        }
        function wbShareFallback() {
            try {
                inp.select();
                document.execCommand('copy');
                done();
            } catch (e) { wbToast('复制失败，请手动选中链接复制', { type: 'warn' }); }
        }
    };
    window.wbShare = function () {
        var hid = window._lastHistoryId;
        if (!hid) {
            wbToast('这份结果还没存进历史记录，暂时无法分享', { type: 'warn', sub: '刷新页面后重新生成一次即可' });
            return;
        }
        var btn = (window.event && window.event.target) || null;
        if (btn) { btn.disabled = true; btn.dataset.old = btn.innerHTML; btn.innerHTML = '生成中...'; }
        var back = function () { if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.old || '分享'; } };
        fetch('/api/share/' + hid, { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                back();
                if (!d.success) { wbToast(d.error || '生成分享链接失败', { type: 'error' }); return; }
                wbShareModal(location.origin + d.url, d.expires);
            })
            .catch(function (e) { back(); wbToast('生成分享链接失败：' + (e && e.message || e), { type: 'error' }); });
    };

    /* ============ 常驻反馈入口（105-1：独立于生成结果，任何状态都能提交） ============ */
    window.wbFeedbackOpen = function () {
        var old = document.getElementById('wbFeedbackModal');
        if (old) old.remove();
        var d = document.createElement('div');
        d.id = 'wbFeedbackModal';
        d.className = 'modal-overlay';
        d.style.display = 'flex';
        d.innerHTML = '<div style="background: var(--surface-solid); border: 1px solid var(--line); border-radius: 14px; padding: 20px; width: 92%; max-width: 460px;">' +
            '<div style="font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px;">反馈 / 建议</div>' +
            '<div style="font-size: 12.5px; color: var(--text-mute); margin-bottom: 12px;">遇到问题或有好想法都可以说，会直接进后台、用于改进工具。</div>' +
            '<textarea id="wbFeedbackTxt" placeholder="例如：XX 按钮点了没反应 / 希望支持 XX 赛事…" style="width: 100%; min-height: 96px; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface-2); color: var(--text); font-size: 13px; box-sizing: border-box; resize: vertical;"></textarea>' +
            '<div style="display: flex; gap: 8px; margin-top: 12px;">' +
            '<button onclick="wbFeedbackSubmit()" style="flex: 1; padding: 11px; background: linear-gradient(135deg, var(--c-a) 0%, var(--c-b) 100%); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;">提交</button>' +
            '<button onclick="document.getElementById(\'wbFeedbackModal\').remove()" style="padding: 11px 18px; background: var(--btn-ghost); color: var(--text); border: 1px solid var(--line); border-radius: 8px; cursor: pointer; font-size: 14px;">关闭</button>' +
            '</div></div>';
        d.addEventListener('click', function (e) { if (e.target === d) d.remove(); });
        document.body.appendChild(d);
        var ta = document.getElementById('wbFeedbackTxt');
        if (ta) ta.focus();
    };
    window.wbFeedbackSubmit = function () {
        var ta = document.getElementById('wbFeedbackTxt');
        var txt = (ta ? ta.value : '').trim();
        if (!txt) { wbToast('反馈内容不能为空', { type: 'warn' }); return; }
        var btn = document.querySelector('#wbFeedbackModal button[onclick="wbFeedbackSubmit()"]');
        if (btn) { btn.disabled = true; btn.textContent = '提交中…'; }
        fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: txt })
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
              if (j && j.success === false) throw new Error(j.error || '提交失败');
              var m = document.getElementById('wbFeedbackModal');
              if (m) m.remove();
              wbToast('感谢你的反馈，我们会持续改进！', { type: 'ok' });
          })
          .catch(function (e) {
              if (btn) { btn.disabled = false; btn.textContent = '提交'; }
              wbToast('没提交成功：' + ((e && e.message) || '网络问题'), { type: 'error' });
          });
    };

    /* ===================== 历史记录：按比赛类型分 tab ===================== */
    var _hisGroups = null, _hisTab = '__all__';
    window.wbLoadHisTabs = function () {
        var box = document.getElementById('hisTabs');
        if (!box) return;
        if (_hisGroups) { renderHisTabs(); return; }
        box.innerHTML = '<span style="font-size:12px;color:var(--text-mute);">加载分组…</span>';
        fetch('/api/history/groups')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                _hisGroups = (d && d.success) ? (d.groups || []) : [];
                renderHisTabs();
            })
            .catch(function () {
                _hisGroups = [];
                box.innerHTML = '';
            });
    };
    function renderHisTabs() {
        var box = document.getElementById('hisTabs');
        if (!box || !_hisGroups) return;
        var total = 0;
        _hisGroups.forEach(function (g) { total += g.count; });
        var html = '<button class="his-tab' + (_hisTab === '__all__' ? ' on' : '') + '" onclick="wbHisTab(\'__all__\')">全部 ' + total + '</button>';
        _hisGroups.forEach(function (g) {
            var key = String(g.competition || '未标注比赛');
            html += '<button class="his-tab' + (_hisTab === key ? ' on' : '') + '" onclick="wbHisTab(' +
                JSON.stringify(key).replace(/"/g, '&quot;') + ')">' +
                _esc(key) + ' ' + g.count + '</button>';
        });
        box.innerHTML = html;
    }
    window.wbHisTab = function (key) {
        _hisTab = key;
        renderHisTabs();
        // 本地过滤：groups 接口已经把全量条目带回来了，不必再打一次接口
        if (_hisTab === '__all__') { loadHistory(0); return; }
        var g = null;
        (_hisGroups || []).forEach(function (x) { if (String(x.competition) === String(key)) g = x; });
        var list = document.getElementById('historyList');
        var pager = document.getElementById('historyPager');
        if (!g || !(g.items || []).length) {
            list.innerHTML = '<p style="color: var(--text-mute); text-align: center;">'
                + '该比赛下还没有记录，去生成第一篇吧</p>';
            if (pager) pager.innerHTML = '';
            return;
        }
        list.innerHTML = (g.items || []).map(function (h) {
            return '<div class="history-item" style="cursor: pointer;" onclick="openHistory(' + h.id + ')">' +
                '<div class="history-info">' +
                    '<div class="history-title">' + _esc(h.competition_name || g.competition || '') + '</div>' +
                    '<div class="history-idea">' + _esc(h.idea || '') + '</div>' +
                    '<div class="history-meta">' + _esc(h.time || '') + ' · 得分 ' + _esc(h.score == null ? '-' : h.score) + '</div>' +
                '</div>' +
                '<div style="display: flex; gap: 6px; flex-shrink: 0;">' +
                    '<button class="history-open" onclick="event.stopPropagation();openHistory(' + h.id + ')">打开</button>' +
                    '<button class="history-del" onclick="event.stopPropagation();deleteHistory(' + h.id + ')">删除</button>' +
                '</div>' +
            '</div>';
        }).join('');
        if (pager) pager.innerHTML = '<span>共 ' + (g.items || []).length + ' 条</span>';
    };

    /* ===================== 失败/超时后重试 ===================== */
    window.wbRetry = function () {
        var w = document.getElementById('retryWrap');
        if (w) w.style.display = 'none';
        var eb = document.getElementById('etaBadge');
        if (eb) eb.style.display = 'none';
        try { startWork(); } catch (e) {
            wbToast('重试失败：' + (e && e.message || e), { type: 'error' });
        }
    };
    window.wbHideRetry = function () {
        var w = document.getElementById('retryWrap');
        if (w) w.style.display = 'none';
    };

        function showHistory() {
            // 同「背景」按钮：引导遮罩还在时先把引导收掉，别让用户点了没反应
            try {
                if (typeof coachEnd === 'function') coachEnd(); // 无条件收引导：veil 有 380ms 创建延迟，只查 veil 会漏掉窗口期
            } catch (e) {}
            document.getElementById('historyModal').style.display = 'flex';
            loadHistory(0);
            try { wbLoadHisTabs(); } catch (e) {}
        }

        function closeHistory(event) {
            var m = document.getElementById('historyModal');
            if (!m) return;
            // 只有「点到遮罩本身」才关，点弹窗内部不关。
            // 没传事件也要能关（右上角 ×、底部「关闭」按钮、Esc 都走这条路）——
            // 2026-09-28 修：原实现直接读 event.target，无参调用会抛错，导致 × 和 Esc 全都关不掉。
            if (event && event.target && event.target !== m) return;
            m.style.display = 'none';
        }

        var _historyLimit = 10;
        var _historyOffset = 0;
        /* ---------- 历史记录的本机兜底（2026-09-28 移动端实测） ----------
           后端历史按 user_id 隔离，user_id 来自 httponly cookie。手机端存储被拦
           （控制台 Tracking Prevention blocked access to storage）时 cookie 存不住，
           下次请求就是新的 uid —— 于是「明明刚生成完，历史页却是 0 条」。
           本机这份不能替代后端，但能保证「刚生成的结果刷新后还能打开」：
           生成完成时顺手存一份到 sessionStorage（同标签页刷新不丢），
           后端查不到时用它兜底。超过 1.2MB 的只存摘要，避免撑爆配额。 */
        var WB_LOCAL_HIST_KEY = 'wbLocalHist';
        function _wbNowStr() {
            var d = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
            return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
                ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
        }
        function wbLocalHistList() {
            try { return JSON.parse(_wbStoreGet(WB_LOCAL_HIST_KEY) || '[]') || []; } catch (e) { return []; }
        }
        function wbLocalHistPush(rec) {
            try {
                var big = 0;
                try { big = JSON.stringify(rec.data || {}).length; } catch (e) {}
                var slim = rec;
                if (big > 1200000) {
                    slim = { id: rec.id, competition_name: rec.competition_name, idea: rec.idea,
                             time: rec.time, score: rec.score, _tooBig: true };
                }
                var list = wbLocalHistList().filter(function (x) { return String(x.id) !== String(rec.id); });
                list.unshift(slim);
                _wbStoreSet(WB_LOCAL_HIST_KEY, JSON.stringify(list.slice(0, 3)));
            } catch (e) {}
        }
        function wbLocalHistFind(id) {
            try {
                var l = wbLocalHistList();
                for (var i = 0; i < l.length; i++) if (String(l[i].id) === String(id)) return l[i];
            } catch (e) {}
            return null;
        }

        /* ---------- 一键同步码（2026-09-28，后端 /api/sync_code + /api/bind_uid） ----------
           历史是按匿名 uid 隔离的，换设备/清 cookie 就看不到之前生成的。
           同步码让两台设备共用一个 uid：A 显示码 → B 输入码 → B 看 A 的历史。
           不登录、不用密码（赛前不露用户名密码入口，后端接口留着不接）。 */
        function wbSyncLoad() {
            var row = document.getElementById('wbSyncCodeRow');
            var el = document.getElementById('wbSyncCode');
            if (!row || !el) return;
            el.textContent = '...';
            row.style.display = 'flex';
            fetch('/api/sync_code', { cache: 'no-store' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d || !d.success || !d.sync_code) {
                        row.style.display = 'none';
                        wbToast('没拿到同步码：' + ((d && d.error) || '请稍后再试'), { type: 'error' });
                        return;
                    }
                    el.textContent = String(d.sync_code);
                })
                .catch(function () {
                    row.style.display = 'none';
                    wbToast('网络不通，同步码没取到', { type: 'error' });
                });
        }
        window.wbSyncLoad = wbSyncLoad;

        function wbSyncCopy() {
            var code = String((document.getElementById('wbSyncCode') || {}).textContent || '').trim();
            if (!code || code === '--------' || code === '...') {
                wbToast('先点「显示我的同步码」', { type: 'warn' }); return;
            }
            function ok() { wbToast('已复制同步码：' + code, { type: 'success' }); }
            function fallback() {
                try {
                    var ta = document.createElement('textarea');
                    ta.value = code; ta.style.position = 'fixed'; ta.style.left = '-9999px';
                    document.body.appendChild(ta); ta.select();
                    document.execCommand('copy'); document.body.removeChild(ta); ok();
                } catch (e) { wbToast('复制失败，请手动记下：' + code, { type: 'warn', ms: 6000 }); }
            }
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(code).then(ok, fallback);
                } else fallback();
            } catch (e) { fallback(); }
        }
        window.wbSyncCopy = wbSyncCopy;

        function wbSyncBind() {
            var inp = document.getElementById('wbSyncInput');
            var code = String((inp && inp.value) || '').trim().toUpperCase().replace(/\s+/g, '');
            if (code.length < 6) { wbToast('请输入另一台设备上的 8 位同步码', { type: 'warn' }); return; }
            var btn = document.querySelector('[onclick="wbSyncBind()"]');
            var old = btn ? btn.textContent : '';
            if (btn) { btn.disabled = true; btn.textContent = '同步中…'; }
            fetch('/api/bind_uid', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (btn) { btn.disabled = false; btn.textContent = old; }
                    if (!d || !d.success) {
                        wbToast((d && d.error) || '同步失败，请检查同步码', { type: 'error' }); return;
                    }
                    if (inp) inp.value = '';
                    wbToast('已同步，正在重新加载历史', { type: 'success' });
                    try { loadHistory(0); } catch (e) {}
                    try { if (typeof wbLoadHisTabs === 'function') wbLoadHisTabs(); } catch (e) {}
                })
                .catch(function () {
                    if (btn) { btn.disabled = false; btn.textContent = old; }
                    wbToast('网络不通，同步失败', { type: 'error' });
                });
        }
        window.wbSyncBind = wbSyncBind;

        function loadHistory(offset) {
            _historyOffset = offset;
            var q = (document.getElementById('historySearch') || {}).value || '';
            var list = document.getElementById('historyList');
            list.innerHTML = '<p style="color: var(--text-mute); text-align: center;">加载中...</p>';
            fetch('/api/history?limit=' + _historyLimit + '&offset=' + offset + '&q=' + encodeURIComponent(q))
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (!d.success) { throw new Error(d.error || '加载失败'); }
                    renderHistoryList(d);
                })
                .catch(function (e) {
                    list.innerHTML = '<p style="color: var(--err-text); text-align: center;">加载失败：' + _esc(_friendlyErr(e)) + '</p>';
                });
        }
        function renderHistoryList(d) {
            var list = document.getElementById('historyList');
            var items = d.history || [];
            if (!items.length) {
                var _locList = [];
                try { _locList = wbLocalHistList(); } catch (e) {}
                if (_locList.length) {
                    list.innerHTML =
                        '<p style="color: var(--text-mute); text-align: center; font-size: 12.5px; line-height: 1.7; margin-bottom: 8px;">'
                        + '浏览器限制了本机存储，后端暂时查不到你的记录；下面是<b>本次会话</b>生成的，'
                        + '换个浏览器或关掉无痕模式就能长期保存。</p>' +
                        _locList.map(function (h) {
                            return '<div class="history-item" style="cursor: pointer;" onclick="openHistory(' + h.id + ')">' +
                                '<div class="history-info">' +
                                    '<div class="history-title">' + _esc(h.competition_name || '') + '</div>' +
                                    '<div class="history-idea">' + _esc((h.idea || '').slice(0, 60)) + '</div>' +
                                    '<div class="history-meta">' + _esc(h.time || '') + ' · 得分 ' +
                                        _esc(h.score == null ? '-' : h.score) +
                                        ' · <span style="color: var(--c-a);">本机记录</span></div>' +
                                '</div>' +
                                '<div style="display: flex; gap: 6px; flex-shrink: 0;">' +
                                    '<button class="history-open" onclick="event.stopPropagation();openHistory(' + h.id + ')">打开</button>' +
                                '</div>' +
                            '</div>';
                        }).join('');
                } else {
                    list.innerHTML = '<p style="color: var(--text-mute); text-align: center;">'
                        + '还没有生成记录，去试试第一篇吧</p>';
                }
            } else {
                list.innerHTML = items.map(function (h) {
                    // 整条都可点开（之前只有「删除」，点不开内容，等于历史记录没法用）
                    return '<div class="history-item" style="cursor: pointer;" onclick="openHistory(' + h.id + ')">' +
                        '<div class="history-info">' +
                            '<div class="history-title">' + _esc(h.competition_name || '') + '</div>' +
                            '<div class="history-idea">' + _esc(h.idea || '') + '</div>' +
                            '<div class="history-meta">' + _esc(h.time || '') + ' · 得分 ' + _esc(h.score == null ? '-' : h.score) + '</div>' +
                        '</div>' +
                        '<div style="display: flex; gap: 6px; flex-shrink: 0;">' +
                            '<button class="history-open" onclick="event.stopPropagation();openHistory(' + h.id + ')">打开</button>' +
                            '<button class="history-del" onclick="event.stopPropagation();deleteHistory(' + h.id + ')">删除</button>' +
                        '</div>' +
                    '</div>';
                }).join('');
            }
            renderHistoryPager(d);
        }
        function renderHistoryPager(d) {
            var pager = document.getElementById('historyPager');
            var total = d.total || 0;
            var limit = d.limit || _historyLimit;
            var offset = d.offset || 0;
            var page = Math.floor(offset / limit);
            var totalPages = Math.max(1, Math.ceil(total / limit));
            var html = '<button onclick="loadHistory(' + Math.max(0, offset - limit) + ')"' + (page <= 0 ? ' disabled' : '') + '>上一页</button>';
            html += '<span>第 ' + (page + 1) + ' / ' + totalPages + ' 页 · 共 ' + total + ' 条</span>';
            html += '<button onclick="loadHistory(' + (offset + limit) + ')"' + (page >= totalPages - 1 ? ' disabled' : '') + '>下一页</button>';
            pager.innerHTML = html;
        }
        // 打开一条历史记录：把服务器上存的结果回填到各 Tab
        // （之前列表只有「删除」按钮，点不开内容，历史记录等于没法用）
        async function openHistory(id) {
            var modal = document.getElementById('historyModal');
            try {
                var d = null;
                try {
                    var res = await fetch('/api/history/' + id);
                    d = await res.json();
                } catch (e) { d = null; }
                if (!d || !d.success || !d.data) {
                    // 后端按 uid 隔离，手机端 uid 存不住时这条会「记录不存在」。
                    // 用生成时存在本机的那份兜底，历史不至于点了打不开。
                    var _loc = wbLocalHistFind(id);
                    if (_loc && _loc.data) { d = { success: true, data: _loc.data }; }
                    else {
                        wbToast('这条记录加载失败：' + ((d && d.error) || '没有数据'), { type: 'error' });
                        return;
                    }
                }
                var data = d.data;
                window._lastData = data;
                // 打开历史必须同步记下 history_id，否则 wbShare 和导出回源都会拿不到 id，
                // 表现成「分享提示还没存进历史」「导出不回源当前记录」。
                window._lastHistoryId = id;
                // 174 轮：回看历史必须重算「沉淀」入口。原来只在生成完成那次同步过，
                // 于是回看一条旧记录时，按钮上写的还是上一条的分数、点下去沉淀的却是当前这条
                // ——「显示的分数」和「实际入库的记录」不是同一条，属于静默错沉淀。
                try {
                    var _hs = 0;
                    try {
                        var _rd = (data && data.result_data) ? JSON.parse(data.result_data) : {};
                        _hs = parseInt((data && data.score) || (_rd && _rd.score) || 0, 10) || 0;
                    } catch (e2) { _hs = parseInt((data && data.score) || 0, 10) || 0; }
                    window._wbLastScore = _hs;
                    wbTrainArchiveSync(_hs);
                } catch (e) {}
                wbFabShow(!!data.rich_deck);
                var isDeep = !!(data.competitor_analysis || data.business_model || data.tech_solution);
                window._lastMode = data.mode || (isDeep ? 'deep' : 'fast');
                var md = function (s) {
                    try { return wbRenderMD(s || ''); } catch (e) { return String(s || '').replace(/\n/g, '<br>'); }
                };
                var set = function (domId, txt) {
                    var el = document.getElementById(domId);
                    if (el) el.innerHTML = txt ? md(txt) : '';
                };
                set('parsedRules', data.parsed_rules);
                set('similarityReport', data.similarity_report);
                try {
                    var si = document.getElementById('simInfo');
                    if (si) {
                        var s = data.similarity || {};
                        si.innerText = (typeof s.percent === 'number') ? (Math.round(s.percent * 10) / 10) + '%' : '暂无';
                        si.title = (s.checked ? '与本地 ' + s.checked + ' 条范文对比（本地初检，非知网正式查重）' : '本地初检，非正式查重');
                    }
                } catch (e) {}
                set('proposalText', data.proposal);
                set('judgeFeedback', data.judge_feedback);
                set('proposalAnalysis', data.proposal_analysis);
                set('competitorAnalysis', data.competitor_analysis);
                set('businessModel', data.business_model);
                set('riskAnalysis', data.risk_analysis);
                set('techSolution', data.tech_solution);
                set('implementationPlan', data.implementation_plan);
                set('socialValue', data.social_value);
                set('projectSummary', data.project_summary);
                set('defenseQuestions', data.defense_questions);
                set('pptOutline', data.ppt_outline);
                try { renderExpertReview(data.expert_review); } catch (e) {}
                try { renderJudgeScores(data.judge_scores); } catch (e) {}
                try { renderIdeaRadar(data.scores, data.idea_score); } catch (e) {}
                try { wbRefreshPhBar(); } catch (e) {}
                try { renderCompleteness(data.completeness); } catch (e) {}
                try { renderRich(data, isDeep); } catch (e) {}
                try { initDeckThemeSelect(); } catch (e) {}
                // 板块显隐：深度版专属块按内容有无显示
                document.querySelectorAll('.deep-only').forEach(function (el) {
                    el.style.display = isDeep ? 'block' : 'none';
                });
                document.querySelectorAll('.auto-show').forEach(function (el) {
                    var cb = el.querySelector('.content-block');
                    el.style.display = (cb && cb.innerHTML.trim().length > 20) ? 'block' : 'none';
                });
                try { wbSyncPptRow(); } catch (e) {}
                var defenseTab = document.getElementById('defenseTab');
                if (defenseTab) defenseTab.style.display = 'block';
                var chartsTab = document.getElementById('chartsTab');
                if (chartsTab) chartsTab.style.display = isDeep ? 'block' : 'none';
                var badge = document.getElementById('tierBadge');
                if (badge) {
                    // 档位以记录自带的 mode 为准；后端还没落库 mode 时才回退到内容嗅探
                    var _hm = data.mode || (_loc && _loc.mode) || (isDeep ? 'deep' : 'fast');
                    badge.innerHTML = wbTierBadgeHtml(_hm, data.competition_name || '',
                        '历史记录 · 深度版', '历史记录 · 简洁版');
                }
                // 关键：结果区默认是隐藏的，不打开就什么都看不到
                var area = document.getElementById('resultArea');
                if (area) {
                    area.style.display = 'block';
                    area.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
                // 打开历史后默认切到「申报与评审」，让用户第一眼看到申报书正文，而不是只看到前期分析
                try { switchTab(null, 'proposal'); } catch (e) {}
                if (modal) modal.style.display = 'none';
                wbToast('已打开历史记录 #' + id + '，可以继续导出', { type: 'ok', ms: 2800 });
            } catch (e) {
                wbToast('打开失败：' + _friendlyErr(e), { type: 'error' });
            }
        }

        function deleteHistory(id) {
            if (!window.confirm('确定删除这条历史记录？')) return;
            fetch('/api/history/' + id, { method: 'DELETE' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d.success) {
                        wbToast('已删除', { type: 'ok' });
                        loadHistory(_historyOffset);
                    } else {
                        wbToast(d.error || '删除失败', { type: 'error' });
                    }
                })
                .catch(function (e) {
                    wbToast('删除失败：' + _friendlyErr(e), { type: 'error' });
                });
        }

        // 健康轮询（第一百四十七轮 / 第一百五十七轮改造）：
        // ① 3 秒超时兜底：/api/health 实测最慢 2.79s，超时一律按「没结果」处理，绝不无限转圈；
        // ② 正常 = 完全不显示（把指示器藏起来），不再常驻「服务正常」——那是内部状态，
        //    评委/用户不需要看见；只有连续 3 次失败（约 90 秒）才显示「服务异常」；
        // ③ 单次失败静默重试，不弹「检测中…」过渡态（它正是「卡住」观感的来源）。
        var _healthFailStreak = 0;
        var HEALTH_TIMEOUT_MS = 3000;
        function _healthHide() {
            var dot = document.getElementById('healthDot');
            if (dot) dot.style.display = 'none';
        }
        function _healthShow(cls, text, tip) {
            var dot = document.getElementById('healthDot');
            var txt = document.getElementById('healthText');
            if (!dot) return;
            dot.style.display = '';
            dot.className = 'health-dot' + (cls ? ' ' + cls : '');
            if (txt) txt.innerText = text;
            dot.title = tip || '';
        }
        function checkHealth() {
            var ctl = (typeof AbortController === 'function') ? new AbortController() : null;
            var timer = setTimeout(function () { if (ctl) { try { ctl.abort(); } catch (e) {} } }, HEALTH_TIMEOUT_MS);
            var opt = ctl ? { signal: ctl.signal, cache: 'no-store' } : { cache: 'no-store' };
            fetch('/api/health', opt)
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    clearTimeout(timer);
                    if (d && d.success && d.status === 'ok') {
                        _healthFailStreak = 0;
                        window._wbHealthOk = true;      // 167 轮：心跳退避计数器复位
                        if (typeof _hbMul !== 'undefined') _hbMul = 1;
                        _healthHide();          // 正常 = 不打扰
                    } else {
                        window._wbHealthOk = false;
                        _healthFail();
                    }
                })
                .catch(function () {
                    clearTimeout(timer);
                    window._wbHealthOk = false;
                    _healthFail();              // 网络失败 / 3 秒超时都走这里
                });
        }
        function _healthFail() {
            _healthFailStreak++;
            if (_healthFailStreak >= 3) {
                _healthShow('err', '服务异常', '连续 ' + _healthFailStreak + ' 次健康检查未通过，服务可能暂时不可用');
            } else {
                // 前两次失败静默重试：用户不需要为一次网络抖动买单
                _healthHide();
            }
        }
    
        
        
        // 页面加载后拉取一次知识库状态（失败也不影响主流程）
        loadKnowledgeStatus();
        // 赛事官方资料索引：拉一次缓存起来，之后选赛事纯本地匹配，不用等网络
        wbLoadCompIndex();
        wbCompReorderChips();   // 老用户回来：常用赛事标签按本机使用频次排好（第一百零二轮）
        // 赛事结构化配置（章节顺序 / 评分口径 / 双盲），同样是拉一次缓存
        wbLoadProfiles();
        // 三个上传入口统一兜底：内置浏览器拦一下、旧版 .doc 提前说清
        ['ruleFile', 'tplFile', 'ideaFile', 'udFile'].forEach(wbUploadGuard);
        // wbMatFile 在「从材料识别」弹层里，那段 HTML 在主块之后，此刻还没进 DOM，
        // 直接 forEach 会取到 null（守卫静默不生效）。等 DOM 就绪再挂，顺便接文件名回显。
        (function () {
            function bind() {
                try { wbUploadGuard('wbMatFile'); } catch (e) {}
                var f = document.getElementById('wbMatFile');
                if (!f) return;
                f.addEventListener('change', function () {
                    var s = document.getElementById('wbMatFileName');
                    var file = f.files && f.files[0];
                    if (s) s.textContent = file ? file.name : '未选择文件（PDF / DOCX / TXT / MD）';
                });
            }
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
            else bind();
        })();
        // 创意写完自动猜赛事：用户不用再从十几项里挑
        (function () {
            var ie = document.getElementById('idea');
            if (!ie) return;
            ie.addEventListener('blur', function () {
                try { wbAutoComp(); } catch (e) {}
            });
        })();
        /* ===== 维护公告（第九十四轮【中】）=====
           为什么要双源：后端 /api/notice 要等 Codex 发版，而「停机前先开公告」本身就是
           应急预案——真到要停机那一刻，改一个 JSON 文件就能挂上去，才算可用。
           所以优先读 /api/notice，拿不到就读静态 /static/notice.json；
           两边都没有 → 整条不渲染（默认行为，不会平白多一条黄条）。
           关闭记忆按「文案指纹」存本地：文案一改就重新弹，
           避免用户关过一次之后再也看不到新公告。 */
        (function () {
            var bar = document.getElementById('wbNoticeBar');
            if (!bar) return;
            var elTitle = document.getElementById('wbNoticeTitle');
            var elText = document.getElementById('wbNoticeText');

            function fingerprint(s) {
                var h = 0;
                for (var i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
                return String(h);
            }

            function render(d) {
                if (!d || typeof d !== 'object') return;
                if (d.active === false) return;   // 后端 /api/notice 的显式开关：关了就当没有
                var text = String(d.text || d.content || d.message || '').trim();
                if (!text) return;
                var title = String(d.title || '维护公告').trim() || '维护公告';
                var fp = fingerprint(title + '|' + text);
                if (_wbStoreGet('wbNoticeClosed') === fp) return;   // 这条已经关过了，不再打扰
                if (elTitle) elTitle.textContent = title;
                if (elText) elText.textContent = ' ' + text;
                bar.setAttribute('data-fp', fp);
                bar.style.display = 'flex';     // 注意：不能写 '' ——会被样式表里的 display:none 盖掉
            }

            window.wbNoticeClose = function () {
                var fp = bar.getAttribute('data-fp') || '';
                if (fp) { try { _wbStoreSet('wbNoticeClosed', fp); } catch (e) {} }
                bar.style.display = 'none';
            };

            function fromStatic() {
                return fetch('/static/notice.json?t=' + Date.now(), { cache: 'no-store' })
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .catch(function () { return null; });
            }

            fetch('/api/notice', { cache: 'no-store' })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    var t = d && String(d.text || d.content || d.message || '').trim();
                    if (t) { render(d); return null; }
                    return fromStatic().then(render);      // 后端没这接口 / 没内容 → 静态兜底
                })
                .catch(function () { return fromStatic().then(render); });
        })();

        /* ---------- 174 轮：内容使用授权（训练开关 + 沉淀入库） ----------
           合规要求「知情 + 可拒绝」，所以：开关默认开但一句话说清后果、状态随本机记忆
           （走 _wbStoreSet，iOS/微信拦 localStorage 时自动降级到 sessionStorage/内存）、
           入库必须用户亲手点（系统绝不自动替他决定他的内容去哪）。 */
        var WB_TRAIN_KEY = 'wb_train_consent';
        function wbTrainConsent() {
            // 没显式关过就是「开」——默认参与，退出路径要显式、进入不必确认
            return _wbStoreGet(WB_TRAIN_KEY) !== '0';
        }
        window.wbTrainConsent = wbTrainConsent;
        function wbTrainToggle(on) {
            _wbStoreSet(WB_TRAIN_KEY, on ? '1' : '0');
            try {
                wbToast(on ? '已开启：达标内容可沉淀入知识库' : '已关闭：你的内容不会再入库',
                        { type: on ? 'ok' : 'warn', ms: 2600 });
            } catch (e) {}
            try { wbTrainArchiveSync(); } catch (e) {}
        }
        window.wbTrainToggle = wbTrainToggle;

        // 仅在评分 ≥85 且已授权时露出「沉淀」按钮；不达标就整行藏掉，别让人撞 422 错误
        function wbTrainArchiveSync(score) {
            var row = document.getElementById('trainArchiveRow');
            if (!row) return;
            if (typeof score !== 'number') score = parseInt(window._wbLastScore || 0, 10);
            var ok = wbTrainConsent() && score >= 85 && window._lastHistoryId;
            if (!ok) { row.style.display = 'none'; row.innerHTML = ''; return; }
            row.style.display = '';
            row.innerHTML =
                '<button class="wb-glass-btn wb-glass-btn-sm" onclick="wbTrainArchive()" '
                + 'title="把这一版脱敏后存入知识库，用于改进后续生成质量">'
                + '<span class="wb-dot"></span>沉淀为训练样本</button>'
                + '<span style="margin-left:8px; font-size:11.5px; color:var(--text-mute);">'
                + '评分 ' + score + ' ≥ 85 · 脱敏后入库</span>';
        }
        window.wbTrainArchiveSync = wbTrainArchiveSync;

        function wbTrainArchive() {
            var row = document.getElementById('trainArchiveRow');
            var hid = window._lastHistoryId;
            if (!hid) { wbToast('这条结果还没入库记录，刷新后再试', { type: 'ok', ms: 2600 }); return; }
            var btn = row ? row.querySelector('button') : null;
            if (btn) { btn.disabled = true; btn.innerHTML = '沉淀中…'; }
            fetch('/api/training/archive', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history_id: hid, consent: wbTrainConsent() })
            }).then(function (r) { return r.json().then(function (d) { return { st: r.status, d: d }; }); })
              .then(function (res) {
                var d = res.d || {};
                if (res.st === 200 && d.success) {
                    if (row) {
                        row.innerHTML = '<span style="font-size:12px; color:var(--c-b);">'
                            + '✓ 已沉淀入知识库' + (d.is_new ? '' : '（库里已有相同内容，未重复写入）')
                            + '</span>';
                    }
                    wbToast('已脱敏入库，感谢贡献', { type: 'ok', ms: 2600 });
                } else if (res.st === 403) {
                    wbToast('你已在设置里关闭授权，开启后才能沉淀', { type: 'error', ms: 3200 });
                    if (btn) { btn.disabled = false; btn.innerHTML = '<span class="wb-dot"></span>沉淀为训练样本'; }
                } else if (res.st === 422 && d.code === 'score_low') {
                    wbToast('评分 ' + d.score + ' < 85，未达入库门槛', { type: 'error', ms: 3200 });
                    if (row) row.style.display = 'none';
                } else {
                    wbToast('沉淀失败：' + (d.error || '请稍后重试'), { type: 'error', ms: 3200 });
                    if (btn) { btn.disabled = false; btn.innerHTML = '<span class="wb-dot"></span>沉淀为训练样本'; }
                }
            }).catch(function () {
                wbToast('网络异常，沉淀未成功', { type: 'error', ms: 2600 });
                if (btn) { btn.disabled = false; btn.innerHTML = '<span class="wb-dot"></span>沉淀为训练样本'; }
            });
        }
        window.wbTrainArchive = wbTrainArchive;

        /* ---------- 186 轮：档位文案的实测数据一律动态取，禁止写死 ----------
           教训（本人 157 轮亲手埋的雷）：当时把「样本数 / 中位字数 / 用时区间」直接
           写进 HTML。样本会增长、口径会变，写死的数字几个月后必然与 /api/stats 打架，
           评委一对照就穿帮——「数据必须真实经得起推敲」这条铁律，最先要约束的是自己。
           现在：页面加载后拉 /api/stats，用 **中位数 + 样本数** 单一口径渲染；
           拿不到数据或样本不足时只显示定性描述，绝不编一个好看的数。 */
        var WB_STATS = null;
        function _wbDurTxt(sec) {
            sec = Math.round(parseFloat(sec) || 0);
            if (sec <= 0) return '';
            if (sec < 60) return sec + ' 秒';
            var m = sec / 60;
            return (m < 10 ? (Math.round(m * 10) / 10) : Math.round(m)) + ' 分钟';
        }
        function _wbTierLine(mode, wantHead) {
            var s = (WB_STATS && WB_STATS[mode]) || null;
            var n = s ? (parseInt(s.sample_count, 10) || 0) : 0;
            var med = s ? (parseInt(s.chars_median, 10) || 0) : 0;
            var dur = s ? _wbDurTxt(s.duration_median_sec) : '';
            if (!n || !med) {
                // 样本不足：只讲定性，不报数字
                return wantHead
                    ? (mode === 'fast' ? '出稿快，字数精' : '内容全，含图表与路演稿')
                    : '（样本积累中，暂不公布实测数据）';
            }
            if (wantHead) {
                return mode === 'fast'
                    ? ('约 ' + (dur || '1 分钟') + '出 ' + Math.round(med / 100) * 100 + ' 字级申报书')
                    : ('约 ' + (dur || '4 分钟') + '出 ' + Math.round(med / 1000) * 1000 + ' 字级完整方案书');
            }
            return '（' + n + ' 次实测中位 ' + med + ' 字' + (dur ? ' / ' + dur : '') + '）';
        }
        function wbStatsFill() {
            var set = function (id, txt) {
                var el = document.getElementById(id);
                if (el && txt) el.innerText = txt;
            };
            var fallback = function () {
                set('statFastHead', '出稿快，字数精');
                set('statFastDetail', '（样本积累中，暂不公布实测数据）');
                set('statDeepHead', '内容全，含图表与路演稿');
                set('statDeepDetail', '（样本积累中，暂不公布实测数据）');
            };
            try {
                fetch('/api/stats').then(function (r) { return r.json(); })
                    .then(function (d) {
                        if (!d || !d.success) { fallback(); return; }
                        WB_STATS = d; window.WB_STATS = d;
                        set('statFastHead', _wbTierLine('fast', true));
                        set('statFastDetail', _wbTierLine('fast', false));
                        set('statDeepHead', _wbTierLine('deep', true));
                        set('statDeepDetail', _wbTierLine('deep', false));
                    }).catch(fallback);
            } catch (e) { fallback(); }
        }
        window.wbStatsFill = wbStatsFill;

        /* ---------- 171 轮：图表配色个性化 ----------
           用户需求：「图表颜色能不能像 ai 对话一样，根据使用对象的想法进行改变」。
           落地原则：①前端 ECharts 配色随所选主题动态走；②按创意关键词轻量词表推荐（不调 LLM，
           167 轮正在治慢，不能再加耗时）；③默认「柔和默认」= 白底 + 低饱和点缀（157 轮视觉铁律）。
           跨端一致性：tech 那套就是原来的 CA，与后端 chart_renderer_pro 的 tech 主题 7 色一一对应，
           选它时导出 PNG 与前台完全一致；其它主题的导出一致性要靠后端接 chart_theme 参数
           （前端已把该字段放进导出 payload，后端接线即可生效）。 */
        var WB_CHART_THEME_KEY = 'wbChartThemeV1';
        var WB_CHART_THEMES = {
            soft: {
                label: '柔和默认',
                series: ['#6B9BC3', '#7BB6A6', '#9C8BC4', '#D9A05B', '#8CBF86', '#C98C94', '#A8C47A'],
                bar: ['#8FB8D9', '#5E87B0'], line: '#6B9BC3', area: 'rgba(107,155,195,.18)',
                text: '#5B6B82', axis: 'rgba(91,107,130,.35)', split: 'rgba(91,107,130,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(91,107,130,.22)', '#1F2A3A'],
                bgL: ['rgba(255,255,255,.55)', 'rgba(244,247,252,.72)'],
                bgD: ['rgba(28,34,52,.45)', 'rgba(18,22,38,.58)']
            },
            tech: {
                label: '科技蓝紫',
                // 与后端 chart_renderer_pro 的 tech 主题一致，改这里要同步后端
                series: ['#818CF8', '#22B8CF', '#C084FC', '#F59E0B', '#34D399', '#FB7185', '#A3E635'],
                bar: ['#67e8f9', '#4f46e5'], line: '#c084fc', area: 'rgba(192,132,252,.22)',
                text: '#93a0c4', axis: 'rgba(148,163,255,.35)', split: 'rgba(148,163,255,.12)',
                tip: ['rgba(10,15,43,.92)', 'rgba(148,163,255,.3)', '#e9eefc'],
                bgL: ['rgba(22,28,62,.62)', 'rgba(8,12,32,.78)'],
                bgD: ['rgba(22,28,62,.62)', 'rgba(8,12,32,.78)']
            },
            green: {
                label: '环保绿',
                series: ['#4F9D7C', '#6FAE86', '#8FBF95', '#B0C97F', '#7FB49E', '#9BCE8E', '#C3D59B'],
                bar: ['#7FBBA0', '#3F8C6E'], line: '#4F9D7C', area: 'rgba(79,157,124,.18)',
                text: '#4A6559', axis: 'rgba(74,101,89,.35)', split: 'rgba(74,101,89,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(74,101,89,.22)', '#1E2F28'],
                bgL: ['rgba(247,252,249,.6)', 'rgba(237,245,240,.74)'],
                bgD: ['rgba(22,40,33,.45)', 'rgba(14,26,22,.58)']
            },
            warm: {
                label: '温暖橙',
                series: ['#C2854E', '#D3A15E', '#BF7F63', '#E0B473', '#A9774F', '#CBA97E', '#D98F5B'],
                bar: ['#E0B473', '#C2854E'], line: '#C2854E', area: 'rgba(194,133,78,.18)',
                text: '#6B563F', axis: 'rgba(107,86,63,.35)', split: 'rgba(107,86,63,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(107,86,63,.22)', '#31251A'],
                bgL: ['rgba(255,251,245,.6)', 'rgba(250,242,232,.74)'],
                bgD: ['rgba(42,32,22,.45)', 'rgba(26,20,14,.58)']
            },
            biz: {
                label: '经典商务',
                series: ['#3F6A94', '#5C7E96', '#7A8FA0', '#94776B', '#5E7B6B', '#836C86', '#6C7A8C'],
                bar: ['#5C7E96', '#33526F'], line: '#3F6A94', area: 'rgba(63,106,148,.18)',
                text: '#42505F', axis: 'rgba(66,80,95,.35)', split: 'rgba(66,80,95,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(66,80,95,.22)', '#1C2530'],
                bgL: ['rgba(248,250,252,.6)', 'rgba(240,243,247,.74)'],
                bgD: ['rgba(24,30,42,.45)', 'rgba(16,20,30,.58)']
            }
        };
        function wbChartThemeKey() {
            var v = '';
            try { v = _wbStoreGet(WB_CHART_THEME_KEY) || ''; } catch (e) {}
            return WB_CHART_THEMES[v] ? v : 'soft';
        }
        // 导出 Beijing 也给后端用：打包 zip / PPT 时把主题带过去
        function wbChartTheme() {
            var k = wbChartThemeKey();
            return WB_CHART_THEMES[k] || WB_CHART_THEMES.soft;
        }
        function wbChartIsLight() {
            return !(document.body && document.body.classList.contains('light') === false) ||
                   (document.body && document.body.classList.contains('light'));
        }
        function wbChartPickSet(v) {
            try { _wbStoreSet(WB_CHART_THEME_KEY, WB_CHART_THEMES[v] ? v : 'soft'); } catch (e) {}
        }
        window.wbChartThemeKey = wbChartThemeKey;
        window.wbChartTheme = wbChartTheme;
        window.wbChartThemePick = function (v) {
            wbChartPickSet(v);
            var sel = document.getElementById('chartTheme'); if (sel) sel.value = wbChartThemeKey();
            wbChartThemeHint(v);
            // 已经画出来的图立即换色（不重新生成，只是重绘）
            if (window.__wbDemoChartDraw) { try { window.__wbDemoChartDraw(); } catch (e) {} }
        };
        window.wbChartThemeHint = function (v) {
            var el = document.getElementById('chartThemeHint');
            if (!el) return;
            var t = WB_CHART_THEMES[v] || WB_CHART_THEMES.soft;
            el.textContent = v === 'tech'
                ? '科技蓝紫：深色玻璃底，与导出的图表 PNG 完全同色。'
                : ('已选「' + t.label + '」：白底低饱和，打印/投屏都不刺眼。');
        };
        // 按创意推荐：纯词表匹配，开销可忽略（167 轮正在压耗时，这里不能再加 LLM 调用）
        window.wbChartThemeGuess = function () {
            var txt = '';
            ['idea', 'keywords', 'wbSchool'].forEach(function (id) {
                var e = document.getElementById(id);
                if (e && e.value) txt += ' ' + e.value;
            });
            var comp = document.getElementById('compInput');
            if (comp && comp.value) txt += ' ' + comp.value;
            var RULES = [
                [/(环保|回收|低碳|碳中和|新能源|光伏|储能|节能|农业|种[植养]|养[殖殖]|生态|绿化|垃圾分类|水处理|林业|海洋|可持续)/, 'green'],
                [/(ai|人工智能|算法|大模型|芯片|机器人|智能化|大数据|物联网|算力|视觉识别|自动驾驶|区块链|软件|算法推荐)/i, 'tech'],
                [/(餐饮|文创|文旅|非遗|手作|烘焙|咖啡|茶饮|校园|养老|助农|乡村振兴|公益|志愿|宠物|服饰|非遗传承)/, 'warm'],
                [/(金融|融资|商业|营销|电商|供应链|物流|制造|工业|企业服务|人力|财税|法律|跨境|物流仓储)/, 'biz']
            ];
            var hit = '';
            for (var i = 0; i < RULES.length; i++) { if (RULES[i][0].test(txt)) { hit = RULES[i][1]; break; } }
            if (!hit) hit = 'soft';
            window.wbChartThemePick(hit);
            var t = WB_CHART_THEMES[hit];
            wbToast(hit === 'soft'
                ? '没识别出明显领域，先用柔和默认，你也可以自己换'
                : '按你的创意推荐了「' + t.label + '」配色', { type: 'ok', ms: 2600 });
        };
        (function () {
            var sel = document.getElementById('chartTheme');
            if (sel) sel.value = wbChartThemeKey();
            wbChartThemeHint(wbChartThemeKey());
        })();

        checkHealth();
        // 167 轮：心跳原来是无脑 30s 一次，切后台也在打，白耗移动端电量。
        // 改为「仅页面可见才请求」+ 失败退避（30s→60s→120s，上限 5 分钟），回到前台立刻补一次。
        var _hbBase = 30000, _hbMul = 1;
        setInterval(function () {
            if (document.hidden) return;
            if (!window._wbHealthOk && _hbMul < 10) _hbMul *= 2;   // 连续失败就拉长间隔
            if (Date.now() - (_hbLast || 0) < _hbBase * _hbMul) return;
            _hbLast = Date.now();
            checkHealth();
        }, 15000);
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) return;
            _hbLast = Date.now();
            try { checkHealth(); } catch (e) {}
        });

/* ===== WB UI 增强：粒子背景 + 滚动进场 ===== */
        (function () {
            var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            /* 滚动进场 */
            var targets = document.querySelectorAll('.card, .result-hero, .content-block, .tabs');
            if (reduce || !('IntersectionObserver' in window)) {
                targets.forEach(function (el) { el.classList.add('wb-in'); });
            } else {
                targets.forEach(function (el) {
                    if (!el.closest('#resultArea')) el.classList.add('wb-reveal');
                });
                var io = new IntersectionObserver(function (entries) {
                    entries.forEach(function (e) {
                        if (e.isIntersecting) {
                            e.target.classList.add('wb-in');
                            io.unobserve(e.target);
                        }
                    });
                }, { threshold: 0.06, rootMargin: '0px 0px -40px 0px' });
                targets.forEach(function (el) { io.observe(el); });
            }

            /* 粒子网络背景 */
            if (reduce) return;
            var cv = document.getElementById('wbParticles');
            if (!cv || !cv.getContext) return;
            var ctx = cv.getContext('2d');
            var W = 0, H = 0, dpr = 1, pts = [], raf = null;

            function resize() {
                dpr = Math.min(window.devicePixelRatio || 1, 2);
                W = cv.width = Math.floor(window.innerWidth * dpr);
                H = cv.height = Math.floor(window.innerHeight * dpr);
                cv.style.width = window.innerWidth + 'px';
                cv.style.height = window.innerHeight + 'px';
                var n = Math.max(24, Math.min(64, Math.round(window.innerWidth / 20)));
                pts = [];
                for (var i = 0; i < n; i++) {
                    pts.push({
                        x: Math.random() * W,
                        y: Math.random() * H,
                        vx: (Math.random() - 0.5) * 0.24 * dpr,
                        vy: (Math.random() - 0.5) * 0.24 * dpr,
                        r: (Math.random() * 1.3 + 0.5) * dpr
                    });
                }
            }

            function draw() {
                ctx.clearRect(0, 0, W, H);
                var i, j, p, q, dx, dy, d2;
                var LINK = 132 * dpr;
                for (i = 0; i < pts.length; i++) {
                    p = pts[i];
                    p.x += p.vx; p.y += p.vy;
                    if (p.x < 0 || p.x > W) p.vx *= -1;
                    if (p.y < 0 || p.y > H) p.vy *= -1;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(150,205,255,.55)';
                    ctx.fill();
                    for (j = i + 1; j < pts.length; j++) {
                        q = pts[j];
                        dx = p.x - q.x; dy = p.y - q.y;
                        d2 = dx * dx + dy * dy;
                        if (d2 < LINK * LINK) {
                            ctx.beginPath();
                            ctx.moveTo(p.x, p.y);
                            ctx.lineTo(q.x, q.y);
                            ctx.strokeStyle = 'rgba(110,170,255,' + (0.18 * (1 - Math.sqrt(d2) / LINK)).toFixed(3) + ')';
                            ctx.lineWidth = 0.6 * dpr;
                            ctx.stroke();
                        }
                    }
                }
                raf = requestAnimationFrame(draw);
            }

            function stop() { if (raf) { cancelAnimationFrame(raf); raf = null; } }

            resize();
            window.addEventListener('resize', resize);
            document.addEventListener('visibilitychange', function () {
                if (document.hidden) { stop(); } else { stop(); draw(); }
            });
            draw();
        /* ---------- 提示收敛：长说明收进字段旁的「?」图标 ----------
           评委反馈首页文案过载。原本 5 条长提示常驻，现在只留 1 条在表单顶部，
           其余进 tooltip：点/悬停才出现，不占版面。做成 fixed 浮层而不是 CSS ::after，
           是因为卡片有 overflow:hidden / backdrop-filter，内联气泡会被裁掉 */
        var wbTipBox = null;
        function wbTipEl() {
            if (!wbTipBox) {
                wbTipBox = document.createElement('div');
                wbTipBox.id = 'wbTipBox';
                wbTipBox.style.cssText = 'position:fixed; z-index:3000; display:none; max-width:min(300px,82vw);'
                    + ' padding:10px 12px; background:var(--surface-solid); color:var(--text);'
                    + ' border:1px solid var(--line); border-radius:10px; font-size:12.5px; line-height:1.7;'
                    + ' box-shadow:0 10px 30px rgba(0,0,0,.45); pointer-events:none;';
                document.body.appendChild(wbTipBox);
            }
            return wbTipBox;
        }
        function wbShowTip(el, noToggle) {
            var box = wbTipEl();
            var txt = el ? (el.getAttribute('data-tip') || '') : '';
            if (!txt) return;
            // 再点一次同一个「?」就收起（移动端没有 hover，必须能靠点击关掉）
            if (!noToggle && box.style.display === 'block' && box.dataset.src === String(el.id || '')) { wbHideTip(); return; }
            box.innerHTML = txt;
            box.style.display = 'block';
            box.dataset.src = String(el.id || '');
            var r = el.getBoundingClientRect();
            var bw = box.offsetWidth, bh = box.offsetHeight;
            var left = Math.min(Math.max(8, r.left + r.width / 2 - bw / 2), window.innerWidth - bw - 8);
            var top = r.top - bh - 8;                       // 默认在「?」上方
            if (top < 8) top = r.bottom + 8;                // 上方放不下就翻到下方
            // 钳进视口：元素在页面靠下时（实测 top 算到 1091px、视口才 905）气泡会飘出屏幕
            top = Math.max(8, Math.min(top, window.innerHeight - bh - 8));
            box.style.left = left + 'px';
            box.style.top = top + 'px';
        }
        function wbHideTip() {
            if (wbTipBox) { wbTipBox.style.display = 'none'; wbTipBox.dataset.src = ''; }
        }
        window.wbShowTip = wbShowTip;
        window.wbHideTip = wbHideTip;
        (function () {
            var tips = document.querySelectorAll('.wb-tip');
            for (var i = 0; i < tips.length; i++) {
                (function (el) {
                    el.addEventListener('mouseenter', function () { wbShowTip(el, true); });
                    el.addEventListener('mouseleave', function () { wbHideTip(); });
                })(tips[i]);
            }
            document.addEventListener('click', function (e) {
                if (e && e.target && e.target.classList && e.target.classList.contains('wb-tip')) return;
                wbHideTip();
            });
            window.addEventListener('resize', wbHideTip);
            window.addEventListener('scroll', wbHideTip, true);
        })();

        // 打包按钮旁的「▾」菜单（导出入口去重后，分项下载 / PPT 主题收在这里）
        function wbExpMenuToggle() {
            var m = document.getElementById('wbExpMenu');
            if (!m) return;
            m.style.display = (m.style.display === 'block') ? 'none' : 'block';
        }
        window.wbExpMenuToggle = wbExpMenuToggle;
        document.addEventListener('click', function (e) {
            var m = document.getElementById('wbExpMenu');
            if (!m) return;
            var wrap = m.parentNode;
            if (wrap && wrap.contains(e.target)) return;
            m.style.display = 'none';
        });

        /* ---------- 自定义背景：本机上传 + 官方预设库 ----------
           合规边界：图片只存本机 IndexedDB，绝不上传服务器、不做公共素材库
           （公共库等于平台再分发他人作品，著作权/肖像权风险由平台承担）。
           预设全部为程序化生成的渐变/几何纹理，无 IP、无真人、无 Logo。 */
        /* img 只放 gradient（background-image）、color 单独放（background-color）。
           别再把两者拼成一条塞进 background-image：末尾那个纯色会让整条声明非法，
           浏览器直接丢弃 → 背景层 backgroundImage 变 none，点了跟没点一样。 */
        var WB_BG_PRESETS = [
            /* 极光的青+紫和默认底色的光晕撞色，所以绿色那团加重并上移到首屏可见处，
               否则切了看不出区别（实测顶部带色差只有 3.5，跟噪声基线差不多） */
            { id: 'aurora', name: '极光', color: '#070b18', img: 'radial-gradient(1200px 700px at 12% 26%, rgba(56,189,248,.46), transparent 60%), radial-gradient(900px 620px at 82% 16%, rgba(168,85,247,.38), transparent 62%), radial-gradient(1000px 760px at 58% 72%, rgba(52,211,153,.36), transparent 66%)' },
            { id: 'nebula', name: '星云', color: '', img: 'radial-gradient(900px 620px at 78% 22%, rgba(244,114,182,.34), transparent 62%), radial-gradient(1100px 700px at 20% 78%, rgba(59,130,246,.34), transparent 64%), linear-gradient(160deg, #0a0f22, #120b24)' },
            { id: 'ocean', name: '深海', color: '', img: 'radial-gradient(1000px 700px at 50% 0%, rgba(20,184,166,.34), transparent 62%), radial-gradient(900px 700px at 10% 90%, rgba(37,99,235,.30), transparent 66%), linear-gradient(180deg, #04121f, #061a2c)' },
            { id: 'ember', name: '熔岩', color: '', img: 'radial-gradient(900px 620px at 20% 20%, rgba(249,115,22,.32), transparent 60%), radial-gradient(1000px 700px at 80% 80%, rgba(190,24,93,.30), transparent 64%), linear-gradient(160deg, #150a10, #1c0f0a)' },
            { id: 'ink', name: '水墨', color: '', img: 'radial-gradient(1000px 700px at 30% 30%, rgba(148,163,184,.26), transparent 62%), radial-gradient(800px 600px at 75% 70%, rgba(71,85,105,.30), transparent 64%), linear-gradient(180deg, #0b0e14, #10141c)' },
            { id: 'cyber', name: '赛博', color: '', img: 'radial-gradient(900px 600px at 15% 80%, rgba(34,211,238,.34), transparent 60%), radial-gradient(900px 600px at 85% 20%, rgba(217,70,239,.30), transparent 62%), linear-gradient(150deg, #0a0716, #131024)' },
            { id: 'forest', name: '林雾', color: '', img: 'radial-gradient(1000px 700px at 60% 20%, rgba(74,222,128,.26), transparent 62%), radial-gradient(900px 700px at 20% 85%, rgba(21,94,117,.30), transparent 66%), linear-gradient(180deg, #07130f, #0a1712)' },
            { id: 'plain', name: '纯净', color: '', img: 'linear-gradient(180deg, #080b14, #0d1220)' }
        ];
        var WB_BG_KEY = 'wb_bg_cfg_v1';
        var wbBgLayer = null, wbBgUserUrl = null;
        function wbBgLayerEl() {
            if (!wbBgLayer) {
                wbBgLayer = document.createElement('div');
                wbBgLayer.id = 'wbUserBg';
                // 必须挂进 .wb-bg 内部：.wb-bg 是 position:fixed + z-index:0 且底色不透明
                // （linear-gradient(180deg,#050816…)）。之前它是 body 下 z-index:-1 的独立层，
                // 按 CSS 绘制顺序 z-index:0 的定位元素盖在 -1 之上，等于永远看不见。
                // 放进 .wb-bg 并插在最前面 → 位于底色之上、网格/光球之下，压暗层 ::after 照常生效。
                wbBgLayer.style.cssText = 'position:absolute; inset:-40px; pointer-events:none;'
                    + ' background-size:cover; background-position:center; transition:opacity .45s ease;';
                var host = document.querySelector('.wb-bg');
                if (host) host.insertBefore(wbBgLayer, host.firstChild);
                else {
                    // .wb-bg 不存在时退回独立层（此时没有不透明层遮挡，-1 也看得见）
                    wbBgLayer.style.position = 'fixed';
                    wbBgLayer.style.zIndex = '-1';
                    document.body.insertBefore(wbBgLayer, document.body.firstChild);
                }
            }
            return wbBgLayer;
        }
        function wbBgLoadCfg() {
            try { return JSON.parse(_wbStoreGet(WB_BG_KEY) || 'null') || {}; } catch (e) { return {}; }
        }
        function wbBgSaveCfg(c) {
            try { _wbStoreSet(WB_BG_KEY, JSON.stringify(c || {})); } catch (e) {}
        }
        // IndexedDB 存 Blob：localStorage 只有 5MB 且只能存字符串，塞不下图片
        function wbBgDb() {
            return new Promise(function (res, rej) {
                try {
                    var rq = indexedDB.open('wb_bg_db', 1);
                    rq.onupgradeneeded = function () {
                        var db = rq.result;
                        if (!db.objectStoreNames.contains('img')) db.createObjectStore('img');
                    };
                    rq.onsuccess = function () { res(rq.result); };
                    rq.onerror = function () { rej(rq.error || new Error('IndexedDB 打开失败')); };
                } catch (e) { rej(e); }
            });
        }
        function wbBgPut(blob) {
            return wbBgDb().then(function (db) {
                return new Promise(function (res, rej) {
                    var tx = db.transaction('img', 'readwrite');
                    tx.objectStore('img').put(blob, 'current');
                    tx.oncomplete = function () { res(true); };
                    tx.onerror = function () { rej(tx.error); };
                });
            });
        }
        function wbBgGet() {
            return wbBgDb().then(function (db) {
                return new Promise(function (res) {
                    var rq = db.transaction('img', 'readonly').objectStore('img').get('current');
                    rq.onsuccess = function () { res(rq.result || null); };
                    rq.onerror = function () { res(null); };
                });
            }).catch(function () { return null; });
        }
        function wbBgApply(cfg) {
            var L = wbBgLayerEl();
            // 0.45：用户图 brightness≈0.66。原先 0.55（brightness 0.59）把上传的图压得太灰，
            // 用户会以为「图坏了」；嫌亮/嫌暗都可以拖面板里的压暗滑块
            var dim = cfg && typeof cfg.dim === 'number' ? cfg.dim : 0.45;
            var blur = cfg && typeof cfg.blur === 'number' ? cfg.blur : 0;
            var img = cfg && cfg.src === 'user' ? wbBgUserUrl : null;
            var preset = null;
            for (var i = 0; i < WB_BG_PRESETS.length; i++) if (WB_BG_PRESETS[i].id === (cfg && cfg.src)) preset = WB_BG_PRESETS[i];
            if (img) {
                L.style.backgroundImage = 'url(' + img + ')';
                L.style.filter = 'blur(' + blur + 'px) brightness(' + (1 - dim * 0.75).toFixed(2) + ')';
                L.style.opacity = '1';
            } else if (preset) {
                // 分两条设置：image 只能是 gradient，color 单独走 background-color
                L.style.backgroundImage = preset.img || 'none';
                L.style.backgroundColor = preset.color || 'transparent';
                // 预设本身是低饱和深色，压暗系数比用户图片轻一档（0.45 vs 0.75），
                // 否则切了跟没切一样；嫌亮可以拖面板里的压暗滑块
                L.style.filter = 'blur(' + blur + 'px) brightness(' + (1 - dim * 0.45).toFixed(2) + ')';
                L.style.opacity = '1';
            } else {
                L.style.opacity = '0';   // 默认：交回原生背景
            }
            wbBgSaveCfg(cfg || {});
        }
        function wbBgPick(id) {
            // 没图却点了「我的图片」（如清过浏览器数据）：别把背景切成一片空
            if (id === 'user' && !wbBgUserUrl) {
                if (window.wbToast) wbToast('还没有上传过图片，先点「上传我的图片」', { type: 'warn' });
                return;
            }
            var cfg = wbBgLoadCfg();
            cfg.src = id;
            wbBgApply(cfg);
            wbBgRenderSwatches();   // 选中框跟着走
            if (window.wbToast) wbToast('背景已切换：' + (id === 'user' ? '我的图片' : (WB_BG_PRESETS.filter(function (p) { return p.id === id; })[0] || {}).name || id), { type: 'ok' });
            wbBgPanelClose();   // 切完背景自动收起，不用再去找 ×
        }
        function wbBgUpload(input) {
            var f = input && input.files && input.files[0];
            if (!f) return;
            if (!/^image\//.test(f.type)) { if (window.wbToast) wbToast('请选择图片文件', { type: 'error' }); return; }
            var ok = window.confirm('这张图只保存在你本机浏览器里，不会上传到服务器。\n请确认它是你自己拍摄 / 自己生成 / 已获授权的图片。');
            if (!ok) { input.value = ''; return; }
            var img = new Image();
            var url = URL.createObjectURL(f);
            img.onload = function () {
                // 压到长边 1600、转 JPEG：原图动辄 5~10MB，塞 IndexedDB 会拖慢首屏
                var max = 1600, w = img.width, h = img.height;
                var s = Math.min(1, max / Math.max(w, h));
                var cv = document.createElement('canvas');
                cv.width = Math.round(w * s); cv.height = Math.round(h * s);
                cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
                URL.revokeObjectURL(url);
                cv.toBlob(function (blob) {
                    if (!blob) { if (window.wbToast) wbToast('图片处理失败', { type: 'error' }); return; }
                    wbBgPut(blob).then(function () {
                        if (wbBgUserUrl) { try { URL.revokeObjectURL(wbBgUserUrl); } catch (e) {} }
                        wbBgUserUrl = URL.createObjectURL(blob);
                        var cfg = wbBgLoadCfg(); cfg.src = 'user';
                        wbBgApply(cfg);
                        wbBgRenderSwatches();   // 让「我的图片」卡出现（上传前它没有图可用）
                        input.value = '';       // 清空，否则再选同一个文件不触发 change
                        if (window.wbToast) wbToast('背景已应用（仅本机保存）', { type: 'ok' });
                        wbBgPanelClose();   // 上传即应用，同样自动收起
                    }).catch(function () {
                        // 私密模式/老内核没有 IndexedDB：退回本次会话内可用的 blob URL，刷新后失效但不报错
                        wbBgUserUrl = URL.createObjectURL(blob);
                        var c2 = wbBgLoadCfg(); c2.src = 'user'; c2.dim = c2.dim || 0.45;
                        wbBgApply(c2);
                        wbBgRenderSwatches();
                        input.value = '';
                        if (window.wbToast) wbToast('已应用，但本浏览器不允许长期保存，刷新后会恢复默认', { type: 'warn' });
                        wbBgPanelClose();
                    });
                }, 'image/jpeg', 0.82);
            };
            img.onerror = function () { if (window.wbToast) wbToast('图片读取失败', { type: 'error' }); };
            img.src = url;
        }
        function wbBgReset() {
            var cfg = wbBgLoadCfg();
            cfg.src = '';
            wbBgApply(cfg);
            if (window.wbToast) wbToast('已恢复默认背景', { type: 'ok' });
        }
        function wbBgSetDim(v) { var c = wbBgLoadCfg(); c.dim = parseFloat(v); wbBgApply(c); }
        function wbBgPanelToggle() {
            // 首次访问的引导遮罩（#wbCoachVeil，z-index 1500）还在时，点开的面板会躺在遮罩下面，
            // 用户看到的就是「点了背景没反应」。既然用户已经在主动用页面了，引导就该让位。
            try {
                if (typeof coachEnd === 'function') coachEnd(); // 无条件收引导：veil 有 380ms 创建延迟，只查 veil 会漏掉窗口期
            } catch (e) {}
            var p = document.getElementById('wbBgPanel');
            if (!p) return;
            if (p.style.display === 'block') { p.style.display = 'none'; return; }
            // 打开前补一次渲染：启动那次若因任何原因没跑到（脚本报错/时序），
            // 面板会展开成一块空的壳子，用户就以为「点了没反应」——这里兜住
            try {
                if (!document.getElementById('wbBgSwatches').children.length) wbBgRenderSwatches();
            } catch (e) {}
            p.style.display = 'block';
        }
        // 面板关闭：× 按钮、切完背景自动收起、点面板外，三条路都走这里
        function wbBgPanelClose() { var p = document.getElementById('wbBgPanel'); if (p) p.style.display = 'none'; }
        window.wbBgPick = wbBgPick;
        window.wbBgUpload = wbBgUpload;
        window.wbBgReset = wbBgReset;
        window.wbBgSetDim = wbBgSetDim;
        window.wbBgPanelToggle = wbBgPanelToggle;
        window.wbBgPanelClose = wbBgPanelClose;

        /* ---- 顶部「更多 ▾」下拉（第一百四十二 / 第一百四十七轮催办）----
           顶部原来并排四个按钮（使用说明 / 历史 / 背景 / 反馈），其中「背景」是低频装饰项，
           和「使用说明、历史」这些真正常用的入口平级占一个位置，既冗杂又容易误点。
           现在收进「更多」下拉，顶部主按钮由 4 个降到 3 个。
           关闭策略：点菜单内任意项即关；点页面别处也关（这里单独监听，
           不复用赛事下拉那个监听器，避免两条逻辑互相干扰）。 */
        function wbMoreClose() {
            var m = document.getElementById('wbMoreMenu');
            var b = document.getElementById('wbMoreBtn');
            if (m) m.style.display = 'none';
            if (b) b.setAttribute('aria-expanded', 'false');
        }
        function wbMoreToggle(e) {
            if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
            var m = document.getElementById('wbMoreMenu');
            var b = document.getElementById('wbMoreBtn');
            if (!m) return;
            var open = (m.style.display === 'block');
            if (open) { wbMoreClose(); return; }
            m.style.display = 'block';
            if (b) b.setAttribute('aria-expanded', 'true');
        }
        window.wbMoreToggle = wbMoreToggle;
        window.wbMoreClose = wbMoreClose;
        document.addEventListener('click', function (e) {
            var m = document.getElementById('wbMoreMenu');
            if (!m || m.style.display !== 'block') return;
            var w = document.getElementById('wbMoreWrap');
            if (w && w.contains(e.target)) return;   // 点按钮或菜单内部都不关（菜单项自己会关）
            wbMoreClose();
        });
        // 背景面板：点面板外自动收起。豁免面板内部（点了不该关）和 #wbMoreWrap
        //（打开入口在「更多」下拉里，同一次点击先 toggle 展开再冒泡到这里，不豁免会秒开秒关）
        document.addEventListener('click', function (e) {
            var p = document.getElementById('wbBgPanel');
            if (!p || p.style.display !== 'block') return;
            var t = e.target;
            if (t && t.closest && (p.contains(t) || t.closest('#wbMoreWrap'))) return;
            wbBgPanelClose();
        });
        // 色卡预览用 background 简写（最后一层可以带 color），但应用时拆成两条
        function wbBgCss(p) {
            return (p.img || '') + (p.color ? ((p.img ? ', ' : '') + p.color) : '');
        }
        function wbBgRenderSwatches() {
            var box = document.getElementById('wbBgSwatches');
            if (!box) return;
            var cur = (wbBgLoadCfg() || {}).src || '';
            var html = '';
            // 「我的图片」：上传过就显示缩略图并可一键切回（之前没有这个入口，
            // 用户一旦切到预设就再也切不回自己那张图，只能重新上传）；
            // 没上传过时点它直接唤起选择框
            var hasUser = !!wbBgUserUrl;
            var onUser = (cur === 'user');
            html += '<div onclick="' + (hasUser ? 'wbBgPick(\'user\')' : 'document.getElementById(\'wbBgFileInput\').click()') + '"'
                + ' title="' + (hasUser ? '我的图片' : '点击上传我的图片') + '"'
                + ' style="cursor: pointer; border-radius: 8px; overflow: hidden; border: 2px solid '
                + (onUser ? 'var(--c-a)' : 'var(--line)') + ';">'
                + '<div style="height: 38px; background: ' + (hasUser ? 'url(' + wbBgUserUrl + ') center/cover no-repeat, ' : '') + 'var(--surface-solid);'
                + ' display: flex; align-items: center; justify-content: center; color: var(--text-mute); font-size: 17px;">'
                + (hasUser ? '' : '＋') + '</div>'
                + '<div style="padding: 3px 0; text-align: center; font-size: 11.5px; background: var(--surface-solid); color: '
                + (onUser ? 'var(--c-a)' : 'var(--text-dim)') + ';">我的图片</div></div>';
            WB_BG_PRESETS.forEach(function (p) {
                var on = (cur === p.id);
                html += '<div onclick="wbBgPick(\'' + p.id + '\')" title="' + p.name + '"'
                    + ' style="cursor: pointer; border-radius: 8px; overflow: hidden; border: 2px solid '
                    + (on ? 'var(--c-a)' : 'var(--line)') + ';">'
                    + '<div style="height: 38px; background: ' + wbBgCss(p) + ';"></div>'
                    + '<div style="padding: 3px 0; text-align: center; font-size: 11.5px; background: var(--surface-solid); color: '
                    + (on ? 'var(--c-a)' : 'var(--text-dim)') + ';">' + p.name + '</div></div>';
            });
            box.innerHTML = html;
        }
        window.wbBgRenderSwatches = wbBgRenderSwatches;
        // 启动时恢复上次选择（读取失败就静默用默认背景，绝不留白屏）
        (function () {
            try {
                wbBgRenderSwatches();
                var cfg = wbBgLoadCfg();
                if (!cfg || !cfg.src) return;
                if (cfg.src === 'user') {
                    wbBgGet().then(function (blob) {
                        if (!blob) {
                            // 配置还在但图片没了（清过浏览器数据 / 换了浏览器）：
                            // 别让「我的图片」一直指向一个不存在的背景
                            var c = wbBgLoadCfg();
                            delete c.src;
                            wbBgSaveCfg(c);
                            wbBgRenderSwatches();
                            return;
                        }
                        wbBgUserUrl = URL.createObjectURL(blob);
                        wbBgApply(cfg);
                        wbBgRenderSwatches();   // 图读回来了，「我的图片」卡才显示缩略图
                    });
                } else {
                    wbBgApply(cfg);
                }
            } catch (e) {}
        })();

        /* ===== 第一百零八轮·106-2：正文重点数字高亮 =====
           用户反馈运营测算/商业模式里的关键数字（21.6万/72万/10%/1.5元…）不显眼。
           只在展示层加亮：TreeWalker 找文本节点，把「数字+单位」包进 .wb-keynum。
           铁律：绝不改 markdown 源文本 —— 导出件取的是原文，不会把高亮带进材料。
           幂等：已在 .wb-keynum / 链接 / 代码里的文本跳过，不会越包越厚；
           MutationObserver（350ms 防抖）覆盖流式打字机、历史回看、一键修正等所有重渲染路径。 */
        var WB_HL_IDS = ['proposalText', 'judgeFeedback', 'proposalAnalysis', 'competitorAnalysis',
            'businessModel', 'riskAnalysis', 'techSolution', 'implementationPlan',
            'socialValue', 'projectSummary', 'defenseQuestions', 'pptOutline', 'speechScript'];
        // 长单位放前面，避免「万元」被「万」截走；不收「年/月」裸单位，免得「2026年」「3月」全变重点
        var WB_NUM_SRC = '\\d+(?:\\.\\d+)?\\s*(?:万元|亿元|万人次|个百分点|万人|万|亿|元|%|％|倍|台|套|家|份|件|天|个月|kg|公里)';

        function wbHlNumbersIn(root) {
            if (!root) return;
            var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
                acceptNode: function (n) {
                    if (!n.nodeValue || n.nodeValue.length < 2) return NodeFilter.FILTER_REJECT;
                    var p = n.parentElement;
                    if (p && (p.closest('.wb-keynum') || p.closest('a,script,style,code,pre,textarea'))) return NodeFilter.FILTER_REJECT;
                    var re = new RegExp(WB_NUM_SRC);
                    return re.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                }
            });
            var nodes = [], n;
            while ((n = walker.nextNode())) nodes.push(n);
            nodes.forEach(function (node) {
                var txt = node.nodeValue;
                var re = new RegExp(WB_NUM_SRC, 'g');
                var frag = document.createDocumentFragment(), last = 0, m, hit = false;
                while ((m = re.exec(txt))) {
                    if (m.index > last) frag.appendChild(document.createTextNode(txt.slice(last, m.index)));
                    var span = document.createElement('span');
                    span.className = 'wb-keynum';
                    span.textContent = m[0].replace(/\s+$/, '');
                    frag.appendChild(span);
                    last = m.index + m[0].length;
                    hit = true;
                }
                if (hit) {
                    if (last < txt.length) frag.appendChild(document.createTextNode(txt.slice(last)));
                    node.parentNode.replaceChild(frag, node);
                }
            });
        }

        function wbHlAll() {
            WB_HL_IDS.forEach(function (id) {
                try { wbHlNumbersIn(document.getElementById(id)); } catch (e) {}
            });
        }
        window.wbHlAll = wbHlAll;

        (function wbHlObserve() {
            var t = null;
            function schedule() {
                if (t) return;
                t = setTimeout(function () { t = null; try { wbHlAll(); } catch (e) {} }, 350);
            }
            function bind() {
                WB_HL_IDS.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (!el || el.__wbHlObs) return;
                    el.__wbHlObs = true;
                    new MutationObserver(schedule).observe(el, { childList: true, subtree: true });
                });
            }
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
            else bind();
        })();

        /* ---------- 170 轮（WorkBuddy 半边）：结果区相邻重复段落去重兜底 ----------
           豆包实测：评委意见「需要改进的地方」重复显示 2 次、作品说明书「四、评审建议」重复 2 次。
           根因在后端重复拼接，但前端不能只指望对方修——这里是第二道防线：
           渲染成 HTML 后，凡是与上一段文本完全相同的相邻块，只保留第一份。 */
        function wbDedupeHtml(html) {
            var box = document.createElement('div');
            box.innerHTML = html;
            var kids = Array.prototype.slice.call(box.children);
            if (kids.length < 2) return html;
            var prevKey = '', kill = [];
            kids.forEach(function (el) {
                var key = String(el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!key) return;
                if (key === prevKey) { kill.push(el); return; }
                prevKey = key;
            });
            kill.forEach(function (el) { if (el.parentNode) el.parentNode.removeChild(el); });
            return kill.length ? box.innerHTML : html;
        }
        // 全站 Markdown 渲染统一入口（原来散落 16 处 marked.parse，现已全部收编到这里）
        // 417 轮：所有生成文档（说明书/各分析报告/PPT 大纲/答辩问题）底部统一一行声明。
        // 措辞与后端导出件完全同一套（app.py 的 AI_NOTICE_LINE），网页与导出件不许两套口径。
        // 禁用「AI」字样，也不写「本内容由AI生成」这类生硬句子。
        var WB_ASSIST_NOTE = '本材料由智能助手辅助起草，已按官方要求排版，请以团队真实情况核对补充后提交';
        function wbRenderMD(s) {
            var html;
            try { html = marked.parse(s == null ? '' : String(s)); }
            catch (e) { html = String(s == null ? '' : s).replace(/\n/g, '<br>'); }
            html = wbDedupeHtml(html);
            // marked 输出的裸 <table> 没有横滑包裹，宽表会撑破正文；
            // 统一包 .rich-table-wrap（overflow-x:auto）并补 rich-table 类，与结果区表格同一套样式
            html = html.replace(/<table>/g, '<div class="rich-table-wrap"><table class="rich-table">')
                       .replace(/<\/table>/g, '</table></div>');
            if (html && String(html).trim()) {
                html += '<p class="wb-assist-note">' + WB_ASSIST_NOTE + '</p>';
            }
            return html;
        }
        window.wbRenderMD = wbRenderMD;

        })();
