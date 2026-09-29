# -*- coding: utf-8 -*-
"""生成 科创赛事助手 路演PPT（标杆版/8页）。
设计系统：16:9、深海军蓝#0F1535 / 高亮#818CF8 / 正文#1A1A2E / 背景#F8F8F6 / 数据#F59E0B。
数据来源：平台数据库 competition.db（实测，56项目）；产品截图来自真实前端 index.html。
"""
import os, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

BASE = r"C:/Users/34984/Doubao/chats/2026-09-29/new-chat/competition-agent"
SHOT = r"C:/Users/34984/.workbuddy/tmp/kcwx_shots/desktop_clean.png"
TMP  = r"C:/Users/34984/.workbuddy/tmp"
OUT  = os.path.join(BASE, "14_路演PPT.pptx")

NAVY  = RGBColor(0x0F,0x15,0x35)
ACCENT= RGBColor(0x81,0x8C,0xF8)
TEAL  = RGBColor(0x22,0xB8,0xCF)
INK   = RGBColor(0x1A,0x1A,0x2E)
BG    = RGBColor(0xF8,0xF8,0xF6)
DATA  = RGBColor(0xF5,0x9E,0x0B)
WHITE = RGBColor(0xFF,0xFF,0xFF)
GRAY  = RGBColor(0x6B,0x72,0x80)
CARD  = RGBColor(0xFF,0xFF,0xFF)
LINE  = RGBColor(0xE3,0xE6,0xEF)

CN = "Microsoft YaHei"
NUM = "Arial"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]

def set_run_font(run, size, color, bold=False, cn=CN, num=NUM):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = num
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', cn)
    cs = rPr.find(qn('a:cs'))
    if cs is None:
        cs = rPr.makeelement(qn('a:cs'), {})
        rPr.append(cs)
    cs.set('typeface', cn)

def slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0,0,SW,SH)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG; bg.line.fill.background()
    bg.shadow.inherit = False
    return s

def rect(s,x,y,w,h,fill=None,line=None,line_w=1.0):
    sp = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x,y,w,h)
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    return sp

def text(s,x,y,w,h,lines,align=PP_ALIGN.LEFT,anchor=MSO_ANCHOR.TOP,wrap=True):
    """lines: list of dict(text,size,color,bold,cn,align) or str"""
    tb = s.shapes.add_textbox(x,y,w,h); tf = tb.text_frame
    tf.word_wrap = wrap; tf.vertical_anchor = anchor
    tf.margin_left=Pt(2); tf.margin_right=Pt(2); tf.margin_top=Pt(1); tf.margin_bottom=Pt(1)
    first=True
    for ln in lines:
        if isinstance(ln,str):
            ln={"text":ln,"size":18,"color":INK,"bold":False}
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first=False
        p.alignment = ln.get("align",align)
        if "space_before" in ln: p.space_before = Pt(ln["space_before"])
        if "space_after" in ln: p.space_after = Pt(ln["space_after"])
        else: p.space_after = Pt(2)
        if "line" in ln: p.line_spacing = ln["line"]
        r = p.add_run(); r.text = ln["text"]
        set_run_font(r, ln.get("size",18), ln.get("color",INK), ln.get("bold",False),
                     ln.get("cn",CN), ln.get("num",NUM))
    return tb

def header(s, kicker, title, dark=False):
    text(s, Inches(0.55), Inches(0.42), Inches(11), Inches(0.4),
         [{"text":kicker,"size":14,"color":ACCENT,"bold":True}])
    text(s, Inches(0.55), Inches(0.82), Inches(12.2), Inches(0.9),
         [{"text":title,"size":30,"color":(WHITE if dark else INK),"bold":True}])

