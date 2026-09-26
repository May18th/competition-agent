"""
科创赛事多智能体协同创作助手
核心工作流：规则解析 → 同质化检测 → 文稿生成 → 模拟评委 → 迭代
"""
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage
from stage_reporter import report_stage as _report_stage, set_partial_field


# ============ 配置 ============
import os
import re
import threading

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


# 峰值并发闸：深度版 START 阶段最多 8 个节点并行打 DeepSeek，
# 限制到 4 个一批，避免瞬时并发过高触发限流。
_LLM_GATE = threading.Semaphore(4)
_llm_invoke_original = llm.invoke


def _llm_invoke_with_quota(*args, **kwargs):
    data = _quota_load()
    if data.get("calls", 0) >= _QUOTA_DAILY_LIMIT:
        raise RuntimeError(f"今日 LLM 调用已达上限（{_QUOTA_DAILY_LIMIT} 次），请明天再试")
    with _LLM_GATE:
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

_PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "competition_profiles.json")
_PROFILES_CACHE = None


def get_competition_profiles() -> list:
    """加载结构化比赛配置（章节顺序/评分重点/类型/提示词侧重/字数要求）。"""
    global _PROFILES_CACHE
    if _PROFILES_CACHE is not None:
        return _PROFILES_CACHE
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            data = _json.load(f)
        _PROFILES_CACHE = data.get("competitions", []) or []
    except Exception as e:
        print(f"[profiles] 读取比赛配置失败（使用空配置）：{e}")
        _PROFILES_CACHE = []
    return _PROFILES_CACHE


def get_competition_profile(competition_name: str) -> dict:
    """按赛事名/别名匹配结构化配置，返回 {} 表示未命中。"""
    if not competition_name:
        return {}
    q = str(competition_name).strip()
    for p in get_competition_profiles():
        names = [p.get("name", "")] + (p.get("aliases") or [])
        for n in names:
            if not n:
                continue
            if q == n or q in n or n in q:
                return p
    return {}


_ALIAS_GROUPS = [
    ["国创", "国创项目", "国创计划", "大创", "国家级大学生创新创业训练计划"],
    ["互联网+", "互联网加", "互联网＋"],
]


def _same_alias_group(a, b):
    for group in _ALIAS_GROUPS:
        if any(x in a for x in group) and any(x in b for x in group):
            return True
    return False


_COMMON_WORDS = ["大学生", "全国", "中国", "国际", "大赛", "竞赛", "训练计划", "计划", "创新创业", "创业"]


def _tokens(s):
    for w in _COMMON_WORDS:
        s = s.replace(w, " ")
    return {t for t in s.split() if len(t) >= 2}


def _match_score(known, query):
    """匹配打分（0=不匹配）：精确=100，括号内子串=100，普通子串=90，token 相同=70，token 交集=50+，别名=40。"""
    if not known or not query:
        return 0
    if known == query:
        return 100
    if known in query:
        # 出现在括号里（如「（小挑）」）说明是更具体的赛事名，加满分，避免品牌前缀串台
        if re.search(r'[（(]' + re.escape(known) + r'[)）]', query):
            return 100
        return 90
    if query in known:
        return 80
    if _same_alias_group(known, query):
        return 40
    kt, qt = _tokens(known), _tokens(query)
    if kt and qt:
        inter = kt & qt
        if kt == qt:
            return 70
        if inter:
            return 50 + len(inter)
    return 0


def get_competition_knowledge(competition_name: str) -> str:
    """根据比赛名称，匹配对应的知识库内容"""
    if not competition_knowledge:
        return ""
    scored = []
    for known_name, content in competition_knowledge.items():
        s = _match_score(known_name, competition_name)
        if s > 0:
            scored.append((s, len(known_name), known_name, content))
    if not scored:
        return ""
    scored.sort(key=lambda x: (-x[0], -x[1]))
    best = scored[0]
    print(f"📚 知识库命中：{best[2]}（匹配度 {best[0]}），候选 {len(scored)} 个")
    return f"\n【知识库中关于{best[2]}的资料】\n{best[3]}\n"
    return ""


_OFFICIAL_DOCS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "official_docs.json")


def save_official_doc(competition_name, text):
    """把用户上传的赛事官方资料存到 data/official_docs.json（按赛事名索引）。"""
    import json
    if not competition_name or not text or not text.strip():
        return False
    try:
        docs = {}
        if os.path.exists(_OFFICIAL_DOCS_PATH):
            with open(_OFFICIAL_DOCS_PATH, encoding="utf-8") as f:
                docs = json.load(f)
        docs[str(competition_name)] = text.strip()
        os.makedirs(os.path.dirname(_OFFICIAL_DOCS_PATH), exist_ok=True)
        with open(_OFFICIAL_DOCS_PATH, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[kb] 保存官方资料失败：{e}")
        return False


def get_official_doc(competition_name):
    """读取用户上传的赛事官方资料；无则返回空串。"""
    import json
    try:
        if not os.path.exists(_OFFICIAL_DOCS_PATH):
            return ""
        with open(_OFFICIAL_DOCS_PATH, encoding="utf-8") as f:
            docs = json.load(f)
        c = str(competition_name or "")
        for name, text in docs.items():
            if name == c or name in c or c in name:
                return text
        return ""
    except Exception:
        return ""


_INDUSTRY_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "knowledge_base", "industry_data.txt")
_industry_cache = None


def get_industry_data() -> str:
    """读取可引用的真实行业/赛事数据（来源：权威公开数据，仅作背景/市场/社会价值引用）。"""
    global _industry_cache
    if _industry_cache is not None:
        return _industry_cache
    try:
        if os.path.exists(_INDUSTRY_DATA_PATH):
            with open(_INDUSTRY_DATA_PATH, encoding="utf-8") as f:
                _industry_cache = f.read()
        else:
            _industry_cache = ""
    except Exception:
        _industry_cache = ""
    return _industry_cache


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
    "互联网+", "挑战杯", "iCAN", "国创", "小挑", "数学建模", "电子设计",
    "西门子杯", "计算机设计", "RoboMaster", "金砖", "信息安全",
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
        "preference": "", "penalty": "", "requirements": "", "raw": content or "",
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
        parts = []
        for k, v in buf.items():
            if any(kw in k for kw in keywords):
                parts.append("\n".join(v).strip())
        return "\n".join(p for p in parts if p)

    result["intro"] = _join(["介绍", "简介"])
    result["scoring"] = _join(["评分", "打分"])
    result["sections"] = _join(["章节", "申报书", "结构", "必须包含"])
    result["preference"] = _join(["偏好", "方向", "喜欢", "区别"])
    result["penalty"] = _join(["扣分", "注意", "误区"])
    result["requirements"] = _join(["立项", "选题", "结题", "赛道", "要求"])
    return result


