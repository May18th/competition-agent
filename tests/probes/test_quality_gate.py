# -*- coding: utf-8 -*-
"""临时测试（2026-10-01 质量门 mode 感知 + 警告放行改造）。

复现云端 271 号记录场景：fast（简洁版）生成 + 缺 deep 专属板块 + 无图表 +
跨板块数字冲突，断言不再拦截（放行 + 警告）；deep 模式缺板块仍产出警告清单；
乱码正文仍拒绝。只 import quality_gate（不 import app，避免碰 .db / 起服务）。
"""
import sys

from quality_gate import check_generation, check_total, score_export

FAILED = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  -> {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


# ---------- 构造 271 号场景的 fast 产物 ----------
# 每段都带数据/技术词，避免触发「空话段落」凑数误判
_PROPOSAL = """## 一、项目背景与痛点
当前校园智能垃圾分类回收率不足20%，混投导致后端处理成本每吨高达800元，基于传感器的智能识别系统可解决该痛点。
## 二、技术方案与系统架构
系统采用边缘计算架构，部署轻量化图像识别模型（YOLOv8n，参数量3.2M），识别准确率实测94%，单次推理延迟120ms。
通过4G Cat.1模块上报数据至云端平台，接口采用MQTT协议，服务器月成本约150元。
## 三、商业模式
向学校按设备收取服务费，客单价每年12000元，预计覆盖50所学校时月收入可达50000元，毛利率约60%。
## 四、实施与验证
已在2所学校试点3个月，回收正确率从65%提升到91%，试点期间日均处理垃圾320公斤，付费转化率42%。"""

FAST_REC = {
    "mode": "fast",
    "proposal": _PROPOSAL,
    # fast 链路产物（comprehensive_analysis_agent 一次产出的四份分析 + 公共节点）
    "parsed_rules": "赛道：人工智能；评审权重：创新性30%…",
    "similarity_report": "与知识库范文最高重复率12%，未见整段抄袭。",
    "competitor_analysis": "现有竞品A依赖人工督导，成本高；竞品B无数据平台。",
    "business_model": "设备服务费模式：单校年均成本约250元/学生，客单价12000元/年；服务器月成本约150元。",
    "risk_analysis": "主要风险：寒暑假设备闲置；应对：与物业合租分摊。",
    "tech_solution": "边缘计算+轻量模型方案，服务器月成本约200元，识别准确率94%。",
    "judge_feedback": "创新性达标，建议补充试点数据。",
    "defense_questions": "1. 识别模型在弱光环境的表现？…",
    "ppt_outline": "封面/痛点/方案/数据/商业模式/团队/致谢",
    "speech_script": "各位评委好，我们的项目是……",
    # fast 没有的 deep 专属板块
    "implementation_plan": "",
    "social_value": "",
    "project_summary": "",
    # fast 没有图表 / deck 管线
    "rich_charts": [],
    "rich_tables": [],
    "rich_deck": None,
}

print("=" * 70)
print("场景一：271 号记录（fast + 缺 deep 板块 + 无图表 + 数字冲突）→ 应放行")
print("=" * 70)

# L1 生成质检：fast 不再报「富媒体（图表/表格）为空」
gok, gissues = check_generation(FAST_REC, "fast")
check("L1 fast 不再误报富媒体为空", "富媒体" not in "；".join(gissues), f"issues={gissues}")
check("L1 fast 整体通过（无图表/字数/deck 误报）", gok, f"issues={gissues}")

# 对照：deep 模式无图表仍要报（保留检查）
dok, dissues = check_generation(FAST_REC, "deep")
check("L1 deep 无图表仍报富媒体为空（deep 检查保留）",
      any("富媒体" in i for i in dissues), f"issues={dissues}")

# 总审：fast 不再报缺 implementation_plan / social_value / project_summary
tok, tissues = check_total(FAST_REC, "fast")
_t = "；".join(tissues)
check("总审 fast 不再误报缺 deep 专属板块",
      not any(k in _t for k in ("实施计划", "社会价值", "项目简介")),
      f"issues={tissues}")
# 数字冲突（成本 150/200/250）两档都保留 → 作为警告
check("总审 fast 仍检出成本数字冲突（降为警告）",
      any("跨板块数字冲突" in i and "成本" in i and "150" in i and "250" in i for i in tissues),
      f"issues={tissues}")
check("总审 fast 数字冲突文案为用户可读的警告",
      any("请核对统一口径" in i for i in tissues), "")

# 评分门：fast 不再因缺图表扣出 veto；hard 为空 → 不拦截
score, dims, reasons, hard = score_export(FAST_REC, "fast")
check("评分门 fast 不再报缺图表（mode 感知）", "缺图表" not in "；".join(reasons), f"reasons={reasons}")
check("评分门 fast 无硬错误（不拦截）", hard == [], f"hard={hard}")
# 模拟 export_word 的导出决策：blocked = bool(hard)
blocked = bool(hard)
check("271 场景导出决策：放行 + 警告清单", (not blocked) and len(reasons + tissues) > 0,
      f"blocked={blocked}, warnings={reasons + tissues}")

print()
print("=" * 70)
print("场景二：deep 模式 + 缺板块 → 仍产出完整警告清单")
print("=" * 70)

DEEP_REC = dict(FAST_REC)
DEEP_REC["mode"] = "deep"
d2ok, d2issues = check_total(DEEP_REC, "deep")
_d2 = "；".join(d2issues)
check("总审 deep 缺三板块仍全部报出",
      all(k in _d2 for k in ("实施计划", "社会价值", "项目简介")), f"issues={d2issues}")
s2, _, r2, h2 = score_export(DEEP_REC, "deep")
check("评分门 deep 缺图表仍进警告", "缺图表" in "；".join(r2), f"reasons={r2}")
check("评分门 deep 缺板块也只是警告不拦截", h2 == [] and (not bool(h2)), f"hard={h2}")
check("deep 导出决策：放行 + 警告", (not bool(h2)) and len(r2 + d2issues) > 0,
      f"warnings={r2 + d2issues}")

print()
print("=" * 70)
print("场景三：硬错误（乱码/空内容）仍拒绝")
print("=" * 70)

GARBLED = dict(FAST_REC)
GARBLED["proposal"] = "？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？？ ？？" * 20
s3, _, r3, h3 = score_export(GARBLED, "fast")
check("乱码正文 → hard 非空 → 仍拦截", bool(h3), f"hard={h3}")

EMPTY = dict(FAST_REC)
EMPTY["proposal"] = ""
s4, _, r4, h4 = score_export(EMPTY, "fast")
check("记录正文为空 → 软警告而非拦截（真正的空内容由导出接口判 400）",
      (not bool(h4)) and any("正文为空" in r for r in r4), f"hard={h4}, reasons={r4}")

print()
print("=" * 70)
if FAILED:
    print(f"结果：{len(FAILED)} 项失败 -> {FAILED}")
    sys.exit(1)
print("结果：全部通过")
