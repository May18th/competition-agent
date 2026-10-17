/* 科创赛事助手 — PWA 注册与安装引导（366 轮）
 *
 * 职责：
 *   1. 注册 Service Worker（仅 https / localhost，失败全静默，绝不影响页面）
 *   2. beforeinstallprompt → 顶部小横幅「安装到主屏幕」，可关闭，关闭后不再打扰
 *   3. online/offline → 顶部小横幅提示「联网后可继续生成与导出」
 *
 * 纪律：
 *   - 不自动弹窗、不自动 reload（避免打断正在进行的生成流程）
 *   - 不修改任何已有 DOM 结构，只在 body 末尾追加自有节点
 *   - 不写入任何已有 CSS 文件，样式自带（内联 style 标签）
 */
(function () {
  'use strict';

  var SW_CANDIDATES = [
    { url: '/sw.js', scope: '/' },          // 首选：根路径（需服务端提供该路由）
    { url: '/static/sw.js', scope: '/' }    // 备选：需服务端返回 Service-Worker-Allowed: /
  ];
  var DISMISS_KEY = 'wb_pwa_install_dismissed';

  function safe(fn) {
    try { return fn(); } catch (e) { return undefined; }
  }

  function canRegister() {
    if (!('serviceWorker' in navigator)) return false;
    if (location.protocol === 'https:') return true;
    var h = location.hostname;
    return (h === 'localhost' || h === '127.0.0.1');
  }

  /* ---------------- 1. 注册 Service Worker ---------------- */
  function registerSW() {
    if (!canRegister()) return;
    var i = 0;
    function attempt() {
      if (i >= SW_CANDIDATES.length) return;
      var c = SW_CANDIDATES[i];
      i += 1;
      navigator.serviceWorker.register(c.url, { scope: c.scope })
        .then(function (reg) {
          // 注册成功：静默检查更新，不自动 reload
          safe(function () {
            if (reg && reg.update) reg.update();
          });
        })
        .catch(function () {
          attempt(); // 换下一个候选地址；都失败则彻底静默
        });
    }
    attempt();
  }

  /* ---------------- 2. 顶部横幅 UI ---------------- */
  var barHost = null;
  var installBar = null;
  var offlineBar = null;

  function injectStyle() {
    if (document.getElementById('wbPwaStyle')) return;
    // 402 轮对比度基线：配色全部走主题变量（带 fallback，主题 token 未注入时也不至于透明），
    // 圆角 8-10px；文字一律用 --text / --warn-text，保证日间夜间双端都满足 WCAG AA。
    var css = [
      '#wbPwaHost{position:fixed;top:12px;left:50%;transform:translateX(-50%);',
      'z-index:9998;display:flex;flex-direction:column;gap:8px;align-items:center;',
      'max-width:min(94vw,720px);pointer-events:none;}',
      '#wbPwaHost .wb-pwa-bar{pointer-events:auto;display:none;align-items:center;gap:10px;',
      'box-sizing:border-box;width:100%;padding:10px 12px;',
      'border-radius:var(--radius-sm,10px);font-size:14px;line-height:1.5;',
      'color:var(--text,#c9d2ea);background:var(--surface-solid,#0d1330);',
      'border:1px solid var(--line-strong,rgba(125,211,252,.40));',
      'box-shadow:0 6px 20px rgba(0,0,0,.18);}',
      '#wbPwaHost .wb-pwa-bar.wb-pwa-show{display:flex;}',
      '#wbPwaHost .wb-pwa-txt{flex:1;min-width:0;color:var(--text,#c9d2ea);}',
      '#wbPwaHost .wb-pwa-btn{flex:none;cursor:pointer;padding:7px 14px;',
      'border-radius:var(--radius-sm,10px);font-size:14px;font-weight:600;white-space:nowrap;',
      'border:1px solid var(--c-a,#38bdf8);',
      'background:var(--btn-ghost,rgba(255,255,255,.08));color:var(--text,#c9d2ea);}',
      '#wbPwaHost .wb-pwa-btn:hover{border-color:var(--c-b,#2dd4bf);}',
      '#wbPwaHost .wb-pwa-close{flex:none;border:0;background:transparent;cursor:pointer;',
      'font-size:18px;line-height:1;padding:2px 6px;color:var(--text-dim,#a9b7d9);}',
      '#wbPwaHost .wb-pwa-off{background:var(--warn-bg,rgba(251,191,36,.12));',
      'border-color:var(--warn-line,rgba(251,191,36,.38));color:var(--warn-text,#fde68a);}',
      '#wbPwaHost .wb-pwa-off .wb-pwa-txt{color:var(--warn-text,#fde68a);}',
      '#wbPwaHost .wb-pwa-off .wb-pwa-close{color:var(--warn-text,#fde68a);}'
    ].join('');
    var st = document.createElement('style');
    st.id = 'wbPwaStyle';
    st.type = 'text/css';
    st.appendChild(document.createTextNode(css));
    safe(function () { document.head.appendChild(st); });
  }

  function buildUI() {
    if (barHost || !document.body) return;
    injectStyle();
    var host = document.createElement('div');
    host.id = 'wbPwaHost';

    installBar = document.createElement('div');
    installBar.className = 'wb-pwa-bar';
    installBar.innerHTML =
      '<span class="wb-pwa-txt">把本工具装到主屏幕，断网也能打开演示样例。</span>' +
      '<button type="button" class="wb-pwa-btn" id="wbPwaInstallBtn">安装到主屏幕</button>' +
      '<button type="button" class="wb-pwa-close" aria-label="关闭">×</button>';

    offlineBar = document.createElement('div');
    offlineBar.className = 'wb-pwa-bar wb-pwa-off';
    offlineBar.innerHTML =
      '<span class="wb-pwa-txt">当前处于离线状态，联网后可继续生成与导出。</span>' +
      '<button type="button" class="wb-pwa-close" aria-label="关闭">×</button>';

    host.appendChild(installBar);
    host.appendChild(offlineBar);
    document.body.appendChild(host);
    barHost = host;

    var ibtn = document.getElementById('wbPwaInstallBtn');
    if (ibtn) {
      ibtn.addEventListener('click', function () {
        doInstall();
      });
    }
    var closes = host.querySelectorAll('.wb-pwa-close');
    for (var i = 0; i < closes.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var bar = btn.parentNode;
          if (bar === installBar) {
            safe(function () { localStorage.setItem(DISMISS_KEY, '1'); });
            deferredPrompt = null;
          }
          if (bar && bar.className) bar.className = bar.className.replace(' wb-pwa-show', '');
        });
      })(closes[i]);
    }
  }

  function showBar(el) {
    if (!el) return;
    if (el.className.indexOf('wb-pwa-show') === -1) el.className += ' wb-pwa-show';
  }

  function hideBar(el) {
    if (!el) return;
    el.className = el.className.replace(' wb-pwa-show', '');
  }

  /* ---------------- 3. 安装引导 ---------------- */
  var deferredPrompt = null;

  function isInstalled() {
    try {
      if (window.navigator.standalone === true) return true;
      if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
    } catch (e) { /* ignore */ }
    return false;
  }

  function dismissed() {
    var v = safe(function () { return localStorage.getItem(DISMISS_KEY); });
    return v === '1';
  }

  function doInstall() {
    if (!deferredPrompt) {
      hideBar(installBar);
      return;
    }
    var p = deferredPrompt;
    deferredPrompt = null;
    hideBar(installBar);
    try {
      p.prompt();
      p.userChoice.then(function (choice) {
        if (choice && choice.outcome === 'accepted') {
          safe(function () { localStorage.setItem(DISMISS_KEY, '1'); });
        }
      }).catch(function () { /* ignore */ });
    } catch (e) { /* ignore */ }
  }

  safe(function () {
    window.addEventListener('beforeinstallprompt', function (e) {
      try { e.preventDefault(); } catch (err) { /* ignore */ }
      deferredPrompt = e;
      if (isInstalled() || dismissed()) return;
      buildUI();
      showBar(installBar);
    });
  });

  safe(function () {
    window.addEventListener('appinstalled', function () {
      deferredPrompt = null;
      safe(function () { localStorage.setItem(DISMISS_KEY, '1'); });
      hideBar(installBar);
    });
  });

  /* ---------------- 4. 网络状态 ---------------- */
  function refreshNetState() {
    var offline = safe(function () { return navigator.onLine === false; });
    if (offline) {
      buildUI();
      showBar(offlineBar);
    } else {
      hideBar(offlineBar);
    }
  }

  safe(function () { window.addEventListener('offline', refreshNetState); });
  safe(function () { window.addEventListener('online', refreshNetState); });

  /* ---------------- 启动 ---------------- */
  function boot() {
    registerSW();
    buildUI();
    refreshNetState();
    // 已安装或用户关过，就不再展示安装横幅
    if (isInstalled() || dismissed()) hideBar(installBar);
  }

  if (document.readyState === 'loading') {
    safe(function () {
      document.addEventListener('DOMContentLoaded', function () {
        safe(function () { boot(); });
      });
    });
  } else {
    safe(function () { boot(); });
  }

  safe(function () {
    window.addEventListener('load', function () {
      // 兜底：load 后再确认一次（body 一定存在）
      safe(function () { buildUI(); refreshNetState(); });
    });
  });

  // 对外只暴露只读状态，便于排查，不提供任何副作用接口
  safe(function () {
    window.WBPWA = {
      check: function () {
        return {
          swSupported: 'serviceWorker' in navigator,
          installable: !!deferredPrompt,
          installed: isInstalled(),
          offline: navigator.onLine === false
        };
      }
    };
  });
})();