def get_competition_knowledge_structured(competition_name: str) -> dict:
    """按比赛名匹配，返回结构化知识库字段（matched=False 表示未收录）"""
    empty = {"matched": False, "matched_name": "", "title": "", "intro": "",
             "scoring": "", "sections": "", "preference": "", "penalty": "", "requirements": ""}
    if not competition_knowledge:
        return empty
    scored = []
    for known_name, content in competition_knowledge.items():
        s = _match_score(known_name, competition_name)
        if s > 0:
            scored.append((s, len(known_name), known_name, content))
    if not scored:
        return empty
    scored.sort(key=lambda x: (-x[0], -x[1]))
    known_name, content = scored[0][2], scored[0][3]
    parsed = parse_knowledge(content)
    parsed["matched"] = True
    parsed["matched_name"] = known_name
    return parsed


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
    user_keywords: str
    outline_requirement: list
    scoring_weights: list
    humanize: str

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
    proposal_outline: str
    proposal_selfcheck: str
    judge_feedback: str
    judge_scores: list
    expert_review: str
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
    # 档位：fast=简洁快速版 / deep=深度完整版
    # 两个工作流共用同一批 Agent 函数（规则解析、评委、答辩、PPT、演讲稿…），
    # 没有这个字段它们就分不清自己在哪一档，产物会长得一模一样。
    # 由 app.py 的 _run_generation() 按 mode 写入；缺省按 deep 处理（宁详勿略）。
    tier: str


# ============ 内容层：输出规格约束（统一提升各 Agent 输出质量）============

_DE_AI_SPEC = """【去 AI 味 —— 必须遵守。下面每条都给「改前(❌) → 改后(✅)」示范，照改后的写法来。】

1. 去模板化开头：开头不要「随着……的发展」「在当今……背景下」「近年来……日益」这类套话，直接切入本项目要解决的问题。
❌ 随着人工智能技术的迅猛发展，大学生创新创业竞赛的备赛压力日益增大。
✅ 参赛团队最头疼的，是申报书、PPT、演讲稿一堆材料要写，还都要写好。

2. 去机械排比：不要「首先/其次/最后」「第一/第二/第三」这种机械罗列，把要点串成自然的叙述。
❌ 本平台首先生成快，其次内容全，最后质量高。
✅ 创意填进去，几分钟拿到申报书初稿，答辩问题和 PPT 大纲也一并生成。

3. 去万能连接词：不要「不仅……而且……」「一方面……另一方面……」这类万能连接，改用具体的关系。
❌ 本平台不仅生成申报书，而且还能生成 PPT 和演讲稿。
✅ 除了申报书，它把答辩问题、PPT 大纲、演讲稿一起生成，省得团队分开准备。

4. 去空洞总结：结尾不要「综上所述」「总而言之」，用一句具体的话收尾。
❌ 综上所述，本平台具有重要的实用价值。
✅ 团队把创意填进去，几十分钟就能拿到一份能直接改的申报书初稿。

5. 去过度修饰：不要「非常」「极其」「十分」「高度」「全面」这类空泛修饰。
❌ 本平台具有极其先进的技术和非常强大的功能。
✅ 它把规则解析、同质化检测、模拟评委这些环节串成一条流水线。

6. 砍冗余副词：砍掉「显著地」「极大地」「有效地」「有力地」这类冗余副词，直接把结果写出来。
❌ 该平台显著提升了申报书写作效率。
✅ 原来要熬几天的申报书，现在几分钟出初稿。

7. 被动改主动：尽量用主动句，少用「被……」，让主语明确。
❌ 创意被输入后，申报书会被自动生成出来。
✅ 你输入创意，平台自动生成申报书。

8. 句子节奏：长短句交错，不要连续好几个句子长度都差不多。
❌ 本平台采用多智能体架构。每个智能体负责一个环节。智能体之间协同工作。最终生成申报书。
✅ 平台底层是一串智能体，有的解析规则，有的检测同质化，有的当模拟评委。它们接力跑完，输出一份完整申报书。

9. 去 AI 式举例：不要「例如……」「比如……」这种泛泛列举，落到本项目的具体场景。
❌ 本平台适用于多种场景，例如比赛、论文、报告等。
✅ 它针对科创赛事设计，先覆盖 iCAN、挑战杯、互联网+ 这几类申报书。

10. 术语一致性：同一个东西从头到尾用同一个词，不要一会儿「终端」、一会儿「设备」、一会儿「装置」。
❌ 本平台的多智能体……该系统的模型……这个工具……
✅ 全程统一叫「平台」，各环节统一叫「智能体」。

11. 整体语气：像项目负责人在跟评委陈述自己的项目，自然、平实、有分寸，不要背范文、写八股、念新闻稿。

12. 匿名要求（硬性）：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名等身份信息；涉及团队一律用「本项目团队」「参赛团队」指代，涉及指导教师一律省略。违者视为不合格。

13. 数据真实（硬性）：只引用可核实的真实数据或用户已给的数据；不知道的具体数字、文献、检测报告、合作方，一律写占位符【待你填写：xxx】或【示例值，需核实】，严禁编造看似真实的假数据。
"""

_HUMANIZE_BANNED = ["随着", "综上所述", "赋能", "生态", "一站式", "闭环", "深度融合"]

_HUMANIZE_STRONG_SPEC = """【去 AI 味强化要求 —— 必须严格遵守】
1. 全文严禁出现这些词/句式：随着……的发展、综上所述、赋能、打造……生态、一站式、闭环、深度融合；出现就必须改写。
2. 每个自然段至少含一个具体数字 / 真实场景 / 明确局限，禁止纯形容词堆叠。
3. 段落长度要自然起伏（80～400 字之间波动），不要每段都差不多长。
4. 结尾不要总结升华，直接收在具体事实上。
5. 只改正文，**不碰章节标题**：章节标题里出现的「痛点」等词必须原样保留（如「二、项目背景与痛点分析」），不得改写标题。
"""


def _humanize_spec(state):
    """文风档位：strong 返回强化去 AI 味规范，否则返回空串。"""
    return _HUMANIZE_STRONG_SPEC if (state or {}).get("humanize") == "strong" else ""


_CONCRETE_SPEC = """【具体化与落地要求 —— 必须遵守（评委最看重）】
1. 用户画像 / 痛点分析 / 项目背景章节：必须写「具体人物 + 具体时刻 + 具体动作 + 卡在哪一步」四要素，
   禁止「广大大学生」「独居老人」「老年人群体」这类无场景集合名词；若用户创意里已写了具体场景，原样继承，不要泛化。
2. 实施计划 / 商业模式 / 应用前景章节：必须给出可核对的数字字段——试点单位类型、测试用户数、留存/活跃、
   客单价与成本结构、时间表（几月到几月、做什么、交付什么）。不知道的就写占位符并明确标注
   【待你填写：xxx】或【示例值，需核实】或【示例值，需替换为真实测算】，严禁写「后续将逐步推进」「实现规模化」这类空话。
3. 每一个自然段都必须同时包含：① 至少 1 个「只属于这个项目」的具体用户场景（谁、在什么时刻、做什么、卡在哪一步）；② 至少 1 个可验证数字（真实数据、用户已给数据、或明确标注的占位符【待你填写：xxx】/【示例值，需核实】/测算值）。两者缺一，就重写这一段。
4. 禁用句式与空话：依托……技术、瞄准……痛点、具有广阔的市场前景、广阔市场前景、显著的社会效益、显著社会价值、为……赋能、打造……生态、全链路、一站式解决方案。
5. 段落不低于 80 字，且每段必须含一个具体数字；纯形容词、纯口号、放哪个项目都能成立的段落直接判不合格。
6. 严禁编造假数据：所有数字、文献、检测报告、合作方、试点成果，只能来自 ① 知识库/官方资料里的真实数据 ② 用户创意里已给出的数据 ③ 占位符【待你填写：xxx】或【示例值，需核实】。凡是拿不准的，一律写占位符，绝不编一个看起来真实但实际是假的数字。
"""


