# -*- coding: utf-8 -*-
"""云端定向同步脚本：419质量标杆(rich_pipeline) + logo定稿 + 对比度 + admin修复 + chkRoadshow P0。幂等可重跑。"""
import io, re, sys, py_compile

ROOT = '/opt/comp-agent'
report = []

def rd(p):
    with io.open(p, encoding='utf-8') as f: return f.read()

def wr(p, s):
    with io.open(p, 'w', encoding='utf-8', newline='') as f: f.write(s)

# ---------- 1) rich_pipeline.py：419 质量标杆 ----------
SPEC = '''

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
"""

'''

p = ROOT + '/rich_pipeline.py'
s = rd(p)
if '_QUALITY_BENCHMARK_SPEC' not in s:
    anchor = 'CHART_FORMAT = """'
    assert anchor in s, 'rich_pipeline: CHART_FORMAT 锚点丢失'
    s = s.replace(anchor, SPEC + anchor, 1)
    old = '团队成员真实姓名，团队一律用「本项目团队」指代"""'
    new = '团队成员真实姓名，团队一律用「本项目团队」指代""" + _QUALITY_BENCHMARK_SPEC'
    n = s.count(old)
    assert n >= 2, f'rich_pipeline: 指代串仅{n}处(<2)，Codex 改了结构'
    s = s.replace(old, new)
    wr(p, s)
    report.append(f'rich_pipeline.py: SPEC插入 + {n}处prompt拼接')
else:
    report.append('rich_pipeline.py: 已有SPEC，跳过')

# ---------- 2) index.html：logo_full + chkRoadshow + 版本 ----------
p = ROOT + '/index.html'
s = rd(p)
img_new = '<img src="/static/logo_full.png?v=20260930f" class="wb-hero-logo" alt="科创赛事助手" width="72" height="76">'
s2, n = re.subn(r'<img src="/static/logo\.png\?v=[^"]*"\s+class="wb-hero-logo"[^>]*>', img_new, s)
if n == 0 and 'logo_full.png' not in s:
    # 兜底：Codex 写法可能参数顺序不同
    s2, n = re.subn(r'<img[^>]*class="wb-hero-logo"[^>]*>', img_new, s)
if n:
    s = s2; report.append(f'index.html: hero logo 换 logo_full({n}处)')
if 'id="chkRoadshow" checked' in s:
    s = s.replace('id="chkRoadshow" checked', 'id="chkRoadshow"', 1)
    report.append('index.html: chkRoadshow 取消默认勾选(P0)')
s3 = s.replace('?v=20260930e', '?v=20260930f')
if s3 != s:
    s = s3; report.append('index.html: 资源版本 e→f')
wr(p, s)

# ---------- 3) style.css：hero 72px + 夜间光晕 + 移动端 + 对比度 ----------
p = ROOT + '/static/style.css'
s = rd(p)
s2, n = re.subn(r'(\.hero \.wb-hero-logo\{\n\s*display: block; )width: 54px; height: 54px;',
                r'\g<1>width: 72px; height: auto;', s)
if n: s = s2; report.append('style.css: hero logo 54→72px')
if 'body:not(.light) .hero .wb-hero-logo' not in s:
    m = re.search(r'\.hero \.wb-hero-logo\{[^}]*\}\n', s)
    if m:
        s = s[:m.end()] + 'body:not(.light) .hero .wb-hero-logo{\n    filter: drop-shadow(0 0 10px rgba(56,189,248,.35)) saturate(1.05);\n}\n' + s[m.end():]
        report.append('style.css: 夜间光晕适配 新增')
s2, n = re.subn(r'(\.hero \.wb-hero-logo \{ )width: 36px; height: 36px;', r'\g<1>width: 56px; height: auto;', s)
if n: s = s2; report.append('style.css: 移动端 hero 36→56px')
for old, new, tag in [
    ('--text-mute:#8b98bd;', '--text-mute:#9aa7cc;', '夜间mute 6.35→7.61'),
    ('--text-dim:#55618a;', '--text-dim:#47527a;', '日间dim 5.91→7.42'),
    ('--text-mute:#5f6b88;', '--text-mute:#4a5575;', '日间mute 5.19→7.18'),
]:
    if old in s:
        s = s.replace(old, new, 1); report.append(f'style.css: {tag}')
wr(p, s)

# ---------- 4) app.py：admin 登录页 logo + 灰字对比度 ----------
p = ROOT + '/app.py'
s = rd(p)
old_form = 'action="/admin/login">\n<h1>科创赛事助手 · 管理后台</h1>'
new_form = ('action="/admin/login">\n<img src="/static/logo_full.png?v=20260930f" alt="logo" '
            'style="display:block;width:76px;height:auto;margin:0 auto 10px;">\n<h1>科创赛事助手 · 管理后台</h1>')
if old_form in s and 'logo_full.png' not in s:
    s = s.replace(old_form, new_form, 1); report.append('app.py: admin登录页加logo')
elif 'logo_full.png' in s:
    report.append('app.py: admin logo已有')
for old, new in [('color:#6b7280', 'color:#4b5563'), ('color:#b0b6c0', 'color:#4b5563'),
                 ('color:#9ca3af', 'color:#57606e')]:
    c = s.count(old)
    if c: s = s.replace(old, new); report.append(f'app.py: {old}→{new} ({c}处)')
wr(p, s)

# ---------- 5) 语法验证 ----------
for f in ['rich_pipeline.py', 'app.py']:
    py_compile.compile(ROOT + '/' + f, doraise=True)
report.append('py_compile: rich_pipeline.py + app.py PASS')

print('\n'.join(report))
