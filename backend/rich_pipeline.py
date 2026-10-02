"""
富媒体流水线：深度版生成完成后，自动产出
1. 结构化表格（tables）—— 前端 HTML 表格 + Word/PPT 复用
2. 数据图表（charts，PNG）—— 前端展示 + Word/PPT 复用
3. 路演 PPT 结构（deck）—— 前端预览 + 一键导出 .pptx

全部由 LLM 输出结构化 JSON，本地渲染，不依赖外部图像服务。
任何一步失败都会降级，不阻断主流程。
"""
import os
import re
import json
import time
import uuid

from langchain_core.messages import HumanMessage
from llm_factory import build_chat_model

try:
    from chart_renderer_pro import render as render_chart
except Exception:
    from chart_renderer import render as render_chart

GEN_DIR = os.path.join(os.path.dirname(__file__), "generated")

# 专用 LLM：比主链路更长超时/更多输出 token（结构化 JSON 比较长）
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        import dotenv
        dotenv.load_dotenv()
        # 清洗 NO_PROXY（与 competition_agents 相同：httpx 无法解析 "::1" 和分号分隔）
        _np = os.environ.get("NO_PROXY", "")
        if _np:
            os.environ["NO_PROXY"] = ",".join(
                x for x in _np.replace("::1", "").replace(";", ",").split(",") if x)
            os.environ["no_proxy"] = os.environ["NO_PROXY"]
        _llm = build_chat_model(
            temperature=0.2,
            max_tokens=8000,
            request_timeout=180,
            max_retries=2,
        )
    return _llm


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    if start < 0:
        raise ValueError("输出中没有 JSON")
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON 不完整")


def _invoke_json(prompt):
    resp = _get_llm().invoke([HumanMessage(content=prompt)])
    return _extract_json(resp.content)



