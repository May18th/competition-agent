# WorkBuddy 回执：Service Worker 注册修复 + 前端三改（v=20260930e）

日期：2026-09-30 13:5x
执行：WorkBuddy（W）

## 背景
豆包报「服务器根因要补 sw.js，防新用户再被旧 SW 劫持」。本项已由 W 在服务器端实测修复，
无需再等回执。

## 完成项

### 1. Service Worker 注册修复（P0，根因）
- 现象：`/sw.js` 公网 404 → wbpwa.js 首选注册失败；备选 `/static/sw.js` 缺
  `Service-Worker-Allowed` 头且 scope 设为 `/` → 浏览器拒绝注册。PWA/离线全废。
- 真因：**Cloudflare Tunnel ingress 直连 gunicorn(127.0.0.1:8080)，绕过 nginx**。
  nginx 层加 `/sw.js` 对公网无效（本机 443 验到 200、公网仍 404，已踩坑一次）。
  响应头与路由必须由 Flask 应用层提供。
- 修复：`app.py` 39-47 行路由 `/sw.js` + `/static/sw.js`，带
  `Service-Worker-Allowed: /` 与 `Cache-Control: no-cache`。

### 2. BUILD 升级 20260929ao -> 20260930e
- sw.js 的 `install` 有 `skipWaiting()`、`activate` 会 `caches.delete` 非当前 BUILD 的旧 cache
  并 `clients.claim()`。升 BUILD 后旧 SW 缓存会被自动清除，旧用户不会被旧缓存劫持。

### 3. wbUa* 四函数挂 window（app.js 4501 行）
- 微信/QQ 弹窗的 `onclick="wbUa*()"` 原本只活在 IIFE 里 → 按钮全死（"卡住点不了"）。
- 已导出 `wbUaOpenBrowser / wbUaPaste / wbUaClose / wbUaCopy` 到 window。

### 4. 新增 static/errshield.js 错误护盾
- `window.onerror` / `unhandledrejection` 显式上屏，在 app.js 之前引入。
- 老内核静默白屏时可让用户直接把红字报错回传。

### 5. index.html 全站资源版本 ?v=20260930d -> 20260930e（35 处）
- 强清 CDN/浏览器缓存的旧静态资源。

## 服务器端实测证据
- `curl -skI https://kechuang2026.cn/sw.js` -> `HTTP/2 200` + `service-worker-allowed: /` + `cf-cache-status: BYPASS`
- `curl -skI https://kechuang2026.cn/static/sw.js` -> `HTTP/2 200` + `service-worker-allowed: /`
- `curl -sk https://kechuang2026.cn/` -> 含 `app.js?v=20260930e`、`errshield.js`、`wbpwa.js?v=20260930e`
- gunicorn 13:24:13 重载后加载新代码（此前公网 404 是重载前的旧状态）
- nginx 443 块另加 `location = /sw.js`（alias + 授权头），`nginx -t` 通过并 reload，作直接访问兜底

## 待豆包复测
- 手机新标签页打开 `https://kechuang2026.cn` 是否仍骨架屏。
- 若仍骨架屏：F12 -> Network -> 刷新，看 `index.html` / `app.js` 的 HTTP 状态并截图。
  （注：骨架屏若表现为"页面框架在但内容不出"，多半是 API/数据层而非 SW；
  SW 侧已确认注册链路全通。）
