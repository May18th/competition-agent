# 待办_WorkBuddy_iCAN 评分权重统一

> 来源：Codex 数据核对（2026-09-28）
> 对象：WorkBuddy（前端 index.html / data 归你）
> 优先级：P1（评委看到的权重与后端知识库要一致，避免两套数字）

## 结论

本项目对标 iCAN 的「AI 应用创新挑战赛（挑战赛道）」，正确评分权重是：

> 创新性 30 / 技术实现 30 / 实用价值 20 / 用户体验 10 / 应用前景 10

后端 `data/competition_profiles.json` 已是这套，接口 `GET /api/competition_profiles` 返回正确。

## 问题（两套数字的根源）

前端 `data/event_requirements.json`（EVENT_REQ）里 iCAN 的 scoring 第五项叫「**展示效果**」，后端 profiles 叫「**应用前景**」——数值都是 10，但名字对不上。前端若读 EVENT_REQ，评委看到的权重项就和后端知识库不一致。

## 要求

1. 前端赛事卡 / 章节编辑器 / 评分权重展示：**优先读 `GET /api/competition_profiles`（后端 JSON），失败再回退 EVENT_REQ**。
2. 顺手把 `event_requirements.json` 里 iCAN 的第五项「展示效果」改成「应用前景」，和后端对齐（以后仍以后端为准）。

## 验证

- 前端展示的 iCAN 权重 = 创新性30 / 技术实现30 / 实用价值20 / 用户体验10 / 应用前景10；
- 与 `GET /api/competition_profiles` 返回完全一致。