# ---------- charts ----------
def bar_dist():
    fig, ax = plt.subplots(figsize=(6.6,3.4), dpi=200)
    labels = ["iCAN","挑战杯","互联网+","国创"]
    vals = [37,13,3,1]
    colors = ["#0F1535","#818CF8","#22B8CF","#F59E0B"]
    bars = ax.barh(labels[::-1], vals[::-1], color=colors[::-1])
    for b,v in zip(bars, vals[::-1]):
        ax.text(b.get_width()+0.6, b.get_y()+b.get_height()/2, str(v),
                va="center", fontsize=13, color="#1A1A2E", fontweight="bold")
    ax.set_xlim(0,42)
    ax.set_title("iCAN 赛道占生成项目 66%", fontsize=15, color="#0F1535", fontweight="bold", loc="left")
    ax.spines[["top","right","bottom","left"]].set_visible(False)
    ax.tick_params(labelsize=13, length=0)
    ax.set_xticks([])
    fig.tight_layout()
    p = os.path.join(TMP,"bench_dist.png"); fig.savefig(p, bbox_inches="tight", facecolor="white"); plt.close(fig)
    return p

# ---------- build ----------
s1 = slide(); s1.shapes[0].fill.fore_color.rgb = NAVY
rect(s1, Inches(0.7), Inches(0.7), Inches(0.18), Inches(0.5), fill=ACCENT)
text(s1, Inches(0.95), Inches(0.66), Inches(10), Inches(0.5),
     [{"text":"科创赛事助手 · 多智能体协同创作系统","size":16,"color":RGBColor(0xC7,0xCC,0xE8),"bold":True}])
text(s1, Inches(0.7), Inches(2.35), Inches(11.9), Inches(1.5),
     [{"text":"科创赛事助手","size":58,"color":WHITE,"bold":True}])
text(s1, Inches(0.72), Inches(3.75), Inches(11.6), Inches(1.2),
     [{"text":"面向大学生科创竞赛的端到端 AI 创作助手：","size":20,"color":RGBColor(0xC7,0xCC,0xE8)},
      {"text":"规则解析 → 申报书 → 路演 PPT → 答辩，一站生成","size":20,"color":WHITE,"bold":True}])
chip = rect(s1, Inches(0.72), Inches(5.25), Inches(6.6), Inches(0.7), fill=ACCENT)
text(s1, Inches(0.9), Inches(5.33), Inches(6.3), Inches(0.55),
     [{"text":"已生成 56 个参赛项目 · 覆盖 4 大赛事","size":17,"color":NAVY,"bold":True}], anchor=MSO_ANCHOR.MIDDLE)
text(s1, Inches(0.72), Inches(6.5), Inches(8), Inches(0.4),
     [{"text":"kcwx.online","size":15,"color":RGBColor(0x8A,0x90,0xB8)}])

# slide2 痛点
s2 = slide()
header(s2, "01 / 痛点", "备赛最难的不是创意，是把创意讲成评委认的标书")
cards = [
    ("10–30 页","一份申报书动辄十余页，逐字打磨耗数周","行业共识"),
    ("27 / 56","生成项目中仅 27 个为不同创意 → 同质化检测是刚需","平台数据库·实测"),
    ("5 大维度","评委按 创新/可行/价值/团队/落地 综合打分，标准难摸透","赛事评审口径"),
]
x = Inches(0.55)
for big, desc, src in cards:
    card = rect(s2, x, Inches(2.0), Inches(3.95), Inches(4.2), fill=CARD, line=LINE, line_w=1.25)
    text(s2, x+Inches(0.25), Inches(2.4), Inches(3.5), Inches(1.2),
         [{"text":big,"size":40,"color":DATA,"bold":True,"num":NUM}])
    text(s2, x+Inches(0.25), Inches(3.7), Inches(3.5), Inches(1.8),
         [{"text":desc,"size":17,"color":INK,"line":1.15}])
    text(s2, x+Inches(0.25), Inches(5.7), Inches(3.5), Inches(0.4),
         [{"text":"来源："+src,"size":12,"color":GRAY}])
    x = x + Inches(4.15)
text(s2, Inches(0.55), Inches(6.5), Inches(12), Inches(0.5),
     [{"text":"痛点不是「不会做」，而是「不知道评委要什么、怎么讲才不像别人」","size":15,"color":GRAY}])

