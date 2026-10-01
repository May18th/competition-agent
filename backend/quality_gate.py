#!/usr/bin/env python3
"""分层自动质检（第一百一十九轮）：把「错误经验蒸馏库」规则程序化。

L1 生成完整性 / L2 导出质量 / L3 内容质量 / L4 历史恢复 / L5 部署守卫。
每层返回 (ok, issues)。检测结果由调用方写入 运行日志.md。
"""
import re
import os


# ============ L1 生成完整性 ============
def check_generation(result, mode="deep"):
    issues = []
    proposal = result.get("proposal") or ""
    n = len(re.sub(r'[#*`\-|>\[\]（）()\s]', '', proposal))
    # 2026-10-01（深度版信息密度导向改造）：深度版无硬性字数下限，2500 只是
    # 异常检测线（低于它大概率截断/漏章，生成端 _expand_to_length 同口径），
    # 通常篇幅 2500～5000 字、以信息完整为准，不再拿 6000 硬卡。
    if mode == "deep" and n < 2500:
        issues.append(f"深度版正文 {n} 字 < 2500 异常检测线（疑似截断/漏章，请核对章节完整性）")
    # 2026-10-01（271 号记录误杀复盘）：富媒体检查按 mode 走——fast（简洁版）
    # 链路本来就没有图表管线（rich_charts/rich_tables 只在 deep 解析），
    # 按 deep 标准审 fast 必然误报「富媒体为空」。
    if mode == "deep" and not (result.get("rich_charts") or result.get("rich_tables")):
        issues.append("富媒体（图表/表格）为空")
    if mode == "deep" and not result.get("rich_deck"):
        issues.append("rich_deck（路演PPT）为空")
    for k in ("defense_questions", "ppt_outline"):
        if not result.get(k):
            issues.append(f"模块缺失：{k}")
    # 防凑数（145/146 轮）：空话段落占比 >30% 判定凑数，两档一起打回。
    _eok, _eissues = check_depth(proposal)
    if not _eok:
        issues.extend(_eissues)
    # 获奖作品反面失分模式（2026-10 蒸馏第 8 节）：普适项两档都查，结构项只查 deep
    _aok, _aissues = check_award_pitfalls(proposal, mode)
    if not _aok:
        issues.extend(_aissues)
    return (not issues), issues


# ============ 防凑数（第一百四十五轮深度版 + 第一百四十六轮简洁版） ============
_INFO_MARK = re.compile(r'\d|%|％|元|万|亿|倍|算法|模型|架构|系统|平台|接口|模块|芯片|传感器|数据|网络|服务器|协议|基于|通过|采用|实现|验证|测算|估计|预测|方案')


def check_depth(proposal):
    """空话段落扫描：无数据/无技术词/无论证词的「铺垫性空段」占比 >30% 判定凑数。"""
    paras = [p.strip() for p in (proposal or "").split("\n") if len(p.strip()) > 30]
    if not paras:
        return False, ["正文无有效段落"]
    empty = 0
    for p in paras:
        if not _INFO_MARK.search(p):
            empty += 1
    ratio = empty / len(paras)
    if ratio > 0.3:
        return False, [f"空话段落占比过高（{empty}/{len(paras)} = {ratio:.0%} > 30%，疑似凑数）"]
    return True, []


# ============ L2 导出质量 ============
def check_docx(docx_path, expect_type="report"):
    issues = []
    try:
        from docx import Document
        doc = Document(docx_path)
        txt = "\n".join(p.text for p in doc.paragraphs)
        if not txt.strip():
            issues.append("docx 正文为空")
        elif txt.count("?") > max(3, len(txt) * 0.3) or "？？" in txt:
            issues.append("docx 中文乱码（? 占比过高）")
        if expect_type in ("report", "default"):
            has_toc = any(("TOC" in p._p.xml) or ("fldChar" in p._p.xml) or ("PAGEREF" in p._p.xml)
                          for p in doc.paragraphs)
            if not has_toc:
                issues.append("申报书 docx 无 TOC 目录域")
        heads = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
        if len(heads) < 3:
            issues.append(f"Heading 层级过少（{len(heads)}）")
    except Exception as e:
        issues.append(f"docx 检查失败：{e}")
    return (not issues), issues


