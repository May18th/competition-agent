"""
科创赛事多智能体协同创作助手
核心工作流：规则解析 → 同质化检测 → 文稿生成 → 模拟评委 → 迭代
"""
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage
from stage_reporter import report_stage as _report_stage


# ============ 配置 ============
import os
import re

from dotenv import load_dotenv
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# sanitize NO_PROXY for httpx2 compatibility (it crashes on "::1" and ";" separators)
_no_proxy = os.environ.get("NO_PROXY", "")
if _no_proxy:
    os.environ["NO_PROXY"] = ",".join(x for x in _no_proxy.replace("::1", "").replace(";", ",").split(",") if x)

# 默认用DeepSeek，速度快便宜
# max_tokens=8192 是 deepseek-chat 单次输出上限：申报书要求 3500 字以上，调小会被截断成半篇
# request_timeout=180：输出 8192 token 需要 1～2 分钟，60 秒会超时断流
llm = ChatDeepSeek(
    model="deepseek-chat",
    api_key=DEEPSEEK_API_KEY,
    temperature=0.3,
    max_tokens=8192,
    request_timeout=180,
    max_retries=3
)

# ============ API 配额保护（防止 DeepSeek 超支） ============
import json as _json
from datetime import datetime as _datetime

_QUOTA_FILE = os.path.join(os.path.dirname(__file__), "quota.json")
_QUOTA_DAILY_LIMIT = int(os.getenv("QUOTA_DAILY_LIMIT", "500"))


def _quota_today():
    return _datetime.now().strftime("%Y-%m-%d")


