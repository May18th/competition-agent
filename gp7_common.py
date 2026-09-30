# -*- coding: utf-8 -*-
"""309 轮：三份「一键演示」样例数据生成公共工具（图表 SVG → base64 data URI + 落盘）。"""
import base64
import json
import os

BASE = '/opt/comp-agent'
STATIC = os.path.join(BASE, 'static')

_FONT = "'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif"


def _b64(svg):
    return 'data:image/svg+xml;base64,' + base64.b64encode(
        svg.encode('utf-8')).decode('ascii')


def chart_bar(cid, title, categories, values, unit, caption, source):
    """竖向柱状图。"""
    n = len(categories)
    w, h = 680, 380
    pad_l, pad_b, pad_t = 60, 56, 46
    plot_w = w - pad_l - 24
    plot_h = h - pad_t - pad_b
    vmax = max(values) if values else 1
    vmax = vmax * 1.18 or 1
    slot = plot_w / float(max(n, 1))
    bw = slot * 0.52
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h))
    parts.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (w, h))
    parts.append('<text x="%d" y="28" font-family="%s" font-size="17" font-weight="700" fill="#101828">%s</text>'
                 % (pad_l, _FONT, title))
    # 网格线 + y 轴刻度
    for i in range(5):
        v = vmax * i / 4.0
        y = pad_t + plot_h - plot_h * i / 4.0
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e6e9f0" stroke-width="1"/>'
                     % (pad_l, y, w - 24, y))
        parts.append('<text x="%d" y="%.1f" font-family="%s" font-size="11" fill="#8a94a6" text-anchor="end">%.0f</text>'
                     % (pad_l - 8, y + 4, _FONT, v))
    for i, (c, v) in enumerate(zip(categories, values)):
        cx = pad_l + slot * (i + 0.5)
        bh = plot_h * (v / vmax)
        y = pad_t + plot_h - bh
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="url(#g)"/>'
                     % (cx - bw / 2, y, bw, bh))
        parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="12" font-weight="600" fill="#2b3a55" text-anchor="middle">%g</text>'
                     % (cx, y - 7, _FONT, v))
        parts.append('<text x="%.1f" y="%d" font-family="%s" font-size="12" fill="#5a6478" text-anchor="middle">%s</text>'
                     % (cx, pad_t + plot_h + 22, _FONT, c))
    parts.append('<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
                 '<stop offset="0" stop-color="#4f7cff"/><stop offset="1" stop-color="#8fb0ff"/>'
                 '</linearGradient></defs>')
    parts.append('<text x="%d" y="%d" font-family="%s" font-size="11" fill="#8a94a6">单位：%s</text>'
                 % (pad_l, h - 12, _FONT, unit))
    parts.append('</svg>')
    return {"id": cid, "url": _b64(''.join(parts)), "title": title,
            "caption": caption, "source": source}


def chart_line(cid, title, stages, progress, unit, caption, source):
    """折线/面积图（进度类）。"""
    n = len(stages)
    w, h = 680, 380
    pad_l, pad_b, pad_t = 60, 56, 46
    plot_w = w - pad_l - 24
    plot_h = h - pad_t - pad_b
    vmax = 105.0
    pts = []
    for i, v in enumerate(progress):
        x = pad_l + plot_w * (i / float(max(n - 1, 1)))
        y = pad_t + plot_h - plot_h * (v / vmax)
        pts.append((x, y))
    parts = []
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h))
    parts.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (w, h))
    parts.append('<text x="%d" y="28" font-family="%s" font-size="17" font-weight="700" fill="#101828">%s</text>'
                 % (pad_l, _FONT, title))
    for i in range(5):
        v = 100.0 * i / 4.0
        y = pad_t + plot_h - plot_h * i / 4.0
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e6e9f0" stroke-width="1"/>'
                     % (pad_l, y, w - 24, y))
        parts.append('<text x="%d" y="%.1f" font-family="%s" font-size="11" fill="#8a94a6" text-anchor="end">%.0f</text>'
                     % (pad_l - 8, y + 4, _FONT, v))
    area = ' '.join('%.1f,%.1f' % p for p in pts)
    parts.append('<polygon points="%d,%.1f %s %.1f,%.1f" fill="#4f7cff" fill-opacity="0.12"/>'
                 % (pad_l, pad_t + plot_h, area, pad_l + plot_w, pad_t + plot_h))
    parts.append('<polyline points="%s" fill="none" stroke="#4f7cff" stroke-width="2.5" stroke-linejoin="round"/>' % area)
    for (x, y), v, s in zip(pts, progress, stages):
        parts.append('<circle cx="%.1f" cy="%.1f" r="4" fill="#ffffff" stroke="#4f7cff" stroke-width="2.5"/>' % (x, y))
        parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="12" font-weight="600" fill="#2b3a55" text-anchor="middle">%g</text>'
                     % (x, y - 10, _FONT, v))
        parts.append('<text x="%.1f" y="%d" font-family="%s" font-size="11.5" fill="#5a6478" text-anchor="middle">%s</text>'
                     % (x, pad_t + plot_h + 22, _FONT, s))
    parts.append('<text x="%d" y="%d" font-family="%s" font-size="11" fill="#8a94a6">单位：%s</text>'
                 % (pad_l, h - 12, _FONT, unit))
    parts.append('</svg>')
    return {"id": cid, "url": _b64(''.join(parts)), "title": title,
            "caption": caption, "source": source}


