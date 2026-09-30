# -*- coding: utf-8 -*-
"""生成《科创赛事助手》作品说明书（竞赛提交版）。
只用已核实的真实项目事实；未核实数据标注『测算/待补』或删除。
"""
import os
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

REPO = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(REPO, "作品说明书_提交版.docx")
HERO = os.path.join(REPO, "交付视频", "hero_clean.png")

SITE = "https://kechuang2026.cn"


def set_cell_font(cell, text, bold=False, size=10.5, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.name = "微软雅黑"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if color:
        r.font.color.rgb = color


def set_run_font(run, size=11, bold=False, color=None):
    run.font.size = Pt(size)
    run.bold = bold
    run.font.name = "微软雅黑"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if color:
        run.font.color.rgb = color


doc = Document()
style = doc.styles["Normal"]
style.font.name = "微软雅黑"
style.font.size = Pt(11)
style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

NAVY = RGBColor(0x0F, 0x15, 0x35)
BLUE = RGBColor(0x81, 0x8C, 0xF8)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
GREY = RGBColor(0x55, 0x55, 0x55)


def h1(t):
    p = doc.add_heading(level=1)
    r = p.add_run(t)
    set_run_font(r, 16, True, NAVY)
    return p


def h2(t):
    p = doc.add_heading(level=2)
    r = p.add_run(t)
    set_run_font(r, 13, True, BLUE)
    return p


def para(t, bold=False, color=None, size=11, align=None):
    p = doc.add_paragraph()
    r = p.add_run(t)
    set_run_font(r, size, bold, color)
    if align:
        p.alignment = align
    return p


def bullet(t, lvl=0):
    p = doc.add_paragraph(style="List Bullet")
    if lvl:
        p.paragraph_format.left_indent = Inches(0.5 * (lvl + 1))
    r = p.add_run(t)
    set_run_font(r, 11)
    return p


def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        set_cell_font(hdr_cells[i], h, bold=True, size=10.5)
        if col_widths:
            hdr_cells[i].width = Inches(col_widths[i])
    for row in rows:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            set_cell_font(cells[i], v, size=10)
            if col_widths:
                cells[i].width = Inches(col_widths[i])
    doc.add_paragraph()
    return table


# ---------- 封面 ----------
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
rt = title.add_run("科创赛事助手")
set_run_font(rt, 30, True, NAVY)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
rs = sub.add_run("作品说明书")
set_run_font(rs, 16, False, BLUE)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
rm = meta.add_run(f"面向互联网+ / 挑战杯 / iCAN / 国创等高校科创赛事的 AI 多智能体协同创作平台\n项目主页：{SITE}")
set_run_font(rm, 11, False, GREY)

doc.add_paragraph()

# ---------- 1 作品概述 ----------
h1("一、作品概述")
para("科创赛事助手是一套面向高校科创赛事的 AI 多智能体协同创作平台。"
     "它将『赛事规则解析 → 同质化检测 → 多维度深度分析 → 申报书/路演PPT/答辩稿撰写 → "
     "评委视角复审 → 一键导出』整条创作链路自动化，帮助学生把材料准备时间从数天压缩到分钟级，"
     "同时让产出对齐评审口径、可溯源、避免同质化。")
para("一句话定位：让学生『写得快、写得对、写得像获奖作品』的赛事材料智能工厂。", bold=True, color=AMBER)
if os.path.exists(HERO):
    para("平台主界面：", size=10)
    doc.add_picture(HERO, width=Inches(5.5))

# ---------- 2 背景与痛点 ----------
h1("二、项目背景与痛点")
bullet("参赛门槛高：申报书、路演PPT、答辩稿各有评分维度，学生常出现『写了很多但没踩中评分点』的问题。")
bullet("资料分散：赛事规则、往届获奖范式、竞品方案散落在不同渠道，缺乏结构化沉淀。")
bullet("同质化风险：同一赛道项目扎堆，学生缺乏差异化策略与撞车预警手段。")
bullet("缺评委视角：自评良好，但评委关注的科学性、先进性、现实意义等权重常被忽略。")
bullet("导出低效：材料最终要落到 Word / PDF / PPT，手工排版与图表制作占用大量时间。")

# ---------- 3 技术方案 ----------
h1("三、技术方案与架构")
para("后端采用 Flask 提供 HTTP 服务，创作主链路基于 LangGraph 编排为状态图（StateGraph），"
     "内含 20 个专职智能体节点协同工作；大模型支持 DeepSeek 等主流 API，图表由 python-pptx 与 matplotlib 真实渲染，"
     "前端为单页应用，支持生成过程的实时逐字流式输出。")

h2("3.1 核心智能体节点（20 个）")
add_table(
    ["智能体节点", "职责"],
    [
        ("rule_parser", "解析赛事规则，输出评分维度与权重，作为后续写作的『评审准星』。"),
        ("similarity_checker", "对输入创意做撞车评估，给出差异化建议。"),
        ("idea_evaluator", "多维度可行性打分，指出优势与待补项。"),
        ("comprehensive_analysis", "前期分析总调度，汇聚多维结论。"),
        ("deep_competitor / business / risk / tech", "竞品、商业、风险、技术四维深度分析。"),
        ("plan / social_value", "实施计划编排与社会价值论证。"),
        ("writer / targeted_revise", "申报书写作与定向修改。"),
        ("judge / expert_review", "评委打分与专家复审，输出失分点与改进优先级。"),
        ("proposal_analysis", "完整性体检与评分总览。"),
        ("defense_questions / speech", "高频答辩问题与路演讲稿生成。"),
        ("ppt_outline / rich_media", "路演PPT 结构规划与图表/富媒体生成。"),
    ],
    col_widths=[2.2, 4.3],
)

h2("3.2 技术栈")
para("Flask · LangGraph · DeepSeek / 兼容 OpenAI 接口 · python-pptx · matplotlib · "
     "流式输出（SSE）· 9 个赛事知识库 JSON（规则/范文/答辩/评委范式）· 训练库蒸馏样本 · "
     "质量自检闸门（quality_gate.py / export_guard.py）。", color=GREY)

# ---------- 4 核心功能 ----------
h1("四、核心功能")
for f in [
    "赛事规则解析与评分权重对齐：自动把科学性、先进性、现实意义等权重注入写作。",
    "同质化检测：开题即提示撞车风险与差异化落点，避免『写完才发现雷同』。",
    "双模式申报书：简洁版（分钟级）与深度版（多章节含 6 维分析）。",
    "路演PPT：python-pptx 真实渲染，含数据图表与表格。",
    "答辩稿 + 高频答辩问题：覆盖评委常见追问口径。",
    "实时逐字流式：生成过程按字数增量渲染，告别『干等再整块输出』。",
    "知识库 RAG：按模块/赛道标签检索高分范文片段注入，提升真实度。",
    "多格式导出：Word / PDF / PPT / PPTX / ZIP 一键导出，目录与格式自检。",
    "质量自检闸门：导出前跑完整性、格式、数字抽查、去 AI 味等校验。",
]:
    bullet(f)

add_table(
    ["导出格式", "说明"],
    [
        ("Word（.docx）", "申报书正文，含目录、标题层级与样式。"),
        ("PDF", "按赛制页数/大小限制导出。"),
        ("PPT（.pptx）", "路演PPT，16:9，含真实数据图表。"),
        ("ZIP", "一键打包全部导出物。"),
        ("原始格式", "按官方模板还原的专项申报书。"),
    ],
    col_widths=[2.0, 4.5],
)

# ---------- 5 创新点 ----------
h1("五、创新点")
bullet("多智能体协同 + 评委反馈回流闭环：judge → proposal_analysis → expert_review → targeted_revise，"
       "让『评委意见』真正改写下一版，而非摆设。")
bullet("标杆对标自学习系统：形成『联网检索 → 蒸馏 → 标杆对标 → 写回生成器』闭环，"
       "让导出物持续对齐网上高质量获奖作品；同时设防污染铁律与质量门禁，只学习可溯源来源。")
bullet("真实数据可溯源：强制要求数字给推算过程、敢写局限，降低 AI 味与空话。")
bullet("流式体验工程：逐字流式 + Tab 拆分 + 进度可视化，把等待过程转化为可信进度。")

# ---------- 6 数据成效 ----------
h1("六、运行数据与成效")
para("基于本地产品数据库统计：累计成功生成记录 56 条，覆盖 iCAN、挑战杯、互联网+、国创等赛事。"
     "知识库包含 9 个结构化 JSON 文件，训练库持续收录经质量门禁的获奖样例蒸馏样本。")
para("注：以上为本地统计时点数据，线上部署库可能独立维护，提交前请以最新统计为准。", color=GREY, size=9)

# ---------- 7 社会价值 ----------
h1("七、社会价值")
bullet("降低参赛门槛：把赛事材料准备时间大幅压缩，普惠更多非重点院校学生。")
bullet("沉淀赛事知识：规则、范式、范文以结构化方式沉淀，形成可复用的双创教育资产。")
bullet("纠偏同质化：用差异化策略引导学生做真问题，而非扎堆热门赛道。")

# ---------- 8 商业模式 ----------
h1("八、商业模式与落地")
bullet("基础能力免费使用，增值能力（私有化部署、院校定制知识库、批量导出）变现。")
bullet("已部署公网演示环境（nginx 反代 + 常驻进程），具备演示与小规模服务条件。")
bullet("院校双创学院采购『私有化 + 赛事知识库』为可行变现方向，具体商业数据待补充。")

# ---------- 9 竞争优势 ----------
h1("九、竞争优势")
bullet("对比通用写作工具：内置赛事评分权重与评委闭环，产出『踩中评分点』而非通用文案。")
bullet("对比单 LLM 提示词：多智能体分工 + 知识库 RAG + 质量闸门，稳定可控、不易跑题。")
bullet("对比模板网站：真实数据图表渲染 + 可溯源数据，拒绝空模板占位。")

# ---------- 10 未来规划 ----------
h1("十、未来规划")
bullet("多模态：支持上传草图/截图辅助生成。")
bullet("院校私有化与赛事知识库定制，沉淀各校往届获奖范式。")
bullet("标杆自学习系统常态化：每日自动检索、蒸馏、对标并写回，持续拉高质量上限。")

# ---------- 11 团队 ----------
h1("十一、团队与分工")
para("（请填写真实团队成员、学校/院系、联系方式与分工）", color=GREY)
add_table(
    ["姓名", "学校/院系", "分工", "联系方式"],
    [("待填写", "待填写", "待填写", "待填写")] * 3,
    col_widths=[1.2, 2.0, 2.3, 1.0],
)

# ---------- 12 参考文献/资料 ----------
h1("十二、参考文献与可溯源资料")
bullet("《互联网+大学生创新创业大赛评审规则》公开文件。")
bullet("《挑战杯》大学生课外学术科技作品竞赛章程与往届优秀作品集。")
bullet("本项目知识库：knowledge_base/*.json（规则/范文/答辩/评委范式）。")
bullet("本项目训练库：训练库/获奖样例蒸馏_v1.json、v2.json。")

doc.save(OUT)
print("SAVED:", OUT)