def _quota_load():
    try:
        with open(_QUOTA_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if data.get("date") == _quota_today():
            return data
    except Exception:
        pass
    return {"date": _quota_today(), "calls": 0}


def _quota_save(data):
    try:
        with open(_QUOTA_FILE, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def get_quota_status():
    """返回今日配额使用情况（供 /api/quota 与前端展示）"""
    data = _quota_load()
    calls = data.get("calls", 0)
    return {
        "date": data.get("date"),
        "calls": calls,
        "limit": _QUOTA_DAILY_LIMIT,
        "remaining": max(0, _QUOTA_DAILY_LIMIT - calls),
        "exceeded": calls >= _QUOTA_DAILY_LIMIT,
    }


_llm_invoke_original = llm.invoke


def _llm_invoke_with_quota(*args, **kwargs):
    data = _quota_load()
    if data.get("calls", 0) >= _QUOTA_DAILY_LIMIT:
        raise RuntimeError(f"今日 LLM 调用已达上限（{_QUOTA_DAILY_LIMIT} 次），请明天再试")
    result = _llm_invoke_original(*args, **kwargs)
    data["calls"] = data.get("calls", 0) + 1
    _quota_save(data)
    return result


# ChatDeepSeek 是 pydantic 模型，需用 object.__setattr__ 绕过字段校验来 monkey-patch
object.__setattr__(llm, "invoke", _llm_invoke_with_quota)

# Claude模型（火山引擎）
# from langchain_openai import ChatOpenAI
# claude_llm = ChatOpenAI(
#     model="ep-20250923144558-7gqfz",
#     api_key=CLAUDE_API_KEY,
#     base_url="https://ark.cn-beijing.volces.com/api/v3",
#     temperature=0.5,
#     max_tokens=6000
# )

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


_ALIAS_GROUPS = [
    ["国创", "国创项目", "国创计划", "大创", "国家级大学生创新创业训练计划"],
    ["挑战杯", "大挑", "小挑"],
    ["互联网+", "互联网加", "互联网＋"],
]


def _same_alias_group(a, b):
    for group in _ALIAS_GROUPS:
        if any(x in a for x in group) and any(x in b for x in group):
            return True
    return False


def _competition_match(known, query):
    """宽松匹配比赛名：去掉通用词后看是否有共同关键词"""
    if not known or not query:
        return False
    if known in query or query in known:
        return True
    if _same_alias_group(known, query):
        return True
    common_words = ["大学生", "全国", "中国", "国际", "大赛", "竞赛", "训练计划", "计划", "创新创业", "创业"]
    def _tokens(s):
        for w in common_words:
            s = s.replace(w, " ")
        return {t for t in s.split() if len(t) >= 2}
    return bool(_tokens(known) & _tokens(query))


def get_competition_knowledge(competition_name: str) -> str:
    """根据比赛名称，匹配对应的知识库内容"""
    if not competition_knowledge:
        return ""
    
    # 宽松匹配：包含关系 或 关键词重叠
    for known_name, content in competition_knowledge.items():
        if _competition_match(known_name, competition_name):
            return f"\n【知识库中关于{known_name}的资料】\n{content}\n"
    
    return ""


# 知识库格式要求（队友提交资料需包含的关键章节）
KNOWLEDGE_SECTIONS = {
    "比赛介绍": ["介绍", "比赛"],
    "评分标准": ["评分标准", "评分维度", "评分"],
    "申报书章节": ["申报书", "章节", "必须包含"],
    "偏好方向": ["偏好", "方向"],
    "常见扣分点": ["扣分点", "扣分", "注意事项"],
}

# 预期收录的赛事（用于提示还缺哪些）
EXPECTED_COMPETITIONS = [
    "互联网+", "挑战杯", "iCAN", "国创", "金砖", "数学建模", "电子设计",
    "西门子", "计算机设计", "RoboMaster", "信息安全",
]


def check_knowledge_format(content: str) -> dict:
    """校验单个知识库文件是否包含必要章节，返回缺失项"""
    missing = []
    detail = {}
    for key, keywords in KNOWLEDGE_SECTIONS.items():
        ok = any(kw in (content or "") for kw in keywords)
        detail[key] = ok
        if not ok:
            missing.append(key)
    return {"ok": not missing, "missing": missing, "detail": detail, "chars": len(content or "")}


def get_knowledge_status() -> dict:
    """返回知识库收录状态 + 每个文件的格式校验结果"""
    import glob
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    files = []
    for filepath in sorted(glob.glob(os.path.join(data_dir, "*.txt"))):
        name = os.path.basename(filepath).replace(".txt", "")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = ""
        files.append({"name": name, **check_knowledge_format(content)})

    loaded_names = list(competition_knowledge.keys())
    missing = []
    for exp in EXPECTED_COMPETITIONS:
        if not any(exp in n or n in exp for n in loaded_names):
            missing.append(exp)

    return {
        "loaded_count": len(competition_knowledge),
        "loaded_names": loaded_names,
        "files": files,
        "missing": missing,
        "coverage": f"{len(competition_knowledge)}/{len(EXPECTED_COMPETITIONS)}",
    }


# 申报书核心章节（用于生成后完整性校验，提示性质）
PROPOSAL_REQUIRED_SECTIONS = [
    ("项目背景", ["项目背景", "背景", "痛点"]),
    ("解决方案", ["解决方案", "方案"]),
    ("技术路线", ["技术路线", "技术方案", "技术架构", "技术实现"]),
    ("核心创新点", ["创新"]),
    ("商业模式", ["商业模式", "盈利", "变现"]),
    ("风险与应对", ["风险"]),
    ("社会价值", ["社会价值", "应用前景", "前景"]),
]

# 简洁版只写 5 节（项目简介/痛点分析/解决方案/核心创新点/社会价值），
# 不包含「技术路线」「商业模式」，所以用独立章节标准，避免误报缺章节。
PROPOSAL_REQUIRED_SECTIONS_FAST = [
    ("项目简介", ["项目简介", "简介"]),
    ("痛点分析", ["痛点"]),
    ("解决方案", ["解决方案", "方案"]),
    ("核心创新点", ["创新"]),
    ("社会价值", ["社会价值"]),
]


def check_proposal_completeness(proposal: str, mode: str = "deep") -> dict:
    """检查申报书是否覆盖核心章节，返回缺失项（提示性质，不阻断）。

    mode='fast' 时按简洁版 5 节校验，否则按深度版 7 节校验。
    """
    text = proposal or ""
    sections = PROPOSAL_REQUIRED_SECTIONS_FAST if mode == "fast" else PROPOSAL_REQUIRED_SECTIONS
    missing = []
    detail = {}
    for name, keywords in sections:
        ok = any(kw in text for kw in keywords)
        detail[name] = ok
        if not ok:
            missing.append(name)
    return {"ok": not missing, "missing": missing, "detail": detail, "chars": len(text)}


def parse_knowledge(content: str) -> dict:
    """把知识库 txt 解析成结构化字段（按 ## 标题切分）"""
    result = {
        "title": "", "intro": "", "scoring": "", "sections": "",
        "preference": "", "penalty": "", "raw": content or "",
    }
    if not content:
        return result
    buf = {}
    current = None
    for line in (content or "").split("\n"):
        line = line.rstrip()
        if line.startswith("# ") and not line.startswith("## "):
            result["title"] = line[2:].strip()
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            buf[current] = []
            continue
        if current is not None:
            buf[current].append(line)

    def _join(keywords):
        for k, v in buf.items():
            if any(kw in k for kw in keywords):
                return "\n".join(v).strip()
        return ""

    result["intro"] = _join(["介绍", "简介"])
    result["scoring"] = _join(["评分", "打分"])
    result["sections"] = _join(["章节", "申报书", "结构", "必须包含"])
    result["preference"] = _join(["偏好", "方向", "喜欢"])
    result["penalty"] = _join(["扣分", "注意", "误区"])
    return result


def get_competition_knowledge_structured(competition_name: str) -> dict:
    """按比赛名匹配，返回结构化知识库字段（matched=False 表示未收录）"""
    empty = {"matched": False, "matched_name": "", "title": "", "intro": "",
             "scoring": "", "sections": "", "preference": "", "penalty": ""}
    if not competition_knowledge:
        return empty
    for known_name, content in competition_knowledge.items():
        if _competition_match(known_name, competition_name):
            parsed = parse_knowledge(content)
            parsed["matched"] = True
            parsed["matched_name"] = known_name
            return parsed
    return empty


# ============ 1. 定义共享状态 ============
def merge_state(old, new):
    """并行的时候，后写的覆盖先写的"""
    return new

class CompetitionState(TypedDict):
    # 输入
    competition_name: str
    rule_content: str
    idea: str
    proposal_draft: str

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
    proposal_analysis: str
    defense_questions: str
    ppt_outline: str
    speech_script: str
    rich_media: str
    one_liner: str
    idea_score: int
    idea_feedback: str
    score: int
    approved: bool

    # 控制
    revision_count: int
    iterate: bool


# ============ 内容层：输出规格约束（统一提升各 Agent 输出质量）============

_REPORT_SPEC = """【输出规格 —— 必须遵守】
1. 使用 Markdown，最多三级标题（## / ###），一级用「一、二、三、」，二级用「（一）（二）」，三级用「1. 2. 3.」
2. 三级标题必须是正式短语，不是完整句子
3. 结构必须包含：摘要 / 背景 / 内容 / 分析 / 总结 / 展望
4. 每个小节必须写成 150～400 字的完整段落，有论点、有展开、有依据；严禁一句话一段、严禁短句罗列
5. 严禁整篇用序号罗列（不要「1. xxx  2. xxx」这种清单体），把要点串成连贯段落
6. 需要逐条对比时用标准 Markdown 表格（| a | b | 换行 |---|---|），不要用序号列表
7. 全文中文标点用全角
"""

_PROPOSAL_SPEC = """【申报书输出规格 —— 优先级最高，覆盖上面所有通用规格】
1. 篇幅：正文 3500～4500 字，低于 3000 字视为不合格。这是一份要提交给评委的完整申报书，不是提纲也不是摘要。
2. 结构：使用 Markdown，最多三级标题（## / ###），一级用「一、二、三、」，二级用「（一）（二）」，三级用「1. 2. 3.」
3. 密度：每个二级小节至少 300 字，拆成 2～3 个自然段，每段不少于 150 字；要有论点、有展开、有依据，严禁一句话一段
4. 严禁空小节：任何标题下面都必须有正文段落，不允许只放一个表格、也不允许标题下面是空的
5. 严禁通篇序号罗列；只有需要逐条对比时才用标准 Markdown 表格，且表格前后都必须有说明段落
6. 每一节都要落到具体事实上：真实场景名称、具体数字（测算值要标明是测算）、具体技术名词与参数、具体执行步骤与时间点。禁止「大幅提高效率」「具有广阔前景」「赋能行业」这类没有信息量的表述
7. 全文中文标点用全角
"""

_ANALYSIS_SPEC = """【输出规格 —— 必须遵守】
1. 必须分段阐述，不能只给结论清单
2. 每个维度按「现状 → 原因 → 影响 → 应对」写成完整段落，不要一句话一行
3. 需要对比时用标准 Markdown 表格
4. 全文中文标点用全角
"""

_OUTLINE_SPEC = """【输出规格 —— 必须遵守】
1. 只要层级清晰的条目，不要段落、不要大段阐述
2. 每页/每条一行短语，不要写完整句子
"""

_OPTIMIZE_SPEC = """【优化输出规格 —— 必须遵守】
1. 优化输出必须保持原申报表的条目结构一一对应：不合并条目、不拆分条目、不新增条目
2. 不加 Markdown 标题符号，每一条只输出改写后的文字
3. 每条优化后的文字长度与原条目大致相当（±30% 以内），宁可精炼也不要大幅膨胀，避免撑破原表格版式
"""


def _cjk_len(text):
    """统计正文有效字数：去掉空白和 Markdown 标记符号后再计数。

    len() 直接算会把 #、*、|、- 这些排版符号也算成字数，导致篇幅判断虚高，
    所以这里先剥掉标记符号，只数真正会被评委看到的内容。
    """
    return len(re.sub(r'[#*`\-\|>\[\]（）()\s]', '', text or ''))


def _expand_to_length(text, min_chars, topic, rounds=2):
    """篇幅兜底：正文不足 min_chars 字时，让模型就地扩写，最多 rounds 轮。

    只在篇幅不够时才发起 LLM 调用；已达标则原样返回，不额外花钱。
    返回 (最终文本, 最终字数)。
    """
    cur = text or ''
    n = _cjk_len(cur)
    for i in range(rounds):
        if n >= min_chars:
            break
        prompt = (
            "下面是关于「%s」的一份科创赛事申报书，当前正文只有约 %d 字，"
            "而要求是不少于 %d 字，篇幅严重不足，评委会认定内容空洞。\n\n"
            "请在**不改变章节结构、不删减已有内容**的前提下做扩写：\n"
            "1. 每一节补充更具体的场景、数据测算、技术参数、实施步骤与风险应对；\n"
            "2. 每个二级小节扩写到 300 字以上，拆成 2～3 个自然段；\n"
            "3. 任何标题下面都必须有正文，不允许出现空小节；\n"
            "4. 保持 Markdown 标题层级不变，中文标点用全角。\n\n"
            "直接输出扩写后的完整申报书全文，不要加任何说明。\n\n"
            "当前申报书：\n%s"
            % (topic, n, min_chars, cur)
        )
        cur = llm.invoke([HumanMessage(content=prompt)]).content
        n = _cjk_len(cur)
        print(f"📏 篇幅兜底第 {i + 1} 轮：{n} 字（目标 {min_chars}）")
    return cur, n


# ============ 2. 四个 Agent ============

def rule_parser_agent(state: CompetitionState) -> CompetitionState:
    """📋 规则解析 Agent：提取评分标准"""
    _report_stage("parsing_rules")
    # 先查知识库（结构化，缺失字段明确标注，避免模型瞎编）
    kb = get_competition_knowledge_structured(state['competition_name'])
    if kb.get("matched"):
        kb_block = f"""【知识库中关于{kb['matched_name']}的资料】
- 比赛介绍：{kb['intro'] or '（无）'}
- 评分标准：{kb['scoring'] or '（无）'}
- 申报书必须包含的章节：{kb['sections'] or '（知识库未提供，请按通用竞赛常识推断）'}
- 偏好方向：{kb['preference'] or '（无）'}
- 常见扣分点：{kb['penalty'] or '（无）'}
"""
    else:
        kb_block = "（知识库未收录该赛事，请根据用户上传的规则或通用竞赛常识分析）"
    
    # 如果用户没上传规则，就说根据知识库来分析
    if not state['rule_content'] or state['rule_content'].strip() == '':
        rule_content_text = "用户没有上传规则PDF，请根据知识库中关于这个比赛的资料来分析。"
    else:
        rule_content_text = f"用户上传的规则内容：\n{state['rule_content']}"
    
    prompt = f"""你是赛事规则分析专家。请分析这个比赛的核心评分标准和要求。

赛事名称：{state['competition_name']}
{kb_block}
{rule_content_text}

请提取：
1. 核心评分维度（如创新性、实用性、技术难度等）及各维度占比
2. 申报书必须包含的章节和要求
3. 这个比赛偏好什么样的项目
4. 关键注意事项

{_REPORT_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    print(f"📋 规则解析 Agent：已提取评分标准")
    return {"parsed_rules": response.content}


def similarity_checker_agent(state: CompetitionState) -> CompetitionState:
    """🔍 同质化检测 Agent：检测创意相似度"""
    _report_stage("similarity")
    prompt = f"""你是科创赛事资深评委，熟悉各类获奖项目。请检测以下创意与常见获奖项目的同质化程度。

赛事：{state['competition_name']}
项目创意：{state['idea']}

请分析：
1. 这个创意和往届常见获奖项目有没有高度重合？
2. 哪些部分容易撞车？
3. 如何差异化突出，避免同质化？

给出具体的改进建议。

{_REPORT_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    print(f"🔍 同质化检测 Agent：已完成分析")
    return {"similarity_report": response.content}


def comprehensive_analysis_agent(state: CompetitionState) -> CompetitionState:
    """📊 综合分析 Agent：一次生成竞品、商业模式、风险、技术方案"""
    _report_stage("analysis")
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

每个部分都要写成完整段落（现状→原因→影响→应对），不要只列要点、不要一句话一行。

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content

    # 按四个标题拆分，正确对应到四个字段
    import re
    parts = re.split(r"##\s*[一二三四]、", text)
    if len(parts) >= 5:
        state["competitor_analysis"] = parts[1].strip()
        state["business_model"] = parts[2].strip()
        state["risk_analysis"] = parts[3].strip()
        state["tech_solution"] = parts[4].strip()
    else:
        # 兜底：模型没按标题输出时，整段放竞品分析，其余留空，避免错位
        state["competitor_analysis"] = text.strip()
        state["business_model"] = ""
        state["risk_analysis"] = ""
        state["tech_solution"] = ""
    
    print(f"📊 综合分析 Agent：已完成（竞品+商业模式+风险+技术）")
    return state


# ============ 深度版专用的四个分析 Agent ============

def deep_competitor_agent(state: CompetitionState) -> CompetitionState:
    """🏢 深度版竞品分析 Agent"""
    _report_stage("analysis")
    prompt = f"""你是资深市场分析专家。请只负责分析竞品情况，不要写商业模式、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 市场上至少 5 个同类产品/解决方案，每个的优缺点
2. 从功能、价格、目标用户、技术壁垒四个维度做对比表格
3. 我们的项目有什么差异化竞争优势，为什么能赢

注意：你只负责竞品分析，不要写怎么赚钱、不要写技术实现、不要写风险。控制在1000字左右。

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])

    print(f"🏢 深度版竞品分析：已完成")
    return {"competitor_analysis": response.content}


def deep_business_agent(state: CompetitionState) -> CompetitionState:
    """💰 深度版商业模式 Agent"""
    _report_stage("analysis")
    prompt = f"""你是资深商业模式专家。请只负责设计商业模式，不要写竞品分析、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 目标客户细分（至少3类，每类的痛点和付费意愿）
2. 具体盈利模式（至少2种收入来源，定价策略）
3. 成本结构（研发、运营、营销各占多少）
4. 3年财务预测（收入、成本、利润）

注意：你只负责商业模式，不要写竞品对比、不要写技术实现、不要写风险。控制在1000字左右。

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])

    print(f"💰 深度版商业模式：已完成")
    return {"business_model": response.content}


def deep_risk_agent(state: CompetitionState) -> CompetitionState:
    """⚠️ 深度版风险分析 Agent"""
    _report_stage("analysis")
    prompt = f"""你是资深风险评估专家。请只负责分析风险，不要写商业模式、技术方案等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 技术风险（具体有哪些技术难题，怎么应对）
2. 市场风险（市场接受度、竞争加剧怎么办）
3. 政策合规风险（数据隐私、政策变化）
4. 团队和财务风险

每个风险都要有具体的应对措施。注意：你只负责风险分析，不要写竞品、不要写商业模式、不要写技术架构。控制在1000字左右。

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])

    print(f"⚠️ 深度版风险分析：已完成")
    return {"risk_analysis": response.content}


def deep_tech_agent(state: CompetitionState) -> CompetitionState:
    """🔧 深度版技术方案 Agent"""
    _report_stage("analysis")
    prompt = f"""你是资深技术架构师。请只负责写技术方案，不要写竞品、商业模式、风险等其他内容。

项目创意：{state['idea']}

请只写以下内容：
1. 整体技术架构（分几层，每层用什么技术）
2. 核心技术难点（为什么难，我们怎么解决）
3. 技术路线图（分阶段，每个阶段做什么）
4. 关键技术选型（为什么选这个技术）

注意：你只负责技术方案，不要写怎么赚钱、不要写竞品、不要写风险。控制在1000字左右。

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])

    print(f"🔧 深度版技术方案：已完成")
    return {"tech_solution": response.content}


