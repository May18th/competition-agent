# 待办_WorkBuddy_实时草稿预览（边生成边展示）

> 来源：Codex 后端（2026-09-28，后端已就绪）
> 对象：WorkBuddy（index.html 归你）
> 优先级：P1（生成等待期从"干等"变"看着正文长出来"）

## 后端已就绪（不用改后端）

`GET /api/status/<task_id>` 已返回：

- `stage_label`（中文阶段）+ `pct`（进度百分比）；
- `partial`：`{字段名: 已生成文本}`，如 `partial.proposal` = 写到一半的正文、`partial.proposal_outline` = 写作纲要；
- 支持 cursor 增量：请求 `?cursor={"proposal": 已见长度}`，只回「新增后缀」，避免每次轮询拉全量。

生成过程中，`_stream_llm` 每 8 个 token 就推一次 partial，所以正文是逐字增长的。

## 前端要做

1. 生成过程中轮询 `/api/status/<task_id>`（带 cursor），把 `partial.proposal`（或 `proposal_outline`）渲染到结果区，边生成边展示已写章节。
2. 进度条继续用 `stage_label` + `pct`；正文预览区和进度条并列，别抢进度条的层级。
3. 生成完成后，用完整 `data.proposal` 覆盖预览区（最终结果以 `done` 返回的 `data` 为准）。

## 验证

- 生成中（尤其 writing 阶段）能看到正文逐字增长；
- 完成后显示完整正文，与预览衔接自然、无闪烁/覆盖错乱。