# ============ L2 扩展：pptx / pdf / zip（第一百二十五轮） ============
def check_pptx(path):
    issues = []
    try:
        import os as _os
        sz = _os.path.getsize(path)
        if sz > 2 * 1024 * 1024:
            issues.append(f"PPT 体积超限（{sz // 1024}KB > 2MB）")
        from pptx import Presentation
        prs = Presentation(path)
        n = len(prs.slides)
        if n < 8:
            issues.append(f"PPT 页数过少（{n} < 8）")
        _prompt_marks = ("用表格呈现", "如下图所示", "请生成", "请用")
        _hit = set()
        for s in prs.slides:
            for sh in s.shapes:
                if sh.has_text_frame and sh.text_frame.text:
                    for m in _prompt_marks:
                        if m in sh.text_frame.text:
                            _hit.add(m)
        if _hit:
            issues.append("PPT 残留生成指令：" + "、".join(sorted(_hit)[:3]))
    except Exception as e:
        issues.append(f"pptx 检查失败：{e}")
    return (not issues), issues


# 417 轮：各赛事对提交 PDF 的页数/体积限制。
# 只放有明确依据的条目；没配到的一律走 DEFAULT_PDF_LIMIT 的宽松值，
# 宁可放过也不能因为「没配」就把用户的正式提交件判死。
PDF_LIMITS = [
    # iCAN 官网要求：作品说明书（申报书）正文不超过 20 页
    {"match": ("ican",), "max_pages": 20, "max_mb": 10,
     "label": "iCAN 作品说明书/申报书"},
    # 「挑战杯」中国大学生创业计划竞赛：申报书正文一般控制在 30 页内（保守值）
    {"match": ("挑战杯", "创青春"), "max_pages": 30, "max_mb": 15,
     "label": "挑战杯申报书"},
]
# 未匹配到赛事时的兜底：宽松，不误杀
DEFAULT_PDF_LIMIT = {"max_pages": 40, "max_mb": 20, "label": "通用文档"}


def pdf_limits_for(competition_name="", doc_title=""):
    """按赛事名（模糊匹配）取 PDF 页数/体积限制，返回 {"max_pages","max_mb","label"}。"""
    comp = (competition_name or "").lower()
    doc = (doc_title or "")
    for item in PDF_LIMITS:
        for kw in item["match"]:
            if kw.lower() in comp or kw in doc:
                return {"max_pages": item["max_pages"],
                        "max_mb": item["max_mb"], "label": item["label"]}
    return dict(DEFAULT_PDF_LIMIT)


def _pdf_trim_suggestions(n_pages, mb, limit):
    """超限时的可执行删减建议——必须带数字，不许写「请精简内容」这种废话。"""
    tips = []
    if n_pages > limit["max_pages"]:
        over = n_pages - limit["max_pages"]
        tips.append("需删掉 %d 页（当前 %d 页 → 上限 %d 页）" % (over, n_pages, limit["max_pages"]))
        tips.append("优先合并连续的数据页：把财务测算、市场规模、成本结构三张表压到 1～2 页并排排版")
        tips.append("附录类内容（访谈记录、问卷原题、代码清单、参考文献）移出正文或改放网盘链接")
        tips.append("每章的「小结」段落整段删掉，评委看的是数据与结论，不是总结")
        if over >= 8:
            tips.append("超出较多（%d 页），建议回到结果页把正文按章节重写为精简版再导出" % over)
    if mb > limit["max_mb"]:
        over_mb = round(mb - limit["max_mb"], 1)
        tips.append("需压掉约 %.1fMB（当前 %.1fMB → 上限 %dMB）" % (over_mb, mb, limit["max_mb"]))
        tips.append("图片/图表统一降到 150dpi，通常能减 30%～50% 体积")
        tips.append("删除正文里重复出现的同一张架构图/流程图，只保留一处")
        if n_pages and mb / max(n_pages, 1) > 0.5:
            tips.append("当前平均每页 %.2fMB，明显是图太重；优先压图而不是删字" % (mb / n_pages))
    return tips


