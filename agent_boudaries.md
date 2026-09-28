# Agent 职责边界表（第一百三十五轮）

> 目的：各板块 Agent 分工明确、互不干扰，Codex / WorkBuddy 对齐用。
> 铁律：每个 Agent 只写自己的输出字段，禁止越界写别人字段；只读快照、不回写上游。

## 分析板块（并行，只读 idea / user_data / 知识库，输出各自独立字段）

| Agent | 输出字段 | 负责 | 禁止越界 |
| --- | --- | --- | --- |
| rule_parser_agent | parsed_rules | 解析赛事官方规则/评分标准/章节 | 不写正文、不写竞品 |
| similarity_checker_agent | similarity_report | 同质化检测 | 不改正文 |
| idea_evaluator | idea_score / idea_feedback | 创意本身打分（只评创意不评文档） | 不写申报书 |
| one_liner_agent | one_liner | 一句话定位 | 不写正文 |
| deep_competitor_agent | competitor_analysis | 竞品分析 | 不写商业测算/技术指标 |
| deep_business_agent | business_model | 商业模式/营收测算 | 不写技术方案 |
| deep_risk_agent | risk_analysis | 风险评估 | 不写实施计划 |
| deep_tech_agent | tech_solution | 技术方案/架构/选型 | 不写商业测算 |
| plan_agent | implementation_plan | 实施计划/里程碑/团队分工 | 不写技术指标 |
| social_value_agent | social_value | 社会价值 | 不写商业模式 |
| summary_agent | project_summary | 项目摘要 | 不展开正文 |

## 写作与评审板块（依赖上游分析结果，只读不写上游）

| Agent | 输出字段 | 负责 | 禁止越界 |
| --- | --- | --- | --- |
| proposal_writer_agent / deep_writer_agent | proposal | 申报书/论文正文（唯一正文写者） | 不写竞品/商业/风险独立模块 |
| judge_agent | judge_feedback / judge_scores / score | 文档质量评分 | 只评文档，不评创意 |
| expert_review_agent | expert_review | 多专家评审 | 只评文档，不评创意 |
| proposal_analysis_agent | proposal_analysis | 快速诊断 | 不改正文 |
| targeted_revise_agent | proposal（修订） | 按评委意见定点返工正文 | 只改正文，不重写分析模块 |

## 交付板块（并行，只读正文 + 分析，输出独立字段）

| Agent | 输出字段 | 负责 | 禁止越界 |
| --- | --- | --- | --- |
| defense_questions_agent | defense_questions | 答辩问题预测 | 不写演讲稿/PPT |
| ppt_outline_agent | ppt_outline | PPT 大纲 | 不写答辩题/演讲稿 |
| speech_agent | speech_script | 演讲稿 | 不写 PPT/答辩 |

## 富媒体（图后生成，独立于主图）

| 组件 | 输出 | 负责 | 禁止越界 |
| --- | --- | --- | --- |
| rich_pipeline._gen_assets | rich_charts / rich_tables | 图表/表格设计（只读数据，不出方案） | 不写正文 |
| rich_pipeline._gen_deck | rich_deck | PPT 页面结构 | 不写正文 |

## 隔离机制（已实现 / 需遵守）

- 各 Agent 返回增量 dict（只含自己的字段），langgraph 合并，避免互相覆盖。
- 上游到下游只传只读快照，下游修改不回写上游字段。
- 同一字段只允许一个写者：正文 = writer（初版）+ targeted_revise（修订），其余 Agent 一律只读。
- 并行组（分析组 / 交付组）互不写对方字段，无锁冲突。
