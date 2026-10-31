/* 科创赛事助手 Service Worker（366 轮：离线安装 / 断网演示兜底）
 *
 * 设计原则：任何一步出错都必须退化为「不拦截」，绝不能让站点变砖。
 *
 * 拦截范围（只这三类，其余一律 return 交给浏览器默认网络）：
 *   1. 导航请求（HTML 页面）      → network-first，失败回落缓存的首页壳，防白屏
 *   2. /static/ 下静态资源        → cache-first + 后台异步更新
 *   3. 只读 GET 接口白名单        → network-first，成功写缓存，离线时回读
 *
 * 绝不缓存：
 *   - 非 GET 请求（/api/generate_async 等写接口天然不受影响）
 *   - /api/status、/api/stream、/api/speech_stream 等实时进度接口
 *   - /api/history 等按用户隔离的私有数据（防共享机器串号）
 *   - /admin /monitor /share /generated 后台与分享页
 */

// ===================== 版本号：每次发版必须改这里 =====================
var BUILD = '20261031b';
var SHELL_CACHE = 'wb-shell-' + BUILD;
var DATA_CACHE = 'wb-data-' + BUILD;
// ====================================================================

var OFFLINE_URL = '/';
var SHELL_MAX = 90;
var DATA_MAX = 40;

// 预缓存：页面壳 + 主要静态资源（不带 ?v= 版本号，运行时用 ignoreSearch 匹配）
var PRECACHE_SHELL = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/chat-panel.js',
  '/static/ui-const.js',
  '/static/defense-panel.js',
  '/static/demo-panel.css',
  '/static/demo-panel.js',
  '/static/kb-panel.js',
  '/static/section-nav.js',
  '/static/page-enhance.js',
  '/static/smart-bar.css',
  '/static/smart-bar.js',
  '/static/steps.css',
  '/static/sync-panel.js',
  '/static/btn-base.css',
  '/static/btn-result.css',
  '/static/btn-admin.css',
  '/static/floating-btn.css',
  '/static/layout-fix.css',
  '/static/tools-bar.css',
  '/static/pwa.js',
  '/static/marked.min.js',
  '/static/purify.min.js',
  '/static/echarts.min.js',
  '/static/logo.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-180.png',
  '/static/icon-maskable-512.png',
  '/static/favicon.ico'
];

// 预缓存：演示样例（离线讲解必备）
var PRECACHE_DEMO = [
  '/api/demo/list',
  '/static/demo_sample.json',
  '/static/demo_sample_ican.json',
  '/static/demo_sample_internet.json',
  '/static/demo_sample_challenge.json'
];

// 只读 GET 接口白名单：不在这个清单里的 /api/ 请求一律不拦截、不缓存
var API_CACHEABLE = [
  '/api/demo/list',
  '/api/demo/sample',
  '/api/competition/index',
  '/api/competition_profiles',
  '/api/ppt_themes',
  '/api/kb/list',
  '/api/notice'
];

// 静态资源可缓存扩展名
var STATIC_EXT = ['js', 'css', 'png', 'ico', 'svg', 'webp', 'jpg', 'jpeg', 'woff2', 'gif'];

// 后台 / 分享 / 生成产物 / 实时流：一律不碰
var BLOCK_PREFIX = ['/admin', '/monitor', '/share/', '/generated/',
  '/api/status/', '/api/stream/', '/api/speech_stream/', '/api/export'];

// 品牌图标与公告：走「网络优先 + 缓存兜底」，不进 cache-first。
// 原因：图标正在并行替换，cache-first 会把旧 logo 钉在用户机器里；
// 网络优先保证联网时永远是最新图标，离线时才用缓存。
var FRESH_FIRST = [
  '/static/logo.png',
  '/static/icon-180.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/icon-maskable-512.png',
  '/static/favicon.ico',
  '/static/og-image.png',
  '/static/notice.json'
];

function isFreshFirst(pathname) {
  for (var i = 0; i < FRESH_FIRST.length; i++) {
    if (pathname === FRESH_FIRST[i]) return true;
  }
  return false;
}

