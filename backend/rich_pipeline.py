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
from langchain_deepseek import ChatDeepSeek

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
        _llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
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

V4. 蒸馏_v4 弱项闭环 + 生成期强制校验（2026-10-03 追加，针对 20261002 差距报告 5 项待修复；深化自 v2/v3 已核验公开来源，非获奖作品原文）：
  V4.1 痛点量化落地（生成期强制，对应待修复①）：痛点段须含≥2个数据锚点（规模×严重度×未被满足率）+1个现有方案具体缺陷点（点名竞品，贵/慢/漏在哪，禁写「目前尚无有效解决方案」）；显式交代调研过程（走访N/访谈M/问卷K，含有效回收率），无真实调研写「测算：基于XX假设」，严禁编造；痛点→方案→该痛点被解决到什么程度用同一组锚点回扣。
  V4.2 图表四查执行（生成期强制，对应待修复②，须导出前逐页过）：①标题即结论（洞察句+20字内）②图注有来源（实测/公开机构+年份/测算基于XX假设，混合来源点明哪条实测哪条测算）③无溢出/无裁切/无压边（headless 截图逐页复核，未过即打回）④去装饰（禁3D/厚边框/Excel网格/装饰图标）；2×2象限轴须可量化并标坐标含义，雷达图≤7维且每维对应正文一个论点。
  V4.3 佐证内容填实（生成期强制，对应待修复③）：每个优势亮点后必须有可指认佐证；佐证章/佐证页须含四件套最小集——①知识产权(标已授权/受理中/撰写中) ②第三方检测/查新(标机构+编号/待补) ③用户反馈/试点(标样本量) ④合作意向/获奖(标状态)；「待补」项必须给「可获取路径」模板（如「实用新型专利1项（撰写中，预计X月提交）」），禁止留白即消失。
  V4.4 财务三情景（生成期强制，对应待修复④）：商业模式/财务章必须含保守/中性/乐观三情景（各给销量/收入/毛利率/盈亏平衡月），假设回溯到试点/调研数据（如获客成本按前100个付费客户实际支出测算）；成本结构按百分比拆解+资金分配比例（如40%研发/30%市场/30%团队，每笔拆到具体动作）；年增长率>300%、毛利率>80%、市占>10%须给保守情景兜底与推导链。
  V4.5 导出物密度自动校验（v4 新增，生成期强制，对应待修复⑤）：路演PPT每页≤100字、≤6行、≤5要点（标题36-44pt、正文18-20pt、指标60-72pt）；申报书每节≤800字；导出/保存后由脚本逐页统计字数与行数，超阈即打回重生成；tmp_export.pdf 等实时导出须做每页密度核查，超线告警。

