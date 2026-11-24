# -*- coding: utf-8 -*-
"""评分项诊断台：把一次生成结果按赛事官方评分维度逐项拆开。

输出三样东西，缺一不可：
  得分（这个维度在当前稿子里估多少分）
  支撑证据（命中的原文片段，人可以直接回原文复核）
  缺失证据 + 具体动作（要补什么才能拿分）

设计边界
--------
- 纯规则启发式，不调 LLM、不写库。规则能判「有没有这一类信息」，
  判不了「写得好不好」，所以每一项都必须带原文片段，让人自己复核。
  没有片段的分数就是编的，不提供。
- 与 quality_gate.score_export 分工不同：score_export 回答「能不能导出」，
  本模块回答「丢分丢在哪」。两者不共用阈值，也不互相调用。
- 只诊断 profile 里配了官方权重的维度。没有权重的赛事（大创立项、蓝桥杯机考）
  直接返回 available=False —— 不能编一套通用维度冒充官方口径。
- 维度名对不上任何判据族时，归入 general 族并在 note 里写明
  「该维度未配置专项判据，按通用质量估算」，分数不计入 total，
  避免把猜出来的分混进总分。
"""

import importlib
import re


def peer(name):
    """按部署布局取同级模块：本地是 backend/ 子目录，线上是扁平目录。

    线上 /opt/comp-agent 没有 backend/ 包，app.py、competition_agents.py 都在根下；
    本地是 backend/ 包。同一份文件要两边都能跑，所以不能写死一种导入路径。
    """
    try:
        return importlib.import_module("backend." + name)
    except ImportError:
        return importlib.import_module(name)

# ============ 维度名 → 判据族 ============
# 顺序即优先级：越具体的族越靠前，value 放最后吃「价值/效果/前景」这类宽泛词。
_FAMILY_KEYWORDS = (
    ("innovation", ("创新", "原创", "创造", "先进性", "创意")),
    ("business", ("商业", "产业", "经营", "财务", "盈利", "营收", "发展前景", "市场化")),
    ("feasibility", ("可行", "实践", "稳定", "可靠", "假设", "检验", "灵敏度", "方案设计")),
    ("social", ("社会",)),
    ("presentation", ("展示", "答辩", "文档", "规范", "表达", "呈现", "演示", "论文", "表现")),
    ("team", ("团队", "协作", "成长", "育人", "个人")),
    ("tech", ("技术", "模型", "算法", "功能", "指标", "原型", "仿真", "工程", "求解", "代码", "架构", "系统")),
    ("value", ("价值", "实用", "应用", "前景", "需求", "效果")),
)

_FAMILY_LABEL = {
    "innovation": "创新性",
    "business": "商业与产业",
    "feasibility": "可行性与验证",
    "social": "社会效益",
    "presentation": "文档与展示",
    "team": "团队与成长",
    "tech": "技术方案",
    "value": "应用价值",
    "general": "通用质量",
}

_PASS, _PARTIAL, _FAIL = "pass", "partial", "fail"
_STATUS_SCORE = {_PASS: 1.0, _PARTIAL: 0.5, _FAIL: 0.0}


def classify_dim(name):
    """把官方维度名归到一个判据族。归不进去返回 general。"""
    s = str(name or "")
    for family, words in _FAMILY_KEYWORDS:
        if any(w in s for w in words):
            return family
    return "general"


# ============ 文本工具 ============
def _clean(text):
    return text or ""


def _snippet(text, start, end, width=32):
    """取命中点前后各 width 字，去掉换行，两端补齐省略号。"""
    a = max(0, start - width)
    b = min(len(text), end + width)
    seg = re.sub(r"\s+", " ", text[a:b]).strip()
    if a > 0:
        seg = "…" + seg
    if b < len(text):
        seg = seg + "…"
    return seg


_NEG_PREFIX = re.compile(
    r"(?:不存在|没有|尚无|缺乏|未申请|未取得|不构成|无高门槛|无相关|不具备|"
    r"可作为|可以作|拟申请|计划申请|待申请|申报基础|尚未)")