function isBlocked(pathname) {
  for (var i = 0; i < BLOCK_PREFIX.length; i++) {
    var p = BLOCK_PREFIX[i];
    if (pathname === p || pathname.indexOf(p) === 0) return true;
  }
  return false;
}

function getExt(pathname) {
  var q = pathname.indexOf('?');
  var base = q === -1 ? pathname : pathname.slice(0, q);
  var dot = base.lastIndexOf('.');
  if (dot === -1) return '';
  return base.slice(dot + 1).toLowerCase();
}

// /static/ 下：白名单扩展名，或演示样例 json；赛事索引 json 随时更新，不缓存
function isCacheableStatic(pathname) {
  if (pathname.indexOf('/static/') !== 0) return false;
  if (pathname.indexOf('competition_index.json') !== -1) return false;
  if (pathname.indexOf('demo_sample') !== -1) return true;
  if (pathname.indexOf('notice.json') !== -1) return true;
  var ext = getExt(pathname);
  for (var i = 0; i < STATIC_EXT.length; i++) {
    if (STATIC_EXT[i] === ext) return true;
  }
  return false;
}

function isCacheableApi(pathname) {
  for (var i = 0; i < API_CACHEABLE.length; i++) {
    var a = API_CACHEABLE[i];
    if (pathname === a || pathname.indexOf(a + '?') === 0) return true;
  }
  return false;
}

function openCache(name) {
  return caches.open(name);
}

function putSafe(name, req, res, max) {
  try {
    if (!res || !res.ok || res.status !== 200) return Promise.resolve(null);
    var copy = res.clone();
    return openCache(name).then(function (cache) {
      return cache.put(req, copy);
    }).then(function () {
      return trimCache(name, max);
    }).catch(function () { return null; });
  } catch (e) {
    return Promise.resolve(null);
  }
}

function trimCache(name, max) {
  return openCache(name).then(function (cache) {
    return cache.keys().then(function (keys) {
      if (keys.length <= max) return null;
      var jobs = [];
      var over = keys.length - max;
      for (var i = 0; i < over; i++) jobs.push(cache.delete(keys[i]));
      return Promise.all(jobs);
    });
  }).catch(function () { return null; });
}

/* ---------------- install：预缓存（逐条容错，单条 404 不拖垮安装） ---------------- */
function precacheAll() {
  var list = PRECACHE_SHELL.concat(PRECACHE_DEMO);
  var jobs = [];
  for (var i = 0; i < list.length; i++) {
    jobs.push(precacheOne(list[i]));
  }
  return Promise.all(jobs);
}

function precacheOne(url) {
  var target = (url.indexOf('/api/') === 0) ? DATA_CACHE : SHELL_CACHE;
  var req = new Request(url, { method: 'GET', mode: 'same-origin', credentials: 'same-origin' });
  return fetch(req).then(function (res) {
    if (!res || !res.ok) return null;
    return openCache(target).then(function (cache) {
      return cache.put(url, res.clone());
    });
  }).catch(function () { return null; });
}

self.addEventListener('install', function (event) {
  self.skipWaiting();
  try {
    event.waitUntil(
      precacheAll().then(function () { return trimCache(SHELL_CACHE, SHELL_MAX); })
        .catch(function () { return null; })
    );
  } catch (e) { /* 预缓存失败不影响安装 */ }
});

/* ---------------- activate：清理旧版本 cache ---------------- */
self.addEventListener('activate', function (event) {
  try {
    event.waitUntil(
      caches.keys().then(function (names) {
        var jobs = [];
        for (var i = 0; i < names.length; i++) {
          if (names[i] !== SHELL_CACHE && names[i] !== DATA_CACHE) {
            jobs.push(caches.delete(names[i]));
          }
        }
        return Promise.all(jobs);
      }).then(function () {
        return self.clients.claim();
      }).catch(function () {
        return self.clients.claim();
      })
    );
  } catch (e) { /* ignore */ }
});

