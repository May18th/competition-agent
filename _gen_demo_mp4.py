#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地合成真实演示视频 MP4：用真实前端截图做 Ken Burns 运镜 + 中文字幕 + 交叉淡入。
不依赖被墙的外部视频 API，用 imageio-ffmpeg 自带 ffmpeg 二进制本地编码。
素材全部为真实产物（index.html 真实渲染截图），不掺 AI 虚构画面。
"""
import os, math
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

REPO = os.path.dirname(os.path.abspath(__file__))
VID = os.path.join(REPO, "交付视频")
OUT = os.path.join(VID, "科创赛事助手_演示视频.mp4")

W, H = 1280, 720
FPS = 24
SCENE_SEC = 5
NFRAME = SCENE_SEC * FPS
XFADE = 12  # 交叉淡入帧数

# ---------- 中文字体 ----------
def load_font(size, bold=False):
    cands = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    if bold:
        cands += [os.path.join(windir, "Fonts", "msyhbd.ttc"),
                  os.path.join(windir, "Fonts", "msyh.ttc")]
    else:
        cands += [os.path.join(windir, "Fonts", "msyh.ttc"),
                  os.path.join(windir, "Fonts", "msyhbd.ttc")]
    cands += [os.path.join(windir, "Fonts", "simhei.ttf"),
              os.path.join(windir, "Fonts", "simsun.ttc")]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

F_BIG = load_font(40, bold=True)
F_SUB = load_font(22)
F_BRAND = load_font(20, bold=True)
F_END = load_font(56, bold=True)

# ---------- 运镜 ----------
def fill_zoom(src, t):
    """铺满并缓慢推近。"""
    s = 1.0 + 0.12 * t
    nw, nh = int(src.width * s), int(src.height * s)
    im = src.resize((nw, nh), Image.LANCZOS)
    l, tp = (nw - W) // 2, (nh - H) // 2
    return im.crop((l, tp, l + W, tp + H))

def pan_down(src, y0, y1, t):
    """竖长图：原生宽度，取景窗由上往下缓慢平移。"""
    sw = W
    sh = int(src.height * (sw / src.width))
    im = src.resize((sw, sh), Image.LANCZOS)
    maxy = max(0, sh - H)
    y = int(y0 + (y1 - y0) * t)
    y = max(0, min(maxy, y))
    return im.crop((0, y, sw, y + H))

def phone(src, t, bg):
    """竖屏手机：居中于深色渐变底，轻微推近。"""
    canvas = bg.copy()
    h = int(660 * (1.0 + 0.06 * t))
    w = int(src.width * h / src.height)
    im = src.resize((w, h), Image.LANCZOS)
    # 圆角描边 + 柔光
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=26, fill=255)
    canvas.paste(im, ((W - w) // 2, (H - h) // 2), mask)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([(W - w) // 2 - 2, (H - h) // 2 - 2,
                         (W - w) // 2 + w + 1, (H - h) // 2 + h + 1],
                        radius=28, outline=(99, 102, 241), width=2)
    return canvas

def gradient_bg():
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        k = y / H
        r = int(10 + 12 * k); g = int(14 + 16 * k); b = int(34 + 30 * k)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    return bg

def end_card(t):
    bg = gradient_bg()
    d = ImageDraw.Draw(bg)
    # 中心柔光
    for i in range(120, 0, -2):
        a = int(26 * (1 - i / 120))
        d.ellipse([W // 2 - i * 3, H // 2 - i * 1.6, W // 2 + i * 3, H // 2 + i * 1.6],
                  outline=(129, 140, 248, a))
    d.text((W // 2, H // 2 - 60), "科创赛事助手", font=F_END, fill=(255, 255, 255),
           anchor="mm")
    d.text((W // 2, H // 2 + 24), "让每一个创意，都有机会被看见", font=F_SUB,
           fill=(199, 208, 240), anchor="mm")
    d.text((W // 2, H // 2 + 78), "kechuang2026.cn", font=F_SUB, fill=(129, 140, 248),
           anchor="mm")
    return bg

# ---------- 字幕叠加 ----------
def overlay_caption(fr, cap, sub, brand=True):
    fr = fr.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # 底部渐隐暗条
    for i in range(200):
        y = H - 200 + i
        a = int(215 * (i / 200))
        d.line([(0, y), (W, y)], fill=(8, 11, 26, a))
    # 强调竖线
    x0 = int(W * 0.06)
    d.rectangle([x0, H - 152, x0 + 6, H - 96], fill=(129, 140, 248, 255))
    d.text((x0 + 24, H - 152), cap, font=F_BIG, fill=(255, 255, 255, 255))
    d.text((x0 + 24, H - 96), sub, font=F_SUB, fill=(205, 213, 245, 240))
    if brand:
        d.rounded_rectangle([x0, int(H * 0.055), x0 + 30, int(H * 0.055) + 30],
                            radius=8, fill=(129, 140, 248, 255))
        d.text((x0 + 40, int(H * 0.055) + 2), "科创赛事助手 KCWX", font=F_BRAND,
               fill=(223, 229, 255, 235))
    return Image.alpha_composite(fr, ov).convert("RGB")

# ---------- 场景 ----------
hero = Image.open(os.path.join(VID, "hero_desktop.png")).convert("RGB")
desk = Image.open(os.path.join(VID, "real_ui_desktop.png")).convert("RGB")
mob = Image.open(os.path.join(VID, "real_ui_mobile.png")).convert("RGB")
BG = gradient_bg()

SCENES = [
    dict(name="定位", mode="fill", cap="科创赛事助手 · AI 驱动的科创竞赛全流程助手",
         sub="输入一个创意，自动跑通规则解析、同质化检测到申报书 / PPT / 答辩稿生成"),
    dict(name="规则解析+查重", mode="pan", y0=0, y1=940,
         cap="输入创意 → 规则解析 + 同质化检测",
         sub="先读懂赛制与评审标准，再比对历史作品库，提前规避创意撞车与雷同"),
    dict(name="多智能体生成", mode="pan", y0=940, y1=1880,
         cap="20+ 智能体协同 · 流式生成",
         sub="申报书、路演 PPT、答辩稿边生成边可见，全程无需人工拼接"),
    dict(name="移动端", mode="phone", cap="移动端适配 · 随时随地生成",
         sub="响应式界面，手机端同样可完成创意提交与作品导出"),
    dict(name="结尾", mode="end", cap="评委口径复审 · 一键导出 Word / PPT / PDF / ZIP",
         sub="质量闸门保障：零绝对化用语、数据可溯源、格式即交即过"),
]

def render(scene, t):
    if scene["mode"] == "fill":
        fr = fill_zoom(hero, t)
    elif scene["mode"] == "pan":
        fr = pan_down(desk, scene["y0"], scene["y1"], t)
    elif scene["mode"] == "phone":
        fr = phone(mob, t, BG)
    else:
        fr = end_card(t)
    return overlay_caption(fr, scene["cap"], scene["sub"], brand=(scene["mode"] != "end"))

# ---------- 生成帧 + 交叉淡入 ----------
print("rendering scenes...")
scene_frames = []
for si, sc in enumerate(SCENES):
    frames = [render(sc, i / (NFRAME - 1)) for i in range(NFRAME)]
    scene_frames.append(frames)
    print(f"  scene {si+1}/{len(SCENES)} {sc['name']}: {len(frames)} frames")

final = []
for i, frames in enumerate(scene_frames):
    seg = frames[:]
    if i < len(scene_frames) - 1:   # 与下一幕交叉淡入
        nxt = scene_frames[i + 1]
        for k in range(XFADE):
            idx = NFRAME - XFADE + k
            seg[idx] = Image.blend(seg[idx], nxt[k], k / XFADE)
    final.extend(seg)
print("total frames:", len(final))

# ---------- 编码 MP4 ----------
print("encoding mp4 ->", OUT)
writer = imageio_ffmpeg.write_frames(
    OUT, (W, H), fps=FPS, codec="libx264",
    output_params=["-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium"],
    macro_block_size=1,
)
writer.send(None)
for fr in final:
    writer.send(fr.tobytes())
writer.close()
print("DONE bytes:", os.path.getsize(OUT), "| seconds:", round(len(final) / FPS, 2))