def _drop_negated(text, hits, window=14):
    """去掉命中点前面带否定词或未来时表述的假阳性。

    实测两类陷阱：
    - 「柜体方案不存在高门槛专利壁垒」会被读成「有专利」，把「没有」夸成「有」
    - 「相关结构差异可作为专利与查新材料的申报基础」是条件式表述，
      实际还没申请；按字面会判成已有专利支撑
    命中点前 14 字内出现否定词或条件式表述即丢弃。
    """
    out = []
    for m, snip in hits:
        pre = (text or "")[max(0, m.start() - window):m.start()]
        if not _NEG_PREFIX.search(pre):
            out.append((m, snip))
    return out


def _hits(text, pattern, limit=3):
    """返回 [(match, snippet)]，snippet 带上下文，供人回原文核对。"""
    out = []
    for m in re.finditer(pattern, text or ""):
        out.append((m, _snippet(text, m.start(), m.end())))
        if len(out) >= limit:
            break
    return out


def _has(text, pattern):
    return bool(re.search(pattern, text or ""))


def _count(text, pattern):
    return len(re.findall(pattern, text or ""))


_UNIT_NUM = r"\d+(?:\.\d+)?\s*(?:%|％|万|亿|元|人|户|台|套|件|次|天|小时|分钟|秒|吨|度|倍|项|篇|个|家|所|亩|kWh|km)"


def _quantified(text, keyword_pattern, span=24):
    """关键词附近出现带单位的数字 → 视为量化证据。

    两个方向都看：中文里「成本约1.8万元」是数字在后，
    「3所高校」「6个课题组」是数字在前，只认后者会漏掉一半表述。
    用拼接而不是 % 格式化：_UNIT_NUM 里含「%」字符，会被当成格式符。
    """
    pat = ("(?:" + keyword_pattern + ")[^。；\\n]{0," + str(span) + "}?(?:" + _UNIT_NUM + ")"
           "|(?:" + _UNIT_NUM + ")[^。；\\n，,]{0,6}?(?:" + keyword_pattern + ")")
    return _hits(text, pat)


# ============ 各族检查项 ============
# 每项: (key, label, weight, detector)；detector(ctx) -> (status, snippet, note)
# ctx: {"text": 正文去掉 Markdown 标记, "raw": 原文, "result": 结果字典, "mode": 档位}

def _check_innovation(ctx):
    t, raw = ctx["text"], ctx["raw"]
    return [
        ("diff_statement", "差异化对比陈述", 0.30, lambda: _diff_statement(t)),
        ("innovation_points", "创新点可数", 0.30, lambda: _innovation_points(t)),
        ("novelty_evidence", "新颖性有外部支撑", 0.25, lambda: _novelty(t)),
        ("non_generic", "非通用表述", 0.15, lambda: _generic_check(t)),
    ]


def _diff_statement(t):
    """与现有做法的对比。分强弱两档。

    实测：模型常用「把误记率从纯称重方案的 8% 压到 3%」这种改进型表述，
    字面没有「相比/不同于」。按强判据只认字面会把它判成「没写差异化」——
    假阴性比假阳性更伤：用户明明写了，工具说没写，直接失去信任。
    """
    strong = _hits(t, r"(?:不同于|区别于|差异(?:化|在于)|相比(?:之下|现有|传统|同类)|优于|相较|"
                      r"替代(?:了|现有|人工|传统)|首创|首次(?:提出|实现)|填补(?:了)?空白|"
                      r"空白(?:地带|区)|两头挤|中间空)")
    if strong:
        return _PASS, strong[0][1], "存在与现有方案的直接对比"
    weak = _hits(t, r"(?:从[^。；\n]{0,18}(?:方案|做法|方式|水平|路线)[^。；\n]{0,12}?(?:压到|降到|提升到|缩短到|减少到|优化到)"
                    r"|解决(?:了)?[^。；\n]{0,16}(?:的问题|误判|漏检|痛点|盲区|缺陷)"
                    r"|现有(?:方案|手段|做法)[^。；\n]{0,20}(?:不足|缺口|痛点|问题|依赖人工))")
    if weak:
        return _PARTIAL, weak[0][1], "有改进型对比（从 X 到 Y / 解决 X 的问题），但没点明对标的是哪类方案"
    return _FAIL, "", "未检出「不同于/相比现有方案/现有做法的缺口」这类差异化表述"