_REPORT_SPEC = """【输出规格 —— 必须遵守】
1. 使用 Markdown，最多三级标题（## / ###），一级用「一、二、三、」，二级用「（一）（二）」，三级用「1. 2. 3.」
2. 三级标题必须是正式短语，不是完整句子
3. 结构必须包含：摘要 / 背景 / 内容 / 分析 / 总结 / 展望
4. 每个小节必须写成 150～400 字的完整段落，有论点、有展开、有依据；严禁一句话一段、严禁短句罗列
5. 严禁整篇用序号罗列（不要「1. xxx  2. xxx」这种清单体），把要点串成连贯段落
6. 需要逐条对比时用标准 Markdown 表格（| a | b | 换行 |---|---|），不要用序号列表
7. 全文中文标点用全角
""" + _DE_AI_SPEC

_PROPOSAL_SPEC = """【申报书输出规格 —— 优先级最高，覆盖上面所有通用规格】
1. 篇幅：正文 3500～4500 字，低于 3000 字视为不合格。这是一份要提交给评委的完整申报书，不是提纲也不是摘要。
2. 结构：使用 Markdown，最多三级标题（## / ###），一级用「一、二、三、」，二级用「（一）（二）」，三级用「1. 2. 3.」
3. 密度：每个二级小节至少 300 字，拆成 2～3 个自然段，每段不少于 150 字；要有论点、有展开、有依据，严禁一句话一段
4. 严禁空小节：任何标题下面都必须有正文段落，不允许只放一个表格、也不允许标题下面是空的
5. 严禁通篇序号罗列；只有需要逐条对比时才用标准 Markdown 表格，且表格前后都必须有说明段落
6. 每一节都要落到具体事实上：真实场景名称、具体数字（测算值要标明是测算）、具体技术名词与参数、具体执行步骤与时间点。禁止「大幅提高效率」「具有广阔前景」「赋能行业」这类没有信息量的表述
7. 全文中文标点用全角
""" + _DE_AI_SPEC

_ANALYSIS_SPEC = """【输出规格 —— 必须遵守】
1. 必须分段阐述，不能只给结论清单
2. 每个维度按「现状 → 原因 → 影响 → 应对」写成完整段落，不要一句话一行
3. 需要对比时用标准 Markdown 表格
4. 全文中文标点用全角
""" + _DE_AI_SPEC

_OUTLINE_SPEC = """【输出规格 —— 必须遵守】
1. 只要层级清晰的条目，不要段落、不要大段阐述
2. 每页/每条一行短语，不要写完整句子
"""

_OPTIMIZE_SPEC = """【优化输出规格 —— 必须遵守】
1. 优化输出必须保持原申报表的条目结构一一对应：不合并条目、不拆分条目、不新增条目
2. 不加 Markdown 标题符号，每一条只输出改写后的文字
3. 每条优化后的文字长度与原条目大致相当（±30% 以内），宁可精炼也不要大幅膨胀，避免撑破原表格版式
"""

# ---- 两档规格：简洁快速版 vs 深度完整版 ----
# 两个工作流共用同一批 Agent 函数（规则解析 / 同质化检测 / 评委 / 诊断），
# 它们靠 _spec_for() 按档位取规格，这是两档产物能真正拉开差距的关键。

_BRIEF_SPEC = """【精简档输出规格 —— 简洁快速版专用】
1. 每个小节 120～200 字，写成 1～2 个完整自然段
2. 只要结论和关键依据，不展开推演过程，不写背景铺陈
3. 严禁一句话一段、严禁空小节
4. 中文标点用全角
""" + _DE_AI_SPEC

_FULL_SPEC = """【完整档输出规格 —— 深度完整版专用】
1. 每个二级小节 300～500 字，拆成 2～3 个自然段
2. 按「现状 → 原因 → 影响 → 应对」展开，要有推算过程和可验证依据
3. 需要对比时用标准 Markdown 表格（| a | b | 换行 |---|---|），表格前后各写一段说明
4. 严禁一句话一段、严禁空小节
5. 中文标点用全角
""" + _DE_AI_SPEC

_SPEC_BY_TIER = {"fast": _BRIEF_SPEC, "deep": _FULL_SPEC}


def _spec_for(state):
    """按档位取输出规格。state 里没有 tier 时按 deep 处理（宁详勿略）。"""
    return _SPEC_BY_TIER.get((state or {}).get("tier"), _FULL_SPEC)


def _tier_hint(state, brief, full):
    """按档位返回二选一的提示文案：简洁版用 brief，深度版用 full。

    用于那些有自己专属结构、不适合整段套 _spec_for 的 Agent
    （评委 / 答辩 / PPT / 演讲稿 / 快速诊断）。
    """
    hint = brief if (state or {}).get("tier") == "fast" else full
    return hint + "\n（匿名要求：严禁出现院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代。）"


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
            "1. 每一节补充更具体的场景、数据测算、技术参数、实施步骤与风险应对，"
            "只补充新论据/数据/案例，不许重复已述内容；\n"
            "2. 每个小节补充成一到两个完整的自然段，不要一句话一段；\n"
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
- 立项/结题/赛道等其他要求：{kb.get('requirements') or '（无）'}
"""
    else:
        kb_block = "（知识库未收录该赛事，请根据用户上传的规则或通用竞赛常识分析）"
    
    # 如果用户没上传规则，就说根据知识库来分析
    if not state['rule_content'] or state['rule_content'].strip() == '':
        rule_content_text = "用户没有上传规则PDF，请根据知识库中关于这个比赛的资料来分析。"
    else:
        rule_content_text = f"用户上传的规则内容：\n{state['rule_content']}"
    official = get_official_doc(state['competition_name'])
    official_block = ("\n【本赛事官方资料（用户上传，务必优先依据）】\n" + official[:4000] + "\n") if official else ""
    
    prompt = f"""你是赛事规则分析专家。请分析这个比赛的核心评分标准和要求。

赛事名称：{state['competition_name']}
{kb_block}
{rule_content_text}
{official_block}

请提取：
1. 核心评分维度（如创新性、实用性、技术难度等）及各维度占比
2. 申报书必须包含的章节和要求
3. 这个比赛偏好什么样的项目
4. 关键注意事项

