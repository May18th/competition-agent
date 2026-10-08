# -*- coding: utf-8 -*-
"""
deck_agent.py —— 从深度版产物中提取结构化 PPT 素材

两个独立任务（可并发）：
  1. build_visuals(state)  → 图表数据（雷达、竞品矩阵、财务、甘特、预算）
  2. build_deck(state)     → PPT slides 结构（每页标题、要点、配图、演讲备注）

优先调用 LLM（DeepSeek）做结构化提取；当 API 余额不足 / 超时 / 输出为空时，
自动降级到规则提取，保证不依赖模型也能出图、出 PPT。

输出格式统一用 ```json 代码块，解析失败时降级，绝不抛异常。

作者：WorkBuddy（阿渡）  2026-09-25
"""
import os
import re
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from llm_factory import build_chat_model
from langchain_core.messages import HumanMessage

load_dotenv()

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
   严禁编造姓名，未提供真人信息时写「姓名由团队补充」或仅保留角色职责，不输出方括号占位符。

E. 图表规范：每张图须「结论式标题 + 20字内洞察 + 数据来源」；
   source 只允许三种合法值（团队输入 / 公开数据「机构+年份」/ 测算「基于XX假设」）；
   雷达=竞品多维对比、象限=竞争力定位、甘特=实施计划、热力=风险矩阵、堆叠=构成占比、环形=完成度；
   禁止 3D 与厚重边框。

F. 防污染（最高优先级，违反即作废本次输出）：
   1. 严禁写入任何获奖作品原文、第三方文档原文或整段转载，只输出自建原创表述。
   2. 严禁编造机构、年份、硬件型号、专利号、检测报告、合作方；有明确假设才写「测算：基于XX假设」，否则写「待核实：需要补充来源/实测数据」。
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


_llm = build_chat_model(
    temperature=0.35,
    max_tokens=4000,
    request_timeout=60,
    max_retries=3,
)


