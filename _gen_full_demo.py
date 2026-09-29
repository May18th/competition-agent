#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全功能演示视频（<=5min）：真实代码标识 + 真实 UI 截图，逐项展示系统全部能力。
连通性：27 项功能按真实流水线顺序排列；右屏常驻「功能 N/27」+ 进度条；每帧常驻品牌角标。
流畅性：24fps、smoothstep 缓动运镜、12 帧交叉淡入转场。
所有功能名与标识符均来自 competition_agents.py / app.py 实际代码；要点只写与标识符对应的事实，
不写未核实的具体数字（如字数、分类数量）。
"""
import os, textwrap
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

REPO = os.path.dirname(os.path.abspath(__file__))
VID = os.path.join(REPO, "交付视频")
OUT = os.path.join(VID, "科创赛事助手_全功能演示.mp4")

W, H = 1280, 720
FPS = 20                 # 流畅性：24->20，降低总帧数以保证渲染能跑完（时长仍 <=5min）
LEFT_W = 700
RIGHT_W = W - LEFT_W
INTRO_SEC, FEAT_SEC, OUTRO_SEC = 10, 8, 10
XFADE = 10               # 流畅性：0.5s 交叉淡入

ACCENT = (129, 140, 248)
ACCENT2 = (245, 158, 11)
WHITE = (255, 255, 255)
SUBC = (198, 207, 238)
DIMC = (150, 160, 200)

def ease(t):
    """smoothstep 缓动，起停更顺滑。"""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def font(size, bold=False):
    win = os.environ.get("WINDIR", r"C:\Windows")
    cands = ([os.path.join(win, "Fonts", "msyhbd.ttc")] if bold else []) + \
            [os.path.join(win, "Fonts", "msyh.ttc")] + \
            [os.path.join(win, "Fonts", "simhei.ttf"), os.path.join(win, "Fonts", "simsun.ttc")]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

F_TITLE = font(38, True)
F_NAME = font(33, True)
F_BULLET = font(21)
F_CODE = font(17)
F_META = font(17)
F_INTRO_T = font(60, True)
F_INTRO_S = font(24)

hero = Image.open(os.path.join(VID, "hero_desktop.png")).convert("RGB")
desk = Image.open(os.path.join(VID, "real_ui_desktop.png")).convert("RGB")
mob = Image.open(os.path.join(VID, "real_ui_mobile.png")).convert("RGB")

def gradient(w, h, top, bot):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        k = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    return im

BG_RIGHT = gradient(RIGHT_W, H, (13, 17, 38), (20, 26, 58))

def txt_w(d, s, f):
    return d.textlength(s, font=f)

def wrap(d, s, f, maxw):
    unit = txt_w(d, "测", f) or 20
    n = max(1, int(maxw // unit))
    out = []
    for para in s.split("\n"):
        out.extend(textwrap.wrap(para, width=n) if para.strip() else [""])
    return out

# ---------- 连通性：常驻品牌角标（每帧粘贴，成本极低） ----------
BRAND = Image.new("RGBA", (300, 42), (0, 0, 0, 0))
_bd = ImageDraw.Draw(BRAND)
_bd.rounded_rectangle([0, 0, 299, 41], radius=10, fill=(13, 17, 38, 190))
_bd.rounded_rectangle([14, 13, 38, 29], radius=6, fill=ACCENT + (255,))
_bd.text((48, 10), "科创赛事助手 KCWX", font=F_META, fill=(223, 229, 255, 235))

# ---------- 左半屏运镜（带缓动） ----------
# 性能：桌面长图只 resize 一次（逐帧仅裁剪），否则每帧重算 1280x2600->700x1422 极慢
DESK_RS = None
Y_MAX_DESIGN = 1880.0   # FEATURES 里 y0/y1 的设计上限，按比例映射到真实可平移范围

def left_frame(kind, t, y0=0, y1=0):
    global DESK_RS
    e = ease(t)
    if kind == "hero":
        s = 1.0 + 0.10 * e
        nw, nh = int(hero.width * s), int(hero.height * s)
        im = hero.resize((nw, nh), Image.BILINEAR)
        l, tp = (nw - LEFT_W) // 2, (nh - H) // 2
        return im.crop((l, tp, l + LEFT_W, tp + H))
    if kind == "desk":
        if DESK_RS is None:
            sw = LEFT_W
            sh = int(desk.height * (sw / desk.width))
            DESK_RS = desk.resize((sw, sh), Image.LANCZOS)
        maxy = max(0, DESK_RS.height - H)
        # 修正：原 y1 最大 1880 远超 maxy(~701)，被 clamp 后多个场景画面完全一致且不动
        y = int((y0 + (y1 - y0) * e) / Y_MAX_DESIGN * maxy)
        y = max(0, min(maxy, y))
        return DESK_RS.crop((0, y, LEFT_W, y + H))
    if kind == "mobile":
        cv = gradient(LEFT_W, H, (10, 14, 30), (16, 21, 46))
        h = int(620 * (1.0 + 0.05 * e))
        w = int(mob.width * h / mob.height)
        im = mob.resize((w, h), Image.BILINEAR)
        m = Image.new("L", im.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=24, fill=255)
        cv.paste(im, ((LEFT_W - w) // 2, (H - h) // 2), m)
        d = ImageDraw.Draw(cv)
        d.rounded_rectangle([(LEFT_W - w) // 2 - 2, (H - h) // 2 - 2,
                             (LEFT_W - w) // 2 + w + 1, (H - h) // 2 + h + 1],
                            radius=26, outline=ACCENT, width=2)
        return cv
    return gradient(LEFT_W, H)

# ---------- 右半屏（每幕缓存一次） ----------
def build_right(idx, total, name, code, bullets):
    im = BG_RIGHT.copy()
    d = ImageDraw.Draw(im)
    P = 44
    y = 78
    d.text((P, 40), f"功能 {idx} / {total}", font=F_META, fill=DIMC)
    bw = RIGHT_W - 2 * P
    d.rectangle([P, 64, P + bw, 68], fill=(40, 48, 88))
    d.rectangle([P, 64, P + int(bw * idx / total), 68], fill=ACCENT2)
    d.text((P, y), name, font=F_NAME, fill=WHITE)
    y += 52
    cw = int(txt_w(d, code, F_CODE)) + 22
    d.rounded_rectangle([P, y, P + cw, y + 30], radius=7, fill=(39, 46, 84))
    d.text((P + 11, y + 5), code, font=F_CODE, fill=(165, 180, 255))
    y += 50
    for b in bullets:
        for ln in wrap(d, b, F_BULLET, RIGHT_W - 2 * P - 26):
            d.ellipse([P + 4, y + 9, P + 11, y + 16], fill=ACCENT)
            d.text((P + 24, y), ln, font=F_BULLET, fill=SUBC)
            y += 32
        y += 6
    return im

# ---------- 开场 / 结尾 ----------
def intro_frame(t):
    e = ease(t)
    s = 1.0 + 0.08 * e
    nw, nh = int(hero.width * s), int(hero.height * s)
    im = hero.resize((nw, nh), Image.LANCZOS)
    l, tp = (nw - W) // 2, (nh - H) // 2
    fr = im.crop((l, tp, l + W, tp + H)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i in range(H):
        a = int(205 * (i / H) ** 1.6)
        d.line([(0, i), (W, i)], fill=(6, 9, 22, a))
    d.text((W // 2, H // 2 - 40), "科创赛事助手", font=F_INTRO_T, fill=WHITE, anchor="mm")
    d.text((W // 2, H // 2 + 34), "全功能演示 · 从创意到提交的一条龙 AI 流水线",
           font=F_INTRO_S, fill=(205, 213, 245), anchor="mm")
    d.rectangle([W // 2 - 60, H // 2 + 62, W // 2 + 60, H // 2 + 66], fill=ACCENT2)
    return Image.alpha_composite(fr, ov).convert("RGB")

def outro_frame(t):
    bg = gradient(W, H, (10, 14, 32), (17, 22, 52))
    d = ImageDraw.Draw(bg)
    for i in range(150, 0, -3):
        a = int(22 * (1 - i / 150))
        d.ellipse([W // 2 - i * 3, H // 2 - i * 1.5, W // 2 + i * 3, H // 2 + i * 1.5],
                  outline=(129, 140, 248, a))
    d.text((W // 2, H // 2 - 62), "让每一个创意，都有机会被看见",
           font=F_INTRO_T, fill=WHITE, anchor="mm")
    d.text((W // 2, H // 2 + 26), "kechuang2026.cn", font=F_INTRO_S, fill=ACCENT, anchor="mm")
    d.text((W // 2, H // 2 + 78), "申报书 · 路演 PPT · 答辩稿 · 一键导出",
           font=F_INTRO_S, fill=SUBC, anchor="mm")
    return bg

# ---------- 功能清单：按真实流水线顺序（标识符取自 competition_agents.py / app.py）----------
FEATURES = [
    ("创意输入与额度管控", "/api/generate · get_quota_status", "desk", 0, 700, [
        "输入一句话创意并选择目标赛事即可启动",
        "内置每日额度与配额管控",
        "支持官方规则文档上传与解析"]),
    ("赛制规则解析", "rule_parser", "desk", 300, 1000, [
        "读取目标赛事规则与评审标准",
        "输出赛制要点与评分维度",
        "为后续生成环节统一定锚"]),
    ("同质化检测 / 查重", "similarity_checker", "desk", 700, 1400, [
        "比对历史作品库识别创意雷同",
        "给出相似度判断与规避建议",
        "赛制别名归一，跨赛事口径对齐"]),
    ("创意可行性评估", "idea_evaluator", "desk", 1000, 1700, [
        "对创意做多维度打分",
        "输出优势项与待补强项",
        "为深度分析提供方向"]),
    ("一句话定位", "one_liner", "desk", 1300, 1880, [
        "把创意压缩成一句可传播的定位",
        "用于标题、路演开场与 PPT 首页"]),
    ("综合分析", "comprehensive_analysis_agent", "desk", 0, 800, [
        "整合规则、查重、评估结果形成分析底稿",
        "输出结构化分析结论"]),
    ("竞品深度分析", "deep_competitor_agent", "desk", 500, 1200, [
        "识别竞品与替代方案",
        "对比差异并给出定位建议"]),
    ("商业可行性分析", "deep_business_agent", "desk", 900, 1600, [
        "目标用户与商业模式推演",
        "梳理成本结构与盈利路径"]),
    ("风险识别与对策", "deep_risk_agent", "desk", 1200, 1880, [
        "扫描项目潜在风险",
        "逐条给出应对建议"]),
    ("技术路径分析", "deep_tech_agent", "desk", 0, 700, [
        "拆解关键技术与实现路径",
        "评估成熟度并给出选型建议"]),
    ("实施计划编排", "plan_agent", "desk", 400, 1100, [
        "把创意拆成可执行的阶段与里程碑",
        "明确每阶段交付物"]),
    ("社会价值论证", "social_value_agent", "desk", 800, 1500, [
        "围绕社会痛点与公共价值展开论证",
        "呼应评审对现实意义的考核"]),
    ("要点汇总", "summary_agent", "desk", 1100, 1800, [
        "把多维分析压缩为评审可读要点",
        "作为申报书论据骨架"]),
    ("申报书正文写作", "deep_writer_agent / proposal_writer_agent", "desk", 0, 900, [
        "按赛制结构生成申报书正文",
        "分章节流式输出，边生成边可见"]),
    ("定向修改", "targeted_revise_agent", "desk", 600, 1400, [
        "针对指定章节做局部重写",
        "保留其余内容，避免全文重跑"]),
    ("评委视角评审", "judge_agent", "desk", 1000, 1800, [
        "按评委口径打分与点评",
        "输出失分点与改进优先级"]),
    ("专家复审", "expert_review_agent", "desk", 0, 800, [
        "在评委评审后做第二轮复核",
        "核查逻辑闭环与论据充分性"]),
    ("申报书体检与评分", "proposal_analysis_agent", "desk", 500, 1300, [
        "完整性体检：缺项、结构告警",
        "评分依据与评分总览可视化"]),
    ("答辩问题预判", "defense_questions_agent", "desk", 900, 1700, [
        "按评委常见追问生成问题库",
        "每题配套应答要点"]),
    ("路演 PPT 大纲", "ppt_outline_agent", "desk", 1200, 1880, [
        "按结构编排每页标题即结论",
        "驱动 python-pptx 生成可编辑 PPTX"]),
    ("路演演讲稿", "speech_agent", "desk", 0, 700, [
        "逐页生成口播稿与时长分配",
        "含过渡句与重点强调提示"]),
    ("图表与富媒体", "rich_media_agent", "desk", 350, 1050, [
        "生成数据图表与配图资产",
        "图表标题即结论，统一视觉规范"]),
    ("多格式一键导出", "/api/export_word|pdf|pptx|defense|competitor|business|all|zip", "desk", 700, 1500, [
        "Word / PDF / PPT / PPTX 逐格式导出",
        "export_all 打包、export_zip 压缩下载",
        "export_original_format 还原官方格式"]),
    ("分享与反馈", "/api/share_export/<token> · /api/feedback/export", "desk", 1000, 1800, [
        "生成分享链接供评委 / 导师查看",
        "收集反馈并可导出"]),
    ("质量闸门", "check_proposal_completeness · _downgrade_fabrication · _spot_check_numbers", "desk", 0, 900, [
        "完整性、格式、数字抽查三重校验",
        "降级虚构表述、剥离占位符",
        "重复句去重、篇幅压缩到赛制要求"]),
    ("知识库与官方文档", "retrieve_knowledge · get_official_doc · get_industry_data", "desk", 500, 1400, [
        "检索召回赛制知识与行业数据",
        "官方文档入库、格式校验与状态自检"]),
    ("移动端适配", "响应式前端", "mobile", 0, 0, [
        "手机端可完成提交、查看与导出",
        "已按 390px 窄屏实测截图"]),
]

TOTAL = len(FEATURES)
est = INTRO_SEC + TOTAL * FEAT_SEC + OUTRO_SEC
print(f"features={TOTAL}  est_duration={est}s = {est/60:.2f}min  (limit 5min) fps={FPS}")

# ---------- 流式渲染：逐帧写盘 ----------
# 关键修正：不能把全部帧攒在内存里。6000+ 帧 x 2.76MB ≈ 17GB 会 OOM 被杀。
# 这里只保留当前幕末尾 XFADE 帧 + 下一幕开头 XFADE 帧（约 24 帧），其余即渲染即写入编码器。
def scene_renderer(sc):
    """返回 (帧数, render(k) -> PIL.Image)。"""
    if sc["kind"] == "intro":
        n = INTRO_SEC * FPS
        return n, (lambda k, n=n: intro_frame(k / max(1, n - 1)))
    if sc["kind"] == "outro":
        n = OUTRO_SEC * FPS
        return n, (lambda k, n=n: outro_frame(k / max(1, n - 1)))
    n = FEAT_SEC * FPS
    idx, name, code = sc["idx"], sc["name"], sc["code"]
    kind, y0, y1, bullets = sc["img"], sc["y0"], sc["y1"], sc["bullets"]
    rp = build_right(idx, TOTAL, name, code, bullets)

    def r(k, n=n, kind=kind, y0=y0, y1=y1, rp=rp):
        t = k / max(1, n - 1)
        fr = Image.new("RGB", (W, H))
        fr.paste(left_frame(kind, t, y0, y1), (0, 0))
        fr.paste(BRAND, (26, H - 58), BRAND)       # 连通性：常驻品牌角标
        fr.paste(rp, (LEFT_W, 0))
        ImageDraw.Draw(fr).line([(LEFT_W, 0), (LEFT_W, H)], fill=(60, 70, 120), width=2)
        return fr
    return n, r

scenes = [{"kind": "intro"}]
for i, (name, code, kind, y0, y1, bullets) in enumerate(FEATURES, 1):
    scenes.append({"kind": "feat", "idx": i, "name": name, "code": code,
                   "img": kind, "y0": y0, "y1": y1, "bullets": bullets})
scenes.append({"kind": "outro"})

writer = imageio_ffmpeg.write_frames(
    OUT, (W, H), fps=FPS, codec="libx264",
    output_params=["-pix_fmt", "yuv420p", "-crf", "21", "-preset", "veryfast"],
    macro_block_size=1)
writer.send(None)

written, start = 0, 0
for si, sc in enumerate(scenes):
    n, render = scene_renderer(sc)
    end = (n - XFADE) if si < len(scenes) - 1 else n
    for k in range(start, end):
        writer.send(render(k).tobytes())
        written += 1
    if si < len(scenes) - 1:
        # 流畅性：与下一幕做 XFADE 帧交叉淡入（下一幕从第 XFADE 帧继续写，避免重复帧）
        tail = [render(k) for k in range(n - XFADE, n)]
        _, render2 = scene_renderer(scenes[si + 1])
        head = [render2(k) for k in range(XFADE)]
        for k in range(XFADE):
            writer.send(Image.blend(tail[k], head[k], k / XFADE).tobytes())
            written += 1
        start = XFADE
    print(f"  scene {si+1}/{len(scenes)} done | written={written}")
writer.close()
print("DONE", OUT, "bytes=", os.path.getsize(OUT),
      "| frames:", written, "| duration:", round(written / FPS, 2), "s")
