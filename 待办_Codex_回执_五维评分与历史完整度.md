# Codex 回执 · 五维评分落地 + 历史完整度修复

> 状态：已改 `app.py`（未提交，等用户本机 git add/commit/push）。
> 对应《指令_2026-09-28.md》F（五维评分 scores）与第二轮 #4（历史恢复不完整）。

## 1. 五维评分 `scores` 之前是「算出来但没交付」

- `idea_evaluator` 一直有返回 `scores: {innovation, feasibility, market, barrier, social}`（创意评分五维，30/25/20/15/10），`CompetitionState` 里也声明了 `scores: dict`。
- 但 `_run_generation` 拼 `payload` 和 `history_item["data"]` 时**都没带 `scores`**，只带了 `idea_score`（总分）和 `judge_scores`（文档质量分）。等于创意五维分白算了，前端雷达图拿不到数据。
- 修复：payload 与历史 data 各补一行 `"scores": result.get("scores", {})`。

## 2. 历史记录缺「完整度/字数/查重/关键词」

- `save_history_item` 在「正文压缩闸门 + 完整度检测」**之前**执行，导致历史里没有 `completeness / proposal_chars / similarity / keywords`，打开历史后「数据支撑论点/待补充/本地查重/字数」都显示「—」。
- 修复：新增 `_update_history_data(hid, extra)`，在 `payload` 拼完、拿到 `_new_hid` 后，把后算的四个字段回写进该历史记录的 `result_data`（JSON 合并式 UPDATE，失败只打日志不影响主流程）。

## 顺带核实（结论：无需改）

- 诊断报告 `diagnosis_report` 并非恒为空：`_run_graph` 用 `app.stream(..., stream_mode="values")` 逐步 `_emit_partial`，`proposal_analysis` 属于 `_PARTIAL_FIELDS`，节点跑完即上报。之前怀疑它漏上报是误判，已回退多余改动。
- `judge_feedback / defense_questions / ppt_outline` 同样由 `_emit_partial` 覆盖，不需要逐个补 `set_partial_field`。
- 打包 zip 的 `11_项目数据图表.docx` / `12_路演PPT.pptx` 代码已在（`export_zip` 内根据 `rich_charts / rich_deck` 生成），历史 data 也已存 `rich_charts/rich_tables/rich_deck`。

## 待确认（留给后续，不动）

- 评分波动（86/62/72/86）：要不要固定 seed 或 3 次采样取均值，属质量取舍，赛前建议先不动。
- 全站计数口径（后台总览/health/历史面板三处不一致）：涉及 uid 过滤与 DB 语义，需要明确「公共可见 vs 当前用户」口径后再统一。