def _to_float(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[，,\s]", "", str(v))
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return 0.0
    val = float(m.group(0))
    if "亿" in str(v):
        val *= 10000
    return val


def _extract_json(text):
    """从模型返回文本里尽量安全地抠出一个 JSON 对象"""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        raw = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        raw = text[start : end + 1]
    try:
        return json.loads(raw)
    except Exception:
        return None


def _state_digest(state):
    key_text = "|".join([
        str(state.get("competition_name", "")),
        str(state.get("idea", ""))[:400],
        str(state.get("one_liner", ""))[:120],
        str(state.get("proposal", ""))[:600],
    ])
    return hashlib.sha256(key_text.encode("utf-8")).hexdigest()[:16]


def _summarize_text(parts, limit=1800):
    out = []
    total = 0
    for label, txt in parts:
        txt = str(txt or "").strip()
        if not txt:
            continue
        chunk = f"【{label}】\n{txt}\n"
        if total + len(chunk) > limit:
            left = max(0, limit - total - 80)
            if left > 40:
                out.append(f"【{label}】\n{txt[:left]}...\n")
            break
        out.append(chunk)
        total += len(chunk)
    return "\n".join(out)


# ------------------------------------------------------------------
# 1. 图表数据
# ------------------------------------------------------------------
def _pick_scores_from_text(text):
    scores = {}
    if not text:
        return scores
    dims = ["创新性", "可行性", "市场价值", "技术壁垒", "社会价值"]
    for dim in dims:
        for pat in [
            dim + r"[：:是为]*\s*(\d{1,3}(?:\.\d+)?)",
            dim + r"[^0-9]{0,8}(\d{1,3}(?:\.\d+)?)",
        ]:
            m = re.search(pat, text)
            if m:
                scores[dim] = _to_float(m.group(1))
                break
    return scores


def _parse_competitor_table(text):
    """从 markdown 表格提取竞品矩阵"""
    try:
        from media_factory import split_blocks
    except Exception:
        return None
    for kind, payload in split_blocks(text or ""):
        if kind != "table" or len(payload) < 3:
            continue
        header = payload[0]
        rows = payload[1:]
        if len(header) < 3:
            continue
        metrics = [str(c).strip() for c in header[1:]]
        items = []
        matrix = []
        for r in rows:
            if not r:
                continue
            items.append(str(r[0]).strip() or f"竞品{len(items) + 1}")
            row_scores = []
            for val in r[1:]:
                val_str = str(val)
                sc = _to_float(val_str)
                # 文字等级不能未经说明换算成 8.5/6/3.5；这会把主观判断伪装成
                # 可比较的量化评分。只有原文明确给出 0-10 数字时才进入矩阵。
                if sc == 0 and not re.search(r"(?<![\d.])0(?:\.0+)?(?![\d.])", val_str):
                    row_scores = []
                    break
                if sc > 10:
                    sc = sc / 10
                row_scores.append(sc)
            if row_scores and len(row_scores) == len(metrics):
                matrix.append(row_scores)
            elif items:
                items.pop()
        if items and matrix and len(items) == len(matrix):
            return {"items": items, "metrics": metrics, "matrix": matrix}
    return None


def _parse_finance(text):
    """从商业模式/申报书里提取前三年财务"""
    text = text or ""
    aliases = [
        ["第1年", "第一年", "Y1", "首年"],
        ["第2年", "第二年", "Y2"],
        ["第3年", "第三年", "Y3"],
    ]
    years_map = {}
    for i, alias_list in enumerate(aliases, 1):
        for a in alias_list:
            # 严格模式：收入、成本、利润
            m = re.search(
                re.escape(a) + r".{0,60}?收入[^0-9]*(\d+(?:\.\d+)?)[^0-9]{0,30}成本[^0-9]*(\d+(?:\.\d+)?)[^0-9]{0,30}利润[^0-9]*(-?\d+(?:\.\d+)?)",
                text, re.DOTALL,
            )
            if m:
                years_map[i] = (_to_float(m.group(1)), _to_float(m.group(2)), _to_float(m.group(3)))
                break
            # 宽松模式：先找到年份，再在附近 120 字抓收入/成本/利润
            m2 = re.search(re.escape(a) + r"[^。;；\n]{0,80}?收入[^0-9]*(\d+(?:\.\d+)?)", text)
            if m2:
                rev = _to_float(m2.group(1))
                tail = text[m2.end(): m2.end() + 120]
                cost = None
                profit = None
                mc = re.search(r"成本[^0-9]*(\d+(?:\.\d+)?)", tail)
                mp = re.search(r"利润[^0-9]*(-?\d+(?:\.\d+)?)", tail)
                if mc:
                    cost = _to_float(mc.group(1))
                if mp:
                    profit = _to_float(mp.group(1))
                if cost is not None and profit is not None:
                    years_map[i] = (rev, cost, profit)
                break
    if not years_map:
        return None
    idxs = sorted(years_map.keys())[:3]
    return {
        "years": [f"第{i}年" for i in idxs],
        "revenue": [years_map[i][0] for i in idxs],
        "cost": [years_map[i][1] for i in idxs],
        "profit": [years_map[i][2] for i in idxs],
        "unit": "万元",
    }


def _parse_timeline(text):
    """从实施计划文本提取阶段和周次"""
    phases = []
    starts = []
    ends = []
    if text:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.search(r"第?(\d+)[\-~～至到](\d+)[周周次]", line)
            if m:
                phase_name = re.sub(r"^[-·*▍\d\.、第周次\-~～至到\s]+", "", line).strip()
                phase_name = phase_name.replace("：", "").replace(":", "")
                if len(phase_name) < 2:
                    phase_name = f"阶段{len(phases) + 1}"
                phases.append(phase_name[:12])
                starts.append(int(_to_float(m.group(1))) - 1)
                ends.append(int(_to_float(m.group(2))))
    if not phases:
        # 没有用户/官方材料就不伪造时间线。空图比把模板周数交给评委更可靠，
        # 上层会把该图标成待核实或跳过渲染，用户补数据后可局部重绘。
        phases, starts, ends = [], [], []
    return {"phases": phases[:6], "start_week": starts[:6], "end_week": ends[:6]}


def _parse_budget(text):
    """从商业模式/申报书里提取预算占比"""
    labels = []
    values = []
    for label in ("研发", "生产", "营销", "运营"):
        m = re.search(label + r"[^0-9：:]{0,5}[:：]?\s*(\d{1,3}(?:\.\d+)?)\s*[%％]", text or "")
        if m:
            labels.append(label)
            values.append(_to_float(m.group(1)))
    if sum(values) > 0:
        return {"labels": labels, "values": values}
    # 没有预算来源时保持空数据，禁止把模板比例伪装成项目预算。
    return {"labels": [], "values": []}


def fallback_visuals(state):
    """LLM 不可用时，用规则从文本里抠图表数据"""
    visuals = {"radar": {}, "competitor": {}, "finance": {}, "timeline": {}, "budget": {}}

    scores = {}
    scores.update(_pick_scores_from_text(state.get("idea_feedback", "")))
    scores.update(_pick_scores_from_text(state.get("judge_feedback", "")))
    if len(scores) >= 3:
        labels = [k for k in ("创新性", "可行性", "市场价值", "技术壁垒", "社会价值") if k in scores]
        visuals["radar"] = {"labels": labels, "values": [scores[k] for k in labels]}

    comp = _parse_competitor_table(state.get("competitor_analysis", ""))
    if comp:
        visuals["competitor"] = comp

    fin = _parse_finance(state.get("business_model", "") or state.get("proposal", ""))
    if fin:
        visuals["finance"] = fin

    visuals["timeline"] = _parse_timeline(state.get("implementation_plan", ""))
    visuals["budget"] = _parse_budget(state.get("business_model", "") or state.get("proposal", ""))
    return visuals


def build_visuals(state):
    """返回 radar/competitor/finance/timeline/budget"""
    parts = [
        ("项目一句话定位", state.get("one_liner", "")),
        ("创意", state.get("idea", "")),
        ("规则解析", state.get("parsed_rules", "")),
        ("同质化分析", state.get("similarity_report", "")),
        ("竞品分析", state.get("competitor_analysis", "")),
        ("商业模式", state.get("business_model", "")),
        ("风险分析", state.get("risk_analysis", "")),
        ("技术方案", state.get("tech_solution", "")),
        ("实施计划", state.get("implementation_plan", "")),
        ("社会价值", state.get("social_value", "")),
        ("评委意见", state.get("judge_feedback", "")),
        ("创意评分反馈", state.get("idea_feedback", "")),
    ]
    context = _summarize_text(parts, limit=2800)

    prompt = f"""你是数据可视化专家。请从下面这份科创项目材料中提取能用于 matplotlib 画图的真实数据，输出一个 ```json 代码块。

要求：
1. 数值必须能在原文里找到依据，禁止凭空编造；找不到的字段就留空数组 / 空对象，不要硬填。
2. 财务数据只提取前三年，统一用“万元”作单位，数值只写纯数字。
3. 实施计划拆成 4-6 个阶段，start_week / end_week 是 0-8 的整数（共 8 周），end_week > start_week。
4. 竞品矩阵只对比“本项目 + 2-3 个竞品”，指标 3-5 个，得分 0-10，第一个条目必须是“本项目”。
5. 雷达图从评委意见/创意评分里提取五个维度得分 0-100；找不到就空对象。
6. 预算构成从商业模式/实施计划里找研发、生产/硬件、营销、运营等类别占比；只写百分比数字。

请严格输出 JSON 代码块，格式如下：
```json
{{
  "radar": {{"labels": ["创新性","可行性","市场价值","技术壁垒","社会价值"], "values": [82,74,68,71,80]}},
  "competitor": {{"items": ["本项目","竞品A","竞品B"], "metrics": ["功能完整度","价格优势","技术壁垒","易用性"], "matrix": [[9,8,9,8],[7,6,5,7],[6,7,4,6]]}},
  "finance": {{"years": ["第1年","第2年","第3年"], "revenue": [120,380,860], "cost": [150,300,560], "profit": [-30,80,300], "unit": "万元"}},
  "timeline": {{"phases": ["需求调研","原型开发","小批量试产","市场推广"], "start_week": [0,2,5,7], "end_week": [2,5,7,8]}},
  "budget": {{"labels": ["研发","生产","营销","运营"], "values": [45,30,15,10]}}
}}
```

材料如下：
{context}
""" + _QUALITY_BENCHMARK_SPEC
    llm_error = None
    try:
        resp = _llm.invoke([HumanMessage(content=prompt)])
        data = _extract_json(resp.content) or {}
    except Exception as e:
        data = {}
        llm_error = str(e)[:120]

    visuals = {"radar": {}, "competitor": {}, "finance": {}, "timeline": {}, "budget": {}}

    r = data.get("radar") or {}
    if r.get("labels") and r.get("values") and len(r["labels"]) == len(r["values"]):
        visuals["radar"] = r

    c = data.get("competitor") or {}
    if (c.get("items") and c.get("metrics") and c.get("matrix")
            and len(c["items"]) == len(c["matrix"])
            and all(len(row) == len(c["metrics"]) for row in c["matrix"])):
        visuals["competitor"] = c

    f = data.get("finance") or {}
    if f.get("years") and f.get("revenue") and f.get("cost"):
        ln = min(len(f["years"]), len(f["revenue"]), len(f["cost"]))
        profit = f.get("profit") or [f["revenue"][i] - f["cost"][i] for i in range(ln)]
        visuals["finance"] = {
            "years": f["years"][:ln],
            "revenue": [_to_float(x) for x in f["revenue"][:ln]],
            "cost": [_to_float(x) for x in f["cost"][:ln]],
            "profit": [_to_float(x) for x in profit[:ln]],
            "unit": f.get("unit") or "万元",
        }

    t = data.get("timeline") or {}
    if t.get("phases") and t.get("start_week") and t.get("end_week"):
        ln = min(len(t["phases"]), len(t["start_week"]), len(t["end_week"]))
        visuals["timeline"] = {
            "phases": [str(x) for x in t["phases"][:ln]],
            "start_week": [int(_to_float(x)) for x in t["start_week"][:ln]],
            "end_week": [max(int(_to_float(t["start_week"][i])) + 1, int(_to_float(t["end_week"][i]))) for i in range(ln)],
        }

    b = data.get("budget") or {}
    if b.get("labels") and b.get("values") and len(b["labels"]) == len(b["values"]):
        visuals["budget"] = {"labels": b["labels"], "values": [_to_float(x) for x in b["values"]]}

    # 若 LLM 没给出任何有效数据，降级到规则提取
    if not any(visuals.values()):
        visuals = fallback_visuals(state)
        return visuals, (llm_error or "LLM 未返回有效数据，已降级规则提取")
    return visuals, None


# ------------------------------------------------------------------
# 2. PPT 结构
# ------------------------------------------------------------------
def _split_proposal(proposal):
    """按章节标题切分申报书"""
    sections = []
    current = {"title": "项目概述", "body": []}
    for line in (proposal or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(?:[\d一二三四五六七八九十]+[、.．)\s]+|第[一二三四五六七八九十\d]+章)", line) and len(line) < 28:
            if current["body"]:
                sections.append(current)
            current = {"title": re.sub(r"^(?:[\d一二三四五六七八九十]+[、.．)\s]+|第[一二三四五六七八九十\d]+章\s*)", "", line), "body": []}
        else:
            current["body"].append(line)
    if current["body"]:
        sections.append(current)
    return sections


def _sentences(text, n=4):
    sents = re.split(r"[。；!！?？\n]", text or "")
    out = []
    for s in sents:
        s = s.strip()
        if 8 <= len(s) <= 60:
            out.append(s)
        if len(out) >= n:
            break
    return out


def fallback_deck(state):
    """LLM 不可用时，从申报书章节生成 PPT 结构"""
    title = state.get("competition_name", "科创项目") or "科创项目"
    idea_first = str(state.get("idea", "") or state.get("project_summary", "") or "").split("\n")[0][:40]
    default_title = idea_first or "科创项目"
    subtitle = str(state.get("one_liner", "") or "")[:50] or ""
    brand = f"{title} · {default_title}"
    deck = {"title": default_title, "subtitle": subtitle, "brand": brand, "slides": []}

    proposal = state.get("proposal", "") or state.get("idea", "") or ""
    sections = _split_proposal(proposal)
    if len(sections) < 3:
        sections = [
            {"title": "项目简介", "body": [state.get("project_summary", "") or state.get("idea", "")]},
            {"title": "解决方案", "body": [proposal[:300]]},
            {"title": "商业模式", "body": [state.get("business_model", "")[:300]]},
            {"title": "实施计划", "body": [state.get("implementation_plan", "")[:300]]},
            {"title": "社会价值", "body": [state.get("social_value", "")[:300]]},
        ]

    deck["slides"].append({"layout": "cover", "title": default_title})
    kickers = ["01 / 项目简介", "02 / 痛点与方案", "03 / 技术路线", "04 / 商业模式", "05 / 实施计划", "06 / 价值与风险"]
    for i, sec in enumerate(sections[:6]):
        bullets = _sentences("\n".join(sec["body"]), n=5)
        if not bullets:
            bullets = [sec["title"]]
        deck["slides"].append({
            "layout": "bullets",
            "kicker": kickers[i] if i < len(kickers) else f"0{i+1} / {sec['title']}",
            "title": sec["title"][:20],
            "bullets": bullets[:5],
            "note": "本页素材来自申报书自动生成，请按路演节奏取舍。",
        })
    deck["slides"].append({"layout": "end", "title": "感谢聆听", "bullets": ["敬请评委老师指正"]})
    return deck


def build_deck(state):
    """返回 deck 结构，可直接交给 media_factory.build_pptx()"""
    parts = [
        ("赛事", state.get("competition_name", "")),
        ("一句话定位", state.get("one_liner", "")),
        ("创意", state.get("idea", "")),
        ("项目简介", state.get("project_summary", "")),
        ("规则解析", state.get("parsed_rules", "")),
        ("同质化分析", state.get("similarity_report", "")),
        ("竞品分析", state.get("competitor_analysis", "")),
        ("商业模式", state.get("business_model", "")),
        ("风险分析", state.get("risk_analysis", "")),
        ("技术方案", state.get("tech_solution", "")),
        ("实施计划", state.get("implementation_plan", "")),
        ("社会价值", state.get("social_value", "")),
        ("申报书全文", state.get("proposal", "")),
        ("评委意见", state.get("judge_feedback", "")),
    ]
    context = _summarize_text(parts, limit=3200)

    title = state.get("competition_name", "科创项目") or "科创项目"
    idea_first = str(state.get("idea", "") or state.get("project_summary", "") or "").split("\n")[0][:40]
    default_title = idea_first or "科创项目"
    subtitle = str(state.get("one_liner", "") or "")[:50] or ""

    prompt = f"""你是资深路演 PPT 专家。请根据下面这份项目材料，生成 11 页路演 PPT 的结构，输出一个 ```json 代码块。

项目名建议：{default_title}
一句话定位建议：{subtitle}
赛事：{title}

结构必须严格按以下顺序，每页字段如下：
- layout: "cover" / "bullets" / "chart" / "table" / "end"
- kicker: 页码标签，例如 "01 / 痛点"、"05 / 竞品"
- title: 本页大标题（不超过 20 字）
- bullets: 3-5 条要点，每条不超过 24 字，必须具体、有数字/场景优先，禁止空话套话
- note: 演讲者备注，80 字以内，提示这一页怎么讲
- chart: 若 layout="chart"，则必填 "competitor" / "finance" / "timeline" / "radar" / "budget"
- caption: chart 页配图下方的说明文字
- table: 若 layout="table"，填 [["列1","列2"], ["行1","行2"]] 的二维数组

11 页顺序：
1. cover（封面）
2. bullets "01 / 痛点"：讲清项目解决的具体问题，带场景或数字
3. bullets "02 / 解决方案"：产品是什么、核心功能、怎么用
4. bullets "03 / 技术路线"：技术架构 + 2-3 个关键技术点
5. bullets "04 / 核心创新点"：3 条差异化优势，每条写清楚「别人做不到什么」
6. chart "05 / 竞品对比"：chart 用 "competitor"，caption 写清对比维度
7. bullets "06 / 商业模式"：目标客户、盈利模式、定价
8. chart "07 / 财务预测"：chart 用 "finance"，caption 写清单位
9. chart "08 / 实施计划"：chart 用 "timeline"，caption 写清总周期
10. bullets "09 / 风险与应对"：2-3 个主要风险 + 具体应对措施
11. end（结束页）

【路演PPT质量标杆 —— 必须遵守】
1. 默认 8 页压缩版：封面→痛点→解决方案→数据/Traction→竞争壁垒→商业模式→团队里程碑→愿景。
2. 一页一核心，标题即结论；每页 ≤100 字、≤6 行、≤5 要点；要点格式「关键词：具体说明（含数字）」。
3. 视觉系统：16:9、12列栅格；主色深海军蓝#0F1535、高亮#818CF8、正文#1A1A2E、背景#F8F8F6、数据强调#F59E0B。
4. 产品页必须有真实产品截图/流程图；数据页必须有大数字指标卡；竞争页必须用 2×2 矩阵或 radar。
5. 图表标题即结论，带 ≤20 字洞察和数据来源；禁用 3D/厚重边框/装饰图例。
6. 数据三分法：真实数据标来源，测算写「测算：基于XX假设」，待补充留空；严禁编造机构/年份/型号。
7. 结尾页不写「谢谢聆听」，写一句话定位+3条核心价值+明确下一步。
8. 禁止出现院校/导师/成员真实姓名、绝对化词汇、大段文字、花哨动画。

注意：
- 不要重复申报书全文，只提炼要点。
- 不要出现 "待补充"/"TODO"/"示例" 等占位词。
- 所有观点必须能在材料里找到依据。

输出格式：
```json
{{
  "title": "项目名",
  "subtitle": "一句话定位",
  "brand": "赛事名 · 项目名",
  "slides": [ {{...}}, {{...}} ]
}}
```

材料如下：
{context}
""" + _QUALITY_BENCHMARK_SPEC
    llm_error = None
    try:
        resp = _llm.invoke([HumanMessage(content=prompt)])
        data = _extract_json(resp.content) or {}
    except Exception as e:
        data = {}
        llm_error = str(e)[:120]

    deck = {
        "title": data.get("title") or default_title,
        "subtitle": data.get("subtitle") or subtitle,
        "brand": data.get("brand") or f"{title} · {default_title}",
        "slides": [],
    }

    slides = data.get("slides") or []
    valid_layouts = {"cover", "bullets", "chart", "table", "end"}
    has_cover = False
    has_end = False

    for s in slides:
        if not isinstance(s, dict):
            continue
        layout = s.get("layout") or "bullets"
        if layout not in valid_layouts:
            layout = "bullets"
        if layout == "cover":
            has_cover = True
        if layout == "end":
            has_end = True

        bullets = []
        for b in (s.get("bullets") or []):
            b = re.sub(r"^[-·*▍]\s*", "", str(b)).strip()
            if b and len(b) <= 80:
                bullets.append(b[:60])
        if len(bullets) > 6:
            bullets = bullets[:6]

        slide = {
            "layout": layout,
            "kicker": str(s.get("kicker") or ""),
            "title": str(s.get("title") or "")[:28],
            "bullets": bullets,
            "note": str(s.get("note") or "")[:180],
            "chart": s.get("chart") if layout == "chart" else None,
            "caption": str(s.get("caption") or "")[:70],
        }
        if layout == "table" and isinstance(s.get("table"), list) and len(s["table"]) >= 2:
            slide["table"] = [[str(c)[:60] for c in row] for row in s["table"][:12]]
        if layout == "end":
            slide["title"] = slide["title"] or "感谢聆听"
            if not slide["bullets"]:
                slide["bullets"] = ["敬请评委老师指正"]
        deck["slides"].append(slide)

    if not has_cover:
        deck["slides"].insert(0, {"layout": "cover", "title": deck["title"]})
    if not has_end:
        deck["slides"].append({"layout": "end", "title": "感谢聆听", "bullets": ["敬请评委老师指正"]})

    # 若 LLM 结果太薄（只有封面+结束），降级到章节切分
    if len(deck["slides"]) <= 2:
        deck = fallback_deck(state)
        return deck, (llm_error or "LLM 未返回有效 slides，已降级规则提取")
    return deck, None


# ------------------------------------------------------------------
# 3. 并发入口
# ------------------------------------------------------------------
def build_media_plan(state):
    """并发提取 visuals + deck，返回 dict（含 fallback 原因）"""
    reasons = []

    def run_visuals():
        v, err = build_visuals(state)
        if err:
            reasons.append(err)
        return v

    def run_deck():
        d, err = build_deck(state)
        if err:
            reasons.append(err)
        return d

    with ThreadPoolExecutor(max_workers=2) as pool:
        v_future = pool.submit(run_visuals)
        d_future = pool.submit(run_deck)
        visuals = v_future.result()
        deck = d_future.result()
    return {
        "visuals": visuals,
        "deck": deck,
        "digest": _state_digest(state),
        "fallback_reason": "；".join(reasons) if reasons else None,
    }


if __name__ == "__main__":
    demo_state = {
        "competition_name": "iCAN 大学生创新创业大赛",
        "one_liner": "让每一瓶危化品试剂的取用都可追溯",
        "idea": "智能危化品试剂管理柜：RFID+称重+三级预警，实现实验室危化品从领用、使用到归还的全流程闭环管理。",
        "parsed_rules": "创新性30%，实用性25%，技术难度20%，团队展示15%，社会价值10%。",
        "competitor_analysis": "## 竞品对比\n| 方案 | 单柜成本 | 识别精度 | 台账自动化 |\n|---|---|---|---|\n| 本项目 | 1.2万元 | ±1g | 全自动 |\n| 传统人工台账 | 0.1万元 | 人工 | 无 |\n| 进口智能柜 | 6.8万元 | ±0.5g | 半自动 |",
        "business_model": "目标客户：高校、科研院所、医药企业实验室。收入来源：智能柜硬件销售（1.2万元/台）、SaaS 年费（3000元/台）、耗材（RFID标签）。三年预测：第1年收入120万元、成本150万元、利润-30万元；第2年收入380万元、成本300万元、利润80万元；第3年收入860万元、成本560万元、利润300万元。预算构成：研发45%、生产30%、营销15%、运营10%。",
        "risk_analysis": "技术风险：称重精度受温湿度影响；市场风险：高校采购周期长；应对：双传感器融合校准、提前布局招投标。",
        "tech_solution": "整体架构：感知层（RFID+称重+摄像头）、平台层（Spring Boot + MySQL）、应用层（微信小程序）。技术难点：危化品混放检测、低功耗连续称重。",
        "implementation_plan": "第1-2周需求调研与用户访谈；第3-5周硬件原型与小程序开发；第6-7周小批量试产与试点部署；第8周市场推广与路演材料准备。",
        "social_value": "降低实验室危化品事故率，提升试剂使用透明度，惠及高校科研人员。",
        "proposal": "项目背景：实验室危化品管理依赖人工台账，500mL 丙酮实际使用 80mL 却无法追踪。解决方案：智能柜通过 RFID 识别试剂、称重记录余量、三级预警防止超期与超量。\n\n1. 项目背景与痛点\n实验室每年因试剂管理不善导致的安全事故超过 200 起。\n\n2. 解决方案\n智能试剂柜集成 RFID、称重、摄像头，实现一物一码一重量。\n\n3. 商业模式\n硬件销售 + SaaS 年费 + 耗材，首年覆盖 20 所高校。\n\n4. 实施计划\n八周完成原型到试点。\n\n5. 社会价值\n降低事故率，提升科研透明度。",
        "judge_feedback": "创新性：85分；可行性：78分；市场价值：72分；技术壁垒：75分；社会价值：80分。",
    }
    plan = build_media_plan(demo_state)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