def plan_agent(state: CompetitionState) -> CompetitionState:
    """🗓️ 项目实施计划 Agent"""
    _report_stage("analysis")
    prompt = f"""你是科创项目规划专家。请为以下项目制定详细的实施计划。

项目创意：{state['idea']}

请写：
1. 分阶段计划（共8周，每周做什么，交付什么成果）
2. 每个阶段的里程碑和验收标准
3. 团队分工（5个人分别负责什么）
4. 风险预案（如果延期了怎么办）

控制在1000字左右，清晰有条理。

{_REPORT_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["implementation_plan"] = response.content
    print(f"🗓️ 项目实施计划：已生成")
    return state


def social_value_agent(state: CompetitionState) -> CompetitionState:
    """🌍 社会价值 Agent"""
    _report_stage("analysis")
    prompt = f"""你是科创项目价值分析专家。请分析这个项目的社会价值和应用前景。

项目创意：{state['idea']}

请写：
1. 社会价值（解决了什么社会问题，惠及哪些人群）
2. 应用前景（可以推广到哪些行业/场景）
3. 推广路径（先从哪里开始，怎么扩大）
4. 长期愿景（3-5年后想做成什么样）

控制在1000字左右，要有高度，不要太商业化。

{_REPORT_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["social_value"] = response.content
    print(f"🌍 社会价值：已生成")
    return state


def summary_agent(state: CompetitionState) -> CompetitionState:
    """📝 项目简介 Agent：生成300字项目摘要"""
    _report_stage("analysis")
    prompt = f"""请根据以下项目，写一段300字左右的项目简介：

项目创意：{state['idea']}
一句话定位：{state.get('one_liner', '')}

要求：
1. 开头讲痛点
2. 中间讲解决方案
3. 结尾讲价值和优势
4. 语言正式，适合写申报书开头

控制在300字左右，写成连贯的完整段落，不要用序号罗列。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["project_summary"] = response.content
    print(f"📝 项目简介：已生成")
    return state


def deep_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 深度版申报书 Agent：写完整详细的申报书"""
    _report_stage("writing")
    draft = state.get('proposal_draft', '')
    has_draft = bool(draft.strip())
    if has_draft:
        task_line = ("用户已经上传了一份现成的申报书草稿，你的任务是**优化这份申报书**："
                     "保留原来的内容和骨架，把写得简略的地方补足、把逻辑不顺的地方理顺、"
                     "把缺失的评分点补上，不要从零推翻重写。\n\n" + _OPTIMIZE_SPEC)
        source_label = '用户上传的申报书草稿'
        source_text = draft
    else:
        task_line = "用户还没有成稿，只提供了项目创意，请根据下面的创意与前面的分析结果，从零写一份完整申报书。"
        source_label = '用户的原始创意'
        source_text = state['idea']
    revise_block = ""
    if state.get('revision_count', 0) > 0:
        revise_block = f"""

【本轮是修改稿】必须针对评委意见逐条改写，不得照抄上一版。
上一版申报书：
{state.get('proposal','')}

评委修改意见：
{state.get('judge_feedback','')}
"""

    prompt = f"""你是资深科创赛事申报书写作专家。
{task_line}

{source_label}：{source_text}
{revise_block}

注意：
1. 保留用户原来的核心内容和结构，不要全部推翻重写
2. 把写得太简略的地方补充完整
3. 把逻辑不通的地方理顺
4. 加上比赛需要的评分点
5. 前面分析的竞品、商业模式、风险、技术方案内容，必须全部融入到申报书对应章节里，补充用户草稿里不足的地方
6. 每个二级小节至少 300 字，拆成 2～3 个自然段；任何标题下面都必须有正文，不允许空小节
7. 涉及数字时给出推算过程并标明是测算值，不要编造引用来源

请写一份完整详实的申报书，全文 4500～6000 字，低于 3800 字判不合格，每个章节都要展开成完整段落，不要简略。
用 Markdown 标题组织章节（最多三级标题），章节依次为：

## 一、项目概述
（350 字以上：做什么、给谁用、解决什么核心问题）

## 二、背景与痛点分析
（450 字以上，下分 2 个二级小节：行业与现实背景 / 具体痛点拆解）

## 三、目标用户与应用场景
（400 字以上，下分 2 个二级小节：核心用户画像 / 典型使用场景）

## 四、解决方案与产品形态
（450 字以上，下分 2 个二级小节：产品形态与核心功能 / 用户使用流程）

## 五、技术方案与系统架构
（500 字以上，下分 2 个二级小节：关键技术选型与原理 / 系统架构与数据流）

## 六、核心创新点
（450 字以上，下分 2 个二级小节：与现有方案的三处以上差异 / 创新点的可验证方式）

## 七、竞品对比与差异化优势
（450 字以上：先用标准 Markdown 表格对比 3～4 类现有方案，表格前后各写一段说明与分析）

## 八、商业模式与市场空间
（450 字以上，下分 2 个二级小节：付费对象与收费模式 / 市场规模测算与成长路径）

## 九、风险分析与应对措施
（400 字以上，下分 2 个二级小节：技术与落地风险 / 团队与外部风险，每段都要给应对措施）

## 十、团队分工与执行计划
（400 字以上，下分 2 个二级小节：角色配置与分工 / 分阶段里程碑与时间点）

## 十一、社会价值与应用前景
（350 字以上：具体受益对象、可验证的效果指标、可复制的推广路径）

## 十二、结语
（200 字以上：项目的核心主张与参赛诉求）

{_PROPOSAL_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    proposal, n = _expand_to_length(
        response.content, 3800,
        state.get('one_liner') or state['idea'][:40])
    state["proposal"] = proposal
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 深度版申报书：第 {state['revision_count']} 版，{n} 字")
    return state


def proposal_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 快速版申报书 Agent：不做外部调研，但篇幅同样要求详实完整"""
    _report_stage("writing")
    draft = state.get('proposal_draft', '')
    if draft.strip():
        source = (f"用户已上传申报书草稿，请保留原结构和核心内容做扩写与优化、补足缺失评分点，"
                  f"不要从零重写。\n\n{_PROPOSAL_SPEC}\n\n用户草稿：\n{draft}\n\n（原始创意：{state['idea']}）")
    else:
        source = f"项目创意：{state['idea']}"
    prompt = f"""你是科创赛事申报书写作专家。你写的内容会被直接排版成正式申报书提交给评委，
必须是一份内容扎实、可以立刻交上去的完整文档，绝不能写成提纲、要点或寥寥数语。

赛事：{state['competition_name']}
{source}
规则解析：{state['parsed_rules']}
同质化分析：{state['similarity_report']}
（本模式不做外部调研，请基于项目创意本身往下推演；涉及数字时给出推算过程并标明是测算值，不要编造引用来源）
一句话定位：{state.get('one_liner','')}

【写作硬性要求】
1. 全文 3500～4500 字，低于 3000 字直接判不合格。
2. 每一节都要落到具体事实上：真实场景名称、具体数字（附推算过程）、具体技术名词与参数、具体执行步骤与时间点。
3. 必须回应上面的规则解析：逐条写清本项目针对哪几条评分点发力、怎么发力。
4. 必须回应上面的同质化分析：写清与现有方案的具体差异在哪，不许只用「更智能、更便捷」这类形容词带过。
5. 禁止「大幅提高效率」「具有广阔前景」「赋能行业」这类没有信息量的表述。
6. 每个二级小节至少 300 字，拆成 2～3 个自然段；任何标题下面都必须有正文，不允许空小节。

请严格按以下十章结构写，不要增删章节、不要中途省略：

## 一、项目概述
（300 字以上：项目是做什么的、给谁用、解决什么核心问题、一句话定位如何落地）

## 二、背景与痛点分析
（450 字以上，下分 2 个二级小节：现实场景中的具体问题 / 现有解决方式的不足）

## 三、解决方案与产品形态
（450 字以上，下分 2 个二级小节：产品形态与核心功能 / 用户使用流程）

## 四、技术方案与实现路径
（450 字以上，下分 2 个二级小节：关键技术选型与原理 / 分阶段实现路径）

## 五、核心创新点
（450 字以上，逐条写与现有方案的三处以上不同，每条都要给出依据和可验证方式）

## 六、竞品对比与差异化优势
（400 字以上：先用标准 Markdown 表格对比 3～4 类现有方案，表格前后各写一段说明与分析）

## 七、商业模式与市场空间
（400 字以上：谁付费、怎么付费、市场规模如何测算、成长路径）

## 八、风险分析与应对措施
（350 字以上：技术风险、落地风险、团队风险各写一段，每段都必须给出应对措施）

## 九、团队分工与执行计划
（350 字以上：角色配置与分工、分阶段里程碑与时间点）

## 十、社会价值与未来展望
（300 字以上：具体受益对象、可验证的效果指标、后续演进方向）

{_PROPOSAL_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    proposal, n = _expand_to_length(
        response.content, 3000,
        state.get('one_liner') or state['idea'][:40])
    state["proposal"] = proposal
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 快速版申报书：第 {state['revision_count']} 版，{n} 字")
    return state


def targeted_revise_agent(state: CompetitionState) -> CompetitionState:
    """🔧 定向修订 Agent：只改评委指出的问题段落，不整篇重写"""
    _report_stage("revision")
    prompt = f"""你是科创赛事申报书修订专家。请根据评委意见，对下面的申报书做**定向修订**。

要求：
1. 只修改评委明确指出的问题段落，其他没问题的地方保持原文，不要整篇重写。
2. 保留原申报书的结构和未涉及问题的内容。
3. 修改后输出完整的申报书全文。

当前申报书：
{state.get('proposal', '')}

评委意见：
{state.get('judge_feedback', '')}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["proposal"] = response.content
    state["revision_count"] = (state.get("revision_count") or 0) + 1
    print(f"🔧 定向修订：第 {state['revision_count']} 版")
    return state


def idea_evaluator(state: CompetitionState) -> CompetitionState:
    """💡 创意评分 Agent：只评估原始创意本身的价值，不评申报书"""
    _report_stage("idea_scoring")
    prompt = f"""你是科创赛事评审专家。请对下面的项目创意本身打分（注意：只评创意，不评申报书写得好不好）。

项目创意：
{state['idea']}

请严格按下面格式输出（每项 0-100 分，可带一位小数）：

创新性：__分
可行性：__分
市场价值：__分
技术壁垒：__分
社会价值：__分

然后给出：
1. 创意亮点（至少2点）
2. 主要风险/短板（至少2点）

打分说明：
- 创新性30%：点子是否新颖、与现有方案差异度
- 可行性25%：技术/资源/落地是否可行
- 市场价值20%：目标用户规模、商业前景
- 技术壁垒15%：别人是否容易复制
- 社会价值10%：社会意义
"""
    response = llm.invoke([HumanMessage(content=prompt)])

    import re
    def _pick(label):
        m = re.search(label + r'[^0-9]*?(\d+(?:\.\d+)?)', response.content)
        return float(m.group(1)) if m else None

    sub = {
        "创新性": _pick("创新性"),
        "可行性": _pick("可行性"),
        "市场价值": _pick("市场价值"),
        "技术壁垒": _pick("技术壁垒"),
        "社会价值": _pick("社会价值"),
    }
    weights = {"创新性": 0.30, "可行性": 0.25, "市场价值": 0.20, "技术壁垒": 0.15, "社会价值": 0.10}
    if all(v is not None for v in sub.values()):
        idea_score = int(round(sum(sub[k] * weights[k] for k in sub)))
    else:
        idea_score = 60
    idea_score = max(0, min(100, idea_score))
    print(f"💡 创意评分：{idea_score} 分")
    return {"idea_score": idea_score, "idea_feedback": response.content}


def judge_agent(state: CompetitionState) -> CompetitionState:
    """⚖️ 模拟评委 Agent：只评申报书文档质量，分项加权"""
    _report_stage("judging")
    prompt = f"""你是科创赛事资深评委。请给下面的申报书文档打分（注意：只评文档质量，不评创意本身）。

申报书：
{state['proposal']}

请严格按下面格式输出（每项 0-100 分，可带一位小数）：

结构完整性：__分
逻辑清晰度：__分
数据支撑：__分
格式规范：__分
说服力：__分

然后给出：
1. 主要优点（至少3点）
2. 需要改进的地方（至少3点）

打分说明：
- 结构完整性30%：章节是否齐全、篇幅是否充实（内容单薄要明显扣分）
- 逻辑清晰度25%：论证是否连贯、有无逻辑漏洞
- 数据支撑20%：是否用了具体数字、案例、技术名词
- 格式规范15%：是否符合申报书格式要求
- 说服力10%：整体是否能让评委信服
不要给所有文档打接近的分数，要拉开差距。

【点评文字要求】
1. 「主要优点」和「需要改进的地方」每点写成完整段落，有具体依据、有展开，不要只写一两个关键词
2. 上面的打分字段（结构完整性：__分 等）保持原格式，不要改动
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["judge_feedback"] = response.content

    import re
    def _pick(label):
        m = re.search(label + r'[^0-9]*?(\d+(?:\.\d+)?)', response.content)
        return float(m.group(1)) if m else None

    sub = {
        "结构完整性": _pick("结构完整性"),
        "逻辑清晰度": _pick("逻辑清晰度"),
        "数据支撑": _pick("数据支撑"),
        "格式规范": _pick("格式规范"),
        "说服力": _pick("说服力"),
    }
    weights = {"结构完整性": 0.30, "逻辑清晰度": 0.25, "数据支撑": 0.20, "格式规范": 0.15, "说服力": 0.10}

    if all(v is not None for v in sub.values()):
        state["score"] = int(round(sum(sub[k] * weights[k] for k in sub)))
    else:
        m2 = re.search(r'SCORE\s*[:：]\s*(\d{1,3})', response.content, re.IGNORECASE)
        if m2:
            state["score"] = max(0, min(100, int(m2.group(1))))
        else:
            m3 = re.search(r'(\d{1,3})\s*分', response.content)
            state["score"] = int(m3.group(1)) if m3 else 60

    state["score"] = max(0, min(100, state["score"]))
    state["approved"] = state["score"] >= 70
    print(f"⚖️ 评委 Agent：文档加权总分 {state['score']} 分")
    return state

def defense_questions_agent(state: CompetitionState) -> CompetitionState:
    """🎤 答辩问题预测 Agent：预测评委可能问什么"""
    _report_stage("defense")
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
    _report_stage("ppt")
    prompt = f"""你是科创赛事路演 PPT 专家。请根据以下项目，生成 3 分钟路演 PPT 大纲（8-10页）。

项目：{state['idea']}
一句话定位：{state['one_liner']}

输出每页的标题和要点。

{_OUTLINE_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["ppt_outline"] = response.content
    print(f"📊 PPT 大纲 Agent：已生成")
    return state


def speech_agent(state: CompetitionState) -> CompetitionState:
    """🎤 路演演讲稿 Agent：生成3分钟路演讲稿"""
    _report_stage("speech")
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
    # 流式生成，边生成边写入缓冲区，前端可实时预览，不再干等 20~40 秒
    import stage_reporter as _sr
    full_text = ""
    try:
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            piece = getattr(chunk, "content", "") or ""
            if piece:
                full_text += piece
                _tid = _sr.current_task_id()
                if _tid:
                    _sr.set_speech_stream(_tid, full_text)
    except Exception:
        # 流式失败兜底：退回一次性生成
        full_text = llm.invoke([HumanMessage(content=prompt)]).content
    state["speech_script"] = full_text
    print(f"🎤 路演演讲稿：已生成")
    return state


def one_liner_agent(state: CompetitionState) -> CompetitionState:
    """💡 一句话定位 Agent：生成路演开场一句话"""
    _report_stage("idea_scoring")
    prompt = f"""请用一句话（30字以内）概括这个项目，用来路演开场。

项目：{state['idea']}

直接输出一句话，不要解释。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    print(f"💡 一句话定位 Agent：已生成")
    return {"one_liner": response.content.strip()}


# ============ 3. 路由 ============
def proposal_analysis_agent(state: CompetitionState) -> CompetitionState:
    """申报书快速诊断 Agent：给出简明、有针对性的诊断"""
    _report_stage("diagnosis")
    prompt = f"""你是科创赛事申报书评审专家。请对下面这份申报书做一份简明、有针对性的快速诊断。

申报书：
{state.get('proposal', '')}

请严格针对这份申报书的具体内容，分四部分输出（每部分 1-2 句话，不要泛泛而谈）：
1. 结构完整性
2. 内容亮点
3. 待优化点
4. 评审建议

{_ANALYSIS_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["proposal_analysis"] = response.content
    print("申报书快速诊断 Agent：完成")
    return state


def rich_media_agent(state: CompetitionState) -> CompetitionState:
    """🎞️ 富媒体 Agent：生成结构化表格 + PPT 幻灯片结构"""
    _report_stage("rich_assets")
    prompt = f"""你是路演材料制作专家。请根据下面的分析结果，生成结构化数据。

项目创意：{state.get('idea', '')}
一句话定位：{state.get('one_liner', '')}
竞品分析：{state.get('competitor_analysis', '')}
商业模式：{state.get('business_model', '')}
风险分析：{state.get('risk_analysis', '')}
技术方案：{state.get('tech_solution', '')}
实施计划：{state.get('implementation_plan', '')}
社会价值：{state.get('social_value', '')}

请只输出一个 JSON 对象（不要任何其他文字、不要 markdown 代码块），结构严格如下：
{{"charts": {{"budget": [{{"name": "研发成本", "value": 40}}, {{"name": "硬件采购", "value": 25}}, {{"name": "市场推广", "value": 20}}, {{"name": "运营备用", "value": 15}}], "market": {{"years": ["2024", "2025", "2026", "2027", "2028"], "values": [120, 280, 560, 980, 1500]}}, "timeline": {{"stages": ["需求调研", "原型开发", "测试迭代", "上线运营", "推广拓展"], "progress": [10, 30, 55, 80, 100]}}}}, "tables": [{{"title": "竞品对比", "header": ["维度", "本项目", "竞品A", "竞品B"], "rows": [["创新性", "强", "中", "中"], ["成本", "低", "高", "中"]]}}], "deck": {{"slides": [{{"type": "cover", "title": "项目名称", "bullets": [], "metrics": [], "chart": "", "table": ""}}, {{"type": "bullets", "title": "痛点分析", "bullets": ["痛点1", "痛点2"], "metrics": [], "chart": "", "table": ""}}, {{"type": "metrics", "title": "核心数据", "bullets": [], "metrics": ["数据1", "数据2"], "chart": "", "table": ""}}, {{"type": "table", "title": "竞品对比", "bullets": [], "metrics": [], "chart": "", "table": "竞品对比"}}, {{"type": "closing", "title": "谢谢", "bullets": [], "metrics": [], "chart": "", "table": ""}}]}}}}

要求：
- charts 的 budget.value 加起来等于 100，market.values 逐年递增，timeline.progress 在 0-100；
- tables 生成 2-3 个（竞品对比、商业模式、实施计划等），header 和 rows 要真实具体、贴合本项目；
- deck.slides 生成 8-12 页，type 只用 cover/section/bullets/metrics/table/closing 这些，标题和内容贴合本项目。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["rich_media"] = response.content
    print("🎞️ 富媒体 Agent：已生成")
    return state

def should_iterate(state: CompetitionState) -> Literal["revise", "defense"]:
    if state["approved"] or (state.get("revision_count") or 0) >= 2:
        return "defense"
    else:
        return "revise"


def should_iterate_fast(state: CompetitionState) -> Literal["revise", "defense"]:
    """简洁版可选迭代：仅当用户开启 iterate 且低分且未迭代过时返工一轮"""
    if not state.get("iterate", False):
        return "defense"
    if state["approved"] or (state.get("revision_count") or 0) >= 2:
        return "defense"
    return "revise"


# ============ 4. 构建工作流 ============
# 简洁版默认不做迭代（保持快速出稿）；用户传 iterate=true 时，低分自动返工一轮
workflow = StateGraph(CompetitionState)

workflow.add_node("rule_parser", rule_parser_agent)
workflow.add_node("similarity_checker", similarity_checker_agent)
workflow.add_node("idea_evaluator", idea_evaluator)
workflow.add_node("one_liner", one_liner_agent)
workflow.add_node("analysis", comprehensive_analysis_agent)
workflow.add_node("writer", proposal_writer_agent)
workflow.add_node("judge", judge_agent)
workflow.add_node("proposal_analysis", proposal_analysis_agent)
workflow.add_node("defense", defense_questions_agent)
workflow.add_node("ppt", ppt_outline_agent)
workflow.add_node("speech", speech_agent)
workflow.add_node("revise", targeted_revise_agent)

workflow.add_edge(START, "rule_parser")
workflow.add_edge(START, "similarity_checker")
workflow.add_edge(START, "idea_evaluator")
workflow.add_edge(START, "one_liner")
workflow.add_edge("rule_parser", "analysis")
workflow.add_edge("similarity_checker", "analysis")
workflow.add_edge("idea_evaluator", "analysis")
workflow.add_edge("one_liner", "analysis")
workflow.add_edge("analysis", "writer")
workflow.add_edge("writer", "judge")
workflow.add_edge("judge", "proposal_analysis")
workflow.add_conditional_edges(
    "proposal_analysis",
    should_iterate_fast,
    {"revise": "revise", "defense": "defense"}
)
workflow.add_edge("revise", "judge")
workflow.add_edge("defense", "ppt")
workflow.add_edge("ppt", "speech")
workflow.add_edge("speech", END)


fast_app = workflow.compile()

# 建深度版工作流：四个分析Agent分开跑
deep_workflow = StateGraph(CompetitionState)
deep_workflow.add_node("rule_parser", rule_parser_agent)
deep_workflow.add_node("similarity_checker", similarity_checker_agent)
deep_workflow.add_node("idea_evaluator", idea_evaluator)
deep_workflow.add_node("one_liner", one_liner_agent)
deep_workflow.add_node("competitor", deep_competitor_agent)
deep_workflow.add_node("business", deep_business_agent)
deep_workflow.add_node("risk", deep_risk_agent)
deep_workflow.add_node("tech", deep_tech_agent)
deep_workflow.add_node("revise", targeted_revise_agent)
deep_workflow.add_node("plan", plan_agent)
deep_workflow.add_node("social", social_value_agent)
deep_workflow.add_node("summary", summary_agent)
deep_workflow.add_node("rich_media", rich_media_agent)
deep_workflow.add_node("writer", deep_writer_agent)
deep_workflow.add_node("judge", judge_agent)
deep_workflow.add_node("proposal_analysis", proposal_analysis_agent)
deep_workflow.add_node("defense", defense_questions_agent)
deep_workflow.add_node("ppt", ppt_outline_agent)
deep_workflow.add_node("speech", speech_agent)

deep_workflow.add_edge(START, "rule_parser")
deep_workflow.add_edge(START, "similarity_checker")
deep_workflow.add_edge(START, "idea_evaluator")
deep_workflow.add_edge(START, "one_liner")
deep_workflow.add_edge(START, "competitor")
deep_workflow.add_edge(START, "business")
deep_workflow.add_edge(START, "risk")
deep_workflow.add_edge(START, "tech")
deep_workflow.add_edge("rule_parser", "plan")
deep_workflow.add_edge("similarity_checker", "plan")
deep_workflow.add_edge("idea_evaluator", "plan")
deep_workflow.add_edge("one_liner", "plan")
deep_workflow.add_edge("competitor", "plan")
deep_workflow.add_edge("business", "plan")
deep_workflow.add_edge("risk", "plan")
deep_workflow.add_edge("tech", "plan")
deep_workflow.add_edge("plan", "social")
deep_workflow.add_edge("social", "summary")
deep_workflow.add_edge("summary", "rich_media")
deep_workflow.add_edge("rich_media", "writer")
deep_workflow.add_edge("writer", "judge")
deep_workflow.add_edge("judge", "proposal_analysis")
deep_workflow.add_conditional_edges(
    "proposal_analysis",
    should_iterate,
    {
        "revise": "revise",
        "defense": "defense"
    }
)
deep_workflow.add_edge("revise", "judge")
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