{_spec_for(state)}
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

{_spec_for(state)}
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
{_ref_block(state, '商业模式')}

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
{_ref_block(state, '风险分析')}

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
{_ref_block(state, '实践过程')}

请写：
1. 分阶段计划（共8周，每周做什么，交付什么成果）
2. 每个阶段的里程碑和验收标准
3. 团队分工（5个人分别负责什么）
4. 风险预案（如果延期了怎么办）

控制在1000字左右，清晰有条理。

{_spec_for(state)}
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
{_ref_block(state, '社会价值')}
{_industry_ref()}

请写：
1. 社会价值（解决了什么社会问题，惠及哪些人群）
2. 应用前景（可以推广到哪些行业/场景）
3. 推广路径（先从哪里开始，怎么扩大）
4. 长期愿景（3-5年后想做成什么样）

控制在1000字左右，要有高度，不要太商业化。

{_spec_for(state)}
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

{_DE_AI_SPEC}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["project_summary"] = response.content
    print(f"📝 项目简介：已生成")
    return state


def _ref_block(state: dict, module_tag: str) -> str:
    """取该模块的范文参考块；检索失败或为空返回空串，绝不抛异常。"""
    try:
        from kb_retrieve import extract_keywords, search_samples
        kws = extract_keywords(state.get("idea", "") + " " + state.get("user_keywords", ""))
        # 按档位决定注入量：简洁版轻量参考，深度版完整参考；只取「范文」不取「材料」
        if (state or {}).get("tier") == "fast":
            top_k, max_chars = 1, 1200
        else:
            top_k, max_chars = 3, 3000
        ref = search_samples(kws, module_tag, top_k=top_k, max_chars=max_chars, types=["范文"])
        if ref:
            return f"【高分范文参考（务必学习其结构与表述风格，不要照抄内容）】\n{ref}\n"
        return ""
    except Exception as e:
        print(f"[kb] 范文检索跳过：{e}")
        return ""


def _official_ref(state: dict) -> str:
    """取用户上传的赛事官方资料块（撰写依据，封顶 3000 字）；无则空串。"""
    try:
        official = get_official_doc(state.get("competition_name", ""))
        if official:
            return ("\n【本赛事官方资料（撰写依据，优先采用其评分维度与章节要求，不要照抄）】\n"
                    + official[:3000] + "\n")
        return ""
    except Exception:
        return ""


def _industry_ref() -> str:
    """注入可引用的真实行业/赛事数据（封顶 2500 字）；无则空串。"""
    data = get_industry_data()
    if not data:
        return ""
    return ("\n【可引用的真实行业/赛事数据（权威公开数据，引用时保留原始口径、不改写数字；"
            "只用于行业背景、市场前景、社会价值等宏观段落，不要硬塞进与本项目无关处）】\n"
            + data[:2500] + "\n")


_DEFAULT_CHAPTERS = """## 一、项目概述
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
（200 字以上：项目的核心主张与参赛诉求）"""


def _official_chapters(state: dict) -> list:
    """从结构化配置里取官方章节标题，作为深度版缺省章节结构。

    返回 ["一、项目概述", ...] 形式的干净标题列表；解析不到就返回空列表。
    """
    profile = get_competition_profile(state.get("competition_name", ""))
    chapters = profile.get("chapters") or []
    return [str(c).strip() for c in chapters if str(c).strip()]


def _competition_focus(state: dict) -> str:
    """按比赛类型给生成 Prompt 注入侧重说明。"""
    profile = get_competition_profile(state.get("competition_name", ""))
    focus = (profile.get("focus") or "").strip()
    if not focus:
        return ""
    return "\n【本赛事写作侧重 —— 必须优先体现】\n" + focus + "\n"


def _defense_focus(state: dict) -> str:
    """按比赛类型生成答辩必问方向（工科问技术、经管问商业、建模问假设等）。"""
    profile = get_competition_profile(state.get("competition_name", ""))
    kind = profile.get("defense_focus") or "engineering"
    sets = {
        "engineering": [
            ("技术路线与关键参数", "核心技术路线是什么？关键器件/模型/算法怎么选型？把具体参数、版本、指标讲清楚，并说清为什么这样选。"),
            ("系统架构与模块边界", "系统由哪些模块组成？模块之间怎么通信/调用？边界条件、异常处理和降级方案是什么？"),
            ("实现细节与代码/硬件", "哪个模块是你自己实现的？哪些用了开源/现成方案？能现场说明关键代码或电路吗？"),
            ("测试与性能数据", "测了多少次？测试条件和样本是什么？关键性能指标（延迟/精度/功耗/可靠性）的实测数据是多少？"),
            ("稳定性与极限场景", "系统在极端输入、断网、并发、长时间运行下会怎样？最不稳定的一环是什么？"),
            ("与同类技术对比", "比现有方案好在哪？把技术指标差异量化，说明你做的不是简单集成。"),
            ("可复制性与技术门槛", "别人复现你的核心技术要多久？真正的技术壁垒在哪，还是主要靠工程集成？"),
            ("安全与合规", "涉及数据、隐私、电气安全时，你是怎么规避风险的？是否符合相关规范？"),
            ("现场演示准备", "演示时最容易出问题的环节是哪个？你准备了什么兜底方案？"),
            ("工程落地与迭代", "从原型到可用产品还差什么？下一阶段的工程里程碑和最大技术卡点是什么？"),
        ],
        "business": [
            ("商业模式与盈利逻辑", "谁付费、为什么愿意付费、怎么持续付费？客单价、毛利、复购/续费分别是多少？"),
            ("市场空间与目标客户", "目标市场多大？可服务市场（SOM）怎么测算？前100个客户是谁、怎么触达？"),
            ("单位经济模型", "获客成本、交付成本、单客户价值是多少？多久能覆盖成本？"),
            ("竞品与差异化", "主要竞品是谁？你比他们便宜/好用/快在哪里？差异能不能量化？"),
            ("增长与渠道", "靠什么渠道获客？冷启动怎么破冰？增长是否可持续？"),
            ("收入来源与定价", "有几种收入来源？定价依据是什么？用户对价格的接受度验证过吗？"),
            ("财务预测依据", "收入、成本、盈亏平衡的测算依据是什么？假设是否过于乐观？"),
            ("团队与运营能力", "团队凭什么能把这个商业模式跑通？缺的关键岗位/资源是什么？"),
            ("失败风险与止损", "这个商业模式最大的失败风险是什么？什么信号出现就该调整方向？"),
            ("规模与复制路径", "从试点到规模复制的关键卡点是什么？不同城市/客群的复制成本一样吗？"),
        ],
        "modeling": [
            ("模型假设合理性", "每条假设的依据是什么？哪个假设最可能不成立，为什么仍采用？"),
            ("符号与变量定义", "关键符号和变量怎么定义？量纲和单位是否自洽？"),
            ("模型建立思路", "为什么选这个模型而不是别的？模型与题意的对应关系是什么？"),
            ("求解方法与算法", "用了什么求解方法？复杂度是多少？有没有更优替代？"),
            ("数据来源与预处理", "数据从哪来？缺失、异常、量纲不一致怎么处理？"),
            ("结果正确性", "结果怎么验证是合理的？有没有量级/边界检查？"),
            ("灵敏度分析", "哪个参数对结果影响最大？参数变化后结论会不会反转？"),
            ("模型检验与误差", "怎么检验模型？误差来源是什么？误差是否在可接受范围？"),
            ("模型评价与局限", "模型的适用条件和局限性是什么？什么情况下会失效？"),
            ("可改进方向", "如果时间充足，你会优先改进模型的哪个部分？为什么？"),
        ],
        "academic": [
            ("研究问题与价值", "你的研究问题是什么？它解决的是哪个真问题，学术/社会价值在哪？"),
            ("文献与创新点", "国内外做到什么程度了？你的创新点是增量还是实质突破？"),
            ("研究设计与方法", "为什么用这个方法？样本、对照、变量怎么设计的？"),
            ("数据与证据链", "关键结论靠哪些数据支撑？数据怎么采集、怎么保证可信？"),
            ("实验与对比", "有没有对照组/基线？结果差异是否显著、可复现？"),
            ("局限性与诚实性", "研究的最大局限是什么？哪些结论不能外推？"),
            ("成果与知识产权", "成果形式是什么？学生第一完成人、产权归属是否清晰？"),
            ("结论的边界", "结论在什么条件下成立？换场景/人群还成立吗？"),
            ("下一步研究", "后续要补什么实验或数据才能让结论更硬？"),
            ("评委挑刺", "如果评委质疑你的方法和数据，你最怕被问哪一点？怎么回答？"),
        ],
    }
    items = sets.get(kind, sets["engineering"])
    return "\n".join(f"{i}. {title}：{detail}" for i, (title, detail) in enumerate(items, 1))


