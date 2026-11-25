/* 2026-11-25：PWA 退场用的「自毁」Service Worker。
 *
 * 背景：前端已整体对齐线上版，线上不再注册 Service Worker（index 里没有 pwa.js）。
 * 但旧版本的 SW 一旦在用户浏览器里注册过，就会一直拿缓存喂页面，出现「前端改了、
 * 用户还看到旧页面」的问题；浏览器只在访问 SW 脚本时才会检查更新。
 *
 * 所以保留 /static/sw.js 这个路径、内容换成下面这段：还活着的老 SW 在下一次更新检查时
 * 会被替换成它 → 清空缓存、注销自己，页面回到正常网络加载。
 * 新访客不会注册 SW（页面里已无注册代码），这段只服务老访客一次。
 */

self.addEventListener('install', function () {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil((async function () {
    try {
      var keys = await caches.keys();
      await Promise.all(keys.map(function (k) { return caches.delete(k); }));
    } catch (e) {}
    try { await self.registration.unregister(); } catch (e) {}
    try {
      var clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach(function (c) { try { c.navigate(c.url); } catch (e) {} });
    } catch (e) {}
  })());
});

/* 不再拦截任何请求：全部走网络，不留缓存 */
self.addEventListener('fetch', function () {});