V5. 蒸馏_v5 弱项强化（2026-10-04 追加，针对 v5 对标差距报告新增弱项；来源均为官方组委会/高校官方/创服机构复盘，非获奖作品原文）：
  V5.1 互联网+ 2026 评审导向（对应新增弱项）：造假一票否决——科技成果/知识产权/财务/运营/荣誉须真实准确有效，弄虚作假直接取消资格；调研须完整证据链（问卷原始数据/访谈转写/带时间地点实地照片/实验记录本归档，调研场所含「企业」）；红旅赛道绑定「四个一线」(科技创新/乡村振兴/城市社区治理/城乡融合发展)，须指认具体一线场景与真实问题，且须参加「青年红色筑梦之旅」活动（资格挂钩）；专创融合成硬条款，计划书须说明与课程/专业/实验/科研训练/社会实践逻辑联系。
  V5.2 iCAN 双盲官方口径（对应新增弱项，补长期缺失）：创新赛道双盲评审，专利/合同/论文不作为评审依据，重点聚焦产品实物与开发过程；总分=巡展评分×20%+分组答辩×80%（巡展：实用性25+技术创新25+现场演示50；答辩：创新性35+实用性25+原创性20+技术方案20）；原创性20分须「构思到成品过程可追溯、逻辑连贯、佐证真实、完整呈现研发节点」；盲审违规(校名/单位名/导师名)每处扣5分；半决赛6分讲+4分答、总决赛10分讲+5分答。
  V5.3 国创结题优秀门槛（对应新增弱项）：合格=国创/省创满足2项结题条件(必选1+可选1)，优秀=至少3项且层级更高；优秀硬成果含学生一作核心/SCI或发明专利授权、实用新型/软著(一作)、B类及以上省一等奖/国奖、研究报告获县以上政府或市以上行业协会盖章采纳、实体公司持续经营且季度营收超2万(完税/对公流水)；研究报告须附知网查重≤15-20%+AIGC检测；成果不得重复用于不同项目结题。结题报告须含「成果清单+佐证路径+查重达标」硬结构。
  V5.4 挑战杯科技发明第4权重澄清（对应往轮待补）：主干=创新性30/可行性30/科学先进性20 稳定，第4项各校不一(以本校通知为准：wids=评委意见20；ncpu=社会价值20+团队15+答辩10；nankai=现实意义40+综合10；hznu=现实意义45)；导出物须同时覆盖技术硬指标与「经济效益+推广价值+成熟度+答辩」软指标。
  V5.5 路演PPT 决策导向叙事（对应新增弱项）：每页先结论→理由→证据(不按时间线)；一页一核心、≤5要点，答不上「对应评委哪个质疑」即删；标准叙事=五大幕(定义问题→凭什么是你→如何解决→值不值得→证据与信任)；决赛陈述7-9分钟/约1800字，备用隐藏页承载技术参数与财务模型。
  V5.6 小挑评审五维巩固（对应新增弱项）：社会价值/实践过程/创新意义/发展前景/团队协作均须有对应章节，「社会价值」「实践过程」须有可指认调研/落地证据。
  V5.7 竞品/第三方数据来源标注（对应往轮待修复③）：第三方与竞品数据须标「检索于 YYYY-MM-DD，来源：xxx」，不得裸引无日期无出处数据。
