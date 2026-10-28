#!/usr/bin/env python3
"""分层自动质检：把错误经验规则程序化。

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
    # 第二百三十轮补：篇幅分层——简洁版非核心板块（竞品/商业/风险/技术）应摘要级，
    # 超出上限即判定「篇幅与优先级倒挂」，打回精简。
    if mode == "fast":
        _noncore = ("competitor_analysis", "business_model", "risk_analysis", "tech_solution")
        for _k in _noncore:
            _v = len(re.sub(r'\s', '', result.get(_k) or ""))
            if _v > 800:
                issues.append(f"简洁版非核心板块篇幅过长：{_k}（{_v} 字 > 800 摘要级上限）")
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


def check_pdf(path, max_pages=20, max_bytes=50 * 1024 * 1024):
    """PDF 终检：页数/体积/中文乱码。

    max_pages / max_bytes 默认按 iCAN 官方口径（应用方案 PDF ≤20 页 / ≤50MB）；
    调用方（export_pdf）可按赛事 word_requirement 传入更精确的上限。
    """
    issues = []
    try:
        import os as _os
        sz = _os.path.getsize(path)
        if sz > max_bytes:
            issues.append(
                f"PDF 体积超限（{sz // 1024}KB > {max_bytes // 1024 // 1024}MB），"
                f"建议压缩图片或删减图表后重试")
        from pypdf import PdfReader
        r = PdfReader(path)
        n = len(r.pages)
        if n < 1:
            issues.append("PDF 无页面")
        elif n > max_pages:
            issues.append(
                f"PDF 页数超限（{n} 页 > {max_pages} 页），"
                f"建议删减次要章节或压缩图表/表格后重试")
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
    return (not issues), issues


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
    if re.search(r'(指导老师|指导教师|导师)\s*[:：]?\s*(?!负责|统筹|整体|管理|协调|组织|设计|开发|运营|推广|主持|参与|带领|姓名|由团队|待填)[\u4e00-\u9fa5]{2,4}', text or ""):
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
    """给一份生成结果打分（0-100，5 维度）。

    放行阈值在调用方 `_export_review_gate` 按档位判定：深度版 ≥85、简洁版 ≥80。
    这里只算分，不做放行判断。

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
       re.search(r'(指导老师|指导教师|导师|负责人|队长)\s*[:：]?\s*(?!负责|统筹|整体|管理|协调|组织|设计|开发|运营|推广|主持|参与|带领|姓名|由团队|待填)[\u4e00-\u9fa5]{2,4}', proposal):
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