def check_pdf(path, competition_name=None, doc_title=None, detail=False):
    """PDF 导出终检。

    向后兼容：不传 competition_name/doc_title 时行为与 417 轮前完全一致，
    只查体积 3MB / 无页面 / 中文乱码，返回 (ok, issues) 二元组。
    detail=True 时返回 dict：{"ok","errors","warnings","suggestions","pages","mb","limit"}。
    """
    issues = []
    pages, mb = 0, 0.0
    try:
        import os as _os
        sz = _os.path.getsize(path)
        mb = sz / (1024.0 * 1024.0)
        if sz > 3 * 1024 * 1024:
            issues.append(f"PDF 体积超限（{sz // 1024}KB > 3MB）")
        from pypdf import PdfReader
        r = PdfReader(path)
        pages = len(r.pages)
        if pages < 1:
            issues.append("PDF 无页面")
        _txt = ""
        for p in r.pages[:3]:
            try:
                _txt += (p.extract_text() or "")
            except Exception:
                pass
        if _txt and _txt.count("?") > max(3, len(_txt) * 0.3):
            issues.append("PDF 中文乱码")
    except Exception as e:
        issues.append(f"pdf 检查失败：{e}")

    if not detail:
        return (not issues), issues

    # 基础检查里「3MB 体积」这条太紧：带图的申报书轻松过 3MB，但 iCAN 上限是 10MB，
    # 拿 3MB 去卡等于误杀正式提交件。detail 路径下它降为 warning，
    # 真正的页数/体积红线交给下面按赛事取到的限制来判。
    errors = [x for x in issues if "体积超限" not in x]
    warnings = [x for x in issues if "体积超限" in x]
    suggestions = []
    limit = pdf_limits_for(competition_name, doc_title)
    if pages and pages > limit["max_pages"]:
        errors.append("本 PDF 共 %d 页，超出%s要求（≤%d 页）"
                      % (pages, limit["label"], limit["max_pages"]))
    if mb and mb > limit["max_mb"]:
        errors.append("本 PDF 共 %.1fMB，超出%s要求（≤%dMB）"
                      % (mb, limit["label"], limit["max_mb"]))
    if errors:
        suggestions = _pdf_trim_suggestions(pages, mb, limit)
    elif pages and pages >= limit["max_pages"] - 2:
        warnings.append("页数已接近上限（%d/%d 页），再补充内容就会超限"
                        % (pages, limit["max_pages"]))
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "suggestions": suggestions, "pages": pages,
            "mb": round(mb, 2), "limit": limit}


# 打包期望文件数（mode 感知，2026-10-01 fast 打包 422 修复）：
# fast（简洁版）链路没有路演 PPT 管线，「一键打包全部」只有 11 个文件，
# 拿 deep 的 12 硬卡会把 fast 记录直接判「文件数不足」→ 422 核心功能不可用。
# deep 全家桶 12 件（含路演 PPT），fast 11 件（无 PPT）。
ZIP_EXPECT = {"deep": 12, "fast": 11}


def check_zip(path, expect_count=None, mode="deep"):
    """zip 导出终检：文件数 / 体积。

    新签名（向后兼容）：
    - check_zip(path)                      → 按 deep 期望 12 件，与历史默认行为一致
    - check_zip(path, mode="fast")         → 按 fast 期望 11 件
    - check_zip(path, expect_count=N)      → 显式传入优先（老调用方式不受影响）
    - check_zip(path, 5)                  → 位置参数仍视为 expect_count
    返回 (ok, issues)。
    """
    if expect_count is None:
        expect_count = ZIP_EXPECT.get(mode, ZIP_EXPECT["deep"])
    issues = []
    try:
        import os as _os
        import zipfile as _zf
        sz = _os.path.getsize(path)
        if sz > 10 * 1024 * 1024:
            issues.append(f"zip 体积超限（{sz // 1024}KB > 10MB）")
        with _zf.ZipFile(path) as z:
            names = z.namelist()
            if len(names) < expect_count:
                issues.append(f"zip 文件数不足（{len(names)} < {expect_count}）")
    except Exception as e:
        issues.append(f"zip 检查失败：{e}")
    return (not issues), issues