# ---- 质量标杆（对标学习守护进程注入，与 competition_agents 同源）----
_QUALITY_BENCHMARK_SPEC = """【质量标杆 —— 必须遵守（对标金奖与官方评审口径，2026-09-30 蒸馏）】

A. 赛事差异化硬约束：按当前赛事套用对应一条，不得张冠李戴；拿不准就按「通用」写并标注待核实。
  · iCAN：作品简介≤400字 / 创新性≤200字 / 实用性≤200字 / 技术方案≤300字（官方申报书字数上限）；
    五要素=简介+核心创新点+市场前景+团队成员及分工+财务融资；须有能实现基本功能的实物。
  · 挑战杯（创业计划竞赛）：社会价值25 / 实践过程25 / 创新意义25 / 发展前景15 / 团队协作10
    —— 团队协作单占10分，团队章缺失即丢分；问辩考察回答的真实性与准确性。
  · 挑战杯（科技发明制作类）：可行性30 / 创新性30 / 科学性先进性20 / 评委意见20
    —— 可行性权重最高，须论证作品本身可行+技术操作可行+国内无同类明显优势。
  · 挑战杯（哲社类）：创新性20 / 科学性先进性20 / 实用性20 / 逻辑论证20 / 文字表述10 / 研究价值10
    —— 逻辑论证含「数据处理方法」4分，论据须科学可靠、结论严密。
  · 互联网+/国创：项目摘要是「定生死」模块（≤3页），须最短话讲清全貌
    （概述 / 核心创新1-2个 / 市场与竞争 / 成果与效益 / 团队与规划）；
    痛点聚焦1-3个真实具体痛点，须有调研数据或用户访谈佐证；意义须量化（社会/经济/教育价值）。
  · 国创申报书：立项依据含申请理由≈1000字、项目方案≈1500字（附图）、特色与创新点、进度安排；
    项目方案须含研究问题+拟解决途径+人员分工+预期成果。

B. 佐证材料（硬要求，缺即扣分）：专利 / 论文 / 软著 / 第三方检测 / 合作意向书 / 用户反馈 / 获奖证书，
   必须在正文或单独佐证页可指认；iCAN 须含《原创性承诺书》与盲审 IP 扫描件。
   「每个优势亮点后面都要有清晰可查的佐证」——禁止只有断言没有证据。

C. 痛点写法：痛点由项目优势倒推，「自己解决不掉的痛点不要写」；
   写具体人物+具体时刻+具体动作+卡在哪一步，配调研数据或用户访谈原话。

D. 团队章（硬要求）：只写「角色 + 职责」，须体现专业背景与项目匹配、组织分工合理；
   严禁编造姓名，需填真人处写「姓名：待填写」。

E. 图表规范：每张图须「结论式标题 + 20字内洞察 + 数据来源」；
   source 只允许三种合法值（团队输入 / 公开数据「机构+年份」/ 测算「基于XX假设」）；
   雷达=竞品多维对比、象限=竞争力定位、甘特=实施计划、热力=风险矩阵、堆叠=构成占比、环形=完成度；
   禁止 3D 与厚重边框。

F. 防污染（最高优先级，违反即作废本次输出）：
   1. 严禁写入任何获奖作品原文、第三方文档原文或整段转载，只输出自建原创表述。
   2. 严禁编造机构、年份、硬件型号、专利号、检测报告、合作方；拿不准写「测算：基于XX假设」或「待补」。
   3. 每个数字必须带来源标注（实测值 / 行业公开数据 / 测算值 / 设计目标值），严禁裸数字。
   4. 严禁断言已发生（已签约 / 已落地 / 已试点 / 已上线），用户没给的一律写「计划 / 拟 / 预计」。

G. 文风与匿名：与上面【去 AI 味】【具体化与落地要求】同为硬性，一并遵守；
   全程严禁出现院校名称、指导老师姓名、成员真实姓名。

H. 蒸馏_v3 弱项强化（2026-10-02 追加，针对对标差距报告弱项；深化自v2已核验公开来源，非获奖作品原文）：
  H1. 佐证材料内联（弱项）：每个优势亮点后须有可指认佐证；佐证页/章须含四件套最小集——①知识产权(专利/软著，标已授权/受理中/撰写中) ②第三方检测或查新(标机构+编号/待补) ③用户反馈或试点(截图/问卷/合同，标样本量) ④合作意向或获奖(标状态)；做成「佐证卡」：左图(截图≥40%)+右文(1行说明+来源标签+状态标签)，不可只写「已申请专利」而无受理号。
  H2. 痛点量化闭环（弱项）：痛点须含≥2个数据锚点(规模×严重度×未被满足率)+1个现有方案具体缺陷点(点名竞品)；显式交代调研过程(走访N/访谈M/问卷K，含有效回收率)，无真实调研写「测算：基于XX假设」，严禁编造；痛点→方案→被解决程度用同一组锚点回扣。
  H3. 图表视觉复核四查（弱项）：导出前逐页四查——①标题即结论(洞察句+20字内) ②图注有来源(实测/公开机构+年份/测算基于XX假设) ③无溢出/无裁切/无压边 ④去装饰(禁3D/厚边框/Excel网格/装饰图标)；2×2象限轴须可量化并标坐标含义。
  H4. 团队章可核验+盲审匿名（弱项）：成员=角色+职责+专业匹配+实质贡献(具体动作句式，禁空头衔)；指导老师只写理论指导专长；盲审用「成员A/B/C」，禁院校/导师/成员真名，需填真人写「姓名：待填写」。
  H5. 答辩证据链框架（答辩维度）：高频问题预生成覆盖[核心壁垒/最大风险/为何是你/数据可复现/专利进度/首年营收预测/资金用途]；回答=结论→证据链(实测+对比基线+来源+样本量)→主动堵质疑；严格区分实测/估算/预测，三处数字(申报书/PPT/答辩)必须一致。
"""

CHART_FORMAT = """
各 type 的 data 格式（严格遵守）：
- bar/column: {"categories":["A","B"],"values":[123,456],"ylabel":"单位"}
- hbar/rank: {"categories":["竞品A","竞品B","我们"],"values":[80,70,95],"xlabel":"评分/性能"}
- line/trend: {"x":["2024","2025"],"series":[{"name":"我们的","values":[1,2]}],"ylabel":"单位"}
- pie/donut: {"labels":["A","B"],"values":[30,70]}
- radar: {"labels":["技术","成本","体验","合规","扩展"],"series":[{"name":"我们","values":[9,7,8,6,8]}]}
- matrix/quadrant: {"points":[{"name":"我们","x":8,"y":7}],"xlabel":"横轴名","ylabel":"纵轴名"}
- architecture/arch: {"layers":[{"name":"应用层","boxes":["用户端","管理后台"]},{"name":"模型层","boxes":["DeepSeek"]}]}
- timeline/gantt: {"stages":[{"name":"需求调研","start":0,"end":2,"label":"第1-2月"}],"xlabel":"时间（月）"}
- funnel: {"labels":["曝光","注册","付费"],"values":[1000,300,80]}
- heatmap/risk: {"rows":["技术风险","市场风险","资金风险"],"cols":["低","中","高"],"values":[[0,1,2],[1,0,1],[0,0,2]]}
- stacked: {"categories":["2024","2025"],"series":[{"name":"软件","values":[30,40]},{"name":"硬件","values":[50,45]}],"ylabel":"万元"}
- gauge/ring: {"value":78,"max":100,"label":"原型完成度","unit":"%"}
每张 chart 顶层字段：id / type / title / caption / source / data。
source 写「来源 + 统计年份」（如「教育部 2024」「中国信通院 2025」），
材料里没有来源的测算值写「行业测算」，并在 caption 里点明是测算口径。
"""