def _innovation_points(t):
    """创新点是否可数。

    显式列出「创新点：1…2…」最好；其次是命名式（「双校验」「三层架构」），
    算部分覆盖——评委能数出来，但不如集中列一遍清楚。
    """
    explicit = _hits(t, r"(?:创新点|技术创新|亮点|核心突破|独创|首创之处)[^。；\n]{0,60}")
    if explicit:
        return _PASS, explicit[0][1], "有独立创新点陈述"
    # 「本项目有三处创新：①②③」是最自然的写法，但「处」原来不在量词表里，
    # 判据把它判成没写（实测模型按提示写出来的正是这种句式）。
    counted = _hits(t, r"(?:[二三三四五]|本项目的?多条|若干)[处项个条]\s*创新[^。；\n]{0,60}")
    if counted:
        return _PASS, counted[0][1], "有编号的创新点陈述"
    named = _hits(t, r"(?:双|两|三|四|五)[项个层道重]?(?:校验|验证|架构|机制|模块|防线|融合)")
    if named:
        return _PARTIAL, named[0][1], "有命名式创新（如「双校验」），但没集中列出创新点，评委不易数"
    return _FAIL, "", "没有单独的创新点陈述，创新性靠读者自己归纳"


def _novelty(t):
    """强信号（专利/查新/软著/对比实验）优先；弱信号（文献/基线）只算部分。

    实测陷阱：「验收基线」「三阶段验收指标」会被朴素正则当成对比实验基线，
    所以弱信号必须先排除「验收/考核/指标」后紧跟的「基线」。
    """
    strong = _drop_negated(t, _hits(t, r"(?:专利|软著|软件著作权|查新(?:报告|检索)|知识产权|对比实验|消融实验|"
                                      r"与(?:竞品|现有方案)对(?:比|照))"))
    if strong:
        return _PASS, strong[0][1], "有专利/查新/软著/对比实验等硬支撑"
    weak = _drop_negated(t, _hits(t, r"(?:文献(?:综述|检索)|基线(?!值)|benchmark|Benchmark)"))
    weak = [h for h in weak if not re.search(r"(?:验收|考核|目标|指标)\s*基线", h[1])]
    if weak:
        return _PARTIAL, weak[0][1], "只有文献/基线级支撑，缺专利、查新或对比实验"
    return _FAIL, "", "新颖性只有自述，缺专利、查新或对比实验支撑"


def _check_business(ctx):
    t = ctx["text"]
    return [
        ("cost_price", "成本与定价", 0.30, lambda: _pick(
            _quantified(t, r"(?:成本|造价|单价|售价|定价)"),
            "成本/定价有数字化表述", "成本与定价缺具体数字")),
        ("revenue_model", "收入模型", 0.30, lambda: _pick(
            _quantified(t, r"(?:营收|收入|毛利|利润|付费|客单价|订阅)"),
            "有收入/毛利口径", "没有收入模型或毛利测算")),
        ("market_size", "市场与客户规模", 0.25, lambda: _pick(
            _quantified(t, r"(?:市场规模|客户|用户数|订单|渗透率|占有率|所高校|个课题组|个学院|家单位|个实验室)"),
            "市场/客户规模有数字", "市场规模的数字缺失")),
        ("go_to_market", "推广路径", 0.15, lambda: _pick(
            _hits(t, r"(?:渠道|推广|试点|合作(?:单位|企业)|落地(?:场景|计划)|首批客户)"),
            "有推广渠道或落地对象", "缺推广路径，商业性止于「有人买」")),
    ]


