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
    return (not issues), issues


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