# ============ 367 评委预审报告（10 项扣分点，纯规则启发式） ============
def preview_report(proposal="", mode="deep", title=""):
    """评委视角预审：10 项常见扣分点，每项 pass/doubt/missing + 一句判据。

    纯规则启发式、不调 LLM、不查库；供 /api/judge_preview 直接复用。
    返回 dict：{total, pass, items:[{key,label,status,note}], summary}
    """
    txt = proposal or ""
    body = re.sub(r'[#*`>\[\]()（）\s]', '', txt)
    items = []

    def _verdict(ok, missing):
        if ok:
            return "pass"
        return "missing" if missing else "doubt"

    # 1 项目名一眼看懂
    name = (title or "").strip()
    name_ok = 2 <= len(name) <= 20 and not re.search(r'[A-Za-z]{6,}', name)
    items.append({
        "key": "project_name", "label": "项目名一眼看懂",
        "status": _verdict(name_ok, not name),
        "note": "项目名 2~20 字且无长英文串" if name_ok else ("未提供项目名" if not name else "项目名偏长或含长英文，建议口语化"),
    })

    # 2 痛点量化（背景段有数字/百分比）
    pain_ok = bool(re.search(r'(\d+(\.\d+)?[%％]|\d+\s*(人|元|万|亿|次|小时|分钟|天|件|家))', txt))
    items.append({
        "key": "pain_quantified", "label": "痛点量化",
        "status": _verdict(pain_ok, False),
        "note": "背景/痛点含量化数字" if pain_ok else "痛点缺少数字支撑，建议补充规模/占比/频次",
    })

    # 3 实测数据
    measured = re.findall(r'(实测|测试|实验|仿真|试点|验证)[^。；\n]{0,30}?\d', txt)
    measured_ok = len(measured) > 0
    items.append({
        "key": "measured_data", "label": "实测数据",
        "status": _verdict(measured_ok, False),
        "note": f"命中 {len(measured)} 处实测/验证数据" if measured_ok else "未见实测/验证数据，建议补充真实测试或试点结果",
    })

    # 4 竞品对比
    comp_ok = bool(re.search(r'(竞品|对比|现有方案|传统|市面|同类|优于|相比|行业)', txt))
    items.append({
        "key": "competitor", "label": "竞品对比",
        "status": _verdict(comp_ok, False),
        "note": "含竞品/现有方案对比" if comp_ok else "缺少竞品对比，建议列出同类方案并说明差异",
    })

    # 5 版权与AI披露
    disc_ok = bool(re.search(r'(版权|授权|许可|开源|AI|人工智能|算法|大模型|生成式|数据来源)', txt))
    items.append({
        "key": "disclosure", "label": "版权与AI披露",
        "status": _verdict(disc_ok, False),
        "note": "含版权/技术来源披露" if disc_ok else "建议说明数据来源、版权授权与是否使用AI生成",
    })

    # 6 团队真实
    team_ok = bool(re.search(r'(团队|成员|分工|负责人|指导老师|队长)', txt))
    fict = any(k in txt for k in ('李然', '张明', '小李', '王雨桐', '王明', '刘洋'))
    items.append({
        "key": "team", "label": "团队真实",
        "status": "doubt" if fict else _verdict(team_ok, not team_ok),
        "note": "疑似虚构人名，需替换" if fict else ("含团队/分工说明" if team_ok else "缺少团队信息，建议补充真实成员与分工"),
    })

    # 7 财务可信
    fin_ok = bool(re.search(r'(成本|营收|收入|利润|预算|融资|单价|售价|ROI|毛利)[^\n]{0,30}?\d', txt))
    items.append({
        "key": "finance", "label": "财务可信",
        "status": _verdict(fin_ok, False),
        "note": "财务/成本有数字支撑" if fin_ok else "财务数据缺失或无数值，建议补充成本/营收估算",
    })

    # 8 字数达标
    n = len(body)
    minc, maxc = (6000, 20000) if mode == "deep" else (800, 3000)
    wc_ok = minc <= n <= maxc
    items.append({
        "key": "word_count", "label": "字数达标",
        "status": _verdict(wc_ok, False),
        "note": f"{n} 字（{mode} 档 {minc}~{maxc}）" if wc_ok else f"{n} 字，偏离 {mode} 档 {minc}~{maxc} 区间",
    })

    # 9 格式规范
    h2 = len(re.findall(r'^#{1,3}\s+\S', txt, re.M))
    placeholder = re.search(r'(待填写|待补充|TBD|TODO)', txt)
    fmt_ok = h2 >= 3 and not placeholder
    items.append({
        "key": "format", "label": "格式规范",
        "status": _verdict(fmt_ok, False),
        "note": f"{h2} 个标题，无占位符" if fmt_ok else ("存在占位符（待填写/TODO）" if placeholder else f"章节标题不足 3 个（{h2}）"),
    })

    # 10 查重过关（基础自检：10 字以上中文串重复率）
    dup_ratio = 0.0
    runs = re.findall(r'[\u4e00-\u9fa5]{10,}', txt)
    if runs:
        from collections import Counter
        c = Counter(runs)
        dup_ratio = sum(v - 1 for v in c.values() if v > 1) / max(len(runs), 1)
    plag_ok = dup_ratio < 0.08
    items.append({
        "key": "plagiarism", "label": "查重过关",
        "status": _verdict(plag_ok, False),
        "note": f"自检重复率 {dup_ratio:.0%}" if plag_ok else f"自检重复率 {dup_ratio:.0%} 偏高，建议改写重复段",
    })

    passed = sum(1 for it in items if it["status"] == "pass")
    return {
        "total": 10,
        "pass": passed,
        "items": items,
        "summary": f"10 项中 {passed} 项通过，{10 - passed} 项需关注",
    }