def _check_feasibility(ctx):
    t = ctx["text"]
    return [
        ("plan", "阶段计划", 0.30, lambda: _pick(
            _hits(t, r"(?:第[一二三四五六1-6]阶段|里程碑|计划(?:于|在)?\s*\d|个月|季度|进度)"),
            "有阶段/时间安排", "没有阶段计划或时间节点")),
        ("resource", "资源投入", 0.25, lambda: _pick(
            _quantified(t, r"(?:预算|经费|投入|人力|设备|场地)"),
            "预算/人力有量化", "资源投入没有数字，可行性无法判断")),
        ("risk", "风险与应对", 0.25, lambda: _pick(
            _hits(t, r"(?:风险[^。；\n]{0,12}(?:应对|规避|预案|措施)|挑战[^。；\n]{0,12}(?:应对|方案)|备选方案)"),
            "风险有对应措施", "只提风险不提应对措施")),
        ("validation", "验证数据", 0.20, lambda: _pick(
            _hits(t, r"(?:实测|测试|试验|试点|验证|仿真)[^。；\n]{0,30}?\d"),
            "有实测/试点验证数据", "没有验证数据，可行性只有推断")),
    ]


def _check_social(ctx):
    t = ctx["text"]
    return [
        ("beneficiary", "受益群体", 0.35, lambda: _pick(
            _hits(t, r"(?:受益|服务对象|帮助|面向[^。；\n]{0,10}(?:农户|患者|老人|学生|社区|职工|残疾人))"),
            "点明了受益群体", "没写清谁受益")),
        ("benefit_quant", "社会效益量化", 0.35, lambda: _pick(
            _quantified(t, r"(?:社会效益|减少|节约|减排|覆盖|惠及|带动)"),
            "社会效益有数字", "社会效益是形容词，没有量化")),
        ("sustainability", "可持续性", 0.30, lambda: _pick(
            _hits(t, r"(?:可持续|长期(?:运行|运营)|公益|复制推广|自我造血)"),
            "说明了可持续方式", "没有说明项目如何长期运转")),
    ]


def _check_presentation(ctx):
    raw, result, mode = ctx["raw"], ctx["result"], ctx["mode"]
    heads = len(re.findall(r"^#{1,4}\s+\S", raw, re.M))
    official = ctx.get("official_chapters") or 0
    need = max(4, int(official * 0.8)) if official else 4
    rich = bool(result.get("rich_charts") or result.get("rich_tables") or result.get("rich_deck"))
    n = ctx["chars"]
    lo, hi = (6000, 20000) if mode == "deep" else (800, 2200)

    def _structure():
        if heads >= need:
            return _PASS, "共 %d 个标题（官方章节 %d）" % (heads, official or need), "结构对齐官方章节"
        return _FAIL, "共 %d 个标题" % heads, "标题数少于官方章节的八成（需 ≥ %d）" % need

    def _rich():
        if rich:
            return _PASS, "含图表/表格/PPT 资产", "有可视化支撑"
        if mode != "deep":
            return _PARTIAL, "%d 字摘要稿" % n, "简洁版不要求图表；要拿展示分需切深度版"
        return _FAIL, "", "深度版仍无图表/表格/PPT"

    def _wc():
        if lo <= n <= hi:
            return _PASS, "%d 字" % n, "字数在档位区间"
        return _PARTIAL, "%d 字" % n, "偏离 %s 档 %d~%d 字" % (mode, lo, hi)

    def _clean():
        bad = []
        if re.search(r"【[^】]*】|待你填写|待补充", raw):
            bad.append("占位符")
        if re.search(r"[\u4e00-\u9fa5]{2,4}大学(?!生|城)", raw):
            bad.append("疑似院校名")
        if bad:
            return _FAIL, "、".join(bad), "有「%s」，展示环节直接扣分" % "、".join(bad)
        return _PASS, "无占位符与双盲信息", "版面干净"

    return [
        ("structure", "章节结构", 0.30, _structure),
        ("rich", "可视化资产", 0.25, _rich),
        ("wordcount", "字数档位", 0.20, _wc),
        ("clean", "版面合规", 0.25, _clean),
    ]


