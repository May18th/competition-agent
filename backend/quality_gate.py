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
    if mode == "deep" and n < 6000:
        issues.append(f"深度版正文 {n} 字 < 6000 下限")
    if not (result.get("rich_charts") or result.get("rich_tables")):
        issues.append("富媒体（图表/表格）为空")
    if mode == "deep" and not result.get("rich_deck"):
        issues.append("rich_deck（路演PPT）为空")
    for k in ("defense_questions", "ppt_outline"):
        if not result.get(k):
            issues.append(f"模块缺失：{k}")
    # 防凑数（第一百四十五轮深度版 + 第一百四十六轮简洁版均适用）：
    # 空话段落占比 >30% 判定凑数，两档一起打回。
    _eok, _eissues = check_depth(proposal)
    if not _eok:
        issues.extend(_eissues)
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


def check_zip(path, expect_count=12):
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
def check_total(result, mode="deep"):
    """板块完整性 + 跨板块数字一致性检查。返回 (ok, issues)。"""
    issues = []
    _modules = ["parsed_rules", "similarity_report", "competitor_analysis", "business_model",
                "risk_analysis", "tech_solution", "implementation_plan", "social_value",
                "project_summary", "proposal", "judge_feedback", "defense_questions",
                "ppt_outline", "speech_script"]
    for m in _modules:
        if not (result.get(m) or "").strip():
            issues.append(f"缺板块：{m}")
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
            issues.append(f"跨板块数字冲突：{k} 出现 {sorted(vals)} 多版本")
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
    """给一份生成结果打分（0-100，5 维度），≥80 放行导出，<80 打回。

    维度：内容完整性 30 + 结构规范性 25 + 数据真实性 25 + 格式合规 10 + 逻辑一致性 10。
    一票否决项（第一百二十三轮）：任一命中直接 0 分打回。
    """
    dims = {"内容完整性": 30, "结构规范性": 25, "数据真实性": 25,
            "格式合规": 10, "逻辑一致性": 10}
    reasons = []
    proposal = result.get("proposal") or ""
    n = _cjk(proposal)

    # ---- 一票否决（任一命中直接 0 分） ----
    veto = []
    if not proposal.strip():
        veto.append("导出内容为空")
    elif proposal.count("?") > max(3, len(proposal) * 0.3) or "？？" in proposal:
        veto.append("中文乱码（? 占比过高）")
    if re.search(r'【[^】]*】|待你填写|待补充|TBD|TODO', proposal):
        veto.append("存在【】占位符/待补提示")
    if re.search(r'据《.{0,30}202\d.{0,20}》', proposal):
        veto.append("无来源的机构+年份数据（编造嫌疑）")
    if re.search(r'[\u4e00-\u9fa5]{2,4}大学(?!生|城)', proposal) or \
       re.search(r'(指导老师|指导教师|导师|负责人|队长)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}', proposal):
        veto.append("双盲信息泄露（院校/导师/姓名）")
    if veto:
        return 0, dims, ["一票否决：" + v for v in veto]

    # 内容完整性
    if mode == "deep" and n < 6000:
        dims["内容完整性"] -= 10; reasons.append(f"正文 {n} 字 < 6000")
    if not (result.get("rich_charts") or result.get("rich_tables")):
        dims["内容完整性"] -= 8; reasons.append("缺图表/表格")
    if mode == "deep" and not result.get("rich_deck"):
        dims["内容完整性"] -= 7; reasons.append("缺路演PPT")
    _miss = (result.get("completeness") or {}).get("missing") or []
    if _miss:
        dims["内容完整性"] -= 5; reasons.append("缺章节：" + "、".join(_miss[:3]))
    # 防凑数（145/146 轮）：空话段落占比 >30% 判定凑数，两档同样扣分打回
    _dok, _diss = check_depth(proposal)
    if not _dok:
        dims["内容完整性"] -= 20
        reasons.extend(_diss)

    # 结构规范性：Markdown 标题层级（>3 视为规范）
    _heads = [l for l in proposal.split("\n") if l.strip().startswith("#")]
    if len(_heads) < 4:
        dims["结构规范性"] -= 8; reasons.append(f"标题层级过少（{len(_heads)}）")

    # 数据真实性：套话 / 编造来源 / 占位 / 双盲泄露
    for c in _CLICHE:
        if c in proposal:
            dims["数据真实性"] -= 3; reasons.append(f"套话：{c}")
            break
    if re.search(r'据《.{0,30}202\d.{0,20}》', proposal):
        dims["数据真实性"] -= 6; reasons.append("疑似编造「机构+年份」引用")
    if re.search(r'【|待你填写|待补充|TBD|TODO', proposal):
        dims["数据真实性"] -= 5; reasons.append("存在占位符")
    if re.search(r'[\u4e00-\u9fa5]{2,4}大学(?!生|城)', proposal):
        dims["数据真实性"] -= 4; reasons.append("疑似泄露院校名（双盲）")

    # 格式合规：占位（无体积信息，这里用相似度近似）
    _sim = result.get("similarity")
    if isinstance(_sim, (int, float)) and _sim > 25:
        dims["格式合规"] -= 4; reasons.append(f"查重偏高（{_sim}%）")

    # 逻辑一致性：复读检测（连续重复句）
    _lines = [l.strip() for l in proposal.split("\n") if len(l.strip()) > 20]
    if len(_lines) > len(set(_lines)) * 1.3:
        dims["逻辑一致性"] -= 4; reasons.append("疑似复读")

    score = max(0, sum(dims.values()))
    return score, dims, reasons