# ============ L6 评价真实性（第一百三十三轮） ============
def check_review(review_str, proposal=""):
    """校验专家评审 JSON：quote 必须真实存在于原文、评分与依据一致、优缺平衡、无套话。"""
    issues = []
    try:
        import json as _json
        s = (review_str or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:]
        data = _json.loads(s)
    except Exception:
        return False, ["评价不是合法 JSON"]
    experts = data.get("experts") or []
    if not experts:
        return False, ["评价缺 experts"]
    _cliche = ("很有潜力", "非常优秀", "前景广阔", "表现不错", "有待提升")
    for i, ex in enumerate(experts):
        score = ex.get("score") if isinstance(ex.get("score"), (int, float)) else 0
        strengths = ex.get("strengths") or []
        eissues = ex.get("issues") or []
        if not strengths:
            issues.append(f"专家{i+1} 无优点")
        if not eissues:
            issues.append(f"专家{i+1} 无缺点")
        if score >= 85 and not strengths:
            issues.append(f"专家{i+1} 高分 {score} 但无亮点依据")
        if score < 60 and not eissues:
            issues.append(f"专家{i+1} 低分 {score} 但无硬伤依据")
        for ei in eissues:
            q = (ei.get("quote") or "").strip() if isinstance(ei, dict) else ""
            if q and proposal and q not in proposal:
                issues.append(f"专家{i+1} quote 不存在于原文：{q[:20]}")
        try:
            txt = _json.dumps(ex, ensure_ascii=False)
            for c in _cliche:
                if c in txt:
                    issues.append(f"专家{i+1} 套话：{c}")
                    break
        except Exception:
            pass
    return (not issues), issues


# ============ 总审质检（第一百三十四轮，轻量规则，不引重模型） ============
# 板块中文名（警告文案要用户能看懂，不暴露内部字段名）
_TOTAL_MODULE_NAMES = {
    "parsed_rules": "赛事规则解析", "similarity_report": "相似度初检",
    "competitor_analysis": "竞品分析", "business_model": "商业模式",
    "risk_analysis": "风险分析", "tech_solution": "技术方案",
    "implementation_plan": "实施计划", "social_value": "社会价值",
    "project_summary": "项目简介", "proposal": "申报书正文",
    "judge_feedback": "评委反馈", "defense_questions": "答辩问题预测",
    "ppt_outline": "PPT大纲", "speech_script": "路演讲稿",
}

# deep 专属板块：fast（简洁版）工作流没有 plan/social/summary 三个节点，
# 这三块只在 deep 链路生成（见 competition_agents.py 的 fast_app / deep_workflow）
_DEEP_ONLY_MODULES = ("implementation_plan", "social_value", "project_summary")


def check_total(result, mode="deep"):
    """板块完整性 + 跨板块数字一致性检查。返回 (ok, issues)。

    2026-10-01（271 号记录误杀复盘）：板块清单按 mode 走——fast 链路没有
    implementation_plan / social_value / project_summary 这三个 deep 专属板块，
    拿 deep 全家桶审 fast 必然「缺板块」误报。数字冲突检查两档都保留（只警告）。
    """
    issues = []
    _modules = ["parsed_rules", "similarity_report", "competitor_analysis", "business_model",
                "risk_analysis", "tech_solution", "implementation_plan", "social_value",
                "project_summary", "proposal", "judge_feedback", "defense_questions",
                "ppt_outline", "speech_script"]
    if mode != "deep":
        _modules = [m for m in _modules if m not in _DEEP_ONLY_MODULES]
    for m in _modules:
        if not (result.get(m) or "").strip():
            issues.append(f"缺板块：{_TOTAL_MODULE_NAMES.get(m, m)}")
    # 跨板块一致性：同一关键词在不同板块出现不同数值 → 冲突
    import re as _re
    _kw = ("市场规模", "客单价", "月收入", "单价", "成本", "毛利率", "转化率", "用户数", "付费率", "日均")
    def _extract(text):
        found = {}
        for k in _kw:
            vals = set()
            for mm in _re.finditer(re.escape(k) + r'[^。；\n]{0,12}?(\d+(?:\.\d+)?)', text or ""):
                vals.add(mm.group(1))
            if vals:
                found[k] = vals
        return found
    _parts = {"tech_solution": result.get("tech_solution", ""),
              "business_model": result.get("business_model", "")}
    _agg = {}
    for _src, _txt in _parts.items():
        for k, vals in _extract(_txt).items():
            _agg.setdefault(k, set()).update(vals)
    for k, vals in _agg.items():
        if len(vals) > 1:
            issues.append(f"跨板块数字冲突：{k}出现{'/'.join(sorted(vals))}多个版本，已按正文原文导出，请核对统一口径")
    return (not issues), issues


