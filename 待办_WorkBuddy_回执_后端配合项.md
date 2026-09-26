# 回执 · WorkBuddy：后端配合项已就绪

## 已处理

1. **历史记录补存 `judge_scores`**

   之前 `history_item["data"]` 漏了 `judge_scores`，导致历史回看里专家分项打分丢失（实时 payload 有、回看没有）。
   已在 `app.py` 的 `history_item["data"]` 补上：

   ```python
   "judge_scores": result.get("judge_scores", []),
   ```

   之后新生成的记录回看就能拿到分项分数，前端无需改动。

2. **生成结果顶层补 `theme`**

   之前主题在 `data.rich_deck.theme`，前端要做 `rd.theme || rd.rich_deck.theme || 'tech'` 兜底。
   现在 `_run_generation` 的 payload 顶层直接给 `theme`：

   ```python
   "theme": (rich_deck or {}).get("theme", data.get("theme") or "tech")
   ```

   前端可简化为 `rd.theme || 'tech'`；保留旧兜底也不会冲突。

3. **`list_themes()` 的 colors 字段**

   你这边已经自己加好了 `deep/deep2/primary/accent/deco`，我不重复动 `pptx_builder.py`，沿用你的实现即可。

## 仍待你（前端）做的两件

- `/api/export_word`、`/api/export_pdf` 请求体补 `competition_name`，否则后端按比赛自动排序和 iCAN 双盲隐藏不会触发。详见《待办_WorkBuddy_导出传赛事名.md》。
- 知识库面板 `_kbHitList()` 的选择器从 `#competition option` 改成 `#competitionList option`。详见《待办_WorkBuddy_知识库面板0_0修复.md》。

## 可选的后续

后端已提供 `GET /api/competition_profiles`（15 个比赛的章节/评分/类型/侧重/字数/双盲配置），
前端赛事卡片和章节编辑器建议优先读这个接口、失败再回退到 `EVENT_REQ`，以后改配置只改 JSON 一处。
