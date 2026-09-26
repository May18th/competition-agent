# 交接（WorkBuddy）：我接手改了 index.html 两个紧急项，请知悉

> 起因：用户反馈你这边推进较慢，授权我直接接手前端两个紧急小项。**我是基于你最新提交（f3552d8）之上改的**，没有覆盖你的 wbAgentStage 等改动，diff 干净（+25/-4）。

## 我改了什么

### 1. XSS 防护（安全，最紧急）

**问题**：`window.marked.parse` 把 LLM 输出转成 HTML 后直接 `innerHTML`，没有过滤。模型若吐出 `<script>`、`onerror=`、`javascript:` 会被执行。

**改法**（两处）：

1. 在 echarts 之后加了 DOMPurify CDN：

```html
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
```

2. 在 `marked.parse` 包装函数里，`_origParse` 之后先白名单过滤，再做占位符高亮：

```js
if (window.DOMPurify) {
  h = DOMPurify.sanitize(h, { ALLOWED_TAGS: [...], ALLOWED_ATTR: [...] });
} else {
  // 兜底：去 script / on* 事件 / javascript: 链接
  h = h.replace(/<script[\s\S]*?<\/script>/gi, '')
       .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
       .replace(/(href|src)\s*=\s*(["']?)\s*javascript:[^"'\s>]*\2/gi, '$1="#"');
}
```

白名单包含 `mark`，所以你的占位符高亮（`<mark class="wb-ph">`）不受影响。

### 2. `/api/status` 接 cursor 增量（移动端减负）

**问题**：之前每 800ms 拉一次全量 partial，越到后面越大。

**改法**：

1. 新增 `var _streamAccum = {}`（字段 -> 累积全文），`streamReset()` 里一并清空。
2. 轮询 URL 带上 cursor（复用你已有的 `_streamLen`）：

```js
fetch('/api/status/' + start.task_id + '?cursor=' + encodeURIComponent(JSON.stringify(_streamLen)))
```

3. 拿到 `res2.partial`（现在是「新增后缀」）后，逐字段累加再交给 `paintPartial`：

```js
var _p = res2.partial || {};
Object.keys(_p).forEach(function (f) {
  _streamAccum[f] = (_streamAccum[f] || '') + (_p[f] || '');
});
paintPartial(_streamAccum);
```

`paintPartial` 本身的逻辑我没动，它还是按 `_streamLen` 判断「有没有新增」再重渲染，所以原有流式体验不变，只是网络传输从「每次全量」变成「每次增量」。

## 后端配套（已就绪，你无需动）

- 后端 `/api/status` 的 cursor 增量在 `81383a7` 就上线了；不传 cursor 时仍返回全量，所以旧逻辑兜底还在。

## 需要你确认/后续

- 这两处改动我已本地用 Node 做了 JS 语法检查（7 个内联脚本 0 报错），并确认保留了你的 `wbAgentStage` 改动。
- 范文库 UI → 官方资料库 那项还挂在你这边（`待办_WorkBuddy_范文库版权整改.md`），不急，等你。

