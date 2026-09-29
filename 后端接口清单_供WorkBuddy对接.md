# 后端接口清单（Codex → WorkBuddy 对接用）

> 以下接口均已实现并上线，WorkBuddy 前端直接调用即可，别重复造。均为同源部署、无需跨域头。

## 生成 / 进度
- `POST /api/generate_async`：`{idea, competition_name, mode(fast|deep), user_data, rule_content, outline_requirement, scoring_weights, length_pref(brief|balanced|detailed), theme, doc_type, humanize, iterate}` → `{task_id}`。quota 撞顶时返 `{success:false, code:"quota_exceeded", error:"今日生成额度已满，明日恢复"}`
- `GET /api/status/<task_id>`：`{status, stage_label, pct, partial, partial_content, eta_seconds, mode_counts, splash_fact, diagnosis_report}`；done 时带 `data` 全量结果

## 赛事 / 主题
- `GET /api/competition/index`：15 个赛事（含「西门子杯」），`{count, items}`（每个含 name/chapters/评分标准/扣分点）
- `GET /api/competition_profiles`：赛事结构化配置（aliases/chapters/…）
- `GET /api/ppt_themes`：31 套主题，每套含 `key/label/tier/family/scene/colors/layout/license/source`（license：蒸馏参考/程序化自绘原创，版权台账）

## 导出（支持直链 GET，fetch-blob 失败可 window.open 降级）
- `GET|POST /api/export_word?history_id=xxx` → docx
- `GET|POST /api/export_pdf?history_id=xxx` → pdf
- `GET|POST /api/export_zip?history_id=xxx` → 14 文件 zip
- `GET /api/share_export/<token>?type=docx|pdf|zip` → 分享页直链下载（微信跨端找回）

## 后台 / 监视
- `GET /api/admin/stats`：`{total, fast_count, deep_count, avg_duration, success_rate, trend(14天补零), failure, recent_failures(10条), feedback, rating, score_buckets}`
- `GET /api/admin/quota`：`{calls, limit, remaining, percent, exceeded, daily(近7日)}`
- `GET /api/health`：`{status, knowledge_count, quota, history_count, last_generation_time, uptime_seconds}`

## 反馈 / 公告 / 异常
- `POST /api/feedback`：`{content, history_id(可空)}` → 任意状态可提交（未生成也能提）
- `GET /api/notice`：`{active, content}` 维护公告
- `POST /api/admin/notice`：`{active, content}` 后台开关公告
- `POST /api/log_error`：`{type(frontend|api|export|generate), path, message, detail}` → 前端异常上报（已自动过滤 health 轮询/用户取消/静态404）

## 已就绪、待前端接的项（对应豆包最近几轮）
- 「全部赛事」下拉：用 `/api/competition/index`（后端已返 15，前端 DOM 渲染层是 bug）
- 常驻反馈入口：调 `/api/feedback`（history_id 不用传）
- 首页公告条：调 `/api/notice`
- 后台额度/失败/趋势卡：调 `/api/admin/quota` + `/api/admin/stats`
- PPT 风格缩略图：调 `/api/ppt_themes`（自带配色，不用前端维护对照表）

## 新增（270/271/246-247 轮，供前端接）
- `GET /api/demo/list`：演示样例清单 → `{success, samples:[{name, competition_name}]}`（2 套样例）
- `GET /api/demo?id=0|1`：取某套演示样例完整结果 → `{success, data:{...全量结果含 rich_deck}}`（不调 LLM、demo 只读可访问）
- `GET /api/defense_faq`：答辩模拟问答静态 FAQ → `{success, faq:[{q, framework}]}`（6 条，不调 LLM）
- `POST /api/revise_chapter`：提出修改 → body `{instruction, history_id(可空), proposal(可空)}` → `{success, proposal(新全文), old_proposal(旧全文)}`

## 演示模式前端接法（270 轮）
1. 「一键演示」按钮 → `GET /api/demo/list` 出下拉选样例
2. 选一套 → `GET /api/demo?id=N` 拿 `data`
3. 把 `data` 喂给现有结果页渲染逻辑（正文/评分/各 tab/PPT 预览/图表兜底全部复用），不走 `/api/generate_async`

详细字段结构见 `docs/后端接口说明_演示模式.md`。
