from competition_agents import deep_app, fast_app, CompetitionState

state: CompetitionState = {
    "competition_name": "iCAN大学生创新创业大赛",
    "rule_content": "评分维度：创新性30%，实用性25%，技术难度20%，团队展示15%，社会价值10%。",
    "idea": "基于计算机视觉的教室智能签到系统，通过摄像头识别学生人脸，自动完成签到，替代传统打卡",
    "parsed_rules": "",
    "similarity_report": "",
    "competitor_analysis": "",
    "business_model": "",
    "risk_analysis": "",
    "tech_solution": "",
    "proposal": "",
    "judge_feedback": "",
    "defense_questions": "",
    "ppt_outline": "",
    "one_liner": "",
    "score": 0,
    "revision_count": 0,
    "approved": False
}

print("开始测试深度版...")
result = deep_app.invoke(state)

print("\n=== 深度版各板块长度 ===")
print(f"竞品分析: {len(result['competitor_analysis'])} 字")
print(f"商业模式: {len(result['business_model'])} 字")
print(f"风险分析: {len(result['risk_analysis'])} 字")
print(f"技术方案: {len(result['tech_solution'])} 字")
print(f"申报书: {len(result['proposal'])} 字")
print(f"评委意见: {len(result['judge_feedback'])} 字")
print(f"答辩问题: {len(result['defense_questions'])} 字")
print(f"PPT大纲: {len(result['ppt_outline'])} 字")

print("\n=== 检查是否被截断（最后20个字）===")
print(f"竞品分析最后: ...{result['competitor_analysis'][-30:]}")
print(f"商业模式最后: ...{result['business_model'][-30:]}")
print(f"风险分析最后: ...{result['risk_analysis'][-30:]}")
print(f"技术方案最后: ...{result['tech_solution'][-30:]}")
print(f"申报书最后: ...{result['proposal'][-30:]}")
print(f"答辩问题最后: ...{result['defense_questions'][-30:]}")
print(f"PPT大纲最后: ...{result['ppt_outline'][-30:]}")