# slide3 解决方案/产品
s3 = slide()
header(s3, "02 / 解决方案", "六合一创作流水线：30 秒出精简版，1–2 分钟出深度版")
feats = ["赛事规则自动解析","创意同质化检测","智能申报书生成 / 优化","申报书诊断分析","模拟评委评审打分","一键导出所有结果"]
fx = Inches(0.55); fy = Inches(2.05)
for i,f in enumerate(feats):
    col = i%3; row = i//3
    cx = Inches(0.55) + Emu(int(Inches(4.15)*col))
    cy = Inches(2.05) + Emu(int(Inches(1.15)*row))
    rect(s3, cx, cy, Inches(3.9), Inches(0.95), fill=NAVY)
    text(s3, cx+Inches(0.2), cy, Inches(3.6), Inches(0.95),
         [{"text":f,"size":16,"color":WHITE,"bold":True}], anchor=MSO_ANCHOR.MIDDLE)
# product shot
if os.path.exists(SHOT):
    pic = s3.shapes.add_picture(SHOT, Inches(7.0), Inches(2.0), height=Inches(3.5))
    rect(s3, Inches(7.0), Inches(2.0), Inches(0.12), Inches(3.5), fill=ACCENT)
    text(s3, Inches(7.0), Inches(5.7), Inches(5.8), Inches(1.2),
         [{"text":"真实产品界面：输入创意即出规则解析 / 同质化检测 / 申报书","size":14,"color":INK,"line":1.2},
          {"text":"简洁版 30 秒 · 深度版 1–2 分钟","size":14,"color":DATA,"bold":True}])
else:
    text(s3, Inches(7.0), Inches(2.0), Inches(5.8), Inches(3),
         [{"text":"[产品截图：真实前端 index.html]","size":16,"color":GRAY}])

# slide4 数据
s4 = slide()
header(s4, "03 / 真实数据", "已经跑通：56 个参赛项目，全部成功生成")
dist = bar_dist()
if os.path.exists(dist):
    s4.shapes.add_picture(dist, Inches(0.55), Inches(2.1), width=Inches(6.4))
metrics = [("56","已生成项目（实测）"),("4","覆盖大赛（iCAN/挑战杯/互联网+/国创）"),("27","不同创意（其余为同质化检测命中）")]
mx = Inches(7.2)
for big, desc in metrics:
    card = rect(s4, mx, Inches(2.1), Inches(5.6), Inches(1.35), fill=CARD, line=LINE, line_w=1.25)
    text(s4, mx+Inches(0.25), Inches(2.2), Inches(2.2), Inches(1.15),
         [{"text":big,"size":44,"color":NAVY,"bold":True,"num":NUM}], anchor=MSO_ANCHOR.MIDDLE)
    text(s4, mx+Inches(2.5), Inches(2.2), Inches(3.0), Inches(1.15),
         [{"text":desc,"size":15,"color":INK,"line":1.1}], anchor=MSO_ANCHOR.MIDDLE)
    mx = mx + Inches(0)  # stacked vertically
    # recompute next y
    mx = Inches(7.2)
    # actually move down:
    break
# redo metrics vertically properly:
for i,(big,desc) in enumerate(metrics):
    cy = Inches(2.1) + Emu(int(Inches(1.5)*i))
    card = rect(s4, Inches(7.2), cy, Inches(5.6), Inches(1.3), fill=CARD, line=LINE, line_w=1.25)
    text(s4, Inches(7.45), cy, Inches(2.2), Inches(1.3),
         [{"text":big,"size":42,"color":NAVY,"bold":True,"num":NUM}], anchor=MSO_ANCHOR.MIDDLE)
    text(s4, Inches(9.7), cy, Inches(3.0), Inches(1.3),
         [{"text":desc,"size":15,"color":INK,"line":1.1}], anchor=MSO_ANCHOR.MIDDLE)
text(s4, Inches(0.55), Inches(6.7), Inches(12), Inches(0.4),
     [{"text":"数据来源：平台数据库 competition.db（实测，全部 status=success）","size":12,"color":GRAY}])