def _load_kb_industry_data(competition):
    """从 data/*.txt 里找当前赛事的「行业数据」章节，喂给图表 LLM 引用真实数字。"""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.isdir(data_dir):
        return ""
    comp = str(competition or "")
    for fn in sorted(os.listdir(data_dir)):
        if not fn.endswith(".txt"):
            continue
        name = fn[:-4]
        if name in comp or comp in name or any(k in comp for k in
                ["国创", "挑战杯", "互联网+", "iCAN", "数学建模", "电子设计",
                 "蓝桥杯", "计算机设计", "广告艺术", "服务外包", "信息安全"]):
            try:
                with open(os.path.join(data_dir, fn), encoding="utf-8") as f:
                    txt = f.read()
            except Exception:
                continue
            m = re.search(r"##\s*行业数据[\s\S]*?(?=\n##\s|\Z)", txt)
            if m:
                return m.group(0).strip()
    return ""


def _gen_assets(result, competition, idea, kb_data=""):
    """第一步：让 LLM 设计图表 + 表格"""
    material = f"""
项目：{idea}
赛事：{competition}
一句话定位：{result.get('one_liner','')}
竞品分析：{result.get('competitor_analysis','')[:2500]}
商业模式：{result.get('business_model','')[:2000]}
风险评估：{result.get('risk_analysis','')[:1500]}
技术方案：{result.get('tech_solution','')[:2000]}
实施计划：{result.get('implementation_plan','')[:1500]}
"""
    # 417 轮：用户填的实测数据必须进图表。之前 prompt 里根本没有 user_data，
    # 模型只能用正文的测算值/示例值，导致「我填了试点准确率 96%，图上还是编的 92%」。
    _ud = (result.get('user_data') or '').strip()
    if _ud:
        material += f"\n【用户实测数据（最高优先级，直接上图）】\n{_ud[:1200]}\n"
    kb_block = f"\n【可引用的行业真实数据】\n{kb_data}\n" if kb_data else ""
    prompt = f"""你是国家级科创赛事的路演数据可视化专家。根据以下项目材料，设计 6-8 张最有说服力的图表（charts）和 2-4 张关键表格（tables），要达到「2026 国赛超精美图表 A」水准。

{material}
{kb_block}

【图表 A 风格要求 —— 必须遵守】
1. 数据墨水比优先：不要 3D、不要厚重边框；网格线只留极淡虚线；关键数据点要突出。
2. 深色科技蓝底（#0F1535），高亮主色 #818CF8，系列色 #22B8CF / #C084FC / #F59E0B / #34D399 / #FB7185 / #A3E635。
3. 每张图都要「结论式标题 + 一句话洞察 + 数据来源」：标题直接给结论（如「目标市场规模三年翻三倍」），caption 是 20 字内的洞察，source 写来源+年份。
0. 【数据来源优先级 —— 417 轮硬规则】①用户实测数据 > ②正文测算值 > ③上面「可引用的行业真实数据」> ④你自己推算。
   凡「用户实测数据」里出现过的指标（如试点准确率、单件成本、响应时长、覆盖人数、营收等），
   图上**必须原样用该实测值**并 source 写「实测」，不许替换成测算值或示例值；
   实测数据里没有的指标才允许用测算/公开数据，且 source 必须写明「测算」或机构+年份。
   同一张图里混用实测与测算时，caption 里点明「X 为实测，Y 为测算」，别让评委误判。
4. 数字必须来自材料或「可引用的行业真实数据」，优先引用上面给的真实数据并标注 source；测算值标「行业测算」并写清口径。每个数据点的 source 只能是三种合法值：①团队输入 ②公开数据（机构+年份，且必须是上面「可引用的行业真实数据」里真实出现的）③测算假设（写明「测算：基于 XX 假设」）。编不出这三种来源的数字一律不准上图；图上没有真实来源的数字，评委一问就露馅。
4-1. 预算构成、市场规模、实施时间线这三张图**必须**从「竞品分析/商业模式/技术方案/实施计划」里抽取已有数据（如排队 12→7 分钟、柜口利用率 55→75%、单柜月收入 1785 元、市场规模 XXX 万），严禁用 40/25/20/15、120/280/560/980/1500、10/30/55/80/100 这类示例占位数值；正文没有对应数字且用户没有明确假设时，不生成数值，改为「待核实：需要补充来源/实测数据」并在图表 caption 标明缺口。只有假设、推导链都写清楚时，才可生成「测算值」。
5. 图表类型必须多样（至少 8 张），且硬性覆盖下面各类，缺一不可：
   - radar 竞品/能力多维对比（1 张）
   - matrix 竞争力定位象限（1 张）
   - funnel 转化漏斗 或 architecture 系统架构（至少 1 张）
   - timeline 实施甘特（1 张）
   - hbar 竞品/能力排名（1 张）
   - heatmap 风险热力矩阵（1 张，rows=风险类型，cols=低/中/高）
   - stacked 构成/占比（1 张，如收入结构、成本结构）
   - gauge 单个关键指标（1 张，如完成度、评分）
   - 其余用 donut / bar / line 补充
   严禁只出 bar / pie / line 三种；预算用 donut、市场规模用 bar、增长用 line、竞品用 radar、竞争力定位用 matrix、转化用 funnel、实施用 timeline、技术用 architecture、排名用 hbar、风险用 heatmap，不要重复。

6. 按「内容 → 图表类型」自动匹配，不要张冠李戴：
   - 预算/成本构成 → donut 或 stacked
   - 市场规模/营收预测 → bar 或 line
   - 增长趋势/累计 → line
   - 竞品多维对比 → radar
   - 竞争定位/性价比 → matrix
   - 转化流程 → funnel
   - 实施计划/里程碑 → timeline
   - 系统/技术架构 → architecture
   - 排名/能力对比 → hbar
   - 风险概率×影响 → heatmap
   - 单个完成度/评分 → gauge

只能输出一个 JSON 对象，不要任何解释文字。格式：
{{
 "charts":[{{"id":"c1","type":"bar","title":"结论式标题","caption":"一句话洞察（20字内）","source":"来源+年份","data":{{...}}}}],
 "tables":[{{"id":"t1","title":"表格标题","header":["维度","我们","竞品A"],"rows":[["价格","99元","199元"]]}}]
}}
{CHART_FORMAT}
要求：
1. id 从 c1/t1 开始编号；type 从上面列表里选
2. 数字必须来自材料或行业真实数据，不能拍脑袋
3. 每张表格 3-6 行、表头不超过 5 列；cells 内容不超过 14 字
4. 图表要能在路演里"一眼看懂"，标题直接给结论（如"目标市场规模三年翻三倍"）
5. 匿名要求：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代""" + _QUALITY_BENCHMARK_SPEC
    return _invoke_json(prompt)


