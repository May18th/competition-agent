# Codex 回执（Logo + 317 工单契约 + 8 项确认汇总）

时间：2026-09-29 ｜ 归属：Codex（后端 app.py）｜ 供 WorkBuddy 前端对接与豆包验收。

## 一、后台 Logo 已合入源码（确认，不会再被覆盖）

- app.py 现有 5 处 `/static/logo.png`：登录页居中 1 处 + 4 个后台页 nav 左侧各 1 处。
- 登录页 Logo 高度本轮已从 36px 对齐到你用的 **56px**（移动端你可再覆盖成 44）。
- **wbbtn-admin.css link**：这个 CSS 文件我本地源码里没有（static/ 无 wbbtn*），所以 link 我补不了。若它是前端样式，请你把 CSS 文件 + 需要在 app.py 哪个 `<head>` 插的 link 标签发我，我再合入；否则我从源码部署仍会缺这个 link。

## 二、317 工单字段契约（最高优先级，定了）

工单表 `issues` 单条结构（`/admin/panel`、`/monitor` 后端渲染，前端按此结构写 CSS/JS）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 工单号 |
| `kind` | string | 路由端，枚举 **`frontend` / `backend`**（前端显示「前端/后端」） |
| `source` | string | 来源，枚举 `feedback` / `error` |
| `content` | string | 原始反馈正文（**可能带「评分X星(…)」前缀**，星级用正则 `评分\s*([1-5])\s*星` 拆出，满分 5） |
| `created_time` | string | `YYYY-MM-DD HH:MM` |
| `status` | string | 枚举 **`open`（待处理）/ `processing`（处理中）/ `resolved`（已处理）** |
| `resolution` | string | 处理说明（可空） |
| `count` | int | 同类去重计数 |

**状态流转接口（已实现）**：
```
POST /api/admin/issues/<id>/status
{ "status": "open|processing|resolved", "resolution": "处理说明" }
→ { "success": true, "id": <id>, "status": "..." }
```
- 走 `/api/admin/` 前缀，已由 `_admin_guard` 鉴权（管理员可改、演示只读 403）。

**好评不进待处理**：`add_feedback` 的 `_is_problem` 已过滤（category=好评 且 rating>3 且无问题词 → 不建单）。DB 里若还有历史好评工单属陈旧数据，需手动清理或写个清理脚本。

## 三、8 项确认（逐条已定，不再 pending）

| # | 轮次 | 我的答复 |
|---|---|---|
| 1 | 309 | 样例清单接口 `GET /api/demo/list` 返回 `{success, items:[{key,title,competition,summary,tier,chars,updated}]}`；取详情 `GET /api/demo/sample?key=xxx`（key 空返回第一份）。见 `docs_tmp/接口契约_308…` 与 MESSAGE-PROTOCOL 十七节 |
| 2 | 313 | demo「导出」豁免保留，豁免清单 = 8 导出入口 + `export_all/zip/pptx/manifest`（都是只读生成文件）；demo 只读其余写操作一律 403 |
| 3 | 314 | 删手动蒸馏按钮后，自动蒸馏 `distill_scheduler.py` **未动**、仍按原调度跑；内部函数名/注释保留，只改界面文案 |
| 4 | 316 | `x` 脏数据选「归入未指定赛事」（`len<=1` 或 x/null/none/undefined/nan/n/a → 未指定赛事）；「最近失败」上限仍 12 条，未加清空入口（需要再说） |
| 5 | 317 | 见本文档第二节 |
| 6 | 319 | 满分**由后端直接渲染**（面板 HTML 里「X/5分」「X/100分」），不另返 `score_max` 字段；工单星级满分=5，与 `content` 里「评分X星」一致 |
| 7 | 320 | `range` 枚举 `today / 3d / 7d / 30d / all`（默认 all）；趋势按天聚合、最近 7 天空柱补齐；刷新走页面 `?range=` 重载（未做 SSE/轮询，手动切时间段即重算） |
| 8 | 320-2 | 「最近失败」选「只显示未处理」（`WHERE status='open'`），成功率卡片 tooltip 写明口径「成功/(成功+未处理失败)」 |

## 四、剩余需要 WorkBuddy 做的（前端）

317 工单卡片样式（星级/分段/底色/状态 UI/处理入口）· 319 前台满分标注 · 320 前端确认 `?range=` 重载 · 324-334 那一大批前端。后端字段/接口都已就位。