# slide5 竞争壁垒 2x2
s5 = slide()
header(s5, "04 / 竞争壁垒", "不是通用 AI，也不是代写机构，而是赛事专用多智能体")
# matrix area
mx0, my0 = Inches(1.0), Inches(2.2)
ms = Inches(7.0)  # square
# quadrant backgrounds
rect(s5, mx0, my0, ms, ms, fill=RGBColor(0xF1,0xF2,0xF8), line=LINE, line_w=1.5)
half = Emu(int(ms/2))
# 我们 quadrant highlight (top-right)
rect(s5, mx0+half, my0, half, half, fill=RGBColor(0xE7,0xEA,0xFD))
# axis labels
text(s5, mx0, my0+ms+Inches(0.05), ms, Inches(0.4),
     [{"text":"赛事专业契合度 →","size":13,"color":GRAY,"bold":True}], align=PP_ALIGN.CENTER)
text(s5, mx0-Inches(0.95), my0+half-Inches(0.2), Inches(0.9), Inches(0.5),
     [{"text":"自动化 ↓","size":13,"color":GRAY,"bold":True}], anchor=MSO_ANCHOR.MIDDLE)
# quadrant labels
text(s5, mx0+Inches(0.2), my0+Inches(0.2), half, Inches(0.9),
     [{"text":"纯手写 / 模板","size":14,"color":GRAY}])
text(s5, mx0+Inches(0.2), my0+half+Inches(0.2), half, Inches(0.9),
     [{"text":"商业辅导机构","size":14,"color":GRAY}])
text(s5, mx0+half+Inches(0.2), my0+Inches(0.2), half, Inches(0.9),
     [{"text":"通用 AI 对话","size":14,"color":GRAY}])
