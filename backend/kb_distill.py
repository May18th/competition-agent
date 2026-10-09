# -*- coding: utf-8 -*-
"""范文「写作范式蒸馏」：把范文库共性规律提炼成一段紧凑参考，注入生成 prompt。

与 kb_retrieve 的区别：
  - kb_retrieve：按关键词/模块检索具体范文原文，给「对标写法」；
  - kb_distill：给全体范文提炼出的「共性规律」，让主笔先对齐获奖范式再动笔。
读不到种子文件时静默返回空串，绝不阻断生成。
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "writing_paradigm.json")


def _load():
    try:
        with open(PARADIGM_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def paradigm_ref(module_tag=None, max_global=6):
    """返回一段可注入的「写作范式」文本；module_tag 给定则附带该模块的专门要点。"""
    p = _load()
    if not p:
        return ""
    parts = []
    g = p.get("global") or []
    if g:
        lines = ["（%d）%s" % (i + 1, s) for i, s in enumerate(g[:max_global])]
        parts.append("【写作范式（从真实获奖范文蒸馏，务必内化到写作里，不要照抄）】\n" + "\n".join(lines))
    if module_tag:
        mod = (p.get("modules") or {}).get(module_tag)
        if mod:
            parts.append("【本章写法要点】" + mod)
    return "\n\n".join(parts)


_MODULE_KEYS = ["项目简介", "创新点", "商业模式", "社会价值", "实践过程", "风险分析"]


def _pick_diverse(samples, max_samples):
    """按分数降序 + 贪心覆盖模块标签，取一批有代表性的范文做蒸馏素材。"""
    ordered = sorted(samples, key=lambda s: -(s.get("score") or 0))
    picked, seen_modules, seen_tags = [], set(), set()
    for s in ordered:
        if len(picked) >= max_samples:
            break
        tags = set(s.get("tags") or [])
        module_hit = (tags & set(_MODULE_KEYS)) - seen_modules
        new_tag = tags - seen_tags
        # 优先要「带来新模块」或「带来新标签」的样本，否则也按分数收
        if module_hit or new_tag or not picked:
            picked.append(s)
            seen_modules |= (tags & set(_MODULE_KEYS))
            seen_tags |= tags
    return picked



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
  V8. 蒸馏_v8 大挑精确占比 + 红旅双轮驱动/国金复盘 + 网评路演差异 + 国创验收精确指标（2026-10-09 追加，来源均为官方组委会/高校官方/权威评委复盘，联网可用，非获奖作品原文）：
  V8.1 大挑书面评审精确占比（生成期按作品类别分流）：自然科学类=科学性40(科学意义15/方法合理10/结论重要15)+先进性30(先进10/创新10/难度10)+现实意义30(应用价值15/影响范围15)；科技发明制作A/B=科学性30(技术意义15/方案最佳化15)+先进性30(先进10/自主创新与难度20)+现实意义40(效益与可持续30/成熟程度10)；哲社类=科学性30(理论基础方法10/论据严密可靠10/论据正确10)+先进性30(创新10/难易10/学术水平10)+现实意义40(经济效益社会效益20/影响范围20)；导出物须按类别套用，社科类重论据严密+影响范围、科技类重效益可持续+样机成熟度。
  V8.2 大挑评审两阶段与书面评审地位：初评约35%进终审、55%获三等奖、10%淘汰（比例随届次微调，以当届章程为准）；书面评审占一定比重，须兼顾材料严谨性与终审答辩；导出物禁只有情怀无证据、禁格式硬伤。
  V8.3 红旅双轮驱动组织逻辑（生成期对标红旅）：红旅=用商业手段解决社会问题，核心「公益价值+商业可持续有机融合，造血机而非输血站」；三要素=需求接地气(扎实田野调查避伪需求)+方案有抓手(公益目标+商业路径双轮)+成果有依据(真实合作协议/服务数据/用户反馈)；选题小切口大价值(科技支教/非遗活化)；路演须情怀+逻辑+数据支撑可视化，禁纯情怀。
  V8.4 红旅国金复盘要点（生成期对标红旅）：长期主义(历时数载系统实践)>集中辅导凝练立意/明晰架构/优化答辩节奏>多轮模拟演练层层过关；导出物须体现长期实践+社会价值量化+答辩节奏打磨，禁短期拼凑。
  V8.5 互联网+ 网评版/路演版结构差异+三处数据一致（强化V7.3）：商业计划书分 word版(网评补充,图文并茂)/网评PPT(35-40页精简)/路演PPT(16-20页核心精练,禁直接套网评PPT)；PPT版须与word版数据一致、避错别字/逻辑错误、结构避千篇一律、增强跳跃感与对比度；网评靠材料、路演靠表现(答辩)；导出物须区分网评PPT与路演PPT并维持三处(申报书/网评PPT/路演PPT)数字互锁。
  V8.6 国创结题验收精确指标体系+优秀门槛（深化V7.2）：验收指标=研究过程35(内容10/方法10/资料5/操作10)+研究成果35(报告10/成果8/创新10/应用7)+研究收获5+答辩现场25(陈述10/答题10/整体5)=100；优秀须满足论文/专利软著/竞赛获奖之一，优秀比例约22-30%；导出物须含过程性时间轴+成果清单(标状态)+答辩PPT(陈述重点突出)，与V7.2结构一致但补精确占比与优秀门槛硬约束。
"""