def chart_donut(cid, title, labels, values, caption, source):
    """环形图（成本构成）。"""
    import math
    w, h = 680, 380
    cx, cy, r_out, r_in = 200.0, 196.0, 116.0, 66.0
    total = float(sum(values)) or 1.0
    colors = ['#4f7cff', '#22c3a6', '#f5a623', '#ef5da8', '#8b7bff', '#5a6478']
    parts = []
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h))
    parts.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (w, h))
    parts.append('<text x="34" y="28" font-family="%s" font-size="17" font-weight="700" fill="#101828">%s</text>'
                 % (_FONT, title))
    a0 = -math.pi / 2
    for i, (lb, v) in enumerate(zip(labels, values)):
        frac = v / total
        a1 = a0 + frac * 2 * math.pi
        large = 1 if frac > 0.5 else 0
        x0, y0 = cx + r_out * math.cos(a0), cy + r_out * math.sin(a0)
        x1, y1 = cx + r_out * math.cos(a1), cy + r_out * math.sin(a1)
        xi1, yi1 = cx + r_in * math.cos(a1), cy + r_in * math.sin(a1)
        xi0, yi0 = cx + r_in * math.cos(a0), cy + r_in * math.sin(a0)
        d = ('M %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f L %.2f %.2f A %.2f %.2f 0 %d 0 %.2f %.2f Z'
             % (x0, y0, r_out, r_out, large, x1, y1, xi1, yi1, r_in, r_in, large, xi0, yi0))
        parts.append('<path d="%s" fill="%s"/>' % (d, colors[i % len(colors)]))
        a0 = a1
        ly = 92 + i * 34
        parts.append('<rect x="400" y="%d" width="12" height="12" rx="3" fill="%s"/>' % (ly, colors[i % len(colors)]))
        parts.append('<text x="422" y="%d" font-family="%s" font-size="13" fill="#2b3a55">%s　%g（%.1f%%）</text>'
                     % (ly + 11, _FONT, lb, v, frac * 100))
    parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="15" font-weight="700" fill="#101828" text-anchor="middle">%.0f</text>'
                 % (cx, cy + 2, _FONT, total))
    parts.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="11" fill="#8a94a6" text-anchor="middle">合计</text>'
                 % (cx, cy + 20, _FONT))
    parts.append('</svg>')
    return {"id": cid, "url": _b64(''.join(parts)), "title": title,
            "caption": caption, "source": source}


def save(fname, obj):
    """写成 {success, data, rating, rich_*, _demo, _demo_note}，data 与顶层富媒体互映。"""
    path = os.path.join(STATIC, fname)
    top = {
        "success": True,
        "data": obj["data"],
        "rating": obj["data"].get("score", 0),
        "rich_deck": obj["data"].get("rich_deck"),
        "rich_charts": obj["data"].get("rich_charts") or [],
        "rich_tables": obj["data"].get("rich_tables") or [],
        "_demo": True,
        "_demo_note": "演示样例（预置内容，非实时生成）",
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(top, f, ensure_ascii=False, indent=1)
    return path