def _gen_deck(result, competition, idea, assets):
    """第二步：让 LLM 设计 PPT 页面结构（引用 c1/t1 资产）"""
    chart_ids = [c.get("id") for c in assets.get("charts", [])]
    table_ids = [t.get("id") for t in assets.get("tables", [])]
    material = f"""
项目：{idea}
赛事：{competition}
一句话定位：{result.get('one_liner','')}
项目简介：{result.get('project_summary','')[:1500]}
核心创新/技术：{result.get('tech_solution','')[:1800]}
商业模式：{result.get('business_model','')[:1500]}
竞品：{result.get('competitor_analysis','')[:1200]}
实施计划：{result.get('implementation_plan','')[:1000]}
社会价值：{result.get('social_value','')[:800]}
已有 PPT 大纲（可参考其结构）：{result.get('ppt_outline','')[:2000]}
可用图表 id：{chart_ids}
可用表格 id：{table_ids}
"""
    prompt = f"""你是顶级路演 PPT 设计师。根据材料设计一份 12-14 页的路演 PPT 页面结构。

{material}

只能输出一个 JSON 对象：{{"slides":[...]}}，不要任何解释文字。

可用页面类型：
- {{"type":"cover"}} 封面（1页，放最前）
- {{"type":"section","num":"1","title":"章节名","bullets":["本章要点一句话"]}} 章节隔页（2-3个）
- {{"type":"bullets","kicker":"01 / 痛点","title":"页标题","bullets":["**关键词**：一句话说明"]}} 要点页
- {{"type":"metrics","title":"页标题","metrics":["4.5亿：年住院人次","60%：复购意向","3倍：效率提升"]}} 数据卡页
- {{"type":"chart","kicker":"..","title":"页标题","bullets":["要点≤3条"],"chart":"c1"}} 图表页（chart 填上面给的 id）
- {{"type":"table","kicker":"..","title":"页标题","table":"t1","note":"数据口径一句话"}} 表格页（table 填 id）
- {{"type":"closing","title":"谢谢聆听","bullets":["slogan"]}} 结尾页

硬性要求：
1. 叙事线：痛点→方案→技术/创新→市场→商业模式→竞争壁垒→发展规划→社会价值→愿景
2. 信息密度要够：每个 bullets 页 4-6 条要点，每条 25-40 字，必须落到具体细节——
   写清"是谁、做什么、达到什么数字/比例/倍数"，禁止"大幅提升""前景广阔""赋能行业"这类空话
3. 每条尽量写成 "**关键词**：具体说明" 的形式，关键词不超过 6 个字
4. 至少 2 页用 chart（引用给定 id）、至少 1 页用 table（引用给定 id）、至少 1 页 metrics
5. kicker 用"序号 / 章节名"格式，全篇编号连贯
6. 每页可选加 "note"：演讲者备注，一句话讲这页想传达什么（导出后可在 PPT 备注栏看到）

【路演PPT质量标杆 —— 页面结构与视觉硬约束】
1. 默认 8 页压缩版：封面→痛点→解决方案→数据/Traction→竞争壁垒→商业模式→团队里程碑→愿景；每页只讲一个核心论点。
2. 标题即结论；每页 ≤100 字、≤6 行、≤5 要点；要点格式「关键词：具体说明（含数字）」。
3. 视觉系统：16:9、12列栅格；主色深海军蓝#0F1535、高亮#818CF8、正文#1A1A2E、背景#F8F8F6、数据强调#F59E0B。
4. 产品页必须有真实产品截图/流程图；数据页必须有大数字指标卡；竞争页必须用 2×2 矩阵或 radar。
5. 图表标题即结论，带 ≤20 字洞察和数据来源；禁用 3D/厚重边框/装饰图例。
6. 数据三分法：真实数据标来源，测算写「测算：基于XX假设」，待补充留空；严禁编造。
7. 结尾页不写「谢谢聆听」，写一句话定位+3条核心价值+明确下一步。

7. 匿名要求：严禁出现任何院校名称、指导老师姓名、团队成员真实姓名，团队一律用「本项目团队」指代""" + _QUALITY_BENCHMARK_SPEC
    return _invoke_json(prompt)