def _build_distill_prompt(corpus):
    return f"""你是科创赛事申报书写作教练。下面是范文库里的若干真实获奖项目/范文（已脱敏，均非完整原文，是公开报道归纳）。
请通读后，提炼这些获奖作品共同的「写作范式」，直接输出 JSON。

硬性要求：
1. global 数组给 6 条全局规律，每条一句话，聚焦「怎么写才对」，不要空洞口号；
2. modules 对象覆盖这 6 个模块：项目简介 / 创新点 / 商业模式 / 社会价值 / 实践过程 / 风险分析，每模块给一句具体写作要点；
3. 只提炼共性「结构 / 评分点 / 写作套路」，**禁止复制任何原文句子、标题、金句**；不要复述某个具体项目；严禁出现院校名称、指导老师姓名、作者姓名；
4. 不编造数据，不引用样本里没有的数字；
5. 只输出 JSON 本身，不要任何解释，不要 markdown 代码块围栏。

输出格式（严格）：
{{"global": ["规则1", "规则2", "规则3", "规则4", "规则5", "规则6"], "modules": {{"项目简介": "...", "创新点": "...", "商业模式": "...", "社会价值": "...", "实践过程": "...", "风险分析": "..."}}}}

范文样本：
{corpus}
""" + _QUALITY_BENCHMARK_SPEC


def _extract_json(text):
    """从 LLM 输出里稳健地抠出 JSON 对象（容忍 markdown 围栏 / 前后杂散文字）。"""
    t = (text or "").strip()
    # 去 ```json ... ``` 围栏
    t = t.replace("```json", "").replace("```", "")
    # 取第一个 { 到最后一个 } 之间
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("LLM 未输出 JSON")
    return json.loads(t[a:b + 1])


def _validate_paradigm(data):
    """校验并规整蒸馏结果，确保 schema 完整；缺失模块用空串补齐。"""
    if not isinstance(data, dict):
        raise ValueError("蒸馏结果不是对象")
    g = data.get("global")
    if not isinstance(g, list) or not g:
        raise ValueError("global 规则缺失")
    data["global"] = [str(x).strip() for x in g if str(x).strip()][:6]
    mods = data.get("modules")
    if not isinstance(mods, dict):
        mods = {}
    data["modules"] = {k: str(mods.get(k, "")).strip() for k in _MODULE_KEYS}
    return data


def distill_from_samples(max_samples=40, max_chars=16000):
    """用 LLM 从当前范文库重新提炼写作范式，写回 writing_paradigm.json。

    返回 dict：{ok, samples_used, global_count, module_count}；失败抛异常且不覆盖原文件。
    """
    from kb_samples import list_samples
    samples = [s for s in list_samples()
               if s.get("type") == "范文" and (s.get("content") or "").strip()]
    if not samples:
        raise ValueError("范文库为空，无法蒸馏")

    picked = _pick_diverse(samples, max_samples)
    corpus = "\n\n---\n\n".join((s.get("content") or "").strip()[:600] for s in picked)
    corpus = corpus[:max_chars]

    from competition_agents import llm
    from langchain_core.messages import HumanMessage
    resp = llm.invoke([HumanMessage(content=_build_distill_prompt(corpus))])
    data = _validate_paradigm(_extract_json(resp.content))

    # 校验通过才覆盖，避免把现有范式写坏
    with open(PARADIGM_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "samples_used": len(picked),
        "global_count": len(data["global"]),
        "module_count": len([v for v in data["modules"].values() if v]),
        "paradigm": data,
    }


