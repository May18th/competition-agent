# PWA 离线安装说明（366 轮）

面向比赛现场断网演示：站点可「安装到主屏幕」，断网后仍能打开页面壳与演示样例。

## 一、文件清单

| 文件 | 大小 | 作用 |
| --- | --- | --- |
| `static/manifest.json` | 1128 B | 可安装性声明；icons 只写品名路径，不生成/不覆盖图片 |
| `static/sw.js` | 11830 B | Service Worker：预缓存 + 三种拦截策略 |
| `static/wbpwa.js` | 9179 B | 注册 SW + 安装引导横幅 + 离线状态横幅 |

接线（`index.html` 中已存在，由 team-lead 统一维护，本轮未改动 index.html）：

```
18 行附近  <link rel="manifest" href="/static/manifest.json?v=20260929ao">
1650 行附近 <script src="/static/wbpwa.js?v=20260929ao"></script>
```

### Service Worker 必须在根路径提供

`wbpwa.js` 依次尝试 `/sw.js` → `/static/sw.js`（均以 `/` 为作用域）。
SW 脚本若只在 `/static/` 下，作用域就只有 `/static/`，**拦截不到 `/` 的导航请求，离线防白屏会失效**。
因此必须由服务端二选一：

- nginx（推荐，无需重启后端）：
  ```nginx
  location = /sw.js {
      alias /opt/comp-agent/static/sw.js;
      default_type text/javascript;
      add_header Service-Worker-Allowed "/" always;
      add_header Cache-Control "no-cache, no-store, must-revalidate" always;
      access_log off;
  }
  ```
- 或 app.py 增加 `/sw.js` 路由：`send_file('static/sw.js')` + 上述两个响应头。

`/sw.js` 必须 `no-store`：`/static/` 当前下发的是 `max-age=2592000`（30 天），SW 脚本被长缓存会导致新版本推不下去。

## 二、缓存策略

cache 名带版本号：`wb-shell-20260929ao`（页面与静态资源）、`wb-data-20260929ao`（只读接口数据）。
`activate` 时删除所有不属于当前版本的 `wb-shell-*` / `wb-data-*`。

| 请求类型 | 策略 |
| --- | --- |
| 导航请求（HTML 页面） | network-first；成功写缓存，失败依次回落「该 URL 缓存」→「缓存的首页 `/`」→ 内置 503 文案页（防白屏） |
| 品牌图标、公告（logo/icon/favicon/og-image/notice.json） | network-first + 缓存兜底。**刻意不走 cache-first**，因为图标正在并行替换，避免旧 logo 被钉在用户机器上 |
| `/static/` 下白名单扩展名（js/css/png/ico/svg/webp/jpg/jpeg/woff2/gif）与 `demo_sample*.json` | cache-first + 后台异步拉取新版本覆盖缓存 |
| 只读 GET 接口白名单 | network-first；成功写缓存，离线时回读缓存；无缓存则返回 `{success:false,offline:true}` |

只读 GET 接口白名单（**只有这些**）：

```
/api/demo/list  /api/demo/sample  /api/competition/index  /api/competition_profiles
/api/ppt_themes  /api/kb/list  /api/notice
```

### 绝不缓存的内容（红线）

- 所有非 GET 请求 —— 含 `/api/generate_async` 等写接口，`fetch` 首行即 `if (req.method !== 'GET') return;`，根本不进入拦截逻辑
- `/api/status/`、`/api/stream/`、`/api/speech_stream/` 实时进度与流式输出
- `/api/history` 等按 uid 隔离的私有数据 —— 共享演示机上缓存会造成串号，故不放白名单
- `/admin`、`/monitor`、`/share/`、`/generated/`、`/api/export*`
- `competition_index.json`（赛事索引随时更新）

预缓存清单：`/`、主要 js/css（含 echarts/marked/purify）、图标、favicon、`/api/demo/list` 与 4 个 `demo_sample*.json`。
逐条容错，单条 404 不会拖垮 install。

## 三、如何更新版本号

发版（前端资源有变动）时改 `static/sw.js` 顶部一行即可：

```js
var BUILD = '20260929ao';   // ← 改成新版本号，例如 20260930aa
```

改后 `wb-shell-<ver>` / `wb-data-<ver>` 两个 cache 名随之变化，`activate` 会自动删掉旧 cache，下次访问重新预缓存。

**忘改的后果**：静态资源走 cache-first，用户会拿到旧文件（导航请求是 network-first，所以 HTML 一定是最新的，只是 js/css 可能滞后一次访问，后台异步更新会在第二次访问纠正）。

同时建议同步 `index.html` 里 `?v=` 的版本串，两处保持一致便于排查。

## 四、如何卸载 / 回滚

1. **软回滚（保留文件，停掉离线能力）**：改 `sw.js` 顶部 `BUILD`，并在浏览器 DevTools → Application → Service Workers 点 Unregister；或让页面执行
   ```js
   navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
   ```
2. **清空缓存**（保留注册）：页面执行，或在 DevTools → Application → Storage 清站点数据
   ```js
   caches.keys().then(ns => ns.filter(n=>/^wb-(shell|data)-/.test(n)).forEach(n => caches.delete(n)))
   ```
   sw.js 也内置了消息通道：`navigator.serviceWorker.controller.postMessage('wb-purge-cache')`。
3. **彻底回滚到 366 轮之前**：删除 `static/manifest.json`、`static/sw.js`、`static/wbpwa.js`，并移除 `index.html` 第 18 行的 manifest link 与第 1650 行的 wbpwa.js script。原文件备份在 `/tmp/wb_bak_pwa_366/`。
4. 客户端已有的 SW 注册在清除前仍会存在，务必配合第 1 步 unregister，否则旧 SW 会继续接管。

## 五、UI 行为

- 顶部居中可关闭小横幅，不自动弹 modal、不自动 reload（避免打断正在进行的生成流程）
- 符合安装条件（`beforeinstallprompt` 触发）时显示「安装到主屏幕」按钮；已安装（standalone）或用户关闭过（`localStorage.wb_pwa_install_dismissed`）则不再显示
- 离线时显示黄色横幅「当前处于离线状态，联网后可继续生成与导出。」
- 配色全部走主题变量带 fallback（`--surface-solid` / `--text` / `--btn-ghost` / `--line-strong` / `--warn-bg|line|text`），圆角 10px，日间夜间双端满足 WCAG AA