def _fallback_deck(result, idea):
    """deck 生成失败时的兜底：从 PPT 大纲 markdown 简单拆页"""
    slides = [{"type": "cover"}]
    outline = result.get("ppt_outline", "")
    cur = None
    for line in outline.split("\n"):
        line = line.strip()
        m = re.match(r"^#{1,3}\s+(.*)", line) or re.match(r"^(?:页?\d+[.、:：]|第?\d+页)\s*(.*)", line)
        if m and len(m.group(1)) <= 30:
            if cur:
                slides.append(cur)
            cur = {"type": "bullets", "title": m.group(1).lstrip("#* "), "bullets": []}
        elif cur and line and len(slides) < 14:
            clean = re.sub(r"^[-*•·]\s*", "", line)
            if len(clean) <= 40:
                cur.setdefault("bullets", []).append(clean)
    if cur:
        slides.append(cur)
    slides.append({"type": "closing", "title": "谢谢聆听"})
    return {"slides": slides}


def _outline_deck(outline):
    """第一百七十轮：PPT 严格以 ppt_outline 为唯一结构输入——大纲 N 页 → PPT N 页，
    每页标题/要点/顺序一一对应，讲解稿写入备注。无大纲返回空 slides + outline_missing 标记，
    不再生成固定页数模板。"""
    outline = (outline or "").strip()
    if not outline:
        return {"slides": [], "outline_missing": True}
    slides = []
    cur = None
    for line in outline.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 标题：## x / # x / 1. x / 第1页 x / 01 / x
        m = re.match(r"^#{1,4}\s+(.*)", line) or re.match(r"^(?:页?\d+|[（(]?\d+[）)])[.、:：\s]+(.*)", line)
        if m:
            title = m.group(1).strip().lstrip("#* ").strip()
            if not title or len(title) > 40:
                continue
            # 跳过文档级标题（「PPT 大纲」「路演大纲」「目录」等），它只是整份大纲的名字，不是某一页
            if (re.match(r"^(?:PPT|路演)?\s*大纲$|^目录$", title, re.IGNORECASE)
                    or re.search(r"(?:路演\s*)?PPT\s*大纲$|路演\s*大纲$", title, re.IGNORECASE)):
                continue
            if cur:
                slides.append(cur)
            cur = {"type": "bullets", "title": title, "bullets": [], "note": ""}
            continue
        if not cur:
            # 第一个标题之前的说明文字（如「PPT大纲」自身标题），跳过
            continue
        if re.match(r"^[-*•·]\s*", line) or re.match(r"^\d+[.、)）]\s*", line):
            clean = re.sub(r"^[-*•·]\s*|\d+[.、)）]\s*", "", line).strip()
            if clean:
                cur["bullets"].append(clean)
        else:
            # 非要点行 = 讲解稿/说明 → 写入演讲者备注
            clean = re.sub(r"^(讲解稿|备注|说明)[:：]\s*", "", line).strip()
            if 15 <= len(clean) <= 220:
                cur["note"] = (cur["note"] + "\n" + clean).strip() if cur["note"] else clean
    if cur:
        slides.append(cur)
    if not slides:
        return {"slides": [], "outline_missing": True}
    # 大纲第一页通常就是「封面」，标记为 cover，避免下游再插一个空封面导致页数 +1
    if "封面" in slides[0].get("title", ""):
        slides[0]["type"] = "cover"
    return {"slides": slides}


