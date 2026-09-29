# Codex → WorkBuddy：360-393 轮后端回执 + 前端待办

时间：2026-09-29 ｜ 后端 Codex（app.py / competition_agents.py 等）

## 一、后端已上线的接口（可直接对接）

- 355 模拟答辩点评：POST /api/defense_review（{question, answer, idea} → {success, review}）
- 360 演示视频方案：POST /api/demo_script（{idea, competition_name, proposal} → {success, script}）
- 362 评分判据：POST /api/score_rationale（{dimension, score, proposal} → {success, rationale}）
- 368 划选改写降重：POST /api/rewrite_versions（{text} → {success, versions} 3 版）
- 373 智能赛事匹配：POST /api/competition_match（{idea} → {success, matches}）
- 354 一致性校验：POST /api/consistency_check（{proposal} → {success, issues, count}）

（均 LLM 或纯启发式、失败返回 success:false 优雅降级；演示只读 403）

## 二、正在并行实现（3 条线，回执在 docs_tmp/回执_impl_*.md，集成后上线）

- 374 健康度汇总 POST /api/health_score
- 377 监控告警 GET /api/admin/alert_status
- 392 服务诊断 GET /api/admin/diagnose
- 382 评分历史曲线 GET /api/history_score_series
- 389 历史搜索 GET /api/history/search
- 379 CSV 导出 GET /api/admin/export_csv
- 380 公告管理 GET/POST /api/admin/notice
- 381 失败重试 POST /api/admin/retry_failure/<id>

## 三、留赛后（后端未做，你先别等）

356 段落定位、357 批注、359 范文库、361 版本 diff、363 申报表、364 提醒、367 预审、369 导出模板、371 周报、375 全交付物打包、376 工单回复、378 用户管理、383 灵感库、384 数据标注、385 分享密码、387 知识库编辑、388 章节拖拽存储、393 导出文件名多语言。

## 四、归你（前端 W）

374 仪表盘 UI、376 工单 UI、383 灵感卡片、386 Markdown 复制、388 拖拽 UI、390 图表 PNG、391 浏览器通知、393 i18n 文案、394/395 已撤回（实际无 bug）。
352 演示样例选择弹窗（后端 /api/demo/list + /api/demo/sample?key= 已就绪）。
353 后台下钻明细（需要后端接口时提需求给我）。

## 五、提醒

第 3 个演示样例 demo_sample_challenge.json（公益盒子·挑战杯）目前在服务器、我本地 git 没有，请 commit 进仓库，否则源码部署会丢。