def _chapter_block(state: dict) -> str:
    """章节结构：前端定制 > 知识库官方章节 > 内置 12 章。"""
    req = [str(c).strip() for c in (state.get("outline_requirement") or []) if str(c).strip()]
    if req:
        return "章节严格按以下顺序与标题组织（标题原样使用，最多三级标题）：\n" + \
               "\n".join("## " + c for c in req[:20])
    official = _official_chapters(state)
    if official:
        return "章节严格按以下官方申报书章节顺序与标题组织（标题原样使用，最多三级标题）：\n" + \
               "\n".join("## " + c for c in official[:20])
    return "章节依次为：\n\n" + _DEFAULT_CHAPTERS


def _stream_llm(prompt, field, every=8):
    """流式调用 LLM：边生成边把累积文本写进 partial，前端即可逐字看到内容。

    这样做的原因：否则一个节点（如写申报书）要跑 40～60 秒才一次性吐出全文，
    用户盯着占位符干等，就是所谓的「块状流动」。
    失败兜底：已生成了较完整内容就用已有部分，否则退回一次性 invoke。
    """
    buf = []
    try:
        for i, ch in enumerate(llm.stream([HumanMessage(content=prompt)])):
            buf.append(ch.content or "")
            if i % every == 0:
                set_partial_field(field, "".join(buf))
        set_partial_field(field, "".join(buf))
    except Exception as e:
        partial_text = "".join(buf)
        print(f"[stream] {field} 流式中断（{e}），已生成 {len(partial_text)} 字")
        if len(partial_text) < 1500:      # 内容太少，残缺不可用，重跑一次
            return llm.invoke([HumanMessage(content=prompt)]).content.strip()
        return partial_text.strip()
    return "".join(buf).strip()


def _build_outline(state: CompetitionState) -> str:
    """Step 1 · 构思纲要：先论证站位与创新点、分配各章要点，再动笔写正文。"""
    prompt = f"""你是科创赛事申报书的主笔。在动笔写正文之前，先为下面这个项目构思一份**写作纲要**。

赛事：{state['competition_name']}
项目创意：{state.get('idea', '')}
一句话定位：{state.get('one_liner', '')}
赛事评分规则：{state.get('parsed_rules', '')[:1200]}
竞品分析：{state.get('competitor_analysis', '')[:1800]}
技术方案：{state.get('tech_solution', '')[:1800]}
商业模式：{state.get('business_model', '')[:1200]}
社会价值：{state.get('social_value', '')[:1000]}
{_ref_block(state, '项目简介')}

请输出一份 Markdown 纲要（1200～1800 字），包含以下六部分：
## 一、项目定位
（赛道现状、同类方案空白、本项目站位，直接对接评审「创新性」）

## 二、需求与痛点
（真实场景、受益对象、痛点强度，对接「社会价值 / 实用性」）

## 三、技术路线关键环节
（3～5 个关键环节，来自技术方案，不许空泛）

## 四、创新点论证（四维）
必须逐条写清「技术 / 产品 / 模式 / 社会价值」四个维度的创新点，每条都要有具体内容支撑，禁止写「具有较强的创新性」这类空话。

## 五、商业闭环与落地路径
（来自商业模式与实施计划的关键结论）

## 六、各章要点分配
（下面 12 章每章写 2～3 句核心论点 + 必须用到的素材：一、项目概述 / 二、背景与痛点分析 / 三、目标用户与应用场景 / 四、解决方案与产品形态 / 五、技术方案与系统架构 / 六、核心创新点 / 七、竞品对比与差异化优势 / 八、商业模式与市场空间 / 九、风险分析与应对措施 / 十、团队分工与执行计划 / 十一、社会价值与应用前景 / 十二、结语）

要求：只写纲要和论点，不要写正文段落；中文标点用全角。
"""
    return _stream_llm(prompt, "proposal_outline")