def _check_team(ctx):
    t = ctx["text"]
    return [
        ("roles", "角色分工", 0.35, lambda: _pick(
            _hits(t, r"(?:成员[^。；\n]{0,20}(?:负责|分工)|分工[^。；\n]{0,20}|负责人|技术负责人|运营负责人)"),
            "有角色分工", "没有成员分工，团队分靠猜")),
        ("collaboration", "协作机制", 0.35, lambda: _pick(
            _hits(t, r"(?:例会|周会|联调会|站会|复盘会|评审会|同步会|迭代制|周迭代|"
                    r"每(?:日|周|月)[^。；\n]{0,8}(?:会|同步|对齐|评审|复盘)|"
                    r"交叉(?:评审|验证)|共同(?:完成|推进)|协同)"),
            "有协作机制", "只列了人，没写怎么协作")),
        ("growth", "成长与收获", 0.30, lambda: _pick(
            _hits(t, r"(?:成长|收获|提升[^。；\n]{0,12}(?:能力|水平)|学会了|掌握了?|培养了|"
                    r"积累[^。；\n]{0,12}经验|锻炼[^。；\n]{0,10}能力|训练价值|育人价值|能力沉淀)"),
            "有成长叙述", "缺「成员在项目里获得了什么」的叙述")),
    ]


def _check_tech(ctx):
    t = ctx["text"]
    return [
        ("stack", "技术构成", 0.25, lambda: _pick(
            _hits(t, r"(?:传感器|算法|模型|框架|协议|嵌入式|数据库|边缘|云端|接口|芯片|视觉|射频|电机|控制)"),
            "点名了具体技术手段", "技术描述停在功能层，没有具体手段")),
        ("metrics", "性能指标", 0.30, lambda: _pick(
            _quantified(t, r"(?:准确率|精度|误差|响应|延时|吞吐|识别率|功耗|续航|分辨率|帧率)"),
            "有性能指标数字", "没有准确率/误差/响应这类可核对的指标")),
        ("architecture", "结构说明", 0.25, lambda: _pick(
            _hits(t, r"(?:架构|模块|数据流|流程|分层|端到端| pipeline|Pipeline)"),
            "描述了模块或数据流", "没有说清系统由哪些部分组成、怎么串起来")),
        ("test", "测试与对比", 0.20, lambda: _pick(
            _hits(t, r"(?:测试(?:集|用例|环境)|对比实验|基线|仿真结果|消融)"),
            "有测试设计", "缺测试设计与对比基线")),
    ]


def _check_value(ctx):
    t = ctx["text"]
    return [
        ("scene", "使用场景", 0.30, lambda: _pick(
            _hits(t, r"(?:场景|用户|客户|使用者|一线|现场)[^。；\n]{0,20}"),
            "场景具体", "场景停留在抽象描述")),
        ("quantified", "价值量化", 0.30, lambda: _pick(
            _quantified(t, r"(?:效率|成本|时间|人工|覆盖|准确|减少|提升)"),
            "价值有数字", "价值只有形容词，没有「提升多少」")),
        ("compare", "与现有方案对比", 0.20, lambda: _pick(
            _hits(t, r"(?:现有(?:方案|手段|做法)|传统(?:方式|方法)|人工(?:盘点|登记|巡检)|竞品)"),
            "点出了被替代的做法", "没说明它替代了什么、好在哪里")),
        ("traction", "落地进展", 0.20, lambda: _pick(
            _hits(t, r"(?:试点|已(?:在|于)[^。；\n]{0,12}(?:使用|部署|上线)|合作单位|意向订单)"),
            "有落地或试点进展", "没有落地进展，价值仍是设想")),
    ]


def _check_general(ctx):
    n = ctx["chars"]
    lo = 6000 if ctx["mode"] == "deep" else 800

    def _body():
        if n >= lo:
            return _PASS, "%d 字" % n, "该维度未配置专项判据，仅按篇幅与结构估算"
        return _PARTIAL, "%d 字" % n, "篇幅偏短，任何维度都难拿高分"

    return [("body", "篇幅基础", 1.0, _body)]


_FAMILY_CHECKS = {
    "innovation": _check_innovation,
    "business": _check_business,
    "feasibility": _check_feasibility,
    "social": _check_social,
    "presentation": _check_presentation,
    "team": _check_team,
    "tech": _check_tech,
    "value": _check_value,
    "general": _check_general,
}


def _pick(hits, ok_note, miss_note):
    """命中即 pass（带首条片段），未命中 fail。"""
    if hits:
        return _PASS, hits[0][1], ok_note
    return _FAIL, "", miss_note