# our badge
badge = rect(s5, mx0+half+Inches(0.7), my0+half-Inches(0.55), Inches(1.9), Inches(0.85), fill=ACCENT)
text(s5, mx0+half+Inches(0.78), my0+half-Inches(0.55), Inches(1.8), Inches(0.85),
     [{"text":"科创赛事助手","size":15,"color":NAVY,"bold":True}], anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
# right side explanation
text(s5, Inches(8.4), Inches(2.2), Inches(4.5), Inches(4.5),
     [{"text":"我们落在「高契合 × 高自动」象限","size":18,"color":NAVY,"bold":True,"space_after":10},
      {"text":"• 通用 AI：不懂赛事规则，产出泛泛","size":15,"color":INK,"line":1.2},
      {"text":"• 代写机构：专业但慢、贵、不可规模化","size":15,"color":INK,"line":1.2},
      {"text":"• 手写模板：无智能、易同质化","size":15,"color":INK,"line":1.2},
      {"text":"• 我们：规则库+多智能体，30 秒出专业稿","size":15,"color":DATA,"bold":True,"line":1.2}])

# slide6 商业模式
s6 = slide()
header(s6, "05 / 商业模式", "免费创作 + 增值服务，按院校 / 赛事机构规模化")
tiers = [
    ("免费层 · 学生 C 端","规则解析 / 申报书生成 / 诊断 / 一键导出；API 免费额度兜底边际成本","当前已上线"),
    ("增值层","深度版、批量生成、定制赛事模板、专属图表样式","规划路径"),
    ("机构层 · 院校 / 赛事","私有部署、赛事规则库共建、批量账号与培训","规划路径"),
]
x = Inches(0.55)
for t,d,tag in tiers:
    rect(s6, x, Inches(2.1), Inches(3.95), Inches(4.0), fill=CARD, line=LINE, line_w=1.25)
    rect(s6, x, Inches(2.1), Inches(3.95), Inches(0.7), fill=NAVY)
    text(s6, x+Inches(0.2), Inches(2.1), Inches(3.6), Inches(0.7),
         [{"text":t,"size":15,"color":WHITE,"bold":True}], anchor=MSO_ANCHOR.MIDDLE)
    text(s6, x+Inches(0.25), Inches(3.1), Inches(3.5), Inches(2.4),
         [{"text":d,"size":15,"color":INK,"line":1.2}])
    text(s6, x+Inches(0.25), Inches(5.5), Inches(3.5), Inches(0.4),
         [{"text":"状态："+tag,"size":13,"color":DATA,"bold":True}])
    x = x + Inches(4.15)
text(s6, Inches(0.55), Inches(6.5), Inches(12), Inches(0.5),
     [{"text":"成本主要是 LLM 调用，按调用计费；免费额度控制边际成本，不靠卖材料盈利","size":15,"color":GRAY}])

# slide7 团队/里程碑
s7 = slide()
header(s7, "06 / 团队与进展", "全栈 + AI 技术团队，已上线持续服务")
steps = [("2026-09","上线 kcwx.online"),("接入 DeepSeek 多智能体","规则→申报书→路演→答辩"),("已服务 56 项目","覆盖 4 大赛事"),("下一步","扩赛事覆盖 + 导出样式")]
tx = Inches(0.55)
for i,(k,v) in enumerate(steps):
    col = i%4
    cx = Inches(0.55) + Emu(int(Inches(3.05)*col))
    rect(s7, cx, Inches(2.1), Inches(2.85), Inches(1.2), fill=NAVY if i%2==0 else ACCENT)
    text(s7, cx+Inches(0.15), Inches(2.15), Inches(2.6), Inches(1.1),
         [{"text":k,"size":15,"color":WHITE,"bold":True},
          {"text":v,"size":13,"color":RGBColor(0xEE,0xF0,0xFA),"line":1.1}], anchor=MSO_ANCHOR.MIDDLE)
text(s7, Inches(0.55), Inches(3.8), Inches(12), Inches(2.6),
     [{"text":"团队角色（盲审以角色指代）","size":17,"color":NAVY,"bold":True,"space_after":8},
      {"text":"• 技术负责人：全栈 + AI，主导多智能体编排与产品落地","size":16,"color":INK,"line":1.2},
      {"text":"• 算法：LangGraph 工作流、规则解析与同质化检测","size":16,"color":INK,"line":1.2},
      {"text":"• 产品 / 赛事：维护 iCAN / 挑战杯 / 互联网+ / 国创 规则库","size":16,"color":INK,"line":1.2},
      {"text":"• 质量：导出件合规闸门（页数 / 数据可溯源 / 无水印）","size":16,"color":INK,"line":1.2}])

# slide8 愿景/结尾
s8 = slide(); s8.shapes[0].fill.fore_color.rgb = NAVY
text(s8, Inches(0.7), Inches(0.7), Inches(11), Inches(0.4),
     [{"text":"07 / 愿景","size":14,"color":ACCENT,"bold":True}])
text(s8, Inches(0.7), Inches(1.2), Inches(12), Inches(1.6),
     [{"text":"让科创备赛，从数月的苦熬","size":34,"color":WHITE,"bold":True},
      {"text":"变成几分钟的智能创作","size":34,"color":DATA,"bold":True}])
vals = [("专业","赛事规则库支撑，不像通用 AI 泛泛"),("真实","数据可溯源、不编造、不虚构人物"),("高效","30 秒出精简版，1–2 分钟出深度版")]
x = Inches(0.7)
for t,d in vals:
    rect(s8, x, Inches(3.5), Inches(3.85), Inches(1.9), fill=RGBColor(0x1A,0x22,0x4A))
    text(s8, x+Inches(0.25), Inches(3.65), Inches(3.4), Inches(1.7),
         [{"text":t,"size":22,"color":ACCENT,"bold":True},
          {"text":d,"size":14,"color":RGBColor(0xD7,0xDB,0xEE),"line":1.15}])
    x = x + Inches(4.05)
rect(s8, Inches(0.7), Inches(5.8), Inches(7.2), Inches(0.85), fill=DATA)
text(s8, Inches(0.9), Inches(5.8), Inches(6.8), Inches(0.85),
     [{"text":"现在就去 kcwx.online 体验 →","size":20,"color":NAVY,"bold":True}], anchor=MSO_ANCHOR.MIDDLE)
text(s8, Inches(0.7), Inches(6.85), Inches(11), Inches(0.4),
     [{"text":"欢迎院校 / 赛事机构合作，共建赛事规则库","size":14,"color":RGBColor(0x8A,0x90,0xB8)}])

prs.save(OUT)
print("SAVED", OUT, "slides:", len(prs.slides._sldIdLst))
