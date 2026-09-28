# Codex 回执 · 五维评分落地 + 历史完整度修复

> 状态：已改 `app.py`（未提交，等用户本机 git add/commit/push）。
> 对应《指令_2026-09-28.md》F（五维评分 scores）与第二轮 #4（历史恢复不完整）。

## 1. 五维评分 `scores` 之前是「算出来但没交付」

- `idea_evaluator` 一直有返回 `scores: {innovation, feasibility, market, barrier, social}`（创意评分五维，30/25/20/15/10），`CompetitionState` 里也声明了 `scores: dict`。
- 但 `_run_generation` 拼 `payload` 和 `history_item["data"]` 时**都没带 `scores`**，只带了 `idea_score`（总分）和 `judge_scores`（文档质量分）。等于创意五维分白算了，前端雷达图拿不到数据。
- 修复：payload 与历史 data 各补一行 `"scores": result.get("scores", {})`。

## 2. 历史记录缺「完整度/字数/查重/关键词」

- `save_history_item` 在「正文压缩闸门 + 完整度检测」**之前**执行，导致历史里没有 `completeness / proposal_chars / similarity / keywords`，打开历史后「数据支撑论点/待补充/本地查重/字数」都显示「—」。
- 修复：新增 `_update_history_data(hid, extra)`，在 `payload` 拼完、拿到 `_new_hid` 后，用**最终 payload 整体覆盖**该历史记录的 `result_data`（去掉自引用 `history_id`，JSON 合并式 UPDATE，失败只打日志不影响主流程）。这样「打开历史 == 刚生成」，正文字数/去重/占位/虚构降级都与实时结果一致，而不只是补 4 个字段。

## 顺带核实（结论：无需改）

- 诊断报告 `diagnosis_report` 并非恒为空：`_run_graph` 用 `app.stream(..., stream_mode="values")` 逐步 `_emit_partial`，`proposal_analysis` 属于 `_PARTIAL_FIELDS`，节点跑完即上报。之前怀疑它漏上报是误判，已回退多余改动。
- `judge_feedback / defense_questions / ppt_outline` 同样由 `_emit_partial` 覆盖，不需要逐个补 `set_partial_field`。
- 打包 zip 的 `11_项目数据图表.docx` / `12_路演PPT.pptx` 代码已在（`export_zip` 内根据 `rich_charts / rich_deck` 生成），历史 data 也已存 `rich_charts/rich_tables/rich_deck`。

## 待确认（留给后续，不动）

- 评分波动（86/62/72/86）：要不要固定 seed 或 3 次采样取均值，属质量取舍，赛前建议先不动。
- 全站计数口径（后台总览/health/历史面板三处不一致）：涉及 uid 过滤与 DB 语义，需要明确「公共可见 vs 当前用户」口径后再统一。

## 3. 历史详情/评分/删除与列表 uid 口径不一致（第二轮补充）

- `load_history`/`count_history` 对无名存量记录（`user_id=''`）做了「公共可见」兼容：`WHERE (user_id = ? OR IFNULL(user_id,'') = '')`。
- 但 `get_history_detail` / `rate_history` / `delete_history` 还是老的 `AND user_id = ?`，导致**列表能看见、点开却「记录不存在」**（评分/删除同理）。
- 修复：三处查询统一成与列表一致的 `(user_id = ? OR IFNULL(user_id, '') = '')`。

## 4. 脱敏误伤官方赛事名（第八/十轮 [严重]）

- 症状：「中国国际大学生创新大赛」被删成「（隐去）生创新大赛」，「双盲评审不显示学校名称」被删成「双盲评（隐去）名称」。
- 根因：`_strip_identifying_text` 的院校正则 `[\u4e00-\u9fa5]{2,4}(?:大学|学校)` 太贪，把「大学生」（college student）和「学校名称」当院校名。
- 修复：①新增 `_deident_protect_terms()`，脱敏前把官方赛事全名 +「大学生/学校名称/学校地址」等泛化词换成哨兵，脱敏后还原；②正则加负向断言 `(?!生|名称|地址|简称|全称|校名)`。实测「清华大学」仍被隐去、「iCAN大学生创新创业大赛」完整保留。

## 5. 导出绑定当前记录（第十一轮 [阻塞·演示灾难]）

- 症状：同一结果页三个导出按钮各拿到不同历史记录内容（Word=取件柜、PDF=李然版、打包=张明版）。
- 根因：`export_zip` 完全依赖前端 POST body，没按 task_id/history_id 回源；`_fetch_proposal_from_source` 只回源 proposal 单字段。
- 修复：把 `_fetch_proposal_from_source` 拆成 `_fetch_record_from_source`（返回完整 result_data），`export_zip` 在拿到请求后先回源整条记录（前端仅覆盖 theme/variant），三个按钮内容一致、格式正确。

## 6. 虚构人名规则制（第十轮 [严重] 第二次强化）

- 症状：名单制（李然/张明/王雨桐）堵不住「小李」这类昵称变体。
- 修复：两处写作硬约束（通用 prompt 第 14 条 + 深度版 writer 第 8 条）从「列举几个名字」改成「禁止任何具体人名/昵称（含小李/小王/小张/李同学等变体）」，一律用泛化表述。

## 7. PPT AI 痕迹泄漏（第十五轮 [严重]）

- 症状：路演 PPT 页面正文混入「用表格呈现三条收入线…」这类写作指令；封面标题直接取整句创意 `idea[:30]`，评委翻 PPT 一眼看到 AI 痕迹。
- 修复（`rich_pipeline.py`）：①新增 `_looks_like_prompt_leak` / `_clean_deck_slides`，deck 归一化后剔除 title/kicker/note/subtitle/bullets/metrics 里的指令句（剥 `**关键词**：` 前缀再判前缀动词）；②新增 `_project_name`，封面标题从创意里提炼简短项目名（「项目名：描述」取冒号前、短创意直接用、长创意退 one_liner），不再把整句创意当标题。实测「用表格呈现三条收入线」被判指令剔除、「**痛点**：排队 20 分钟」保留。

## 8. 「下载路演PPT」也绑定当前记录（第十四轮四入口补齐）

- 之前 `export_zip` 已回源，但 `export_pptx` 还直接读前端 POST 的 `deck`，历史打开后可能拿到别的记录的 PPT。
- 修复（`app.py`）：`export_pptx` 同样先 `_fetch_record_from_source` 回源，`deck` 取记录里的 `rich_deck`，`tables/charts` 取 `rich_tables/rich_charts`（兼容前端旧字段 `deck/tables/charts`），前端仅覆盖 theme/variant。至此 Word/PDF（proposal 回源）、PPT（rich_deck 回源）、打包（全量回源）四入口内容都绑定当前记录。

## 9. `partial_content` 受 cursor 污染返回碎片后缀（第十三轮支撑）

- `/api/status` 里 `partial_content` 在 cursor 增量处理**之后**才取 `_partial.get("proposal")`，前端传 cursor 时拿到的是「新增后缀」而非完整正文，与字段注释「完整累积正文」矛盾，也导致等待区草稿预览对不上。
- 修复：`partial_content` 改从 `t["partial"]`（cursor 之前的全量）取 proposal 全文；`partial` 字段仍按 cursor 返回增量，两者职责分开。