/* ---------------- fetch ---------------- */
self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (!req) return;

  // 非 GET（含 /api/generate_async 等所有写接口）一律不拦截
  if (req.method !== 'GET') return;

  // Range 请求（音视频/大文件续传）不拦截
  try {
    if (req.headers && req.headers.get('range')) return;
  } catch (e) { /* ignore */ }

  var url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }

  // 跨源不拦截
  if (url.origin !== self.location.origin) return;

  var pathname = url.pathname;
  if (isBlocked(pathname)) return;

  var isNavigation = (req.mode === 'navigate') ||
    (req.headers && (req.headers.get('accept') || '').indexOf('text/html') !== -1);

  /* 1. 导航请求：network-first，离线回落首页壳 */
  if (isNavigation) {
    event.respondWith(
      fetch(req).then(function (res) {
        putSafe(SHELL_CACHE, req, res, SHELL_MAX);
        return res;
      }).catch(function () {
        return caches.match(req).then(function (hit) {
          if (hit) return hit;
          return caches.match(OFFLINE_URL).then(function (shell) {
            if (shell) return shell;
            return new Response(
              '<!doctype html><meta charset="utf-8"><title>离线</title>' +
              '<body style="font-family:sans-serif;padding:24px;line-height:1.8">' +
              '当前网络不可用，页面内容未能缓存成功，请联网后重试。</body>',
              { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            );
          });
        });
      })
    );
    return;
  }

  /* 2. 品牌图标 / 公告：network-first，保证联网时一定是最新的（离线才用缓存） */
  if (isFreshFirst(pathname)) {
    event.respondWith(
      fetch(req).then(function (res) {
        putSafe(SHELL_CACHE, req, res, SHELL_MAX);
        return res;
      }).catch(function () {
        return caches.match(req, { ignoreSearch: true }).then(function (hit) {
          return hit || new Response('', { status: 504, statusText: 'offline' });
        });
      })
    );
    return;
  }

  /* 3. 静态资源：cache-first + 后台异步更新 */
  if (isCacheableStatic(pathname)) {
    event.respondWith(
      caches.match(req, { ignoreSearch: true }).then(function (hit) {
        var network = fetch(req).then(function (res) {
          putSafe(SHELL_CACHE, req, res, SHELL_MAX);
          return res;
        }).catch(function () {
          return null;
        });
        if (hit) {
          // 命中缓存：立即返回，network 已在后台拉新版本覆盖缓存，结果丢弃即可
          return hit;
        }
        return network.then(function (res) {
          if (res) return res;
          return new Response('', { status: 504, statusText: 'offline' });
        });
      }).catch(function () {
        return fetch(req);
      })
    );
    return;
  }

  /* 4. 只读 GET 接口：network-first，离线回读缓存 */
  if (isCacheableApi(pathname)) {
    event.respondWith(
      fetch(req).then(function (res) {
        putSafe(DATA_CACHE, req, res, DATA_MAX);
        return res;
      }).catch(function () {
        return caches.match(req, { ignoreSearch: true }).then(function (hit) {
          if (hit) return hit;
          return new Response(
            JSON.stringify({ success: false, offline: true, error: '当前离线，暂无缓存数据' }),
            { status: 503, headers: { 'Content-Type': 'application/json; charset=utf-8' } }
          );
        });
      })
    );
    return;
  }

  // 其余请求（含所有 /api/ 写接口、实时进度、后台页面）走浏览器默认网络
  return;
});

/* ---------------- 消息：手动跳过等待 / 清空缓存（回滚用） ---------------- */
self.addEventListener('message', function (event) {
  var data = event.data;
  if (!data) return;
  if (data === 'wb-skip-waiting') {
    try { self.skipWaiting(); } catch (e) { /* ignore */ }
    return;
  }
  if (data === 'wb-purge-cache') {
    try {
      event.waitUntil(
        caches.keys().then(function (names) {
          var jobs = [];
          for (var i = 0; i < names.length; i++) {
            if (names[i].indexOf('wb-shell-') === 0 || names[i].indexOf('wb-data-') === 0) {
              jobs.push(caches.delete(names[i]));
            }
          }
          return Promise.all(jobs);
        }).catch(function () { return null; })
      );
    } catch (e) { /* ignore */ }
  }
});
