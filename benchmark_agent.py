# -*- coding: utf-8 -*-
"""标杆对标 Agent（benchmark_agent）

职责：把一份"生成导出物"与"质量标杆(doc)"逐维度对比，产出可机读的差距报告，
供 报告 agent / 写回 agent 使用，形成「学 → 对标 → 报告 → 改」闭环。

设计为可独立导入的模块：competition_agents / 周任务 / 本地评测均可调用。
不依赖具体 LLM 实现，只暴露 prompt 构造与解析函数，调用方传入 llm 或走规则模式。
"""
from __future__ import annotations
import json, re

# 对标维度（与 docs/导出物质量标杆_蒸馏版.md 对齐）
BENCHMARK_DIMENSIONS = [
    ("structure", "结构完整：覆盖标准章节/页面，无缺失核心页"),
    ("one_core_per_page", "一页/一节一核心：标题即结论，不堆叠多主题"),
    ("data_tracing", "数据可溯源：真实数据标来源，测算标「测算：基于XX假设」，无编造"),
    ("visual_system", "视觉系统：16:9、统一配色、固定字号层级、无花哨动画"),
    ("real_product", "真实产品证据：含真实截图/流程图/演示，非空泛描述"),
    ("charts_tables", "图表规范：标题即结论、带洞察与来源、类型匹配内容"),
    ("competition_matrix", "竞争表达：用 2x2 矩阵或雷达图，不用密集 feature 表"),
    ("no_absolutize", "无绝对化词汇：行业第一/彻底解决/全球领先等禁用"),
    ("blind_safe", "盲审安全：不出现院校/导师/成员真实姓名"),
    ("ending_cta", "结尾页：一句话定位+核心价值+明确下一步，非「谢谢聆听」空页"),
]


def build_benchmark_prompt(export_text: str, benchmark_text: str, export_type: str = "路演PPT") -> str:
    """构造对标 prompt。调用方把它发给 LLM，期望返回 JSON。"""
    dims = "\n".join(f"- {k}: {v}" for k, v in BENCHMARK_DIMENSIONS)
    return f"""你是 科创赛事助手 的「标杆对标 agent」。请严格、客观地评审下面这份【{export_type}】导出物，
把它与《质量标杆》逐维度对比，指出差距，不要客套、不要美化。

【质量标杆（节选）】
{benchmark_text[:4000]}

【待评审的导出物】
{export_text[:6000]}

【对标维度】
{dims}

【输出要求】只输出一个 JSON 对象，不要解释文字：
{{
  "scores": {{"structure": 0-100, "one_core_per_page": 0-100, "data_tracing": 0-100, "visual_system": 0-100, "real_product": 0-100, "charts_tables": 0-100, "competition_matrix": 0-100, "no_absolutize": 0-100, "blind_safe": 0-100, "ending_cta": 0-100}},
  "missing": ["缺失或明显不达标的具体项，逐条"],
  "pollution_risk": ["可能污染/编造/侵权的风险点，逐条；无则空数组"],
  "fixes": ["针对 missing 的可执行整改建议，逐条"],
  "overall": 0-100
}}"""


def parse_gap_report(resp: str) -> dict:
    """从 LLM 返回中解析差距报告；容错：找不到 JSON 返回空结构。"""
    try:
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"scores": {}, "missing": [], "pollution_risk": [], "fixes": [], "overall": None,
            "parse_error": True}


def _negated(text: str, phrase: str) -> bool:
    """判断 phrase 是否出现在否定语境（如「不写谢谢聆听」「禁止行业第一」），
    避免把禁令示例误判为违规。"""
    idx = text.find(phrase)
    if idx < 0:
        return False
    window = text[max(0, idx - 3):idx]
    return any(n in window for n in ["不", "禁止", "勿", "避免", "别", "拒", "无", "没有"])


def heuristic_review(export_text: str) -> dict:
    """无 LLM 时的规则自检，用于本地快速闸门（不替代 LLM 对标）。"""
    t = export_text or ""
    banned = ["行业第一", "彻底解决", "全球领先", "颠覆式", "独一无二", "世界第一"]
    hits_banned = [b for b in banned if b in t and not _negated(t, b)]
    has_thanks = (("谢谢聆听" in t) and not _negated(t, "谢谢聆听")) or \
                 (("敬请指正" in t) and not _negated(t, "敬请指正"))
    scores = {
        "no_absolutize": 0 if hits_banned else 100,
        "ending_cta": 0 if has_thanks else 100,
        "blind_safe": 100,  # 规则层无法判定，交由 LLM
    }
    missing = []
    if hits_banned:
        missing.append("出现绝对化词汇：" + "/".join(hits_banned))
    if has_thanks:
        missing.append("结尾页为「谢谢聆听/敬请指正」空页")
    return {
        "scores": scores, "missing": missing, "pollution_risk": [],
        "fixes": ["移除绝对化词汇", "结尾改为一句话定位+核心价值+下一步"] if missing else [],
        "overall": None, "mode": "heuristic",
    }


if __name__ == "__main__":
    # 自测：规则自检
    sample = "我们是世界上最牛的项目，谢谢聆听，敬请评委老师指正"
    print(json.dumps(heuristic_review(sample), ensure_ascii=False, indent=2))