_PROMPT_LEAK_PREFIXES = (
    "用表格", "用图表", "用一段", "用数据", "用一张", "请给", "请输", "请用",
    "按如下", "按要求", "只输出", "不要任何", "不要写", "不要出现", "呈现三条",
    "列出三条",
)
_PROMPT_LEAK_RE = re.compile(
    r"(?:请(?:给出|提供|填写|生成|用(?:表格|图表|数据|一段|一张)?))|"
    r"(?:用(?:表格|图表|数据|一段|一张))|(?:按(?:如下|要求))"
)


def _strip_md_bold(t):
    """剥掉「**关键词**：」这类 Markdown 加粗前缀，方便判断剩余文字是否是指令句。"""
    return re.sub(r'^\*{1,2}[^*]+\*{1,2}\s*[:：]?\s*', '', (t or '').strip())


def _looks_like_prompt_leak(t):
    """判断一段文字是不是 LLM 把写作指令误写进页面正文（评委直接看到 AI 痕迹）。"""
    s = _strip_md_bold(t)
    if not s:
        return False
    return s.startswith(_PROMPT_LEAK_PREFIXES) or bool(_PROMPT_LEAK_RE.search(s))


def _clean_deck_slides(slides):
    """剔除 deck 页面里残留的 prompt 指令句，只保留成品内容。"""
    out = []
    for s in slides:
        if not isinstance(s, dict):
            out.append(s)
            continue
        s = dict(s)
        for _k in ("title", "kicker", "note", "subtitle"):
            _v = s.get(_k)
            if isinstance(_v, str) and _looks_like_prompt_leak(_v):
                s[_k] = ""
        for _k in ("bullets", "metrics"):
            _v = s.get(_k)
            if isinstance(_v, list):
                s[_k] = [x for x in _v if not (isinstance(x, str) and _looks_like_prompt_leak(x))]
        st = str(s.get("type") or "bullets").lower()
        if st not in ("cover", "closing", "thanks", "end"):
            has_content = bool(s.get("bullets") or s.get("metrics") or s.get("chart") or s.get("table"))
            if not has_content:
                s["type"] = "bullets"
                s["bullets"] = ["本页内容尚未取得可核验材料，请以申报书正文补充"]
        out.append(s)
    return out


