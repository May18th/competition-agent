"""Shared deterministic content rules used by generation prompts and quality gates."""

# Keep this list in one place so the prompt and the post-generation audit cannot drift.
HUMANIZE_BANNED = (
    "随着",
    "综上所述",
    "赋能",
    "生态",
    "一站式",
    "闭环",
    "深度融合",
)

JUDGE_FACING_OUTPUT = """【所有生成物的受众】
提交材料、分析报告、答辩材料、路演稿、PPT、Word 与 PDF 均围绕赛事评委的判断链组织：问题是否真实、场景是否具体、方案是否有效、证据是否可信、差异化是否成立、项目是否能落地。使用正式、清晰、可核验的陈述口吻，不写团队内部待办、开发任务、排期沟通或“本页讲什么”；涉及团队时，只呈现与项目完成度和执行能力相关的事实。
规则分析、同质化分析、诊断、答辩预测等备赛工具虽供参赛团队使用，仍须按评委的评判标准、质询重点与证据要求组织，不输出与评审无关的内部工作记录。答辩回答框架可用参赛者现场陈述口吻，但论据、边界和结论必须对应评委问题。
"""