V6. 蒸馏_v6 官方/高校精确权重 + 路演结构字号 + 答辩实战（2026-10-07 追加，来源均为官方组委会/高校官方/创服机构评委复盘，非获奖作品原文）：
  V6.1 互联网+ 高教主赛道精确分值（生成期自检）：创意组=个人成长30+项目创新30+产业价值25+团队协作15；创业组=个人成长25+项目创新30+产业价值30+团队协作15；四维度均须显式覆盖，调研深入为个人成长核心项。
  V6.2 互联网+ 红旅赛道精确分值：公益组=个人成长30+公益价值10+项目创新20+发展前景20+团队协作20；创意组=个人成长30+项目创新30+发展前景20+团队协作20；创业组=个人成长25+项目创新30+发展前景30+团队协作15；各组均须参加「青年红色筑梦之旅」活动(参赛资格挂钩)，公益组须显式声明非营利导向。
  V6.3 iCAN 创新组/创业组 100分制精确维度：创新组=创新性30+商业性25+技术方案25+产品介绍20(表达逻辑/团队协作/实物展示占20)；创业组=创始人背景20+创新性先进性30+市场化能力20+融资潜力20+落地规划10；专利/合同/论文不作评审依据，盲审违规每处扣5分。
  V6.4 路演PPT 标准10-15页结构+设计三原则（生成期强制）：结构=封面→痛点→方案→数据→壁垒→模式→团队→财务→规划→封底(15页为极限)；三原则=简洁(每页一事、正文≥18pt、禁Word搬家)/一致(配色≤3、字体≤2、全对齐)/可视化(柱状图/箭头流程、图旁必加结论、禁装饰图)；每页≤6条每条≤6字；全程5分钟内讲完。
  V6.5 答辩应对框架（生成期强制，对应答辩稿/答辩问题导出物）：PPT别当稿念(一页一重点≤6条)；图表一图一说删网格线高亮；答辩听清再答别抢答、没听清礼貌确认、结构化「首先其次最后」输出；遇到不懂坦诚「数据还在测算」+承诺赛后补发，绝不瞎编；预生成逐字稿分时段版(背景1min/方案1.5min/数据1min/规划1.5min)。
  V6.6 痛点场景化写法（强化V4.1，生成期强制）：痛点用真实场景+具体数据钩子开场(拒绝空话)；数据讲故事(「市场很大」→「2026年规模破200亿」并标来源)；竞品对比用一张表标黄自身优势栏；财务页须含成本结构占比(人/研发/推广各占%)。
  V7. 蒸馏_v7 挑战杯/国创专项 + 跨赛事证据链互锁 + 路演页级时间分配（2026-10-08 追加，来源均为 v6 已核验官方/高校/评委复盘，网络降级深化，非获奖作品原文）：
  V7.1 挑战杯专项（生成期按赛事分流）：社科类须附调研方法章(样本量/地域/信效度)+参考文献，重实证规范性；科技发明类须附发明点对比表(功能/成本/效率)+样机状态，重实物成熟度；挑战杯导出物用「应用前景+推广路径+社会/学术效益」替代「三情景财务」。
  V7.2 国创专项（生成期结构）：结题/中期须含过程性时间轴(立项→内容→路线→阶段成果→经费→下一步)+成果清单(论文/专利/软著/获奖标状态)+经费科目占比(设备/材料/差旅/出版)；重学生主体性，成员实质贡献可指认。
  V7.3 跨赛事证据链互锁（生成期硬门禁，强化V4.3）：申报书/路演PPT/答辩稿 三处同一指标必须完全一致；每个关键数字带来源标签(实测/估算/预测)，禁裸数字；方案章承诺效果须在佐证章回扣同一数字与来源；导出前做跨文件数字一致性校验。
  V7.4 路演页级时间分配（深化V6.4，生成期输出）：10-15页按300秒分配(封面10→痛点25→方案40→数据35→壁垒25→模式30→团队20→财务25→规划30→封底10，技术壁垒页加25s从模式/规划挤，总时不超5'30")；每页配一句话结论作演讲锚点。
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


def _gen_assets(result, competition, idea, kb_data="", user_data=""):
    """第一步：让 LLM 设计图表 + 表格"""
    _ud = (("\n实测数据（团队输入；图表数字优先采用这里的值，source 标「团队输入」）：\n" + user_data + "\n")
           if user_data else "")
    material = f"""
项目：{idea}
赛事：{competition}
一句话定位：{result.get('one_liner','')}
竞品分析：{result.get('competitor_analysis','')[:2500]}
商业模式：{result.get('business_model','')[:2000]}
风险评估：{result.get('risk_analysis','')[:1500]}
技术方案：{result.get('tech_solution','')[:2000]}
实施计划：{result.get('implementation_plan','')[:1500]}
{_ud}"""
    kb_block = f"\n【可引用的行业真实数据】\n{kb_data}\n" if kb_data else ""
    prompt = f"""你是国家级科创赛事的路演数据可视化专家。根据以下项目材料，设计 6-8 张最有说服力的图表（charts）和 2-4 张关键表格（tables），要达到「2026 国赛超精美图表 A」水准。

{material}
{kb_block}

【图表 A 风格要求 —— 必须遵守】
1. 数据墨水比优先：不要 3D、不要厚重边框；网格线只留极淡虚线；关键数据点要突出。
2. 深色科技蓝底（#0F1535），高亮主色 #818CF8，系列色 #22B8CF / #C084FC / #F59E0B / #34D399 / #FB7185 / #A3E635。
3. 每张图都要「结论式标题 + 一句话洞察 + 数据来源」：标题直接给结论（如「目标市场规模三年翻三倍」），caption 是 20 字内的洞察，source 写来源+年份。
4. 数字必须来自材料或「可引用的行业真实数据」，优先引用上面给的真实数据并标注 source；测算值标「行业测算」并写清口径。每个数据点的 source 只能是三种合法值：①团队输入 ②公开数据（机构+年份，且必须是上面「可引用的行业真实数据」里真实出现的）③测算假设（写明「测算：基于 XX 假设」）。编不出这三种来源的数字一律不准上图；图上没有真实来源的数字，评委一问就露馅。
4-1. 预算构成、市场规模、实施时间线这三张图**必须**从「竞品分析/商业模式/技术方案/实施计划」里抽正文的具体测算值，严禁用 40/25/20/15、120/280/560/980/1500、10/30/55/80/100 这类示例占位数值；正文里没有对应的数就写「测算：基于 XX 假设」推一个，不许照搬示例数字。
4-2. 【主题一致性·硬性】所有竞品/场景/数据必须与「项目」同一赛道——先判断项目属于哪个赛道（如垃圾分类/环保、快递物流、医疗、教育…），竞品必须从该赛道选同类产品，严禁跨赛道（环保项目不得出现快递柜/驿站/丰巢/灯条/末端配送等物流竞品）；数字必须来自本项目正文，不得套用其他项目（如取件柜）的排队/柜口/单柜收入等数字。
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
0. 【团队实测数据优先】material 中的「实测数据（团队输入）」字段是用户填写的真实试点/成本/指标/时间线，图表数字优先采用这里的值，并在 source 标「团队输入」；该字段为空时才用正文/行业数据/测算。
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
            cur = {"type": "bullets", "title": m.group(1).strip().strip("#* ").strip(), "bullets": []}
        elif cur and line and len(slides) < 14:
            clean = re.sub(r"^[-*•·]\s*", "", line).strip()
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
            # 第二百三十五轮：标题剥掉两端 Markdown 加粗/标题标记，避免「市场规模**」这类星号残留
            title = m.group(1).strip().strip("#* ").strip()
            if not title or len(title) > 40:
                continue
            # 跳过文档级标题（「PPT 大纲」「路演大纲」「目录」等），它只是整份大纲的名字，不是某一页
            # 2026-09-30 417-2 残留修复：旧判据只认绝对等于「大纲/目录」，
            # 不认「智能巡检系统 · 3分钟路演大纲」「项目PPT大纲（16页）」这类带前后缀写法，
            # 导致文档级标题被当成一页正文 -> PPT 页数 +1、与大纲对不上（417-2 投诉场景）。
            # 新判据：去符号空白后以「大纲」结尾（允许 PPT/路演 前缀与括号页数后缀）或等于目录类。
            _norm = re.sub(r"[\s\u00b7\-\u2014_()（）\[\]【】]+", "", title)
            if re.search(r"(?:PPT|路演)?大纲(?:\d+页?)?$", _norm, re.IGNORECASE) \
                    or _norm in ("目录", "PPT目录", "目录页"):
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
    "列出三条", "给出", "输出", "列出", "呈现", "每条",
)


def _strip_md_bold(t):
    """剥掉「**关键词**：」这类 Markdown 加粗前缀，方便判断剩余文字是否是指令句。"""
    return re.sub(r'^\*{1,2}[^*]+\*{1,2}\s*[:：]?\s*', '', (t or '').strip())


def _looks_like_prompt_leak(t):
    """判断一段文字是不是 LLM 把写作指令误写进页面正文（评委直接看到 AI 痕迹）。"""
    s = _strip_md_bold(t)
    if not s:
        return False
    return s.startswith(_PROMPT_LEAK_PREFIXES)


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


def build_rich_assets(result, competition="", idea="", theme=None, user_data=""):
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
            _f_assets = _ex.submit(_gen_assets, result, competition, idea, kb_data, user_data)
            _f_deck = _ex.submit(_outline_deck, _outline)
            assets = _f_assets.result() or {}
            deck = _f_deck.result()
    except Exception as e:
        print(f"[rich] 并行设计失败，退回串行兜底：{e}")
        try:
            assets = _gen_assets(result, competition, idea, kb_data, user_data) or {}
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
        for s in slides[:18]:
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
        # L6：把图表引用注入到匹配的页面（市场/数据/趋势/对比/规模/用户/财务/架构/流程等），
        # 让 build_deck 能嵌入图表图片，不再「8 页全文字 0 图」。
        _chart_keywords = ("市场", "数据", "趋势", "对比", "竞品", "规模", "增长", "用户",
                           "财务", "架构", "流程", "痛点", "营收", "份额")
        _chart_iter = iter(sorted(chart_ids))
        for _s in norm:
            if _s.get("type") == "bullets" and any(k in (_s.get("title") or "") for k in _chart_keywords):
                try:
                    _cid = next(_chart_iter)
                except StopIteration:
                    break
                _s["type"] = "chart"
                _s["chart"] = _cid
        if norm and norm[0].get("type") != "cover":
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