def _project_name(idea, one_liner):
    """从创意里提一个简短项目名（封面标题/页脚用），别把整句创意当标题。"""
    idea = (idea or "").strip()
    m = re.match(r'^([^：:，,\n]{2,18})[：:，,]', idea)
    if m:
        return m.group(1).strip()
    if len(idea) <= 14:
        return idea
    ol = (one_liner or "").strip().rstrip('。！？!?')
    if 2 <= len(ol) <= 18:
        return ol
    return idea[:12]


VARIANT_FOR_THEME = {
    "tech": "v1", "cyber": "v1", "finance": "v2", "craft": "v1",
    "medical": "v2", "agri": "v1", "edu": "v1", "social": "v2",
    "ink": "v4", "academic": "v3",
}


def pick_theme(text):
    """按项目内容推断PPT主题：用户没手动指定主题时的兜底。

    打分规则：命中词越多分越高；同分时按 rules 顺序（越具体的赛道排越前）。
    """
    t = str(text or "")
    rules = [
        ("medical", "医疗 健康 护理 康复 护士 医药 问诊 病人 残障 养老 陪护 心理"),
        ("edu", "教育 教学 学生 校园 课程 学习 培训 教师 儿童 少儿 高考 考研"),
        ("agri", "农业 种植 养殖 农机 乡村 农户 生态 林业 畜牧 粮食 乡村振兴"),
        ("craft", "智能制造 机械 材料 建筑 工业 装备 机器人 嵌入式 传感器 硬件 自动化"),
        ("social", "公益 助老 无障碍 社区 志愿 慈善 弱势 留守儿童 帮扶"),
        ("ink", "文化 非遗 文创 古籍 书法 国风 传统 博物馆 艺术 文学 汉服"),
        ("cyber", "人工智能 大模型 算法 神经网络 机器学习 深度学习 自动驾驶 算力"),
        ("academic", "论文 开题 结题 科研 课题 学术 学位 毕业设计"),
        ("finance", "金融 支付 供应链 财务 融资 保险 银行 结算 投融"),
        ("tech", "平台 系统 软件 数据 互联网 区块链 物联网 小程序 APP 数字化"),
    ]
    best, best_score = "tech", 0
    for key, words in rules:
        score = sum(1 for w in words.split() if w in t)
        if score > best_score:
            best, best_score = key, score
    return best


