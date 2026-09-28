# -*- coding: utf-8 -*-
"""第一百零七轮：logo 重做（v3 定稿构图：递增柱 + 星）。

旧 logo 是深紫科技风，与「白底 + 柔和点缀色」的新界面违和（用户原话：「赛创助手上面的
logo 真的很违和」）。这里程序化重绘一枚与主色同系的 logo：
  - 主色沿用主题变量：青蓝 #38bdf8 / 青绿 #2dd4bf，底端深青 #0c86ad 压住白色图形
  - 造型：圆角方块（品牌底）+ 三根递增圆头柱（成长/进阶）+ 右上角四角星（创意）
  - 4x 超采样后缩小，保证 16px favicon 尺寸下也能看清是「柱状上升 + 星」
输出：static/logo.png（512x512 RGBA，覆盖前自动备份 logo.png.bak_时间戳）
"""
import os
import time
import shutil
from PIL import Image, ImageDraw

SS = 4              # 超采样倍数
SIZE = 512
C_A = (56, 189, 248)    # #38bdf8 青蓝（亮端）
C_T = (45, 212, 191)    # #2dd4bf 青绿（过渡）
C_B = (12, 134, 173)    # #0c86ad 深青（暗端，比 #0e7490 亮一档，避免发黑）
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

    # 1) 圆角方块：垂直渐变（上亮青蓝 -> 中青绿 -> 下深青），亮端占比大，避免发黑
    pad = int(N * 0.035)
    r = int(N * 0.235)
    grad = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    steps = 240
    for i in range(steps):
        t = i / (steps - 1)
        if t < 0.55:
            col = lerp((*C_A, 255), (*C_T, 255), t / 0.55)
        else:
            col = lerp((*C_T, 255), (*C_B, 255), (t - 0.55) / 0.45)
        y = int(N * t)
        gd.line([(0, y), (N, y)], fill=col)
    mask = Image.new('L', (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, N - pad, N - pad], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)

    # 2) 三根递增圆头柱（成长/进阶），底边对齐
    w = int(N * 0.125)                       # 柱宽
    base = int(N * 0.760)                    # 底边 y
    bars = [(0.265, 0.560), (0.470, 0.415), (0.675, 0.270)]  # (x中心, 顶端y)
    for cx, top in bars:
        x0 = int(N * cx - w / 2)
        x1 = int(N * cx + w / 2)
        y0 = int(top * N)
        y1 = base + w // 2                   # 底端圆头
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