def _generic_check(text):
    _CLICHE = peer("quality_gate")._CLICHE
    bad = [c for c in _CLICHE if c in (text or "")]
    if bad:
        return _FAIL, "命中套话：%s" % "、".join(bad[:3]), "开头出现套话，创新性的第一印象被拉低"
    return _PASS, "", "未见套话开场"


# ============ 汇总 ============
def _strip_md(text):
    return re.sub(r"[#*`>\-\[\]()（）]", "", text or "")


def diagnose(result, competition_name, track=None, mode="fast"):
    """按官方维度诊断一份生成结果。

    返回 dict；赛事无官方权重时 available=False，dims 为空，不猜分数。
    """
    ca = peer("competition_agents")

    result = result or {}
    mode = "deep" if str(mode).strip().lower() == "deep" else "fast"
    dims = ca._official_scoring_dims(competition_name, track)
    proposal = result.get("proposal") or ""
    if not dims:
        return {
            "available": False,
            "reason": "该赛事未配置官方评分权重（机考类或评审制），无法按项诊断",
            "competition": competition_name or "",
            "track": track or "",
            "dims": [],
            "total": None,
        }

    try:
        official = len(ca._official_chapters({"competition_name": competition_name or "", "track": track}) or [])
    except Exception:
        official = 0

    ctx = {
        "raw": proposal,
        "text": _strip_md(proposal),
        "result": result,
        "mode": mode,
        "chars": len(_strip_md(proposal).replace(" ", "")),
        "official_chapters": official,
    }

    total_w = sum(float(d.get("weight") or 0) for d in dims) or 0.0
    scored_w, weighted = 0.0, 0.0
    items = []
    for d in dims:
        name, weight = str(d.get("name") or ""), float(d.get("weight") or 0)
        family = classify_dim(name)
        checks_raw = _FAMILY_CHECKS[family](ctx)
        checks, gaps, gap_items = [], [], []
        dim_ratio = 0.0
        for key, label, w, fn in checks_raw:
            try:
                status, snippet, note = fn()
            except Exception as e:                                # 判据本身坏掉不能拖垮整张表
                status, snippet, note = _FAIL, "", "判据执行异常：%s" % e
            lost_ratio = 1.0 - _STATUS_SCORE.get(status, 0.0)
            dim_ratio += w * _STATUS_SCORE.get(status, 0.0)
            checks.append({
                "key": key, "label": label, "status": status,
                "snippet": snippet, "note": note, "weight": round(w, 2),
            })
            if status != _PASS:
                gaps.append(label + "：" + note)
                # 丢分按「该检查项的权重 × 未得分比例」拆，不能把整个维度的丢分
                # 复制给每一条缺口——那样 3 条缺口会把 30 分算成 49.5 分。
                gap_items.append({"key": key, "label": label, "note": note,
                                  "lost": round(weight * w * lost_ratio, 2)})
        dim_score = round(weight * min(1.0, dim_ratio), 1)
        items.append({
            "name": name,
            "weight": weight,
            "family": family,
            "family_label": _FAMILY_LABEL.get(family, family),
            "score": dim_score,
            "ratio": round(min(1.0, dim_ratio), 3),
            "judged": family != "general",
            "checks": checks,
            "gaps": gaps,
            "gap_items": gap_items,
        })
        if family != "general":
            scored_w += weight
            weighted += dim_score

    # general 族不计入总分：没有专项判据的维度，算出来的分是猜的
    total = round(weighted / scored_w * 100, 1) if scored_w else None
    return {
        "available": True,
        "competition": competition_name or "",
        "track": track or "",
        "mode": mode,
        "full_mark": round(scored_w, 1),
        "total": total,
        "basis": "按官方评分项逐项核对，只在找得到原文证据时给分；缺证据按 0 计",
        "coefficient_note": (
            "总分按已配置专项判据的维度归一（覆盖 %s / %s 分）" % (round(scored_w, 1), round(total_w, 1))
            if scored_w and scored_w != total_w else "全部维度均已配置判据"
        ),
        "dims": items,
        "top_gaps": _top_gaps(items),
    }