def _parse_patch_list(text):
    """解析自检补丁清单（JSON 数组）；失败返回空列表。"""
    import json as _json
    t = re.sub(r"```(?:json)?", "", text or "")
    start = t.find("[")
    if start < 0:
        return []
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "[":
            depth += 1
        elif t[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return _json.loads(t[start:i + 1])
                except Exception:
                    return []
    return []


def _apply_patches(proposal, patches):
    """按 find→replace 逐条定点替换（只替换第一处），找不到就跳过。"""
    n = 0
    for p in (patches or []):
        if not isinstance(p, dict):
            continue
        find = p.get("find") or ""
        replace = p.get("replace") or ""
        if find and find in proposal:
            proposal = proposal.replace(find, replace, 1)
            n += 1
    return proposal, n


def _selfcheck_proposal(state: CompetitionState, proposal: str):
    """Step 3 · 轻量自检：只输出补丁清单并本地 apply，不重输出全文。

    返回 (修补后的正文, 实际应用补丁数)。
    """
    prompt = f"""你是科创赛事申报书的终审编辑。请快速自检下面这份申报书，**只输出需要修补的补丁清单（JSON 数组），不要输出全文**。

项目创意：{state.get('idea', '')}
赛事：{state['competition_name']}

【申报书全文】
{proposal}

自检要点：
① 章节呼应有无前后矛盾；
② 空泛表述（「显著提升」「广泛应用」「赋能」「前景广阔」等无数据支撑）；
③ 数字有无推算过程、有无编造引用；
④ 禁用套话出现即改写：随着、综上所述、赋能、打造生态、一站式、闭环、深度融合（章节标题中的词不在此列）。

只输出一个 JSON 数组（不要任何其它文字、不要 markdown 代码块），每个补丁形如：
{{"find":"申报书里逐字存在的短句（20～60 字）","replace":"改后文字"}}

要求：
1. find 必须从申报书里逐字原样摘出，否则替换不上；
2. 只列真正有问题的补丁，没问题就输出 []；
3. 不要改动标题与结构，每处只做定点修补。
"""
    resp = llm.invoke([HumanMessage(content=prompt)])
    patches = _parse_patch_list(resp.content)
    proposal, n = _apply_patches(proposal, patches)
    return proposal, n


def deep_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 深度版申报书 Agent：三段链式——构思纲要 → 正文写作 → 自检修补"""
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

    analysis_block = f"""
【前面的深度分析结果 —— 必须融入申报书对应章节，不要照抄原文，而是提炼关键结论与数字】
竞品分析：
{state.get('competitor_analysis', '')[:2500]}

商业模式：
{state.get('business_model', '')[:2000]}

风险分析：
{state.get('risk_analysis', '')[:1500]}

技术方案：
{state.get('tech_solution', '')[:2500]}

实施计划：
{state.get('implementation_plan', '')[:1500]}

社会价值：
{state.get('social_value', '')[:1200]}

项目简介：
{state.get('project_summary', '')[:800]}
"""

    # Step 1 · 构思纲要
    outline = _build_outline(state)
    state["proposal_outline"] = outline

    prompt = f"""你是资深科创赛事申报书写作专家。
{task_line}

【写作纲要 —— 各章必须按此纲要的核心论点与素材展开，不得与之冲突】
{outline}

{source_label}：{source_text}
{revise_block}
{analysis_block}
{_ref_block(state, '项目简介')}
{_official_ref(state)}
{_industry_ref()}

注意：
1. 保留用户原来的核心内容和结构，不要全部推翻重写
2. 把写得太简略的地方补充完整
3. 把逻辑不通的地方理顺
4. 加上比赛需要的评分点
5. 前面分析的竞品、商业模式、风险、技术方案内容，必须全部融入到申报书对应章节里，补充用户草稿里不足的地方
6. 每个二级小节至少 300 字，拆成 2～3 个自然段；任何标题下面都必须有正文，不允许空小节
7. 涉及数字时给出推算过程并标明是测算值，不要编造引用来源

请写一份完整详实的申报书，全文 4500～6000 字，低于 3200 字判不合格，每个章节都要展开成完整段落，不要简略。
{_chapter_block(state)}
{_competition_focus(state)}

{_CONCRETE_SPEC}
{_humanize_spec(state)}
{_PROPOSAL_SPEC}
"""
    proposal = _stream_llm(prompt, "proposal")

    # Step 3 · 自检修补（轻量：只输出补丁并本地 apply，不重输出全文）
    proposal, patch_count = _selfcheck_proposal(state, proposal)
    state["proposal_selfcheck"] = f"已完成自检，定点修补 {patch_count} 处。"

    proposal, n = _expand_to_length(
        proposal, 3200,
        state.get('one_liner') or state['idea'][:40])
    state["proposal"] = proposal
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 深度版申报书：第 {state['revision_count']} 版，{n} 字")
    return state


def proposal_writer_agent(state: CompetitionState) -> CompetitionState:
    """✍️ 简洁版申报书 Agent：写约 1300 字的精简申报书（对应前端「简洁快速版」卡片）

    与深度版刻意拉开差距：这里只求「短而准」，五章、约 1300 字，
    供快速判断创意是否站得住脚；完整详实的提交版由 deep_writer_agent 输出（约 5000 字）。
    """
    _report_stage("writing")
    draft = state.get('proposal_draft', '')
    if draft.strip():
        source = (f"用户已上传申报书草稿，请做「优化精简」：保留原结构与核心内容，"
                  f"收紧啰嗦表述、补足缺失的评分点，篇幅与原稿大致相当，不要大幅膨胀。\n\n"
                  f"{_OPTIMIZE_SPEC}\n\n用户草稿：\n{draft}\n\n（原始创意：{state['idea']}）")
    else:
        source = f"项目创意：{state['idea']}"
    prompt = f"""你是科创赛事申报书写作专家。请写一份**精简版**申报书（对应前端「简洁快速版」）。

这一档的定位是「短而准」：用尽量短的篇幅把项目讲清楚，供快速判断创意是否站得住脚。
完整详实、可直接提交的申报书由深度版输出（约 5000 字、十二章），
所以这里**刻意不展开成长篇**，写太长反而违背这一档的用途。

赛事：{state['competition_name']}
{source}
规则解析：{state['parsed_rules']}
同质化分析：{state['similarity_report']}
（本模式不做外部调研，请基于项目创意本身往下推演；涉及数字时标明是测算值，不要编造引用来源）
一句话定位：{state.get('one_liner','')}
{_ref_block(state, '项目简介')}
{_official_ref(state)}
{_industry_ref()}

【篇幅硬性要求】
1. 全文 1300 字左右，允许区间 1100～1600 字。不足 1100 字或超出 1600 字都不合格。
2. 结构固定为以下五章，不要增删章节、不要中途省略：

## 项目简介
（约 200 字：做什么、给谁用、一句话定位如何落地）

## 痛点分析
（约 300 字：谁在什么场景下遇到什么麻烦，现有办法差在哪）

## 解决方案
（约 300 字：产品形态、核心功能、关键技术手段）

## 核心创新点
（约 300 字：与现有方案的两到三处具体差异，每处都要给依据）

## 社会价值
（约 200 字：落到具体受益对象和可验证的效果）

【质量要求】
1. 每章写成 1～2 个完整自然段，段内有论点、有展开、有依据；严禁一句话一段、严禁空小节。
2. 每章都要有实打实的内容：真实场景名称、具体数字（附推算或标明测算）、具体技术名词。
3. 禁止「大幅提高效率」「具有广阔前景」「赋能行业」这类没有信息量的表述。
4. 必须回应规则解析里的评分点，必须回应同质化分析里的差异点。
5. 中文标点用全角。
{_CONCRETE_SPEC}
{_humanize_spec(state)}
{_competition_focus(state)}
"""
    proposal, n = _expand_to_length(
        _stream_llm(prompt, "proposal"), 1100,
        state.get('one_liner') or state['idea'][:40])
    state["proposal"] = proposal
    state["revision_count"] = state.get("revision_count", 0) + 1
    print(f"✍️ 简洁版申报书：第 {state['revision_count']} 版，{n} 字")
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

{_tier_hint(state,
"【精简档】创意亮点、主要风险各写 2 点，每点 40～60 字，点到为止。上面的打分字段保持原格式，不要改动。",
"【完整档】创意亮点、主要风险各写 3～4 点，每点写成 100～150 字的完整段落，有具体依据。上面的打分字段保持原格式，不要改动。"
)}
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
    # 评分维度：优先用 scoring_weights（前端传），缺省用默认 5 维
    sw = state.get("scoring_weights") or []
    dims = []
    for item in sw:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and str(item[0]).strip():
            try:
                w = float(item[1])
            except Exception:
                w = 0
            if w > 0:
                dims.append((str(item[0]).strip(), w))
    if not dims:
        dims = [("结构完整性", 30), ("逻辑清晰度", 25), ("数据支撑", 20), ("格式规范", 15), ("说服力", 10)]
    score_lines = "\n".join("%s：__分" % name for name, _ in dims)
    weight_desc = "、".join("%s %d%%" % (name, int(w)) for name, w in dims)

    prompt = f"""你是科创赛事资深评委。请给下面的申报书文档打分（注意：只评文档质量，不评创意本身）。

申报书：
{state['proposal']}

请严格按下面格式输出（每项 0-100 分，可带一位小数）：

{score_lines}

然后给出：
1. 主要优点（至少3点）
2. 需要改进的地方（至少3点）

打分说明：
- {weight_desc}
不要给所有文档打接近的分数，要拉开差距。

{_tier_hint(state,
"【点评文字要求（精简档）】「主要优点」「需要改进的地方」各写 3 点，每点 40～60 字，点到为止。上面的打分字段保持原格式，不要改动。",
"【点评文字要求（完整档）】「主要优点」「需要改进的地方」各写 4～5 点，每点写成 120～200 字的完整段落，有具体依据、有展开。上面的打分字段保持原格式，不要改动。"
)}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["judge_feedback"] = response.content

    import re
    def _pick(label):
        m = re.search(re.escape(label) + r'[^0-9]*?(\d+(?:\.\d+)?)', response.content)
        return float(m.group(1)) if m else None

    sub = {name: _pick(name) for name, _ in dims}
    weights = {name: w / 100.0 for name, w in dims}
    state["judge_scores"] = [
        {"name": name, "score": (sub[name] if sub[name] is not None else None), "weight": int(w)}
        for name, w in dims
    ]

    if all(v is not None for v in sub.values()):
        state["score"] = int(round(sum(sub[name] * weights[name] for name, _ in dims)))
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
    return {"judge_feedback": state["judge_feedback"], "judge_scores": state["judge_scores"],
            "score": state["score"], "approved": state["approved"]}


def expert_review_agent(state: CompetitionState) -> CompetitionState:
    """🧑‍⚖️ MedPeer 式多专家模拟评审：技术/商业/落地三视角，分维度打分 + 逐条批注"""
    _report_stage("expert_review")
    prompt = f"""你是国家级科创赛事的评审委员会。请以「多专家视角」对下面这份申报书做一次模拟评审，就像专业同行评议（MedPeer 式）那样：不是只给一个总分，而是让不同专家从各自视角独立评审，给出分维度打分和能落地的逐条批注。

赛事：{state['competition_name']}
项目创意：{state.get('idea', '')}
一句话定位：{state.get('one_liner', '')}
单评委快评得分：{state.get('score', 0)}（仅供你参考，不是你的结论）

【申报书全文】
{state.get('proposal', '')[:6000]}

请只输出一个 JSON 对象（不要任何解释文字、不要 markdown 代码块），结构严格如下：
{{
  "overall_score": 86,
  "verdict": "修改后晋级",
  "experts": [
    {{"role":"技术视角","focus":"技术可行性、创新性、实现难度","score":88,
      "dimensions":[{{"name":"创新性","score":90,"comment":"一句话点评"}},{{"name":"技术可行性","score":86,"comment":"一句话点评"}},{{"name":"实现难度","score":88,"comment":"一句话点评"}}],
      "strengths":["具体优点1","具体优点2"],
      "issues":[{{"quote":"申报书中的相关原文（10-30字）","problem":"这里的问题是什么","suggestion":"怎么改"}}]}},
    {{"role":"商业视角","focus":"商业模式、市场空间、落地可行性","score":82,
      "dimensions":[{{"name":"商业模式","score":80,"comment":"一句话点评"}},{{"name":"市场空间","score":84,"comment":"一句话点评"}},{{"name":"落地可行性","score":82,"comment":"一句话点评"}}],
      "strengths":["具体优点1"],
      "issues":[{{"quote":"原文","problem":"问题","suggestion":"改法"}}]}},
    {{"role":"落地视角","focus":"落地可行性、实施路径、团队执行力","score":87,
      "dimensions":[{{"name":"落地可行性","score":86,"comment":"一句话点评"}},{{"name":"实施路径","score":88,"comment":"一句话点评"}},{{"name":"团队执行力","score":87,"comment":"一句话点评"}}],
      "strengths":["具体优点1"],
      "issues":[{{"quote":"原文","problem":"问题","suggestion":"改法"}}]}}
  ],
  "consensus":["三位专家一致认可的结论，至少1条"],
  "divergence":["专家之间存在分歧的点，至少1条；没有分歧就写\"无明显分歧\""],
  "priority_actions":[{{"priority":1,"action":"最优先改的动作","reason":"为什么"}},{{"priority":2,"action":"次优先动作","reason":"为什么"}},{{"priority":3,"action":"第三优先动作","reason":"为什么"}}],
  "disclaimer":"本评审由 AI 模拟多位专家视角生成，专家身份为虚构，仅供备赛参考，不代表真人评审意见。"
}}

硬性要求：
1. 三个视角必须各自独立给分；**三位专家总分两两相差 ≥8 分**（不要挤在 88-92）；overall_score 是三者按「落地视角权重略高」综合后的整数（0-100）。
2. role 只写「技术视角 / 商业视角 / 落地视角」三种之一，**不设任何专家人设、不出现任何职称、人名、院校名**。
3. issues 里必须包含**一条只有这个视角才会提的尖锐反对意见**（技术视角可质疑"算法门槛不高、别人三个月能复制"；商业视角可质疑"客单价撑不起获客成本"；落地视角可质疑"试点资源和实施路径支撑不起落地、团队执行力存疑"），三位不能都说"落地路径需要细化"这种谁都能说的话；quote 必须从申报书里摘原句，problem 说清问题，suggestion 给出可执行改法。
4. strengths 不要写「项目定位清晰」「痛点抓得准」这类通用褒义前缀，直接写具体、有依据的优点。
5. 每个维度 comment 20-40 字，必须是「打分依据」：指出申报书里哪句话/哪个数据支撑了这个分数，禁止「表现不错」「有待提升」这类空话。
6. 中文标点用全角。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["expert_review"] = response.content
    print("🧑‍⚖️ 多专家模拟评审：已生成")
    return {"expert_review": state["expert_review"]}


def defense_questions_agent(state: CompetitionState) -> CompetitionState:
    """🎤 答辩问题预测 Agent：出 10 个评委必问的尖锐问题，每个附约 200 字回答框架"""
    _report_stage("defense")
    proposal_brief = (state.get('proposal') or '').strip()
    proposal_line = (f"申报书要点（供提问时抓具体把柄，不要脱离它提问）：\n{proposal_brief[:2500]}\n"
                     if proposal_brief else "")
    prompt = f"""你是科创赛事答辩专家。请站在真实评委的角度，为下面的项目准备 10 个**必问、尖锐、能筛出项目真伪**的问题，并为每个问题给出约 200 字的回答框架。

项目：{state['idea']}
一句话定位：{state.get('one_liner', '')}
评委意见：{state['judge_feedback']}
{proposal_line}

【10 个问题必须按本比赛类型覆盖以下方向，每题都要点到具体质疑点；禁止「请介绍你的项目」「你的创新点是什么」这类泛泛而问】
{_defense_focus(state)}

【输出格式】每个问题单独一段，用「问题 N：……」开头，紧接着另起一行写「回答框架：」，再用约 200 字写出「从哪几个方向答、要摆哪些数据、要提前堵住哪个质疑」。不要写成标准答案，不要写成演讲稿，不要照抄申报书原文。

（匿名要求：严禁出现院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代。）
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["defense_questions"] = response.content
    print("🎤 答辩问题 Agent：已生成 10 个尖锐问题")
    # 只回传自己负责的字段：defense 与 ppt 在图上并行，若各自 return 整个 state，
    # 两者会同时写 competition_name 等公共字段，触发 LangGraph
    # InvalidUpdateError（Can receive only one value per step），导致整轮生成失败。
    return {"defense_questions": response.content}


def _media_context(state: dict) -> str:
    """PPT/演讲稿节点共享：把已产出的分析结果 + 申报书拼成参考块，避免内容空洞。"""
    blocks = []
    for label, key, cap in [
        ("项目简介", "project_summary", 600),
        ("竞品分析", "competitor_analysis", 1200),
        ("商业模式", "business_model", 1200),
        ("风险分析", "risk_analysis", 800),
        ("技术方案", "tech_solution", 1200),
        ("社会价值", "social_value", 800),
        ("实施计划", "implementation_plan", 800),
    ]:
        v = (state.get(key) or "").strip()
        if v:
            blocks.append(f"{label}：\n{v[:cap]}")
    proposal_brief = (state.get("proposal") or "").strip()
    if proposal_brief:
        blocks.append(f"申报书正文（提炼用，不照抄）：\n{proposal_brief[:3000]}")
    return "\n\n".join(blocks)


def ppt_outline_agent(state: CompetitionState) -> CompetitionState:
    """📊 PPT 大纲 Agent：生成路演 PPT 大纲"""
    _report_stage("ppt")
    prompt = f"""你是科创赛事路演 PPT 专家。请根据下面的项目与已产出的申报书/分析结果，生成路演 PPT 大纲。

项目：{state['idea']}
一句话定位：{state['one_liner']}
评委意见（PPT 要回应或补齐的短板）：{state.get('judge_feedback') or '（无）'}

【已产出的内容 —— 每页要点必须从中提炼具体数据/场景/结论，不要脱离这些空编】
{_media_context(state)}

{_tier_hint(state,
"生成 3 分钟路演大纲（8～10 页），每页只写标题 + 2～3 个要点短语，不要写完整句子。",
"生成 15～20 页路演大纲，每页写「标题 + 3～5 个要点 + 一段 50～80 字讲解稿」；要点必须落到具体数据、真实场景或明确结论，禁止「市场前景广阔」「赋能行业」这类空话，也不要整页只放一个口号。"
)}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["ppt_outline"] = response.content
    print(f"📊 PPT 大纲 Agent：已生成")
    # 同上：ppt 与 defense 并行，不能 return 整个 state
    return {"ppt_outline": response.content}


def speech_agent(state: CompetitionState) -> CompetitionState:
    """🎤 路演演讲稿 Agent：生成3分钟路演讲稿"""
    _report_stage("speech")
    prompt = f"""你是科创赛事路演专家。请根据以下项目，生成路演演讲稿。

项目：{state['idea']}
一句话定位：{state['one_liner']}
PPT大纲：{state['ppt_outline']}

【已产出的内容 —— 讲稿里的数据、场景、竞品对比必须来自下面这些，不要脱离空编】
{_media_context(state)}

请写：
1. 开场：抓眼球，讲痛点
2. 中间：讲解决方案、创新点、竞品对比
3. 结尾：讲价值、呼吁

语言口语化，有感染力，照着念就行，不要太书面。
{_tier_hint(state,
"控制在 800～1000 字左右（约 3 分钟语速）。",
"控制在 2000～2500 字左右（约 8 分钟语速），每个部分讲得更深入、更有细节。"
)}
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

请严格针对这份申报书的具体内容，分四部分输出：
1. 结构完整性
2. 内容亮点
3. 待优化点
4. 评审建议

{_tier_hint(state,
"【精简档】每部分 1～2 句，全文 300～500 字，直接给结论，不要泛泛而谈。",
"【完整档】每部分写成 200～350 字的完整段落，全文 1000～1500 字，按「现状→问题→影响→建议」展开，要有具体依据。"
)}
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["proposal_analysis"] = response.content
    print("申报书快速诊断 Agent：完成")
    return {"proposal_analysis": state["proposal_analysis"]}


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
- 匿名要求：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代。
"""
    response = llm.invoke([HumanMessage(content=prompt)])
    state["rich_media"] = response.content
    print("🎞️ 富媒体 Agent：已生成")
    return state


def should_iterate(state: CompetitionState):
    if state["approved"] or (state.get("revision_count") or 0) >= 2:
        return ["defense", "ppt"]
    return ["revise"]


def should_iterate_fast(state: CompetitionState):
    """简洁版可选迭代：仅当用户开启 iterate 且低分且未迭代过时返工一轮"""
    if not state.get("iterate", False):
        return ["defense", "ppt"]
    if state["approved"] or (state.get("revision_count") or 0) >= 2:
        return ["defense", "ppt"]
    return ["revise"]


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
workflow.add_edge("writer", "proposal_analysis")
workflow.add_conditional_edges("judge", should_iterate_fast)
workflow.add_edge("revise", "judge")
workflow.add_edge("defense", "speech")
workflow.add_edge("ppt", "speech")
workflow.add_edge("proposal_analysis", END)
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
deep_workflow.add_node("expert_review", expert_review_agent)
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
deep_workflow.add_edge("writer", "expert_review")
deep_workflow.add_edge("judge", "proposal_analysis")
deep_workflow.add_edge("expert_review", "proposal_analysis")
deep_workflow.add_conditional_edges("proposal_analysis", should_iterate)
deep_workflow.add_edge("revise", "judge")
deep_workflow.add_edge("revise", "expert_review")
deep_workflow.add_edge("defense", "speech")
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