# ============ L3 内容质量 ============
_CLICHE = ("进一步提升", "不断完善", "积极探索", "高度重视", "显著提高",
           "赋能", "闭环", "抓手", "扎实推进", "深入贯彻")


def check_content(text):
    issues = []
    for c in _CLICHE:
        if c in (text or ""):
            issues.append(f"套话：{c}")
    if re.search(r'[\u4e00-\u9fa5]{2,4}大学(?!生|城)', text or ""):
        issues.append("疑似泄露院校名（双盲）")
    if re.search(r'(指导老师|指导教师|导师)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}', text or ""):
        issues.append("疑似泄露导师姓名")
    return (not issues), issues


# ============ L3 扩展：获奖作品反面失分模式检查（2026-10 蒸馏，docs/获奖作品写作规范_蒸馏.md 第 8 节） ============
# 与 judge_paradigm.json 互补不重复：那边是「评委批评语」注入模拟评委 LLM；
# 这里把 12 条反面模式中可程序化的 9 条做成正则/结构检查（#4 #11 #12 见下方注释说明）。
# 普适项（#1 空话 / #2 无数据论断 / #5 痛点泛泛 / #6 财务浮夸 / #10 落地含糊）两档都查；
# 结构项（#3 概念堆砌 / #7 拍脑袋 / #8 前三页密度 / #9 六要素）只查 deep——fast 篇幅短、
# 章节结构不同，查了必误杀。
_EMPTY_GRAND = re.compile(r'(?:助力|推动|服务|赋能)(?:乡村振兴|碳达峰|碳中和|教育公平|数字化转型|高质量发展|共同富裕)')
_LEAD_CLAIM = re.compile(r'国内领先|国际先进|国际领先|行业领先|全国领先|业内领先')
_PAIN_VAGUE = re.compile(r'面临很多问题|面临许多问题|需求旺盛|痛点众多|存在诸多问题|问题日益突出|尚无有效(?:的)?解决方案')
_HOT_CONCEPTS = ("人工智能", "大模型", "数字孪生", "元宇宙", "区块链", "物联网", "大数据", "机器学习", "深度学习", "神经网络", "生成式AI", "边缘计算")
_GROWTH_RATE = re.compile(r'(?:年增|年增长|同比增长|年增长率|增速)[^。；\n]{0,8}?(\d+(?:\.\d+)?)\s*[%％]')
_GROSS_MARGIN = re.compile(r'毛利率[^。；\n]{0,8}?(\d+(?:\.\d+)?)\s*[%％]')
_GROW_TIMES = re.compile(r'增长[^。；\n]{0,6}?(\d+(?:\.\d+)?)\s*倍')
_BIG_MARKET = re.compile(r'千亿|万亿')
_SURVEY_TRACE = re.compile(r'走访|访谈|问卷|样本|实地调研|深度调研')
_VAGUE_DOING = re.compile(r'正在对接|正在洽谈|即将敲定|逐步落地|持续推进')
_SIX_ELEMENTS = (("痛点", r'痛点|难题|困境|困扰|面临.{0,6}问题'),
                 ("方案", r'解决方案|技术方案|产品形态|产品介绍|方案设计'),
                 ("验证数据", r'试点|实测|测试结果|验证数据|实验数据'),
                 ("商业模式", r'商业模式|盈利模式|收费模式|付费'),
                 ("财务", r'财务|成本结构|盈亏平衡|毛利率|收入'),
                 ("团队", r'团队|分工|成员'))


def _sentences(text):
    return [s for s in re.split(r'[。；;！!？?\n]', text or "") if s.strip()]


