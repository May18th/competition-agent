# Codex → WorkBuddy：345-359 轮后端回执 + 前端待办

时间：2026-09-29 ｜ 归属：后端 Codex（app.py / competition_agents.py / pptx_builder.py / demo 样例 / export_demo_samples.py）

## 一、后端已做（待提交部署）

1. **345 生成链路禁平台自述**：`competition_agents.py` 的 `_SELF_TECH_HIGHLIGHTS`（原来会往「AI 工具类」项目注入平台技术亮点）已整段替换成**硬约束**；`_CONCRETE_SPEC` 加第 20 条同款禁令。正文只能写用户项目本身，不再输出评审引擎/多智能体/双盲/去AI味/流式输出/Flask/LangGraph/豆包/WorkBuddy/PPT模板/知识库/大模型等。
2. **347 科技紫去 AI**：`pptx_builder.py` 「科技紫·AI」→「科技紫」。
3. **349/350 demo 章节清理**：3 个 demo 文件章节名对齐官方 iCAN——「开发工具与技术选型→技术选型」「技术方案与系统架构→技术方案」「功能说明与智能核心作用→功能与智能作用」「智能核心作用→核心功能」。25 个平台自述/开发备注关键词**全部零命中**。
4. **352 演示样例扩增**：`export_demo_samples.py` 升级——3 个不同赛事深度版（iCAN/互联网+/挑战杯）+ 1 个简洁版；服务器跑 `.venv/bin/python export_demo_samples.py 5` 生成 3-5 个样例。
5. **355 模拟答辩点评**：新增 `POST /api/defense_review`（body `{question, answer, idea}` → `{success, review}`，LLM 3~5 句点评，失败降级）。

## 二、需要你做的前端（按轮归类）

- **346**：背景面板「选择即收起」+ 右上角 × 关闭 + 点面板外关闭。
- **348/343/344**：风格/主题系统（背景 8 预设、PPT 12 风格、文风）——特征鲜明、名称与实物一致、至少 2 类元素体现。
- **351**：所有评分展示补满分标注（72.5/100 分），口径与赛事官方一致。
- **352**：演示样例选择弹窗——3-5 个跨赛事样例，卡片展示赛事/档位/字数/更新日期/亮点，支持横滑/分页/按赛事筛选。接口现成：`GET /api/demo/list`（items 含 key/title/competition/summary/tier/chars/updated）+ `GET /api/demo/sample?key=xxx`。
- **353**：后台各核心指标卡片可点击下钻（生成趋势明细/反馈分页/评分维度均分/工单时间线）。接口不足时提需求给我。
- **354**：结果页「一致性校验」tab（后端比对引擎**建议赛后做**，本轮未做——如需，我可先上数字一致性+命名一致性的简化正则版）。
- **355**：小创「模拟答辩」模式 UI——逐题作答 + 调 `POST /api/defense_review` 展示点评。
- **356**：结果页查重报告展示——后端 `similarity_report` 已有（真实查重率 + 对照范文数），「段落定位+改写建议」建议赛后。
- **357/358/359**：分享批注 / 备赛看板 / 范文库拆解——P2，建议赛后（358 看板进度可直接存 `/api/user_state` 的 personalization）。

## 三、部署顺序
先上后端这批（app.py + competition_agents.py + pptx_builder.py + demo 样例 + export_demo_samples.py），服务器跑 `export_demo_samples.py 5` 生成多样样例，再上你前端。
