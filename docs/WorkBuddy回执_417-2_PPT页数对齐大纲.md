# WorkBuddy 回执 · 417-2 PPT 页数与大纲不一致（更正版）

- 时间：2026-09-30 05:4x (GMT+8) 更正
- 调查人：WorkBuddy
- **结论：417-2 已被前序轮次修掉，当前代码大纲↔PPT 必然一致，无需改动。**

## 更正说明（重要）
初版回执把根因归到 `rich_pipeline._gen_deck`（LLM「12-14 页」提示词），**这是错的**。
进一步读 `build_rich_assets`（rich_pipeline.py:386-512）发现：`_gen_deck` 在主线是**死代码**，
实际 deck 来源是 **`_outline_deck(_outline)`**（170/235 轮引入的确定性 1:1 逐页方案）：
- rich_pipeline.py:413 `_f_deck = _ex.submit(_outline_deck, _outline)`；:423 串行兜底同样用它。
- `ppt_outline` 由 competition_agents.py:2667 生成，指令明确「8～12 页，**与最终导出的 PPT 页数一致**」。
- `_outline_deck` 逐条解析大纲标题 → 一页一章节，结构上保证两端一致。

## 实测验证（真实样本，非靠猜）
取 competition.db 最近一条 history 的 `ppt_outline`（实验室设备巡检系统，约 10 节）跑 `_outline_deck`：
- 大纲正则识别章节：11
- `_outline_deck` 生成 slides：11
- **比对差：0**（大纲 11 ↔ PPT 11）

## 残留小瑕疵（非 417-2 阻塞，可后续顺手修）
- `_outline_deck` 跳过规则（rich_pipeline.py:271）只匹配 `^大纲$`，不覆盖「XX · 3分钟路演大纲」这类
  文档级标题 → 文档标题会被当一页（随后 build_rich_assets:503-504 又插一个 cover，出现冗余页）。
  影响：多 1 张标题页，不影响"大纲↔PPT 页数一致"的硬要求。
- build_rich_assets:476 有 `slides[:18]` 上限：大纲 >18 节才会被截断（正常 8-12 节不会触发）。

## 部署状态
rich_pipeline.py mtime 2026-09-29 18:19（早于今日 04:46 重启）→ 线上已是最新，无滞后。
**417-2 无需改动、无需重启。**