def check_award_pitfalls(text, mode="deep"):
    """获奖作品反面失分模式检查（蒸馏文档第 8 节 12 条）。

    12 条处置：#1 空话排比 / #2 无数据论断 / #5 痛点泛泛 / #6 财务浮夸 /
    #10 落地含糊 为普适项；#3 概念堆砌 / #7 市场拍脑袋 / #8 前三页数据密度 /
    #9 六要素闭环 仅 deep。#4 术语堆砌（技术章开头价值陈述）与 #11 答辩背稿
    属生成端与答辩稿管线的指令约束（已写入 competition_agents._AWARD_SPEC），
    正文正则无法可靠判定，不在此查；#12 格式硬伤已由 L2（docx/pdf）与
    check_total（跨板块数字一致性）覆盖，不重复。
    返回 (ok, issues)。
    """
    text = text or ""
    issues = []

    # #1 空话排比 /「正确的废话」：大词组合直接命中；「助力/赋能/推动」句无数字绑定按句计数
    if _EMPTY_GRAND.search(text):
        issues.append("社会价值空话：出现「助力/服务/推动 + 乡村振兴/碳达峰/教育公平」类不可核验大词（正确的废话，评委点名批评模式）")
    _empty_talk = [s for s in _sentences(text)
                   if re.search(r'助力|推动', s) and not re.search(r'\d', s)]
    if len(_empty_talk) >= 3:
        issues.append(f"空话句过多：{len(_empty_talk)} 个「助力/推动」句不带任何数字")

    # #2 无数据论断：领先类断言所在句无数字即报（评委原话「这句话没有任何意义」）
    _lead_hits = [s for s in _sentences(text) if _LEAD_CLAIM.search(s) and not re.search(r'\d', s)]
    if _lead_hits:
        issues.append(f"无数据论断：{len(_lead_hits)} 处「国内领先/国际先进」类断言不带对比数字（{_LEAD_CLAIM.search(_lead_hits[0]).group() if _lead_hits else ''}）")

    # #5 痛点泛泛：评委视为「无效数据、无调研」的泛化表述
    _vague = _PAIN_VAGUE.search(text)
    if _vague:
        issues.append(f"痛点泛泛：出现「{_vague.group()}」（无人群无场景无数据，判无效痛点）")

    # #6 财务过乐观：增长率 >300% / 毛利率 >80% / 「增长 N 倍」N>=9
    for m in _GROWTH_RATE.finditer(text):
        if float(m.group(1)) > 300:
            issues.append(f"财务浮夸：年增速 {m.group(1)}%（超 300% 区间，须给保守情景兜底与推导链）")
            break
    for m in _GROSS_MARGIN.finditer(text):
        if float(m.group(1)) > 80:
            issues.append(f"财务浮夸：毛利率 {m.group(1)}%（超 80% 区间，评委一眼判不合理）")
            break
    for m in _GROW_TIMES.finditer(text):
        if float(m.group(1)) >= 9:
            issues.append(f"财务浮夸：「增长 {m.group(1)} 倍」（等同于年增 900% 式翻车）")
            break

    # #10 落地描述含糊：「正在对接/持续推进」式等于没说（预期目标单独成段是合法的，「正在对接」不是）
    _vdoing = len(_VAGUE_DOING.findall(text))
    if _vdoing >= 2:
        issues.append(f"落地描述含糊：「正在对接/持续推进」类表述出现 {_vdoing} 处（要么写已发生的事实，要么写计划与时点）")

    if mode == "deep":
        # #3 概念堆砌蹭热点：热点概念词种类 >=6 提示核对（每个概念应对应实际功能）
        _kinds = [c for c in _HOT_CONCEPTS if c in text]
        if len(_kinds) >= 6:
            issues.append(f"疑似概念堆砌：热点技术概念出现 {len(_kinds)} 种（{'、'.join(_kinds[:4])}…），请核对每个概念都有对应实际功能")

        # #7 市场规模拍脑袋：千亿/万亿或占有率断言，全文却无任何调研过程痕迹
        if _BIG_MARKET.search(text) and not _SURVEY_TRACE.search(text):
            issues.append("市场规模拍脑袋：出现千亿/万亿级市场但全文无调研痕迹（走访/访谈/问卷/样本）")

        # #8 前三页数据密度：第一章（前两个 ## 标题之间）数字锚点 < 2 判定开头无硬数据
        _heads = [m.start() for m in re.finditer(r'^#{1,3}\s', text, re.M)]
        _first = text[_heads[0]:_heads[1]] if len(_heads) >= 2 else text[:800]
        if len(re.findall(r'\d', _first)) < 2:
            issues.append("前3页法则不达标：第一章没有至少 2 个数字锚点（评委前 3 页看不到「痛点+方案+硬数据」直接失分）")

        # #9 六要素闭环：商业逻辑缺项（技术强但闭环缺失得不了高分）
        _miss = [name for name, pat in _SIX_ELEMENTS if not re.search(pat, text)]
        if _miss:
            issues.append("商业闭环六要素缺项：" + "、".join(_miss))

    return (not issues), issues