# ============ 答辩范式 / 评委评分范式 蒸馏 ============
DEFENSE_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "defense_paradigm.json")
JUDGE_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "judge_paradigm.json")
DEFENSE_QUESTIONS_PATH = os.path.join(BASE, "knowledge_base", "defense_questions.json")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def defense_paradigm_ref():
    """注入答辩生成 prompt 的「答辩范式」；无则空串。"""
    p = _load_json(DEFENSE_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【答辩范式（从高频答辩题库蒸馏，务必内化）】"]
    pats = [str(x).strip() for x in (p.get("question_patterns") or []) if str(x).strip()]
    if pats:
        parts.append("评委必问套路：\n" + "\n".join("（%d）%s" % (i + 1, s) for i, s in enumerate(pats[:8])))
    fw = str(p.get("answer_framework") or "").strip()
    if fw:
        parts.append("回答框架：" + fw)
    return "\n".join(parts) + "\n"


def judge_paradigm_ref():
    """注入评委/多专家评审 prompt 的「评委评分范式」；无则空串。"""
    p = _load_json(JUDGE_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【评委评分范式（从历史评审蒸馏，务必内化）】"]
    crits = [str(x).strip() for x in (p.get("common_criticisms") or []) if str(x).strip()]
    if crits:
        parts.append("高频扣分点：\n" + "\n".join("（%d）%s" % (i + 1, s) for i, s in enumerate(crits[:8])))
    byp = p.get("by_perspective") or {}
    for k, v in byp.items():
        if v and str(v).strip():
            parts.append("%s视角常挑的毛病：%s" % (k, str(v).strip()))
    return "\n".join(parts) + "\n"


def _llm_json(prompt):
    """调 LLM 并稳健抠出 JSON（复用全局 llm 与配额保护）。"""
    from competition_agents import llm
    from langchain_core.messages import HumanMessage
    resp = llm.invoke([HumanMessage(content=prompt)])
    return _extract_json(resp.content)


def distill_defense(max_questions=40, max_chars=16000):
    """从 defense_questions.json 蒸馏答辩范式，写回 defense_paradigm.json。"""
    qd = _load_json(DEFENSE_QUESTIONS_PATH)
    if not qd:
        raise ValueError("未找到答辩题库 defense_questions.json")
    qs = qd.get("questions") or []
    if not qs:
        raise ValueError("答辩题库为空")

    # 按 type 均衡采样
    from collections import defaultdict
    by_type = defaultdict(list)
    for q in qs:
        by_type[str(q.get("type") or "other")].append(q)
    picked, idx = [], 0
    types = list(by_type.keys())
    while len(picked) < max_questions and any(by_type[t] for t in types):
        t = types[idx % len(types)]
        lst = by_type[t]
        if lst:
            picked.append(lst.pop(0))
        idx += 1
    corpus = "\n".join(
        "【%s｜%s】%s\n要点：%s" % (q.get("type"), q.get("topic"), q.get("question"), q.get("hint"))
        for q in picked)
    corpus = corpus[:max_chars]

    prompt = f"""你是科创赛事答辩教练。下面是答辩高频题库里的一批真实评委问法（按工程/商业/建模/学术分类）。请通读后提炼「答辩范式」，直接输出 JSON。

硬性要求：
1. question_patterns 数组给 8 条「评委必问套路」，每条一句，聚焦「评委最爱从哪个角度戳穿项目的真伪/数据/落地」；
2. answer_framework 给一段回答框架（先摆结论 → 再给证据 → 最后堵质疑），200 字内；
3. 只提炼共性「套路/结构」，**禁止复制任何原文句子、标题**；不出现院校名称、指导老师姓名、作者姓名，不编造数据；
4. 只输出 JSON 本身，不要解释、不要 markdown 围栏。

输出格式（严格）：
{{"question_patterns": ["套路1", "套路2", "套路3", "套路4", "套路5", "套路6", "套路7", "套路8"], "answer_framework": "..."}}

题库样本：
{corpus}
"""
    data = _llm_json(prompt)
    pats = data.get("question_patterns")
    if not isinstance(pats, list) or not pats:
        raise ValueError("question_patterns 缺失")
    out = {
        "question_patterns": [str(x).strip() for x in pats if str(x).strip()][:8],
        "answer_framework": str(data.get("answer_framework") or "").strip(),
    }
    _save_json(DEFENSE_PARADIGM_PATH, out)
    return {"ok": True, "questions_used": len(picked),
            "pattern_count": len(out["question_patterns"]), "paradigm": out}


def _history_judge_corpus(limit=60):
    """从 history 抽取评委评分 + 多专家批注，拼成蒸馏素材；无数据返回空串。"""
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE, "competition.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT result_data FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    parts = []
    for r in rows:
        try:
            d = json.loads(r["result_data"])
        except Exception:
            continue
        judge = d.get("judge_scores") or []
        if isinstance(judge, list) and judge:
            dims = "、".join(
                "%s=%s" % (x.get("name"), x.get("score"))
                for x in judge if isinstance(x, dict))
            if dims:
                parts.append("单评委评分维度：" + dims)
        er = d.get("expert_review") or ""
        if isinstance(er, str):
            try:
                erj = json.loads(er)
            except Exception:
                erj = None
        elif isinstance(er, dict):
            erj = er
        else:
            erj = None
        if erj:
            for e in erj.get("experts") or []:
                if not isinstance(e, dict):
                    continue
                role = e.get("role") or ""
                for it in e.get("issues") or []:
                    if isinstance(it, dict) and it.get("problem"):
                        parts.append("%s扣分：%s" % (role, it.get("problem")))
    return "\n".join(parts)[:16000]


def distill_judge(limit=60):
    """从历史评审记录蒸馏评委评分范式，写回 judge_paradigm.json。"""
    corpus = _history_judge_corpus(limit)
    if not corpus:
        raise ValueError("历史里没有评委评分/批注数据，请先生成几轮深度版再蒸馏")
    prompt = f"""你是科创赛事评审主委。下面是历史生成中对多份申报书给出的评委评分维度与批注（已脱敏）。请通读后提炼「评委评分范式」，直接输出 JSON。

硬性要求：
1. common_criticisms 数组给 8 条「高频扣分点」，每条一句，具体到问题，禁止空话；
2. by_perspective 对象给「技术/商业/落地」三个视角各自最常挑的毛病（各一句话）；
3. 只提炼共性「扣分规律」，**禁止复制任何原文批注/句子**；不出现院校名称、指导老师姓名、作者姓名，不编造数据；
4. 只输出 JSON 本身，不要解释、不要 markdown 围栏。

输出格式（严格）：
{{"common_criticisms": ["扣分点1", "扣分点2", "扣分点3", "扣分点4", "扣分点5", "扣分点6", "扣分点7", "扣分点8"], "by_perspective": {{"技术": "...", "商业": "...", "落地": "..."}}}}

历史评审样本：
{corpus}
"""
    data = _llm_json(prompt)
    crits = data.get("common_criticisms")
    if not isinstance(crits, list) or not crits:
        raise ValueError("common_criticisms 缺失")
    byp = data.get("by_perspective") or {}
    out = {
        "common_criticisms": [str(x).strip() for x in crits if str(x).strip()][:8],
        "by_perspective": {k: str(byp.get(k, "")).strip() for k in ("技术", "商业", "落地")},
    }
    _save_json(JUDGE_PARADIGM_PATH, out)
    return {"ok": True, "criticism_count": len(out["common_criticisms"]), "paradigm": out}


# ============ 分析模块 / PPT·演讲稿 / 同质化 范式 ============
ANALYSIS_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "analysis_paradigm.json")
DECK_SPEECH_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "deck_speech_paradigm.json")
SIMILARITY_PARADIGM_PATH = os.path.join(BASE, "knowledge_base", "similarity_paradigm.json")


