# -*- coding: utf-8 -*-
"""
chart_render_wb.py —— 单图渲染器的独立副本（WorkBuddy）

存在理由：`rich_pipeline.py` 依赖 `chart_renderer.render(chart, out_dir)`，
而 chart_renderer.py 由 Codex 维护、被重写过多次，render 有被覆盖丢失的风险。
本文件是同一份实现的独立副本，chart_renderer.py 末尾有兜底导入：

    if "render" not in dir():
        from chart_render_wb import render

只要这个文件在，即使 chart_renderer 被重写也不会让整条富媒体链路 ImportError。

支持的 type：bar/column、line/trend、pie/donut、radar、matrix/quadrant、
timeline/gantt、funnel、architecture/arch；未知类型退化为柱状图。
配色：深色底 #0F1535 + 浅字，与 pptx_builder 深蓝版式、网页深色主题一致。
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for _fp in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"]:
    if os.path.exists(_fp):
        try:
            font_manager.fontManager.addfont(_fp)
            plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=_fp).get_name()]
            break
        except Exception:
            continue
plt.rcParams["axes.unicode_minus"] = False

BG = "#0F1535"
FG = "#E9EEFC"
FG_DIM = "#93A0C4"
AXIS = "#3A4470"
C1 = "#818CF8"
C2 = "#22B8CF"
C3 = "#C084FC"
C4 = "#F59E0B"
C5 = "#34D399"
SERIES_COLORS = [C1, C2, C3, C4, C5, "#FB7185", "#A3E635"]

_FIGSIZE = (10.0, 5.4)
_DPI = 110


def _new_fig():
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=FG_DIM, labelsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.yaxis.grid(True, color=AXIS, linewidth=0.7, linestyle="--", alpha=0.55)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig, path, title=None, caption=None):
    if title:
        fig.suptitle(str(title)[:40], fontsize=17, color=FG, fontweight="bold", y=0.97)
    if caption:
        fig.text(0.5, 0.028, str(caption)[:60], fontsize=10.5, color=C2, ha="center")
    fig.tight_layout(rect=(0.02, 0.06, 0.98, 0.92))
    fig.savefig(path, facecolor=BG, dpi=_DPI)
    plt.close(fig)
    return path


def _f(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def render(chart, out_dir):
    """把一张图表定义渲染成 PNG，返回文件路径；失败返回 None"""
    try:
        if not isinstance(chart, dict):
            return None
        cid = str(chart.get("id") or "chart")
        ctype = str(chart.get("type") or "bar").lower()
        data = chart.get("data") or {}
        title = chart.get("title")
        caption = chart.get("caption")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"chart_{cid}.png")

        if ctype in ("pie", "donut"):
            labels = [str(x) for x in (data.get("labels") or [])]
            values = [_f(x) for x in (data.get("values") or [])]
            if not labels or not values or sum(values) <= 0:
                return None
            fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
            fig.patch.set_facecolor(BG)
            w, t, a = ax.pie(
                values, labels=labels, autopct="%1.0f%%", startangle=95,
                colors=SERIES_COLORS[: len(values)],
                wedgeprops={"width": 0.42 if ctype == "donut" else 1.0,
                            "edgecolor": BG, "linewidth": 2},
                textprops={"color": FG, "fontsize": 12}, pctdistance=0.78)
            for x in a:
                x.set_color(BG)
                x.set_fontsize(11)
                x.set_fontweight("bold")
            ax.axis("equal")
            return _save(fig, path, title, caption)

        if ctype in ("bar", "column"):
            cats = [str(x) for x in (data.get("categories") or [])]
            vals = [_f(x) for x in (data.get("values") or [])]
            if not cats or not vals:
                return None
            fig, ax = _new_fig()
            bars = ax.bar(cats, vals, color=C1, width=0.55)
            for b, v in zip(bars, vals):
                ax.annotate(f"{v:g}", (b.get_x() + b.get_width() / 2, v),
                            textcoords="offset points", xytext=(0, 5),
                            ha="center", fontsize=10, color=FG, fontweight="bold")
            ax.set_ylabel(str(data.get("ylabel") or ""), color=FG_DIM, fontsize=10.5)
            return _save(fig, path, title, caption)

        if ctype in ("line", "trend"):
            xs = [str(x) for x in (data.get("x") or [])]
            series = data.get("series") or []
            if not xs or not series:
                return None
            fig, ax = _new_fig()
            for i, s in enumerate(series[:4]):
                vs = [_f(x) for x in (s.get("values") or [])][: len(xs)]
                vs += [0] * (len(xs) - len(vs))
                col = SERIES_COLORS[i % len(SERIES_COLORS)]
                ax.plot(xs, vs, marker="o", linewidth=2.4, color=col,
                        label=str(s.get("name") or f"系列{i+1}"))
                ax.fill_between(range(len(xs)), vs, color=col, alpha=0.12)
            ax.set_xticks(range(len(xs)))
            ax.set_xticklabels(xs)
            ax.set_ylabel(str(data.get("ylabel") or ""), color=FG_DIM, fontsize=10.5)
            ax.legend(fontsize=10, frameon=False, labelcolor=FG_DIM)
            return _save(fig, path, title, caption)

        if ctype == "radar":
            import math
            labels = [str(x) for x in (data.get("labels") or [])]
            series = data.get("series") or []
            if len(labels) < 3 or not series:
                return None
            n = len(labels)
            ang = [i * 2 * math.pi / n for i in range(n)]
            fig = plt.figure(figsize=_FIGSIZE, dpi=_DPI)
            fig.patch.set_facecolor(BG)
            ax = fig.add_subplot(111, projection="polar")
            ax.set_facecolor(BG)
            for i, s in enumerate(series[:3]):
                vs = [_f(x) for x in (s.get("values") or [])][:n]
                vs += [0] * (n - len(vs))
                col = SERIES_COLORS[i % len(SERIES_COLORS)]
                a2 = ang + ang[:1]
                v2 = vs + vs[:1]
                ax.plot(a2, v2, linewidth=2.2, color=col, label=str(s.get("name") or f"系列{i+1}"))
                ax.fill(a2, v2, color=col, alpha=0.18)
            ax.set_xticks(ang)
            ax.set_xticklabels(labels, fontsize=11.5, color=FG)
            ax.tick_params(colors=FG_DIM)
            ax.grid(color=AXIS, linewidth=0.8)
            ax.spines["polar"].set_color(AXIS)
            ax.legend(fontsize=10, frameon=False, labelcolor=FG_DIM,
                      loc="upper right", bbox_to_anchor=(1.18, 1.12))
            return _save(fig, path, title, caption)

        if ctype in ("matrix", "quadrant"):
            pts = data.get("points") or []
            if not pts:
                return None
            fig, ax = _new_fig()
            xs = [_f(p.get("x")) for p in pts]
            ys = [_f(p.get("y")) for p in pts]
            ax.scatter(xs, ys, s=260, color=C1, alpha=0.85, edgecolors=BG, linewidths=2)
            for p, x, y in zip(pts, xs, ys):
                ax.annotate(str(p.get("name") or "")[:10], (x, y),
                            textcoords="offset points", xytext=(10, 8),
                            fontsize=11.5, color=FG, fontweight="bold")
            pad = max(1.0, (max(xs) - min(xs)) * 0.25 if xs else 1)
            ax.set_xlim(min(xs) - pad, max(xs) + pad)
            ax.set_ylim(min(ys) - pad, max(ys) + pad)
            ax.axhline((min(ys) + max(ys)) / 2, color=AXIS, linewidth=1, linestyle="--")
            ax.axvline((min(xs) + max(xs)) / 2, color=AXIS, linewidth=1, linestyle="--")
            ax.set_xlabel(str(data.get("xlabel") or ""), color=FG_DIM, fontsize=11)
            ax.set_ylabel(str(data.get("ylabel") or ""), color=FG_DIM, fontsize=11)
            return _save(fig, path, title, caption)

        if ctype in ("timeline", "gantt"):
            stages = data.get("stages") or []
            if not stages:
                return None
            names = [str(s.get("name") or f"阶段{i+1}") for i, s in enumerate(stages)]
            starts = [_f(s.get("start")) for s in stages]
            ends = [_f(s.get("end")) for s in stages]
            for i in range(len(stages)):
                if ends[i] <= starts[i]:
                    ends[i] = starts[i] + 1
            ypos = list(range(len(stages)))[::-1]
            fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
            fig.patch.set_facecolor(BG)
            ax.set_facecolor(BG)
            colors = [SERIES_COLORS[i % len(SERIES_COLORS)] for i in range(len(stages))]
            ax.barh(ypos, [ends[i] - starts[i] for i in range(len(stages))],
                    left=starts, height=0.5, color=colors)
            for i, y in enumerate(ypos):
                lbl = str(stages[i].get("label") or f"{starts[i]:g}-{ends[i]:g}")
                ax.text(starts[i] + (ends[i] - starts[i]) / 2, y, lbl,
                        va="center", ha="center", fontsize=10.5, color="white", fontweight="bold")
            ax.set_yticks(ypos)
            ax.set_yticklabels(names, fontsize=11.5, color=FG)
            ax.set_xlabel(str(data.get("xlabel") or ""), color=FG_DIM, fontsize=11)
            ax.tick_params(colors=FG_DIM, labelsize=10)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            for s in ("left", "bottom"):
                ax.spines[s].set_color(AXIS)
            ax.xaxis.grid(True, color=AXIS, linewidth=0.7, linestyle="--", alpha=0.55)
            ax.set_axisbelow(True)
            return _save(fig, path, title, caption)

        if ctype == "funnel":
            labels = [str(x) for x in (data.get("labels") or [])]
            values = [_f(x) for x in (data.get("values") or [])]
            if not labels or not values:
                return None
            fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
            fig.patch.set_facecolor(BG)
            ax.set_facecolor(BG)
            mx = max(values) or 1
            ypos = list(range(len(labels)))[::-1]
            widths = [v / mx for v in values]
            ax.barh(ypos, widths, height=0.55, color=[SERIES_COLORS[i % len(SERIES_COLORS)] for i in range(len(labels))])
            for y, v, lab in zip(ypos, values, labels):
                ax.text(0.02, y, f"{lab}  {v:g}", va="center", fontsize=11.5, color=FG, fontweight="bold")
            ax.set_yticks([])
            ax.set_xlim(0, 1.08)
            ax.axis("off")
            return _save(fig, path, title, caption)

        if ctype in ("architecture", "arch"):
            layers = data.get("layers") or []
            if not layers:
                return None
            fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
            fig.patch.set_facecolor(BG)
            ax.set_facecolor(BG)
            ax.axis("off")
            n = len(layers)
            h = 0.82 / max(n, 1)
            for i, layer in enumerate(layers):
                top = 0.9 - i * (h + 0.06)
                ax.add_patch(plt.Rectangle((0.05, top - h), 0.9, h,
                                           facecolor=BG, edgecolor=SERIES_COLORS[i % len(SERIES_COLORS)],
                                           linewidth=2.2, joinstyle="round"))
                ax.text(0.085, top - h / 2, str(layer.get("name") or f"层{i+1}")[:12],
                        va="center", ha="left", fontsize=12.5, color=FG, fontweight="bold")
                boxes = layer.get("boxes") or []
                for j, b in enumerate(boxes[:5]):
                    bx = 0.30 + j * 0.135
                    ax.add_patch(plt.Rectangle((bx, top - h + 0.055), 0.115, h - 0.11,
                                               facecolor=SERIES_COLORS[i % len(SERIES_COLORS)],
                                               alpha=0.22, edgecolor=SERIES_COLORS[i % len(SERIES_COLORS)],
                                               linewidth=1.3, joinstyle="round"))
                    txt = str(b)[:6]
                    ax.text(bx + 0.0575, top - h / 2, txt, va="center", ha="center",
                            fontsize=10, color=FG)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            return _save(fig, path, title, caption)

        # 未知类型：退化成柱状图（取 data 里能找到的第一组键值对）
        pairs = [(str(k), _f(v)) for k, v in (data or {}).items()
                 if isinstance(v, (int, float, str))]
        if not pairs:
            return None
        fig, ax = _new_fig()
        ax.bar([p[0][:8] for p in pairs[:8]], [p[1] for p in pairs[:8]], color=C1, width=0.55)
        return _save(fig, path, title, caption)
    except Exception as e:
        print(f"[chart_renderer] render 失败：{e}")
        return None