# ============ L4 历史恢复 ============
def check_history_detail(resp):
    issues = []
    for k in ("rich_deck", "rich_charts", "rich_tables"):
        if k not in resp:
            issues.append(f"历史详情缺字段：{k}")
    return (not issues), issues


# ============ L5 部署守卫 ============
def check_version(v):
    """静态资源版本号必须时间戳唯一（如 v=20260928e），禁 v=12 递增整数。"""
    if re.fullmatch(r'v=\d{6,}', v or ""):
        return True, []
    return False, [f"版本号非时间戳唯一：{v or '(空)'}"]


def run_all(result=None, mode="deep", docx_path=None, history_resp=None):
    """跑全链路质检，返回 {层级: (ok, issues)}。"""
    report = {}
    if result is not None:
        report["L1_generation"] = check_generation(result, mode)
        if result.get("proposal"):
            report["L3_content"] = check_content(result["proposal"])
    if docx_path and os.path.exists(docx_path):
        report["L2_docx"] = check_docx(docx_path)
    if history_resp is not None:
        report["L4_history"] = check_history_detail(history_resp)
    return report


def summarize(report):
    """把质检报告压成一行文本，供写运行日志。"""
    parts = []
    for layer, (ok, issues) in report.items():
        parts.append(f"{layer}:{'PASS' if ok else 'FAIL(' + '；'.join(issues[:3]) + ')'}")
    return " | ".join(parts)


# ============ 系统默认评委（第一百二十一轮，前台不可见） ============
def _cjk(text):
    return len(re.sub(r'[#*`\-|>\[\]（）()\s]', '', text or ""))