def _top_gaps(items, n=3):
    """按「丢分绝对值」排序，最值得先补的几条。

    同一处缺口会被同族维度重复报（创新性 35 与原创性 20 共用一套判据），
    按缺口文案合并、把两个维度的丢分累加，只报一次。
    丢分按检查项拆算，不按维度整块复制（否则 3 条缺口会算出 49.5 分 > 维度满分 30）。
    """
    agg = {}
    for d in items:
        if not d.get("judged"):
            continue
        for gi in d.get("gap_items") or []:
            slot = agg.setdefault(gi["label"], {"dims": [], "lost": 0.0, "note": gi["note"]})
            if d["name"] not in slot["dims"]:
                slot["dims"].append(d["name"])
            slot["lost"] += gi["lost"]
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]["lost"])
    return [{"dim": "、".join(v["dims"]), "gap": "%s：%s" % (k, v["note"]),
             "lost": round(v["lost"], 1)}
            for k, v in ranked[:n]]


def diagnose_history(db_path, history_id, track=None):
    """从历史库取一次生成的结果并诊断。"""
    import json
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT result_data, mode, competition_name FROM history WHERE id=?",
            (history_id,)).fetchone()
    if not row:
        return {"available": False, "reason": "记录不存在", "dims": [], "total": None}
    try:
        result = json.loads(row[0] or "{}")
    except Exception:
        result = {}
    # 按用户实际看到的样子诊断：修订说明、外造待办节、套话在展示/交付前就被清掉了，
    # 拿未清理的原稿判分会把「针对意见（1）」这类痕迹和「赋能闭环」当成正文内容。
    # 必须与 scorecard_patch 的清理链完全一致，否则面板显示 66.2、点补强却报
    # 「74.5 → 91.0」，用户会以为工具在乱跳数字（线上 hid 323 实测踩到）。
    try:
        _ca = peer("competition_agents")
        if isinstance(result, dict) and result.get("proposal"):
            result["proposal"] = _ca._strip_cliches(_ca._strip_ai_artifacts(
                _ca._fix_mislabeled_measured(_ca._strip_fabricated_times(
                    _ca._downgrade_fabrication(_ca._strip_placeholders(
                        _ca._dedupe_consecutive(_ca._strip_pending_sections(
                            _ca._strip_revision_note(result["proposal"])))))))))
    except Exception:
        pass
    return diagnose(result, row[2] or "", track, row[1] or "fast")


def render_text(diag):
    """把诊断结果渲染成纯文本（探针与命令行用，前端走 json）。"""
    if not diag.get("available"):
        return "无法诊断：%s" % diag.get("reason", "")
    lines = ["%s%s  按官方评分项自查 %s / 100" % (
        diag["competition"], ("·" + diag["track"]) if diag.get("track") else "", diag.get("total"))]
    if diag.get("basis"):
        lines.append("口径：%s" % diag["basis"])
    for d in diag["dims"]:
        mark = "" if d["judged"] else "  (无专项判据，不计入总分)"
        lines.append("")
        lines.append("[%s] %s/%s 分 · %s%s" % (
            d["name"], d["score"], _fmt(d["weight"]), d["family_label"], mark))
        for c in d["checks"]:
            flag = {"pass": "√", "partial": "~", "fail": "×"}[c["status"]]
            lines.append("  %s %s：%s" % (flag, c["label"], c["note"]))
            if c["snippet"]:
                lines.append("      证据：%s" % c["snippet"])
    if diag.get("top_gaps"):
        lines.append("")
        lines.append("优先补这三处：")
        for i, g in enumerate(diag["top_gaps"], 1):
            lines.append("  %d. [%s] %s（丢约 %s 分）" % (i, g["dim"], g["gap"], g["lost"]))
    return "\n".join(lines)


def _fmt(v):
    return ("%g" % v) if v is not None else "?"


if __name__ == "__main__":
    import os
    import sys

    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "backend", ".data", "competition.db")
    db = os.environ.get("COMPETITION_DB_PATH") or db
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        import sqlite3
        with sqlite3.connect(db) as _c:
            target = _c.execute("SELECT MAX(id) FROM history").fetchone()[0]
    print(render_text(diagnose_history(db, int(target))))
