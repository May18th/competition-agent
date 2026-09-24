"""
科创赛事多智能体协同创作助手
核心工作流：规则解析 → 同质化检测 → 文稿生成 → 模拟评委 → 迭代
"""
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage


# ============ 配置 ============
import os

from dotenv import load_dotenv
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# 默认用DeepSeek，速度快便宜
llm = ChatDeepSeek(
    model="deepseek-chat",
    api_key=DEEPSEEK_API_KEY,
    temperature=0.5,
    max_tokens=6000
)

# Claude模型（火山引擎）
from langchain_openai import ChatOpenAI
claude_llm = ChatOpenAI(
    model="ep-20250923144558-7gqfz",
    api_key=CLAUDE_API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    temperature=0.5,
    max_tokens=6000
)

# GPT模型框架（后面加API key就能用，现在先注释掉）
# GPT_API_KEY = ""
# gpt_llm = ChatOpenAI(
#     model="gpt-4o",
#     api_key=GPT_API_KEY,
#     temperature=0.5,
#     max_tokens=6000
# )

# ============ 比赛知识库 ============
def load_competition_knowledge():
    """加载data目录里的所有比赛资料"""
    knowledge = {}
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith(".txt"):
                filepath = os.path.join(data_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    comp_name = filename.replace(".txt", "")
                    knowledge[comp_name] = f.read()
    return knowledge

# 启动时加载所有比赛资料
competition_knowledge = load_competition_knowledge()
print(f"📚 已加载 {len(competition_knowledge)} 个比赛知识库：{', '.join(competition_knowledge.keys())}")


def get_competition_knowledge(competition_name: str) -> str:
    """根据比赛名称，匹配对应的知识库内容"""
    if not competition_knowledge:
        return ""
    
    # 简单匹配：用户输入的比赛名，和知识库的比赛名，只要有包含关系就算匹配
    for known_name, content in competition_knowledge.items():
        if known_name in competition_name or competition_name in known_name:
            return f"\n【知识库中关于{known_name}的资料】\n{content}\n"
    
    return ""


# ============ 1. 定义共享状态 ============
def merge_state(old, new):
    """并行的时候，后写的覆盖先写的"""
    return new

class CompetitionState(TypedDict):
    # 输入
    competition_name: str
    rule_content: str
    idea: str

    # 中间结果
    parsed_rules: str
    similarity_report: str
    competitor_analysis: str
    business_model: str
    risk_analysis: str
    tech_solution: str
    implementation_plan: str
    social_value: str
    project_summary: str
    proposal: str
    judge_feedback: str
    defense_questions: str
    ppt_outline: str
    speech_script: str
    one_liner: str
    score: int
    approved: bool

    # 控制
    revision_count: int
    approved: bool              # 是否通过


# ============ 2. 四个 Agent ============

def rule_parser_agent(state: CompetitionState) -> CompetitionState:
    """📋 规则解析 Agent：提取评分标准"""
    # 先查知识库，有没有这个比赛的资料
    kb_content = get_competition_knowledge(state['competition_name'])
    
    # 如果用户没上传规则，就说根据知识库来分析
    if not state['rule_content'] or state['rule_content'].strip() == '':
        rule_content_text = "用户没有上传规则PDF，请根据知识库中关于这个比赛的资料来分析。"
    else:
        rule_content_text = f"用户上传的规则内容：\n{state['rule_content']}"
    
    prompt = f"""你是赛事规则分析专家。请分析这个比赛的核心评分标准和要求。

赛事名称：{state['competition_name']}
{kb_content}
{rule_content_text}

请提取：
1. 核心评分维度（如创新性、实用性、技术难度等）及各维度占比
2. 申报书必须包含的章节和要求
3. 这个比赛偏好什么样的项目
4. 关键注意事项

输出格式清晰，分点列出。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["parsed_rules"] = response.content
    print(f"📋 规则解析 Agent：已提取评分标准")
    return state


def similarity_checker_agent(state: CompetitionState) -> CompetitionState:
    """🔍 同质化检测 Agent：检测创意相似度"""
    prompt = f"""你是科创赛事资深评委，熟悉各类获奖项目。请检测以下创意与常见获奖项目的同质化程度。

赛事：{state['competition_name']}
项目创意：{state['idea']}

请分析：
1. 这个创意和往届常见获奖项目有没有高度重合？
2. 哪些部分容易撞车？
3. 如何差异化突出，避免同质化？

给出具体的改进建议。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["similarity_report"] = response.content
    print(f"🔍 同质化检测 Agent：已完成分析")
    return state


def comprehensive_analysis_agent(state: CompetitionState) -> CompetitionState:
    """📊 综合分析 Agent：一次生成竞品、商业模式、风险、技术方案"""
    prompt = f"""你是科创赛事分析专家。请根据以下项目，一次性完成所有分析。

项目创意：{state['idea']}

请分四部分输出：

## 一、竞品分析
1. 同类产品（至少3个）
2. 我们的差异化优势

## 二、商业模式
1. 目标客户
2. 盈利模式
3. 成本与盈利预测

## 三、风险分析
1. 技术风险及应对
2. 市场风险及应对

## 四、技术方案
1. 整体架构
2. 核心技术点
3. 技术路线

输出简洁，分点列出。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content
    
    # 直接把完整内容都存到 competitor_analysis 里，不拆分了
    state["competitor_analysis"] = text
    state["business_model"] = text  # 先都存同一个内容，避免报错
    state["risk_analysis"] = text
    state["tech_solution"] = text
    
    print(f"📊 综合分析 Agent：已完成（竞品+商业模式+风险+技术）")
    return state


# ============ 深度版专用的四个分析 Agent ============

def deep_competitor_agent(state: CompetitionState) -> CompetitionState:
    """🏢 深度版竞品分析 Agent"""
    prompt = f"""你是资深市场分析专家。请只负责分析竞品情况，不要写商业模式、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 市场上至少 5 个同类产品/解决方案，每个的优缺点
2. 从功能、价格、目标用户、技术壁垒四个维度做对比表格
3. 我们的项目有什么差异化竞争优势，为什么能赢

注意：你只负责竞品分析，不要写怎么赚钱、不要写技术实现、不要写风险。控制在1000字左右。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["competitor_analysis"] = response.content
    print(f"🏢 深度版竞品分析：已完成")
    return state


def deep_business_agent(state: CompetitionState) -> CompetitionState:
    """💰 深度版商业模式 Agent"""
    prompt = f"""你是资深商业模式专家。请只负责设计商业模式，不要写竞品分析、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 目标客户细分（至少3类，每类的痛点和付费意愿）
2. 具体盈利模式（至少2种收入来源，定价策略）
3. 成本结构（研发、运营、营销各占多少）
4. 3年财务预测（收入、成本、利润）

注意：你只负责商业模式，不要写竞品对比、不要写技术实现、不要写风险。控制在1000字左右。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["business_model"] = response.content
    print(f"💰 深度版商业模式：已完成")
    return state


def deep_risk_agent(state: CompetitionState) -> CompetitionState:
    """⚠️ 深度版风险分析 Agent"""
    prompt = f"""你是资深风险评估专家。请只负责分析风险，不要写商业模式、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 技术风险（具体有哪些技术难题，怎么应对）
2. 市场风险（市场接受度、竞争加剧怎么办）
3. 政策合规风险（数据隐私、政策变化）
4. 团队和财务风险

每个风险都要有具体的应对措施。注意：你只负责风险分析，不要写竞品、不要写商业模式、不要写技术架构。控制在1000字左右。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["risk_analysis"] = response.content
    print(f"⚠️ 深度版风险分析：已完成")
    return state


def deep_tech_agent(state: CompetitionState) -> CompetitionState:
    """🔧 深度版技术方案 Agent"""
    prompt = f"""你是资深技术架构师。请只负责写技术方案，不要写竞品、商业模式、风险等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 整体技术架构（分几层，每层用什么技术）
2. 核心技术难点（为什么难，我们怎么解决）
3. 技术路线图（分阶段，每个阶段做什么）
4. 关键技术选型（为什么选这个技术）

注意：你只负责技术方案，不要写怎么赚钱、不要写竞品、不要写风险。控制在1000字左右。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["tech_solution"] = response.content
    print(f"🔧 深度版技术方案：已完成")
    return state


def plan_agent(state: CompetitionState) -> CompetitionState:
    """🗓️ 项目实施计划 Agent"""
    prompt = f"""你是科创项目规划专家。请为以下项目制定详细的实施计划。

项目创意：{state['idea']}

请写：
1. 分阶段计划（共8周，每周做什么，交付什么成果）
2. 每个阶段的里程碑和验收标准
3. 团队分工（5个人分别负责什么）
4. 风险预案（如果延期了怎么办）

控制在1000字左右，清晰有条理。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["implementation_plan"] = response.content
    print(f"🗓️ 项目实施计划：已生成")
    return state


def social_value_agent(state: CompetitionState) -> CompetitionState:
    """🌍 社会价值 Agent"""
    prompt = f"""你是科创项目价值分析专家。请分析这个项目的社会价值和应用前景。

项目创意：{state['idea']}

请写：
1. 社会价值（解决了什么社会问题，惠及哪些人群）
2. 应用前景（可以推广到哪些行业/场景）
3. 推广路径（先从哪里开始，怎么扩大）
4. 长期愿景（3-5年后想做成什么样）

控制在1000字左右，要有高度，不要太商业化。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["social_value"] = response.content
    print(f"🌍 社会价值：已生成")
    return state


def summary_agent(state: CompetitionState) -> CompetitionState:
    """📝 项目简介 Agent：生成300字项目摘要"""
    prompt = f"""请根据以下项目，写一段300字左右的项目简介：

项目创意：{state['idea']}
一句话定位：{state.get('one_liner', '')}

要求：
1. 开头讲痛点
2. 中间讲解决方案
3. 结尾讲价值和优势
4. 语言正式，适合写申报书开头

控制在300字左右。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["project_summary"] = response.content
    print(f"📝 项目简介：已生成")
    return state


def deep_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 深度版申报书 Agent：写完整详细的申报书"""
    prompt = f"""你是资深科创赛事申报书写作专家。
注意：用户已经上传了一份现成的申报书草稿，你的任务是**优化这份申报书**，保留用户原来的内容和结构，不要从零开始重新写，只是把写得不好的地方改好，补充不足的内容，让它更符合比赛要求。

用户上传的申报书草稿：{state['idea']}

注意：
1. 保留用户原来的核心内容和结构，不要全部推翻重写
2. 把写得太简略的地方补充完整
3. 把逻辑不通的地方理顺
4. 加上比赛需要的评分点
5. 前面分析的竞品、商业模式、风险、技术方案内容，融入到申报书里，补充用户草稿里不足的地方

请写一份完整详细的申报书，总共2000字以上，每个章节都要展开写，不要简略，包含以下章节：
1. 项目背景与痛点（300字，详细讲现在行业有什么问题，用户痛点有多严重，数据支撑）
2. 解决方案（400字，详细讲我们的产品是什么，怎么解决这些问题，核心功能）
3. 技术路线（400字，整合前面的技术方案，讲清楚技术架构、关键技术实现）
4. 核心创新点（300字，和现有方案比，我们的3个核心创新点是什么，为什么别人做不到）
5. 商业模式（300字，整合前面的商业模式，讲清楚怎么赚钱，目标用户）
6. 风险与应对（200字，整合前面的风险分析，讲清楚我们怎么应对）
7. 社会价值与应用前景（100字，讲这个项目的意义）

要求：内容详细，逻辑清晰，不要用markdown符号，直接写正文，每个章节展开写，不要太简略。
5. 商业模式（整合前面的商业模式分析）
6. 竞争优势（整合前面的竞品分析）
7. 应用价值
8. 风险与应对（整合前面的风险分析）

输出详细完整，不要重复前面已经说过的内容。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["proposal"] = response.content
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 深度版申报书：第 {state['revision_count']} 版")
    return state


def proposal_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 简洁版申报书 Agent：写精简的申报书"""
    prompt = f"""你是科创赛事申报书写作专家。请根据以下分析结果，写一份精简的申报书。

赛事：{state['competition_name']}
项目创意：{state['idea']}
规则解析：{state['parsed_rules']}
同质化分析：{state['similarity_report']}
竞品分析：{state['competitor_analysis']}
商业模式：{state['business_model']}
风险分析：{state['risk_analysis']}
技术方案：{state['tech_solution']}

请按以下结构写，总共500字左右，简洁明了：

## 项目简介
（100字，一句话说清楚这个项目是做什么的）

## 痛点分析
（100字，现在这个领域有什么问题，用户有什么麻烦）

## 解决方案
（150字，我们的产品是什么，怎么解决这些问题）

## 核心创新点
（100字，和现有方案比，我们好在哪里，有什么不一样）

## 社会价值
（50字，这个项目能带来什么好处，有什么意义）

【简洁版要求】不要写商业模式、技术方案这些复杂内容，就写以上5部分，500字以内，快速出结果。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["proposal"] = response.content
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 简洁版申报书：第 {state['revision_count']} 版")
    return state


def judge_agent(state: CompetitionState) -> CompetitionState:
    """⚖️ 模拟评委 Agent：打分提意见"""
    prompt = f"""你是科创赛事资深评委。请给以下申报书打分并提修改意见。

申报书：{state['proposal']}

请输出：
1. 总分（60-85分之间，不要打太低，正常大学生项目一般在这个区间）
2. 主要优点（至少写3点）
3. 需要改进的地方（至少写3点）

打分标准：创新性30%，实用性25%，技术难度20%，完整性15%，商业价值10%。
打分要客观合理，不要故意打低分，这是大学生项目，不要用职业项目的标准要求。
根据申报书实际内容质量打分：
- 如果申报书内容详细、有具体细节和数字，创新性强，打78-85分
- 如果申报书内容一般，结构完整但细节不足，打70-77分
- 如果申报书内容简略，只有核心要点，打65-72分
不要固定分数，根据实际内容调整。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["judge_feedback"] = response.content
    
    # 简单提取分数
    import re
    match = re.search(r'(\d+)\s*分', response.content)
    if match:
        state["score"] = int(match.group(1))
    else:
        state["score"] = 60
    
    state["approved"] = state["score"] >= 70
    print(f"⚖️ 评委 Agent：打分 {state['score']} 分")
    return state


def defense_questions_agent(state: CompetitionState) -> CompetitionState:
    """🎤 答辩问题预测 Agent：预测评委可能问什么"""
    prompt = f"""你是科创赛事答辩专家。请预测评委可能会问的 5 个问题，并给出答题思路。

项目：{state['idea']}
评委意见：{state['judge_feedback']}

输出 5 个问题，每个问题附简短答题思路。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["defense_questions"] = response.content
    print(f"🎤 答辩问题 Agent：已生成")
    return state


def ppt_outline_agent(state: CompetitionState) -> CompetitionState:
    """📊 PPT 大纲 Agent：生成路演 PPT 大纲"""
    prompt = f"""你是科创赛事路演 PPT 专家。请根据以下项目，生成 3 分钟路演 PPT 大纲（8-10页）。

项目：{state['idea']}
一句话定位：{state['one_liner']}

输出每页的标题和要点。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["ppt_outline"] = response.content
    print(f"📊 PPT 大纲 Agent：已生成")
    return state


def speech_agent(state: CompetitionState) -> CompetitionState:
    """🎤 路演演讲稿 Agent：生成3分钟路演讲稿"""
    prompt = f"""你是科创赛事路演专家。请根据以下项目，生成3分钟路演演讲稿。

项目：{state['idea']}
一句话定位：{state['one_liner']}
PPT大纲：{state['ppt_outline']}

请写：
1. 开场（30秒）：抓眼球，讲痛点
2. 中间（2分钟）：讲解决方案、创新点、竞品对比
3. 结尾（30秒）：讲价值、呼吁

语言口语化，有感染力，照着念就行，不要太书面。
控制在600字左右（3分钟语速）。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["speech_script"] = response.content
    print(f"🎤 路演演讲稿：已生成")
    return state


def one_liner_agent(state: CompetitionState) -> CompetitionState:
    """💡 一句话定位 Agent：生成路演开场一句话"""
    prompt = f"""请用一句话（30字以内）概括这个项目，用来路演开场。

项目：{state['idea']}

直接输出一句话，不要解释。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["one_liner"] = response.content.strip()
    print(f"💡 一句话定位 Agent：已生成")
    return state


# ============ 3. 路由 ============
def should_iterate(state: CompetitionState) -> Literal["writer", "defense"]:
    if state["approved"] or state["revision_count"] >= 1:
        return "defense"
    else:
        return "writer"


# ============ 4. 构建工作流 ============
workflow = StateGraph(CompetitionState)

workflow.add_node("rule_parser", rule_parser_agent)
workflow.add_node("similarity_checker", similarity_checker_agent)
workflow.add_node("analysis", comprehensive_analysis_agent)
workflow.add_node("plan", plan_agent)
workflow.add_node("social", social_value_agent)
workflow.add_node("summary", summary_agent)
workflow.add_node("writer", proposal_writer_agent)
workflow.add_node("judge", judge_agent)
workflow.add_node("defense", defense_questions_agent)
workflow.add_node("ppt", ppt_outline_agent)
workflow.add_node("speech", speech_agent)

workflow.add_edge(START, "rule_parser")
workflow.add_edge("rule_parser", "similarity_checker")
workflow.add_edge("similarity_checker", "writer")
workflow.add_edge("writer", "judge")
workflow.add_edge("judge", END)


fast_app = workflow.compile()

# 建深度版工作流：四个分析Agent分开跑
deep_workflow = StateGraph(CompetitionState)
deep_workflow.add_node("rule_parser", rule_parser_agent)
deep_workflow.add_node("similarity_checker", similarity_checker_agent)
deep_workflow.add_node("competitor", deep_competitor_agent)
deep_workflow.add_node("business", deep_business_agent)
deep_workflow.add_node("risk", deep_risk_agent)
deep_workflow.add_node("tech", deep_tech_agent)
deep_workflow.add_node("plan", plan_agent)
deep_workflow.add_node("social", social_value_agent)
deep_workflow.add_node("summary", summary_agent)
deep_workflow.add_node("writer", deep_writer_agent)
deep_workflow.add_node("judge", judge_agent)
deep_workflow.add_node("defense", defense_questions_agent)
deep_workflow.add_node("ppt", ppt_outline_agent)
deep_workflow.add_node("speech", speech_agent)

deep_workflow.add_edge(START, "rule_parser")
deep_workflow.add_edge("rule_parser", "similarity_checker")
deep_workflow.add_edge("similarity_checker", "competitor")
deep_workflow.add_edge("competitor", "business")
deep_workflow.add_edge("business", "risk")
deep_workflow.add_edge("risk", "tech")
deep_workflow.add_edge("tech", "plan")
deep_workflow.add_edge("plan", "social")
deep_workflow.add_edge("social", "summary")
deep_workflow.add_edge("summary", "writer")
deep_workflow.add_edge("writer", "judge")
deep_workflow.add_conditional_edges(
    "judge",
    should_iterate,
    {
        "writer": "writer",
        "defense": "defense"
    }
)
deep_workflow.add_edge("defense", "ppt")
deep_workflow.add_edge("ppt", "speech")
deep_workflow.add_edge("speech", END)

deep_app = deep_workflow.compile()


# ============ 5. 运行 ============
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 科创赛事多智能体协同创作助手")
    print("=" * 60)
    print()

    result = app.invoke({
        "competition_name": "iCAN 大学生创新创业大赛",
        "rule_content": "评分维度：创新性30%，实用性25%，技术难度20%，团队展示15%，社会价值10%。申报书需包含项目背景、解决方案、技术路线、应用前景。",
        "idea": "基于计算机视觉的教室智能签到系统，通过摄像头识别学生人脸，自动完成签到，替代传统打卡",
        "parsed_rules": "",
        "similarity_report": "",
        "proposal": "",
        "judge_feedback": "",
        "score": 0,
        "revision_count": 0,
        "approved": False
    })

    print()
    print("=" * 60)
    print("📊 最终结果")
    print("=" * 60)
    print(f"\n【规则解析】\n{result['parsed_rules'][:200]}...")
    print(f"\n【同质化检测】\n{result['similarity_report'][:200]}...")
    print(f"\n【申报书全文】\n{result['proposal']}")
    print(f"\n【评委意见】\n{result['judge_feedback']}")
    print(f"\n最终得分：{result['score']}/100")
    print(f"修改次数：{result['revision_count']}")
    print("=" * 60)