def score_export(result, mode="deep"):
    """给一份生成结果打分（0-100，5 维度）。返回 (score, dims, reasons, hard_reasons)。

    2026-10-01（用户反馈「网站的功能就是帮用户修改，而不是让他们自己改」）：
    - hard_reasons 非空（正文乱码这类「文本非法」）时 score=0，调用方据此拒绝导出；
    - 其余所有问题（评分不足、缺图表、占位符、双盲泄露、编造来源等）只进 reasons，
      由导出层作为警告随文件放行，不再作为拒绝导出的理由。
    - 富媒体/路演PPT 缺失的扣分检查只在 deep 模式生效——fast 链路没有图表与
      deck 管线（271 号记录误杀复盘）。
    """
    dims = {"内容完整性": 30, "结构规范性": 25, "数据真实性": 25,
            "格式合规": 10, "逻辑一致性": 10}
    reasons = []
    proposal = result.get("proposal") or ""
    n = _cjk(proposal)

    # ---- 硬错误（文本非法，可拒绝导出）与软问题（只警告放行）分开 ----
    hard = []
    soft = []
    if proposal.count("?") > max(3, len(proposal) * 0.3) or "？？" in proposal:
        hard.append("中文乱码（? 占比过高）")
    if not proposal.strip():
        # 最终导出文本是否为空由导出接口判 400（那边才是真正要拦的空内容），
        # 这里只提示记录侧正文为空，供用户核对，不作为拒绝理由。
        soft.append("记录正文为空，已按页面文本导出")
    if re.search(r'【[^】]*】|待你填写|待补充|TBD|TODO', proposal):
        soft.append("存在【】占位符/待补提示，建议替换为实际内容后再提交")
    if re.search(r'据《.{0,30}202\d.{0,20}》', proposal):
        soft.append("存在无来源的「机构+年份」数据引用（编造嫌疑），请核实或删除")
    # 2026-10-01 收紧：[:：]? 可选导致「指导教师意见/与导师沟通」这类正常提及被误杀
    # （实测 268 号记录命中 4 处全是误判）。分隔符必须存在，只抓「指导教师：张三」式真签名。
    if re.search(r'[\u4e00-\u9fa5]{2,4}大学(?!生|城)', proposal) or \
       re.search(r'(指导老师|指导教师|导师|负责人|队长)\s*[:：]\s*[\u4e00-\u9fa5]{2,4}\s*(?:$|[，。、；！？,.;!?）)\]])', proposal, re.M):
        soft.append("疑似双盲信息泄露（院校/导师/姓名），提交前请自行确认已脱敏")
    if hard:
        return 0, dims, ["一票否决：" + h for h in hard] + soft, hard
    reasons.extend(soft)

    # 内容完整性
    # 2026-10-01：与 check_generation 同步——深度版无硬性字数下限，2500 为异常检测线
    if mode == "deep" and n < 2500:
        dims["内容完整性"] -= 6; reasons.append(f"正文 {n} 字 < 2500（疑似截断/漏章）")
    if mode == "deep" and not (result.get("rich_charts") or result.get("rich_tables")):
        dims["内容完整性"] -= 8; reasons.append("深度版缺图表/表格")
    if mode == "deep" and not result.get("rich_deck"):
        dims["内容完整性"] -= 7; reasons.append("深度版缺路演PPT")
    _miss = (result.get("completeness") or {}).get("missing") or []
    if _miss:
        dims["内容完整性"] -= 5; reasons.append("缺章节：" + "、".join(_miss[:3]))
    # 防凑数（145/146 轮）：空话段落占比 >30% 判定凑数，两档同样扣分打回
    _dok, _diss = check_depth(proposal)
    if not _dok:
        dims["内容完整性"] -= 20
        reasons.extend(_diss)

    # 获奖作品反面失分模式（2026-10 蒸馏第 8 节）：命中按数据真实性扣分，
    # 每条 3 分、上限 15 分，只警告放行不拒导出（与 soft 口径一致）
    _gok, _giss = check_award_pitfalls(proposal, mode)
    if not _gok:
        dims["数据真实性"] -= min(15, 3 * len(_giss))
        reasons.extend(_giss)

    # 结构规范性：Markdown 标题层级（>3 视为规范）
    _heads = [l for l in proposal.split("\n") if l.strip().startswith("#")]
    if len(_heads) < 4:
        dims["结构规范性"] -= 8; reasons.append(f"标题层级过少（{len(_heads)}）")

    # 数据真实性：套话 / 编造来源 / 占位 / 双盲泄露
    # （占位/编造引用/院校名三条已在 soft 警告里给过用户文案，这里只扣分不重复报）
    for c in _CLICHE:
        if c in proposal:
            dims["数据真实性"] -= 3; reasons.append(f"套话：{c}")
            break
    if re.search(r'据《.{0,30}202\d.{0,20}》', proposal):
        dims["数据真实性"] -= 6
    if re.search(r'【|待你填写|待补充|TBD|TODO', proposal):
        dims["数据真实性"] -= 5
    if re.search(r'[\u4e00-\u9fa5]{2,4}大学(?!生|城)', proposal):
        dims["数据真实性"] -= 4

    # 格式合规：占位（无体积信息，这里用相似度近似）
    _sim = result.get("similarity")
    if isinstance(_sim, (int, float)) and _sim > 25:
        dims["格式合规"] -= 4; reasons.append(f"查重偏高（{_sim}%）")

    # 逻辑一致性：复读检测（连续重复句）
    _lines = [l.strip() for l in proposal.split("\n") if len(l.strip()) > 20]
    if len(_lines) > len(set(_lines)) * 1.3:
        dims["逻辑一致性"] -= 4; reasons.append("疑似复读")

    score = max(0, sum(dims.values()))
    return score, dims, reasons, hard
