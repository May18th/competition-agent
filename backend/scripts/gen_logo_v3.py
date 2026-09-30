# -*- coding: utf-8 -*-
"""第一百五十七轮：logo 再调色（白底大气专项）。

157 轮实测：白底页面上，旧 logo（近黑深青方块）是一整块「重色」，和
「白底 + 柔和点缀色」的界面打架——用户上一轮的原话就是「logo 真的很违和」。
本次不改构图（递增柱 + 星已定稿），只把底色从近黑换成主题日间主色同一族：
  #0891b2（顶）→ #0e7490（主）→ #0f766e（底）
与按钮 / 强调文字 / 标题渐变完全同源，白底上是一块「有品牌的深青」
而不是「一块黑」，夜间主题下也协调（深青在深底上不刺眼）。
输出：static/logo.png（512x512 RGBA，覆盖前自动备份）。
"""
import os
import time
import shutil
from PIL import Image, ImageDraw

SS = 4
SIZE = 512
C_TOP = (8, 145, 178)     # #0891b2 亮青（顶端提一点，避免死黑感）
C_MAIN = (14, 116, 144)   # #0e7490 日间主色（--c-a）
C_BOT = (15, 118, 110)    # #0f766e 日间辅色（--c-b）
WHITE = (255, 255, 255)


def lerp(c1, c2, t):
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(root, 'static', 'logo.png')
    if os.path.exists(out):
        bak = out + '.bak_' + time.strftime('%Y%m%d%H%M%S')
        shutil.copy2(out, bak)
        print('已备份旧 logo ->', os.path.basename(bak))

    N = SIZE * SS
    img = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1) 圆角方块：垂直渐变（亮青 -> 主色 -> 辅色），全部取自主题变量同族
    #    ⚠️ 必须逐行画满 range(N)：之前按 240 步画，2048px 画布上每行之间留了 8px 透明缝，
    #    缩到 512px 后变成扫描条纹 + 整体透黑（这就是旧 logo「发黑发暗」的真正根因）
    pad = int(N * 0.035)
    r = int(N * 0.235)
    grad = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(N):
        t = i / (N - 1)
        if t < 0.45:
            col = lerp((*C_TOP, 255), (*C_MAIN, 255), t / 0.45)
        else:
            col = lerp((*C_MAIN, 255), (*C_BOT, 255), (t - 0.45) / 0.55)
        gd.line([(0, i), (N, i)], fill=col)
    mask = Image.new('L', (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, N - pad, N - pad], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)

    # 2) 三根递增圆头柱（成长/进阶），底边对齐
    w = int(N * 0.125)
    base = int(N * 0.760)
    bars = [(0.265, 0.560), (0.470, 0.415), (0.675, 0.270)]
    for cx, top in bars:
        x0 = int(N * cx - w / 2)
        x1 = int(N * cx + w / 2)
        y0 = int(top * N)
        y1 = base + w // 2
        d.rounded_rectangle([x0, y0, x1, y1], radius=w // 2, fill=WHITE + (255,))

    # 3) 右上角四角星（创意点亮）
    cx, cy = int(N * 0.745), int(N * 0.200)
    R, r2 = int(N * 0.150), int(N * 0.045)
    star = [(cx, cy - R), (cx + r2, cy - r2), (cx + R, cy), (cx + r2, cy + r2),
            (cx, cy + R), (cx - r2, cy + r2), (cx - R, cy), (cx - r2, cy - r2)]
    d.polygon(star, fill=WHITE + (255,))

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(out, 'PNG', optimize=True)
    print('生成', out, os.path.getsize(out), 'bytes', img.size)


if __name__ == '__main__':
    main()
