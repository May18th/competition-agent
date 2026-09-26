# -*- coding: utf-8 -*-
"""图表渲染 · 国赛超精美版（Pro）

与 chart_renderer.py 的区别：同样的输入数据，出图从「能用」升级到「路演级」。
本文件**不改动** chart_renderer.py —— 两者并存，靠开关切换，随时可回退。

升级维度（对应对比表里的每一行）：
  1. 分辨率   dpi 110 → 200，Word/PPT 放大不糊
  2. 画布     10×5.4 → 11×6.2，留白更舒展；圆角卡片打底
  3. 标题区   主标题 20pt + 左侧强调色竖条；洞察语独立成行、带浅色底条
  4. 配色     同色系渐变填充，替代纯色平涂
  5. 柱形     圆角顶 + 竖向渐变 + 底部投影，替代直角平涂
  6. 数据标签 值 + 单位，白色描边保证在深色底上可读
  7. 网格     只留横向虚线、透明度降到 0.35，不抢数据
  8. 饼/环    环形化 + 中心总计 + 引导线外置标签，替代挤在扇区里的百分比
  9. 雷达     多层半透明填充 + 细网格 + 标签带底色 + 卡片化图例
 10. 甘特     圆角条 + 阶段名左对齐 + 顶部时间刻度 + 末阶段高亮
 11. 架构图   圆角卡片分层 + 同层同色渐变 + 层间连接箭头
 12. 象限     象限浅色分区 + 中心十字 + 点带白描边 + 名称引导线

用法：
    from chart_renderer_pro import render
    render(chart_spec, out_dir, theme='tech')   # 签名与旧版一致，可直接替换
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from matplotlib.colors import LinearSegmentedColormap, to_rgba
import numpy as np

import chart_renderer as _cr          # 复用其中文字体注册，避免中文变方框

# ---------------------------------------------------------------- 画布常量
FIGSIZE = (11.0, 6.2)
DPI = 200                              # 升级点 1：高清
ROUND = 0.035                          # 圆角半径（相对坐标）

CARD = "#0B1026"                       # 卡片底
BG = "#0F1535"                         # 画布底
FG = "#E9EEFC"
FG_DIM = "#93A0C4"
FG_MUTE = "#6B7899"
AXIS = "#3A4470"
ACCENT = "#22D3EE"

_THEMES = {
    "tech":     {"bg": "#0F1535", "card": "#0B1026",
                 "series": ["#818CF8", "#22B8CF", "#C084FC", "#F59E0B", "#34D399", "#FB7185", "#A3E635"]},
    "ink":      {"bg": "#1B1B1B", "card": "#151515",
                 "series": ["#7A8B9A", "#B94A4A", "#D4A24C", "#6E8474", "#8B7B93", "#4F6A80", "#C68648"]},
    "medical":  {"bg": "#09332F", "card": "#062724",
                 "series": ["#0E9E8C", "#2E86C1", "#45B39D", "#F0B429", "#27AE60", "#5DADE2", "#16A085"]},
    "edu":      {"bg": "#4A2410", "card": "#3D1E0D",
                 "series": ["#E2803A", "#F0B429", "#C0563A", "#5B8C5A", "#4A7FB5", "#A463C8", "#D45B5B"]},
    "agri":     {"bg": "#1E3D1A", "card": "#183015",
                 "series": ["#4E8C3A", "#C9A227", "#7BA05B", "#6B8E23", "#3E7C59", "#A0703A", "#2E6B4F"]},
    "finance":  {"bg": "#0C1A33", "card": "#091527",
                 "series": ["#2E5C8A", "#B8860B", "#40607A", "#C99700", "#5B7A99", "#8B6914", "#7A94AD"]},
    "craft":    {"bg": "#1F2A30", "card": "#182125",
                 "series": ["#5C6B73", "#E08A38", "#3D5A6C", "#A63A2F", "#7A8B5A", "#C77B3E", "#4A5D63"]},
    "social":   {"bg": "#4A2320", "card": "#3D1C1A",
                 "series": ["#D46A5C", "#E4A03C", "#5E8C7E", "#C2564F", "#7B6DA8", "#3E8C86", "#B5713C"]},
    "academic": {"bg": "#00254D", "card": "#001E3E",
                 "series": ["#2E75B6", "#4A7FB5", "#5B8C5A", "#8B6914", "#6B5B73", "#7E93AB", "#002FA7"]},
    "cyber":    {"bg": "#160826", "card": "#11061E",
                 "series": ["#7C3AED", "#22D3EE", "#A855F7", "#F472B6", "#8B5CF6", "#4B0082", "#F59E0B"]},
}


def _lighten(hex_color, k=0.34):
    """把颜色往白色方向提亮 k，用于渐变顶端。"""
    r, g, b, _ = to_rgba(hex_color)
    return (r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k, 1.0)


def _cmap(hex_color):
    """同色系竖向渐变：底部原色 → 顶部提亮。"""
    return LinearSegmentedColormap.from_list("g", [_lighten(hex_color, 0.42), hex_color])


def set_theme(theme=None):
    t = _THEMES.get(str(theme or "").lower()) or _THEMES["tech"]
    return t


def _fig(t):
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    fig.patch.set_facecolor(t["bg"])
    ax.set_facecolor(t["card"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
        ax.spines[s].set_linewidth(1.1)
    ax.tick_params(colors=FG_DIM, labelsize=11, length=0)
    ax.yaxis.grid(True, color=AXIS, linewidth=0.8, linestyle=(0, (4, 4)), alpha=0.35)  # 升级点 7
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    return fig, ax


def _head(fig, title, caption, t):
    """升级点 3：标题区 = 强调色竖条 + 主标题 + 洞察底条。"""
    if title:
        fig.text(0.045, 0.955, "▍", fontsize=21, color=ACCENT, va="top", fontweight="bold")
        fig.text(0.072, 0.952, str(title)[:44], fontsize=20, color=FG,
                 va="top", fontweight="bold")
    if caption:
        fig.patches.append(
            Rectangle((0.045, 0.045), 0.91, 0.052, transform=fig.transFigure,
                      facecolor=to_rgba(ACCENT, 0.10), edgecolor=to_rgba(ACCENT, 0.34),
                      linewidth=1.0, zorder=0))
        fig.text(0.5, 0.071, "· " + str(caption)[:64], fontsize=11.5,
                 color=ACCENT, ha="center", va="center")


def _save(fig, path):
    fig.tight_layout(rect=(0.03, 0.13, 0.985, 0.90))
    fig.savefig(path, facecolor=fig.get_facecolor(), dpi=DPI)
    plt.close(fig)
    return path


def _fmt(v):
    try:
        f = float(v)
    except Exception:
        return str(v)
    return f"{f:g}"


def _outline(txts, **kw):
    """升级点 6：白色描边，保证深色底上可读。"""
    return dict(path_effects=None, **kw)


def _lum(hex_color):
    """相对亮度（0-1），用于决定条内文字用深色还是白色。"""
    r, g, b, _ = to_rgba(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _grad_round(ax, x, y, w, h, hex_color, radius, lift=0.42, vertical=True, zorder=4):
    """圆角渐变块：顶（或右）端提亮，圆角用 alpha 蒙版实现。

    不用 imshow+clip_path —— mpl ≥3.8 起 set_clip_path 不再接受
    (patch, transform) 元组，只传 patch 又不生效。把圆角写进 RGBA 的
    alpha 通道后，跨版本稳定，圆角也不会被方形切片盖掉。
    """
    if w <= 0 or h <= 0:
        return
    W, H = 128, 384
    base = to_rgba(hex_color)
    top_c = _lighten(hex_color, lift)

    # 渐变：vertical=True 时上亮下暗；否则左暗右亮
    if vertical:
        t = np.linspace(0.0, 1.0, H).reshape(H, 1)
    else:
        t = np.linspace(0.0, 1.0, W).reshape(1, W)
    rgb = np.empty((H, W, 3))
    for k in range(3):
        rgb[:, :, k] = top_c[k] + (base[k] - top_c[k]) * t

    # 圆角蒙版：在数据坐标下判定，避免宽高比把圆角拉成椭圆
    u = (np.arange(W) + 0.5) / W
    v = (np.arange(H) + 0.5) / H
    dx = (np.minimum(u, 1.0 - u) * w)[None, :]      # (1, W)
    dy = (np.minimum(v, 1.0 - v) * h)[:, None]      # (H, 1)
    r = float(max(radius, 0.0))
    alpha = np.ones((H, W))
    if r > 0:
        yy, xx = np.nonzero((dy < r) & (dx < r))
        if yy.size:
            ddx = r - dx[0, xx]
            ddy = r - dy[yy, 0]
            alpha[yy, xx] = (ddx * ddx + ddy * ddy) <= r * r

    ax.imshow(np.dstack([rgb, alpha]), extent=(x, x + w, y, y + h),
              aspect="auto", interpolation="bilinear", zorder=zorder)


# ---------------------------------------------------------------- 各类型
def _bar(ax, data, S, t):
    cats = [str(x) for x in (data.get("categories") or [])]
    vals = [_cr._f(x) for x in (data.get("values") or [])]
    if not cats or not vals:
        return False
    unit = str(data.get("unit") or "")
    ymax = max(vals) or 1
    ax.set_ylim(0, ymax * 1.18)
    x = np.arange(len(cats))
    w = 0.52
    for i, (xi, v) in enumerate(zip(x, vals)):
        # 「我们的项目」高亮成强调色，评委一眼看到自己
        if any(k in cats[i] for k in ("我们的项目", "本项目", "我们")):
            col = ACCENT
        else:
            col = S[0] if len(cats) > 1 else S[i % len(S)]
        top = v
        # 投影
        ax.add_patch(Rectangle((xi - w / 2 + 0.035, -ymax * 0.012), w, ymax * 0.012,
                               facecolor=(0, 0, 0, 0.34), edgecolor="none", zorder=1))
        # 圆角柱体 + 同色系渐变（升级点 4/5）
        radius = min(w * 0.34, top * 0.05) if top > 0 else 0
        ax.add_patch(FancyBboxPatch((xi - w / 2, 0), w, top,
                                    boxstyle=f"round,pad=0,rounding_size={radius}",
                                    facecolor=col, edgecolor="none", zorder=3))
        _grad_round(ax, xi - w / 2, 0, w, top, col, radius, zorder=4)
        # 数据标签 + 描边
        ax.text(xi, top + ymax * 0.035, f"{_fmt(v)}{unit}", ha="center", va="bottom",
                fontsize=12.5, color=FG, fontweight="bold", zorder=6)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, color=FG)
    if data.get("ylabel"):
        ax.set_ylabel(str(data["ylabel"]), color=FG_DIM, fontsize=11.5)
    return True


def _hbar(ax, data, S, t):
    """横向条形图：适合竞品/能力排名对比（从上到下按值递减展示）。"""
    cats = [str(x) for x in (data.get("categories") or [])]
    vals = [_cr._f(x) for x in (data.get("values") or [])]
    if not cats or not vals:
        return False
    unit = str(data.get("unit") or "")
    # 反转，让最大值排在最上面
    cats = cats[::-1]
    vals = vals[::-1]
    y = np.arange(len(cats))
    w = 0.56
    xmax = max(vals) or 1
    ax.set_xlim(0, xmax * 1.18)
    for i, (yi, v) in enumerate(zip(y, vals)):
        if any(k in cats[i] for k in ("我们的项目", "本项目", "我们")):
            col = ACCENT
        else:
            col = S[i % len(S)]
        radius = min(w * 0.32, v * 0.06) if v > 0 else 0
        ax.add_patch(FancyBboxPatch((0, yi - w / 2), v, w,
                                    boxstyle=f"round,pad=0,rounding_size={radius}",
                                    facecolor=col, edgecolor="none", zorder=3))
        _grad_round(ax, 0, yi - w / 2, v, w, col, radius, vertical=False, zorder=4)
        ax.text(v + xmax * 0.02, yi, f"{_fmt(v)}{unit}", va="center",
                fontsize=12.5, color=FG, fontweight="bold", zorder=6)
    ax.set_yticks(y)
    ax.set_yticklabels(cats, color=FG, fontsize=11.5)
    ax.set_ylim(-0.6, len(cats) - 0.4)
    if data.get("xlabel"):
        ax.set_xlabel(str(data["xlabel"]), color=FG_DIM, fontsize=11.5)
    return True


def _heatmap(ax, data, S, t):
    """风险热力矩阵：rows × cols 的格子，强度 0~3 → 空/绿/黄/红。"""
    rows = [str(x) for x in (data.get("rows") or [])]
    cols = [str(x) for x in (data.get("cols") or [])]
    vals = data.get("values") or []
    if not rows or not cols:
        return False
    R, C = len(rows), len(cols)
    cmap = {0: "#26304E", 1: "#1F8A70", 2: "#B07A18", 3: "#C0392B"}
    for i in range(R):
        for j in range(C):
            try:
                v = float(vals[i][j])
            except Exception:
                v = 0.0
            lvl = 0 if v <= 0 else (1 if v < 1.5 else (2 if v < 2.5 else 3))
            col = cmap[lvl]
            ax.add_patch(Rectangle((j, R - 1 - i), 1, 1,
                                   facecolor=to_rgba(col, 0.92),
                                   edgecolor=t["card"], linewidth=2.5, zorder=2))
            ax.text(j + 0.5, R - 1 - i + 0.5, _fmt(v), ha="center", va="center",
                    fontsize=13, fontweight="bold",
                    color=("#0B1026" if lvl in (2, 3) else FG), zorder=3)
    ax.set_xlim(0, C)
    ax.set_ylim(0, R)
    ax.set_xticks([j + 0.5 for j in range(C)])
    ax.set_xticklabels(cols, color=FG, fontsize=11.5)
    ax.set_yticks([i + 0.5 for i in range(R)])
    ax.set_yticklabels(rows[::-1], color=FG, fontsize=11.5)
    ax.tick_params(length=0)
    return True


def _stacked(ax, data, S, t):
    """堆叠柱状图：展示构成/占比随类别变化（收入结构、成本结构、渠道结构）。"""
    cats = [str(x) for x in (data.get("categories") or [])]
    series = data.get("series") or []
    if not cats or not series:
        return False
    x = np.arange(len(cats))
    w = 0.52
    bottom = np.zeros(len(cats))
    for i, s in enumerate(series[:4]):
        vals = [_cr._f(v) for v in (s.get("values") or [])][: len(cats)]
        vals = np.array(vals + [0.0] * (len(cats) - len(vals)))
        col = S[i % len(S)]
        ax.bar(x, vals, width=w, bottom=bottom, color=col,
               edgecolor=t["card"], linewidth=1.5, zorder=3)
        bottom = bottom + vals
    ax.set_xticks(x)
    ax.set_xticklabels(cats, color=FG)
    if data.get("ylabel"):
        ax.set_ylabel(str(data["ylabel"]), color=FG_DIM, fontsize=11.5)
    ax.legend([str(s.get("name") or f"系列{i+1}") for i, s in enumerate(series[:4])],
              fontsize=10, frameon=False, labelcolor=FG_DIM)
    return True


def _gauge(ax, data, S, t):
    """进度环：单个指标完成度/评分，中心大字显示数值。"""
    val = _cr._f(data.get("value"))
    mx = _cr._f(data.get("max")) or 100.0
    if mx <= 0:
        return False
    ratio = max(0.0, min(1.0, val / mx))
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.xaxis.grid(False)
    ax.yaxis.grid(False)
    r = 0.62
    theta_bg = np.linspace(0, 2 * np.pi, 320)
    ax.plot(np.cos(theta_bg) * r, np.sin(theta_bg) * r,
            color=AXIS, linewidth=16, zorder=2)
    if ratio > 0:
        theta = np.linspace(-np.pi / 2, -np.pi / 2 + ratio * 2 * np.pi, 240)
        ax.plot(np.cos(theta) * r, np.sin(theta) * r, color=ACCENT,
                linewidth=16, solid_capstyle="round", zorder=3)
    ax.text(0, 0.06, f"{_fmt(val)}{str(data.get('unit') or '')}",
            ha="center", va="center", fontsize=32, color=FG,
            fontweight="bold", zorder=4)
    ax.text(0, -0.3, str(data.get("label") or ""), ha="center", va="center",
            fontsize=13, color=FG_DIM, zorder=4)
    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-1.15, 1.15)
    ax.set_aspect("equal")
    return True


def _line(ax, data, S, t):
    xs = [str(x) for x in (data.get("x") or [])]
    series = data.get("series") or []
    if not xs or not series:
        return False
    xi = np.arange(len(xs))
    for i, s in enumerate(series[:4]):
        vs = [_cr._f(x) for x in (s.get("values") or [])][: len(xs)]
        vs += [0] * (len(xs) - len(vs))
        col = S[i % len(S)]
        ax.plot(xi, vs, marker="o", markersize=8, linewidth=3.0, color=col,
                markerfacecolor=t["card"], markeredgecolor=col, markeredgewidth=2.4,
                label=str(s.get("name") or f"系列{i+1}"), zorder=5)
        ax.fill_between(xi, vs, color=col, alpha=0.16, zorder=2)
        for a, b in zip(xi, vs):
            ax.text(a, b, f"{_fmt(b)}", ha="center", va="bottom", fontsize=10.5,
                    color=col, fontweight="bold", zorder=6)
    ax.set_xticks(xi)
    ax.set_xticklabels(xs, color=FG)
    if data.get("ylabel"):
        ax.set_ylabel(str(data["ylabel"]), color=FG_DIM, fontsize=11.5)
    ax.legend(fontsize=11, frameon=True, facecolor=t["card"], edgecolor=AXIS,
              labelcolor=FG, loc="upper left")
    return True


def _pie(ax, data, S, t, donut=True):
    labels = [str(x) for x in (data.get("labels") or [])]
    values = [_cr._f(x) for x in (data.get("values") or [])]
    if not labels or not values or sum(values) <= 0:
        return False
    total = sum(values)
    w = ax.pie(
        values, labels=None, autopct=None, startangle=95,
        colors=S[: len(values)],
        wedgeprops={"width": 0.44 if donut else 1.0, "edgecolor": t["card"], "linewidth": 3},
        pctdistance=0.8)[0]
    # 引导线 + 外置标签（升级点 8）
    for i, (lb, v) in enumerate(zip(labels, values)):
        ang = (w[i].theta2 + w[i].theta1) / 2.0
        rad = np.deg2rad(ang)
        r0, r1 = 0.62, 0.92
        x0, y0 = r0 * np.cos(rad), r0 * np.sin(rad)
        x1, y1 = r1 * np.cos(rad), r1 * np.sin(rad)
        ax.plot([x0, x1], [y0, y1], color=S[i % len(S)], linewidth=1.4, alpha=0.85)
        ha = "left" if np.cos(rad) >= 0 else "right"
        ax.text(x1 * 1.06, y1 * 1.06, f"{lb}\n{v/total*100:.0f}%", ha=ha, va="center",
                fontsize=12, color=FG, fontweight="bold",
                linespacing=1.35)
    if donut:
        ax.text(0, 0.08, f"{_fmt(total)}", ha="center", va="center",
                fontsize=26, color=FG, fontweight="bold")
        ax.text(0, -0.16, str(data.get("unit") or "合计"), ha="center", va="center",
                fontsize=11.5, color=FG_MUTE)
    ax.axis("equal")
    return True


def _radar(fig, data, S, t):
    import math
    labels = [str(x) for x in (data.get("labels") or [])]
    series = data.get("series") or []
    if len(labels) < 3 or not series:
        return False
    n = len(labels)
    ang = [i * 2 * math.pi / n for i in range(n)]
    ax = fig.add_subplot(111, projection="polar", facecolor=t["bg"])
    ax.set_facecolor(t["bg"])
    step = 0.9 / max(n - 1, 1)
    for i, s in enumerate(series[:4]):
        vs = [_cr._f(x) for x in (s.get("values") or [])][:n]
        vs += [0] * (n - len(vs))
        col = S[i % len(S)]
        a2 = ang + ang[:1]
        v2 = vs + vs[:1]
        ax.plot(a2, v2, linewidth=2.8, color=col,
                label=str(s.get("name") or f"系列{i+1}"), zorder=4 + i)
        ax.fill(a2, v2, color=col, alpha=0.20 if i else 0.30, zorder=2 + i)   # 升级点 9
        ax.scatter(a2[:-1], v2[:-1], s=42, color=t["bg"], edgecolor=col,
                   linewidths=2.2, zorder=7)
    ax.set_xticks(ang)
    ax.set_xticklabels(labels, fontsize=13, color=FG, fontweight="bold")
    ax.tick_params(colors=FG_DIM, labelsize=10.5)
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], color=FG_MUTE, fontsize=9.5)
    ax.grid(color=AXIS, linewidth=0.9, alpha=0.55)
    ax.spines["polar"].set_color(AXIS)
    ax.legend(fontsize=11.5, frameon=True, facecolor=t["card"], edgecolor=AXIS,
              labelcolor=FG, loc="upper right", bbox_to_anchor=(1.24, 1.14))
    return ax


def _gantt(ax, data, S, t):
    stages = data.get("stages") or []
    if not stages:
        return False
    names = [str(s.get("name") or f"阶段{i+1}") for i, s in enumerate(stages)]
    starts = [_cr._f(s.get("start")) for s in stages]
    ends = [_cr._f(s.get("end")) for s in stages]
    for i in range(len(stages)):
        if ends[i] <= starts[i]:
            ends[i] = starts[i] + 1
    total = max(ends) or 1
    ypos = list(range(len(stages)))[::-1]
    h = 0.46
    for i, y in enumerate(ypos):
        col = S[i % len(S)]
        last = (i == len(stages) - 1)
        ax.add_patch(Rectangle((starts[i] + 0.06, y - h / 2 - 0.05), ends[i] - starts[i], h,
                               facecolor=(0, 0, 0, 0.32), zorder=1))     # 投影
        ax.add_patch(FancyBboxPatch((starts[i], y - h / 2), ends[i] - starts[i], h,
                                    boxstyle=f"round,pad=0,rounding_size={h*0.32}",
                                    facecolor=col, edgecolor="none", zorder=3))
        _grad_round(ax, starts[i], y - h / 2, ends[i] - starts[i], h, col,
                    h * 0.32, lift=0.36, vertical=False, zorder=4)
        ax.text(starts[i] + (ends[i] - starts[i]) / 2, y,
                str(stages[i].get("label") or f"{starts[i]:g}-{ends[i]:g}"),
                va="center", ha="center", fontsize=11.5,
                color=("#0B1026" if _lum(col) > 0.45 else "#EDF2FF"),
                fontweight="bold", zorder=6)
    ax.set_yticks(ypos)
    ax.set_yticklabels(names, fontsize=12.5, color=FG, fontweight="bold")
    ax.set_xlim(-0.4, total * 1.04)
    ax.set_xticks(list(range(0, int(total) + 1)))
    ax.set_xticklabels([f"第{i}周" if i else "启动" for i in range(0, int(total) + 1)],
                       color=FG_DIM, fontsize=10.5)
    ax.xaxis.grid(False)
    ax.yaxis.grid(False)
    if data.get("xlabel"):
        ax.set_xlabel(str(data["xlabel"]), color=FG_DIM, fontsize=11.5)
    return True


def _arch(ax, data, S, t):
    layers = data.get("layers") or []
    if not layers:
        return False
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    n = len(layers)
    gap = 0.045
    h = (0.90 - gap * (n - 1)) / max(n, 1)
    for i, layer in enumerate(layers):
        top = 0.94 - i * (h + gap)
        col = S[i % len(S)]
        ax.add_patch(FancyBboxPatch((0.035, top - h), 0.93, h,
                                    boxstyle=f"round,pad=0,rounding_size={h*0.22}",
                                    facecolor=to_rgba(col, 0.13), edgecolor=col,
                                    linewidth=2.0, zorder=2))
        # 层名：左侧标签块
        ax.add_patch(FancyBboxPatch((0.055, top - h + h * 0.22), 0.155, h * 0.56,
                                    boxstyle=f"round,pad=0,rounding_size={h*0.16}",
                                    facecolor=col, edgecolor="none", zorder=3))
        ax.text(0.1325, top - h / 2, str(layer.get("name") or f"层{i+1}")[:8],
                va="center", ha="center", fontsize=13, color="#0B1026",
                fontweight="bold", zorder=4)
        boxes = layer.get("boxes") or []
        m = min(len(boxes), 5)
        for j, b in enumerate(boxes[:5]):
            bw = (0.90 - 0.245) / max(m, 1) - 0.018
            bx = 0.245 + j * (bw + 0.018)
            ax.add_patch(FancyBboxPatch((bx, top - h + h * 0.20), bw, h * 0.60,
                                        boxstyle=f"round,pad=0,rounding_size={h*0.14}",
                                        facecolor=to_rgba(col, 0.30),
                                        edgecolor=to_rgba(_lighten(col, 0.30), 0.9),
                                        linewidth=1.3, zorder=3))
            ax.text(bx + bw / 2, top - h / 2, str(b)[:7], va="center", ha="center",
                    fontsize=11.5, color=FG, fontweight="bold", zorder=4)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch((0.5, top - h - 0.004), (0.5, top - h - gap + 0.004),
                                         arrowstyle="-|>", mutation_scale=15,
                                         color=FG_MUTE, linewidth=1.6, zorder=5))
    return True


def _quadrant(ax, data, S, t):
    pts = data.get("points") or []
    if not pts:
        return False
    xs = [_cr._f(p.get("x")) for p in pts]
    ys = [_cr._f(p.get("y")) for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    px = max((xmax - xmin) * 0.30, 1.0)
    py = max((ymax - ymin) * 0.30, 1.0)
    x0, x1 = xmin - px, xmax + px
    y0, y1 = ymin - py, ymax + py
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    # 象限浅色分区（升级点 12）
    for (qa, qb, ca) in [((mx, x1), (my, y1), S[0]), ((x0, mx), (my, y1), S[1]),
                         ((x0, mx), (y0, my), S[2]), ((mx, x1), (y0, my), S[3])]:
        ax.add_patch(Rectangle((qa[0], qb[0]), qa[1] - qa[0], qb[1] - qb[0],
                               facecolor=to_rgba(ca, 0.07), edgecolor="none", zorder=0))
    ax.axhline(my, color=AXIS, linewidth=1.3, linestyle=(0, (5, 4)), zorder=1)
    ax.axvline(mx, color=AXIS, linewidth=1.3, linestyle=(0, (5, 4)), zorder=1)
    for i, (p, x, y) in enumerate(zip(pts, xs, ys)):
        me = "我们的项目" in str(p.get("name") or "") or i == 0
        col = ACCENT if me else S[(i + 1) % len(S)]
        ax.scatter([x], [y], s=560 if me else 380, color=col, alpha=0.95,
                   edgecolors="#FFFFFF" if me else t["card"],
                   linewidths=2.6 if me else 1.8, zorder=5)
        ax.annotate(str(p.get("name") or "")[:9], (x, y),
                    textcoords="offset points", xytext=(0, 20 if me else 16),
                    fontsize=12.5 if me else 11.5,
                    color=FG if me else FG_DIM,
                    fontweight="bold" if me else "normal", ha="center", zorder=6)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xlabel(str(data.get("xlabel") or ""), color=FG_DIM, fontsize=12)
    ax.set_ylabel(str(data.get("ylabel") or ""), color=FG_DIM, fontsize=12)
    ax.yaxis.grid(False)
    ax.xaxis.grid(False)
    return True


def _funnel(ax, data, S, t):
    labels = [str(x) for x in (data.get("labels") or [])]
    values = [_cr._f(x) for x in (data.get("values") or [])]
    if not labels or not values:
        return False
    mx = max(values) or 1
    ypos = list(range(len(labels)))[::-1]
    ax.set_xlim(0, 1.10)
    ax.set_ylim(-0.55, len(labels) - 0.45)
    for i, (y, v, lab) in enumerate(zip(ypos, values, labels)):
        w = v / mx
        col = S[i % len(S)]
        ax.add_patch(FancyBboxPatch((0.02, y - 0.26), w * 0.86, 0.52,
                                    boxstyle="round,pad=0,rounding_size=0.09",
                                    facecolor=col, edgecolor="none", zorder=3))
        _grad_round(ax, 0.02, y - 0.26, w * 0.86, 0.52, col, 0.09,
                    lift=0.34, vertical=False, zorder=4)
        bar_end = 0.02 + w * 0.86
        # 标签放条内还是条外：按「标签估宽 + 余量」能否塞进条里判断，
        # 否则窄条标签会溢出压到右侧数值（深字压深底也不可读）。
        lab_w = 0.031 * len(lab)          # CJK 字符在当前坐标系下的估宽
        if w * 0.86 >= lab_w + 0.05:
            txt_col = "#0B1026" if _lum(col) > 0.55 else "#FFFFFF"
            ax.text(0.045, y, lab, va="center", fontsize=12.5, color=txt_col,
                    fontweight="bold", zorder=6)
            val_x = bar_end + 0.025
        else:
            ax.text(bar_end + 0.022, y, lab, va="center", fontsize=12.5,
                    color=FG, fontweight="bold", zorder=6)
            val_x = bar_end + 0.030 + lab_w + 0.015
        ax.text(val_x, y, f"{_fmt(v)}", va="center", fontsize=12,
                color=FG, fontweight="bold", zorder=6)
    ax.set_yticks(ypos)
    ax.set_yticklabels([""] * len(labels))
    ax.axis("off")
    return True


def render(chart, out_dir, theme=None):
    """与 chart_renderer.render 同签名：chart 定义 → PNG 路径 / None"""
    t = set_theme(theme)
    try:
        if not isinstance(chart, dict):
            return None
        cid = str(chart.get("id") or "chart")
        ctype = str(chart.get("type") or "").lower()
        data = chart.get("data") or {}
        title = chart.get("title")
        caption = chart.get("caption")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"chart_{cid}.png")

        # 类型兜底推断：rich_pipeline 有时没写 type，按 data 的键猜
        if not ctype:
            if "layers" in data:
                ctype = "architecture"
            elif "stages" in data:
                ctype = "timeline"
            elif "points" in data:
                ctype = "matrix"
            elif "series" in data and ("labels" in data or "x" in data):
                ctype = "radar" if "labels" in data else "line"
            elif "categories" in data:
                ctype = "bar"
            elif "labels" in data:
                ctype = "pie"

        if ctype in ("radar",):
            fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
            fig.patch.set_facecolor(t["bg"])
            ax = _radar(fig, data, t["series"], t)
            if ax is False:
                plt.close(fig)
                return None
            fig.text(0.045, 0.955, "▍", fontsize=21, color=ACCENT, va="top", fontweight="bold")
            if title:
                fig.text(0.072, 0.952, str(title)[:44], fontsize=20, color=FG,
                         va="top", fontweight="bold")
            if caption:
                fig.text(0.5, 0.045, "· " + str(caption)[:64], fontsize=11.5,
                         color=ACCENT, ha="center", va="center")
            return _save(fig, path)

        if ctype in ("architecture", "arch"):
            fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
            fig.patch.set_facecolor(t["bg"])
            ax.set_facecolor(t["card"])
            if not _arch(ax, data, t["series"], t):
                plt.close(fig)
                return None
            _head(fig, title, caption, t)
            return _save(fig, path)

        fig, ax = _fig(t)
        ok = False
        if ctype in ("pie", "donut"):
            ok = _pie(ax, data, t["series"], t, donut=(ctype == "donut" or True))
        elif ctype in ("bar", "column"):
            ok = _bar(ax, data, t["series"], t)
        elif ctype in ("hbar", "hcolumn", "rank"):
            ok = _hbar(ax, data, t["series"], t)
        elif ctype in ("heatmap", "risk", "riskmap"):
            ok = _heatmap(ax, data, t["series"], t)
        elif ctype in ("stacked", "stackbar"):
            ok = _stacked(ax, data, t["series"], t)
        elif ctype in ("gauge", "progress", "ring"):
            ok = _gauge(ax, data, t["series"], t)
        elif ctype in ("line", "trend"):
            ok = _line(ax, data, t["series"], t)
        elif ctype in ("timeline", "gantt"):
            ok = _gantt(ax, data, t["series"], t)
        elif ctype in ("matrix", "quadrant"):
            ok = _quadrant(ax, data, t["series"], t)
        elif ctype == "funnel":
            ok = _funnel(ax, data, t["series"], t)
        else:
            pairs = [(str(k), _cr._f(v)) for k, v in (data or {}).items()
                     if isinstance(v, (int, float, str))]
            if pairs:
                ok = _bar(ax, {"categories": [p[0][:8] for p in pairs[:8]],
                               "values": [p[1] for p in pairs[:8]]}, t["series"], t)
        if not ok:
            plt.close(fig)
            return None
        _head(fig, title, caption, t)
        return _save(fig, path)
    except Exception as e:
        print(f"[chart_renderer_pro] render 失败：{e}")
        return None


def render_charts(chart_data):
    """与 chart_renderer.render_charts 同输入输出：{budget, market, timeline} → [{url, title, caption}]。

    内部改用本文件的「路演级」渲染（dpi 200 / 渐变 / 环形 / 卡片底），app.py 可直接替换 import 无缝切换。
    """
    if not isinstance(chart_data, dict) or not chart_data:
        return []
    out_dir = "generated"
    os.makedirs(out_dir, exist_ok=True)
    results = []

    # 1) 预算构成 → 环形图
    budget = chart_data.get("budget") or []
    if isinstance(budget, list) and budget:
        labels = [str(b.get("name", "") or "") for b in budget]
        values = [_cr._f(b.get("value", 0)) for b in budget]
        if labels and any(v > 0 for v in values):
            spec = {"id": "budget", "type": "donut", "title": "预算构成",
                    "caption": "成本结构占比",
                    "data": {"labels": labels, "values": values}}
            if render(spec, out_dir):
                results.append({"url": "/generated/chart_budget.png",
                                "title": "预算构成", "caption": "成本结构占比"})

    # 2) 市场规模 → 柱状图
    market = chart_data.get("market") or {}
    years = [str(y) for y in (market.get("years") or [])]
    values = [_cr._f(v) for v in (market.get("values") or [])]
    if years and values and len(years) == len(values):
        spec = {"id": "market", "type": "bar", "title": "市场规模预测",
                "caption": "逐年市场空间（万元）",
                "data": {"categories": years, "values": values, "unit": "万元"}}
        if render(spec, out_dir):
            results.append({"url": "/generated/chart_market.png",
                            "title": "市场规模预测", "caption": "逐年市场空间（万元）"})

    # 3) 实施进度 → 折线图
    timeline = chart_data.get("timeline") or {}
    stages = [str(s) for s in (timeline.get("stages") or [])]
    progress = [_cr._f(v) for v in (timeline.get("progress") or [])]
    if stages and progress and len(stages) == len(progress):
        spec = {"id": "timeline", "type": "line", "title": "实施进度",
                "caption": "分阶段推进节奏",
                "data": {"x": stages, "series": [{"name": "进度", "values": progress}]}}
        if render(spec, out_dir):
            results.append({"url": "/generated/chart_timeline.png",
                            "title": "实施进度", "caption": "分阶段推进节奏"})

    return results