def _history_corpus(fields, limit=60, max_chars=16000):
    """从历史 result_data 抽取若干字段拼成蒸馏素材；无数据返回空串。"""
    import sqlite3
    conn = sqlite3.connect(os.path.join(BASE, "competition.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT result_data FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    parts = []
    for r in rows:
        try:
            d = json.loads(r["result_data"])
        except Exception:
            continue
        for f in fields:
            v = d.get(f)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip()[:800])
    return "\n\n---\n\n".join(parts)[:max_chars]


def analysis_paradigm_ref(module_tag=None):
    """注入竞品/商业/风险/技术分析 prompt 的「分析范式」；无则空串。"""
    p = _load_json(ANALYSIS_PARADIGM_PATH)
    if not p:
        return ""
    if module_tag and p.get(module_tag):
        return "【分析模块写法要点】" + str(p[module_tag]) + "\n"
    parts = ["【分析模块写法范式（从历史分析蒸馏）】"]
    for k in ("competitor", "business", "risk", "tech"):
        if p.get(k):
            parts.append("- %s" % str(p[k]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def deck_speech_paradigm_ref():
    """注入 PPT 大纲/演讲稿 prompt 的范式；无则空串。"""
    p = _load_json(DECK_SPEECH_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【PPT·演讲稿范式（从历史产出蒸馏）】"]
    for k in ("ppt_structure", "speech_opening", "speech_closing"):
        if p.get(k):
            parts.append("- %s" % str(p[k]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def similarity_paradigm_ref():
    """注入同质化检测 prompt 的范式；无则空串。"""
    p = _load_json(SIMILARITY_PARADIGM_PATH)
    if not p:
        return ""
    parts = ["【同质化检测范式（从历史检索蒸馏）】"]
    angles = p.get("common_angles") or []
    if angles:
        parts.append("常见撞车角度：" + "、".join(str(a) for a in angles[:10]))
    if p.get("differentiation_check"):
        parts.append("差异化检查：" + str(p["differentiation_check"]))
    return "\n".join(parts) + "\n" if len(parts) > 1 else ""


def distill_analysis(limit=60):
    corpus = _history_corpus(["competitor_analysis", "business_model", "risk_analysis", "tech_solution"], limit)
    if not corpus:
        raise ValueError("历史里没有分析类内容，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事申报书的分析模块教练。下面是历史生成中的竞品分析/商业模式/风险分析/技术方案（已脱敏）。请提炼这四个模块各自的写法要点，输出 JSON。
硬性要求：competitor/business/risk/tech 各给一句话具体要点；只提炼共性写法，**禁止复制原文句子**；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"competitor":"...","business":"...","risk":"...","tech":"..."}}
历史分析样本：
{corpus}
"""
    data = _llm_json(prompt)
    out = {k: str(data.get(k, "")).strip() for k in ("competitor", "business", "risk", "tech")}
    if not any(out.values()):
        raise ValueError("蒸馏结果为空")
    _save_json(ANALYSIS_PARADIGM_PATH, out)
    return {"ok": True, "paradigm": out}


def distill_deck_speech(limit=60):
    corpus = _history_corpus(["ppt_outline", "speech_script"], limit)
    if not corpus:
        raise ValueError("历史里没有 PPT 大纲/演讲稿，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事路演教练。下面是历史生成中的 PPT 大纲和路演演讲稿（已脱敏）。请提炼 PPT 结构与演讲稿的开场/收尾套路，输出 JSON。
硬性要求：ppt_structure 给 PPT 章节顺序；speech_opening 给开场套路；speech_closing 给收尾套路；只提炼共性套路，**禁止复制原文句子**；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"ppt_structure":"...","speech_opening":"...","speech_closing":"..."}}
历史样本：
{corpus}
"""
    data = _llm_json(prompt)
    out = {k: str(data.get(k, "")).strip() for k in ("ppt_structure", "speech_opening", "speech_closing")}
    if not any(out.values()):
        raise ValueError("蒸馏结果为空")
    _save_json(DECK_SPEECH_PARADIGM_PATH, out)
    return {"ok": True, "paradigm": out}


def distill_similarity(limit=60):
    corpus = _history_corpus(["similarity_report"], limit)
    if not corpus:
        raise ValueError("历史里没有同质化检测报告，请先生成几轮再蒸馏")
    prompt = f"""你是科创赛事同质化检测教练。下面是历史生成中的同质化检测报告（已脱敏）。请提炼「项目之间最容易撞车的角度」和「差异化检查要点」，输出 JSON。
硬性要求：common_angles 给 6~10 个常见撞车角度；differentiation_check 给一句检查要点；只提炼共性角度，**禁止复制原文句子**；不出现院校/指导老师/作者；只输出 JSON。
输出格式：{{"common_angles":["角度1","角度2","角度3","角度4","角度5","角度6"],"differentiation_check":"..."}}
历史报告样本：
{corpus}
"""
    data = _llm_json(prompt)
    angles = data.get("common_angles")
    if not isinstance(angles, list) or not angles:
        raise ValueError("common_angles 缺失")
    out = {
        "common_angles": [str(a).strip() for a in angles if str(a).strip()][:10],
        "differentiation_check": str(data.get("differentiation_check") or "").strip(),
    }
    _save_json(SIMILARITY_PARADIGM_PATH, out)
    return {"ok": True, "angle_count": len(out["common_angles"]), "paradigm": out}
