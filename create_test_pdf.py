"""生成测试用的 iCAN 大赛规则 PDF"""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 注册中文字体
pdfmetrics.registerFont(TTFont('SimSun', 'C:\\Windows\\Fonts\\simsun.ttc'))

c = canvas.Canvas("iCAN大赛规则_测试.pdf", pagesize=A4)
width, height = A4

# 标题
c.setFont("SimSun", 18)
c.drawCentredString(width/2, height - 50, "iCAN 大学生创新创业大赛")
c.setFont("SimSun", 14)
c.drawCentredString(width/2, height - 80, "赛事规则与评分标准")

# 正文
c.setFont("SimSun", 12)
y = height - 120

content = [
    "一、赛事介绍",
    "",
    "iCAN 大学生创新创业大赛是面向全国大学生的国家级创新创业赛事，旨在培养大学生的创新精神、创业意识和创新创业能力。",
    "",
    "二、参赛要求",
    "",
    "1. 全日制在校本科生、研究生均可报名",
    "2. 每队 3-5 人，指导教师 1-2 名",
    "3. 项目需具有创新性、实用性和可操作性",
    "",
    "三、评分标准（总分 100 分）",
    "",
    "1. 创新性（30 分）",
    "   - 项目创意是否新颖，是否有独特的技术或模式",
    "   - 是否解决了真实存在的问题",
    "   - 是否具有差异化竞争优势",
    "",
    "2. 实用性（25 分）",
    "   - 项目是否有明确的应用场景",
    "   - 是否具备落地可行性",
    "   - 是否有市场需求",
    "",
    "3. 技术难度（20 分）",
    "   - 技术方案是否合理",
    "   - 是否有技术壁垒",
    "   - 团队是否具备实现能力",
    "",
    "4. 团队展示（15 分）",
    "   - 团队分工是否明确",
    "   - 路演表达是否清晰",
    "   - 答辩表现是否专业",
    "",
    "5. 社会价值（10 分）",
    "   - 项目是否具有社会意义",
    "   - 是否符合国家战略方向",
    "   - 是否有可持续发展潜力",
    "",
    "四、申报书要求",
    "",
    "申报书需包含以下内容：",
    "1. 项目背景与痛点分析",
    "2. 解决方案与创新点",
    "3. 技术路线与实现方案",
    "4. 应用前景与市场分析",
    "5. 团队介绍与分工",
    "",
    "五、提交要求",
    "",
    "1. 申报书字数 3000-5000 字",
    "2. 格式：PDF 格式，A4 纸",
    "3. 截止时间：每年 6 月",
    "",
    "六、奖项设置",
    "",
    "一等奖：10%",
    "二等奖：20%",
    "三等奖：30%",
    "优秀奖：若干",
]

for line in content:
    if line == "":
        y -= 10
    else:
        c.drawString(60, y, line)
        y -= 20
    if y < 60:
        c.showPage()
        c.setFont("SimSun", 12)
        y = height - 50

c.save()
print("✅ 已生成：iCAN大赛规则_测试.pdf")