def build_rich_assets(result, competition="", idea="", theme=None):
    """主入口：返回 {"charts":[...], "tables":[...], "deck":{...}, "theme":...}；失败字段为空"""
    out = {"charts": [], "tables": [], "deck": None}
    os.makedirs(GEN_DIR, exist_ok=True)

    # 主题：用户指定优先，没指定就按项目内容推断
    if not theme:
        theme = pick_theme(" ".join([idea or "", competition or "",
                                     result.get("one_liner", "") or ""]))
    out["theme"] = str(theme).lower()
    print(f"[rich] PPT 主题：{out['theme']}")

    # ---- 1. 图表/表格设计 与 PPT 结构设计 并行（第一百二十九轮） ----
    # 两者只共享「可用图表/表格 id」，而 id 是确定性的（c1..c8 / t1..t4），
    # 所以 PPT 结构可以用预测 id 先并行生成；后续链接时缺失的引用会自动降级为要点页。
    from concurrent.futures import ThreadPoolExecutor
    kb_data = ""
    try:
        kb_data = _load_kb_industry_data(competition)
    except Exception:
        pass
    assets, deck = {}, None
    # 第一百七十轮：PPT 结构唯一来源 = ppt_outline 大纲，不再让 LLM 自由设计页数/替换大纲。
    _outline = (result.get("ppt_outline") or "").strip()
    try:
        with ThreadPoolExecutor(max_workers=2) as _ex:
            _f_assets = _ex.submit(_gen_assets, result, competition, idea, kb_data)
            _f_deck = _ex.submit(_outline_deck, _outline)
            assets = _f_assets.result() or {}
            deck = _f_deck.result()
    except Exception as e:
        print(f"[rich] 并行设计失败，退回串行兜底：{e}")
        try:
            assets = _gen_assets(result, competition, idea, kb_data) or {}
        except Exception as e2:
            print(f"[rich] 图表/表格设计失败，降级：{e2}")
        try:
            deck = _outline_deck(_outline)
        except Exception as e3:
            print(f"[rich] PPT 结构生成失败，降级：{e3}")
            deck = {"slides": [], "outline_missing": True}

    charts, tables = [], []
    # 图表 PNG 用本次生成唯一后缀命名，避免每次生成都写 chart_c1.png 同名覆盖——
    # 否则历史记录里的图表 url 会被后续生成覆盖成别人的图，或文件被删后变空。
    _chart_suffix = "%d_%s" % (int(time.time()), uuid.uuid4().hex[:6])
    for c in (assets.get("charts") or [])[:8]:
        cid = str(c.get("id") or f"c{len(charts)+1}")
        path = render_chart(dict(c, id=cid), GEN_DIR, theme=theme)
        if path:
            _base, _ext = os.path.splitext(os.path.basename(path))
            safe = f"{_base}_{_chart_suffix}{_ext}"
            try:
                os.replace(path, os.path.join(GEN_DIR, safe))
            except Exception:
                safe = os.path.basename(path)  # 改名失败退回原名，不阻断
            charts.append({
                "id": cid, "title": c.get("title", ""),
                "caption": c.get("caption", ""),
                "source": c.get("source", ""),
                "url": f"/generated/{safe}",
                # 保留原始数值：PNG 不可 hover，前端要用 ECharts 重绘才支持「显示具体数值」
                "spec": c,
            })
            print(f"[rich] 图表 {cid} 渲染完成 -> {safe}")
    for t in (assets.get("tables") or [])[:5]:
        if not t.get("header") or not t.get("rows"):
            continue
        tables.append({
            "id": str(t.get("id") or f"t{len(tables)+1}"),
            "title": t.get("title", ""),
            "header": t["header"][:6],
            "rows": [r[:6] for r in t["rows"][:7]],
        })

    # ---- 2. PPT 结构（已在上面并行生成 deck）----
    slides = (deck or {}).get("slides") or []
    outline_missing = bool((deck or {}).get("outline_missing"))
    if not slides and not outline_missing:
        # 旧兜底仅在大纲解析失败时使用；无大纲(outline_missing)不再生成固定页数模板
        try:
            deck = _fallback_deck(result, idea)
            slides = deck.get("slides") or []
        except Exception as e:
            print(f"[rich] PPT 兜底也失败：{e}")
            deck = None
    if slides:
        table_map = {t["id"]: t for t in tables}
        chart_ids = {c["id"] for c in charts}
        norm = []
        # 417 轮：原上限 18 页会静默砍掉大纲后半章节（大纲 16 页时刚好不触发，
        # 但 20 页大纲会被砍到 18，评委对照大纲时发现缺页）。放宽到 30，
        # 足够覆盖任何赛事大纲长度；真超了也只在 30 处截断，不会误伤常规 15～20 页大纲。
        for s in slides[:30]:
            if not isinstance(s, dict):
                continue
            s.setdefault("type", "bullets")
            # table 引用 -> 实体
            if isinstance(s.get("table"), str):
                s["table"] = table_map.get(s["table"])
            # chart 引用必须存在，否则退化为普通要点页
            if s.get("chart") and s["chart"] not in chart_ids:
                s.pop("chart", None)
                s["type"] = "bullets"
            if s["type"] == "chart" and not s.get("chart"):
                s["type"] = "bullets"
            norm.append(s)
        # 417 轮：只在「大纲第一页确实不是封面」时才补封面。
        # 原判断只看 type，大纲首页写成「1. 项目封面」但没被标记成 cover 时会多插一页，
        # 导致 PPT 比大纲多 1 页。这里补一道标题识别，避免页数虚增。
        if norm and norm[0].get("type") != "cover":
            _t0 = str(norm[0].get("title") or "")
            if re.search(r"封面|首页|标题页|扉页", _t0):
                norm[0]["type"] = "cover"
            else:
                norm.insert(0, {"type": "cover"})
        deck["slides"] = _clean_deck_slides(norm)
        deck.setdefault("one_liner", result.get("one_liner", ""))
        deck.setdefault("project", _project_name(idea, result.get("one_liner", "")))
        deck.setdefault("competition", competition)
        deck.setdefault("theme", out["theme"])
        # 不同赛道配不同版式：学术类要序号列表居中，水墨类要留白，医疗类偏极简
        deck.setdefault("variant", VARIANT_FOR_THEME.get(out["theme"], "v1"))
        out["deck"] = deck

    out["charts"] = charts
    out["tables"] = tables
    return out
