# 待办（WorkBuddy）：XSS 防护 + 学术诚信措辞

## 1. XSS：LLM 输出直接 innerHTML，缺 HTML 过滤（前端，重点）

现状：`index.html` 里包了一层 `window.marked.parse`，把后端/LLM 的 Markdown 转成 HTML 后直接 `innerHTML` 塞进页面，**没有做 HTML 白名单过滤**。如果模型输出里混进 `<script>`、`<img onerror=...>` 之类，会被浏览器执行。

### 改法（任选其一，推荐 ①）

① 引入 DOMPurify，所有 `marked.parse` 的结果过一遍：

```html
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
```

```js
window.marked.parse = function (t) {
  var raw = _origParse(String(t == null ? '' : t));
  var clean = window.DOMPurify ? DOMPurify.sanitize(raw, { ALLOWED_TAGS: ['p','br','h1','h2','h3','h4','ul','ol','li','strong','em','b','i','blockquote','table','thead','tbody','tr','th','td','hr','code','pre','mark'] }) : raw;
  // 再做占位符高亮
  return clean.replace(PH_RE, ...);
};
```

② 不想引 DOMPurify 就退一步：`_origParse` 之前先把 `<` 转义成 `&lt;`，代价是 Markdown 里的内联 HTML（比如表格）会失效——你们正文里有表格，所以**更推荐 ①**。

## 2. 学术诚信措辞（低优先，已基本 OK）

首页已经有「查重风险：AI 生成率可能偏高，直接交有被判不合格风险」的提示，这个很好，保留。

再检查一遍首页/落地页别出现「一键交稿 / AI 代写 / 帮你拿奖」这类宣传；统一说成「创作助手 / 生成初稿供修改 / 最终以你补充的真实数据为准」。

## 后端已完成（Codex，无需你动）

- `backup_db.py` 已加（SQLite 每日备份，保留最近 7 份）。
- 后台 `ADMIN_TOKEN` 鉴权 + 蒸馏限流 + 草稿不入库已完成。

