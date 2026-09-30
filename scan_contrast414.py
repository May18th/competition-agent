# -*- coding: utf-8 -*-
"""
414 轮 · 对比度 AA 扫描器（只读，不改任何文件）

做法：解析 static/*.css 的每条规则块，取块内的 color 与 background/background-color，
按 WCAG 2.1 公式算对比度，列出不达标的条目。
- 正文要求 >= 4.5:1（AA 正常文本）
- 大字/按钮要求 >= 3.0:1（AA 大文本：>=18.66px 且 bold，或 >=24px）

块内没有背景色时，按白底 #ffffff 估算，并在输出里标注 ESTIMATED，
便于人工判断是否真的踩在深色背景上（那种情况白字反而没问题）。
"""
import os
import re
import io

CSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# 大字号判定用的粗略依据：块里有 font-size >= 18px，或 font-weight >= 600
RE_SIZE = re.compile(r'font-size:\s*([0-9.]+)\s*(px|rem|em)', re.I)
RE_WEIGHT = re.compile(r'font-weight:\s*([0-9]{3}|bold)', re.I)


def parse_color(s):
    """返回 (r,g,b,a) 或 None。支持 #rgb / #rrggbb / rgb() / rgba() / 常见命名色。"""
    if not s:
        return None
    s = s.strip().lower()
    named = {
        'white': (255, 255, 255, 1.0), 'black': (0, 0, 0, 1.0),
        'transparent': None, 'inherit': None, 'currentcolor': None,
        'none': None, 'initial': None, 'unset': None,
    }
    if s in named:
        return named[s]
    m = re.match(r'^#([0-9a-f]{3})$', s)
    if m:
        a, b, c = m.group(1)
        return (int(a * 2, 16), int(b * 2, 16), int(c * 2, 16), 1.0)
    m = re.match(r'^#([0-9a-f]{6})$', s)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    m = re.match(r'^#([0-9a-f]{8})$', s)
    if m:
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16),
                int(h[6:8], 16) / 255.0)
    m = re.match(r'^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?\)$', s)
    if m:
        r, g, b = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        a = float(m.group(4)) if m.group(4) else 1.0
        return (r, g, b, a)
    return None


def blend(fg, bg):
    """前景带 alpha 时与背景混合。"""
    r, g, b, a = fg
    if a >= 1.0:
        return (r, g, b)
    br, bg_, bb = bg[:3]
    return (r * a + br * (1 - a), g * a + bg_ * (1 - a), b * a + bb * (1 - a))


def lum(rgb):
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = [ch(x) for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb1, rgb2):
    l1, l2 = lum(rgb1), lum(rgb2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def main():
    files = sorted([f for f in os.listdir(CSS_DIR) if f.endswith('.css')])
    rows = []

    for fn in files:
        path = os.path.join(CSS_DIR, fn)
        with io.open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            css = fh.read()

        # 去掉注释，避免注释里的示例颜色干扰
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)

        # 匹配 选择器 { 声明块 }
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
            sel = m.group(1).strip().replace('\n', ' ')[:90]
            body = m.group(2)
            if 'color' not in body:
                continue

            cm = re.search(r'(?<!-)\bcolor\s*:\s*([^;]+)', body)
            if not cm:
                continue
            fg = parse_color(cm.group(1))
            if fg is None:
                continue

            bgm = re.search(r'background(?:-color)?\s*:\s*([^;]+)', body)
            estimated = False
            unknown_bg = False
            if bgm:
                raw_bg = bgm.group(1).strip()
                # 渐变 / CSS 变量解析不了真实颜色，不能一口咬定白底——
                # 否则「白字+渐变深底」会被误报成 1.00（第一版就踩了这个坑）
                if 'gradient' in raw_bg or 'var(' in raw_bg or 'url(' in raw_bg:
                    unknown_bg = True
                bg = parse_color(raw_bg)
                if bg is None:
                    bg = (255, 255, 255, 1.0)
                    estimated = True
            else:
                bg = (255, 255, 255, 1.0)
                estimated = True

            # 半透明背景要先与页面底色（按白）混合，再与前景比
            page_bg = (255, 255, 255)
            bg_solid = blend(bg, page_bg) if bg[3] < 1.0 else bg[:3]

            fg_rgb = blend(fg, bg_solid)
            ratio = contrast(fg_rgb, bg_solid)

            # 大字判定
            big = False
            sm = RE_SIZE.search(body)
            if sm:
                try:
                    v = float(sm.group(1))
                    unit = sm.group(2).lower()
                    px = v * 16 if unit in ('rem', 'em') else v
                    big = px >= 18.66
                except Exception:
                    pass
            wm = RE_WEIGHT.search(body)
            if wm:
                w = wm.group(1)
                big = big or (w == 'bold') or (w.isdigit() and int(w) >= 600)

            need = 3.0 if big else 4.5
            if ratio < need:
                rows.append((ratio, need, fn, sel, cm.group(1).strip(),
                             (bgm.group(1).strip() if bgm else '(无/按白底)'),
                             'UNKNOWN' if unknown_bg else ('EST' if estimated else 'REAL'),
                             unknown_bg))

    # 背景能确定的真问题排前面；渐变/变量背景（UNKNOWN）排后面，避免噪声盖住真问题
    rows.sort(key=lambda r: (r[7], r[0]))
    print('=== 不达标条目总数：%d ===' % len(rows))
    print('%-7s %-5s %-18s %-52s %-22s %-20s %s'
          % ('比值', '要求', '文件', '选择器', '前景色', '背景色', '背景是否推定'))
    for ratio, need, fn, sel, fgc, bgc, est, _u in rows[:60]:
        print('%-7.2f %-5.1f %-18s %-52s %-22s %-20s %s'
              % (ratio, need, fn[:18], sel[:52], fgc[:22], bgc[:20], est))
    if len(rows) > 60:
        print('...(仅显示最差 60 条，共 %d 条)' % len(rows))


if __name__ == '__main__':
    main()
