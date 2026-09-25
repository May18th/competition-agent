"""图表渲染：把结构化数据渲染成 PNG 图片（供前端 rich_charts 和 PPT 使用）"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


# 中文字体（Windows 微软雅黑）
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]
for _fp in _FONT_CANDIDATES:
    if os.path.exists(_fp):
        try:
            font_manager.fontManager.addfont(_fp)
            _name = font_manager.FontProperties(fname=_fp).get_name()
            plt.rcParams["font.sans-serif"] = [_name]
            break
        except Exception:
            continue
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = "generated"


def _ensure_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def render_charts(chart_data):
    """chart_data: {budget, market, timeline} → [{url, title, caption}]"""
    if not isinstance(chart_data, dict) or not chart_data:
        return []
    _ensure_dir()
    results = []

    # 1) 预算构成饼图
    budget = chart_data.get("budget") or []
    if isinstance(budget, list) and budget:
        labels = [str(b.get("name", "") or "") for b in budget]
        values = [float(b.get("value", 0) or 0) for b in budget]
        if labels and any(v > 0 for v in values):
            fig, ax = plt.subplots(figsize=(5.2, 3.6), dpi=110)
            ax.pie(
                values,
                labels=labels,
                autopct="%1.0f%%",
                startangle=90,
                colors=["#667EEA", "#22B8CF", "#C084FC", "#F59E0B", "#34D399"],
                textprops={"color": "#1A1A2E", "fontsize": 11},
            )
            ax.axis("equal")
            fig.tight_layout()
            fig.savefig(os.path.join(OUT_DIR, "chart_budget.png"), transparent=True)
            plt.close(fig)
            results.append({"url": "/generated/chart_budget.png", "title": "预算构成", "caption": "成本结构占比"})

    # 2) 市场规模柱状图
    market = chart_data.get("market") or {}
    years = market.get("years") or []
    values = market.get("values") or []
    if years and values and len(years) == len(values):
        fig, ax = plt.subplots(figsize=(5.2, 3.6), dpi=110)
        ax.bar(years, values, color="#22B8CF", width=0.55)
        ax.set_ylabel("万元", fontsize=10)
        ax.tick_params(colors="#1A1A2E", labelsize=9)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "chart_market.png"), transparent=True)
        plt.close(fig)
        results.append({"url": "/generated/chart_market.png", "title": "市场规模预测", "caption": "逐年市场空间（万元）"})

    # 3) 实施进度折线图
    timeline = chart_data.get("timeline") or {}
    stages = timeline.get("stages") or []
    progress = timeline.get("progress") or []
    if stages and progress and len(stages) == len(progress):
        fig, ax = plt.subplots(figsize=(5.2, 3.6), dpi=110)
        ax.plot(stages, progress, marker="o", color="#C084FC", linewidth=2)
        ax.fill_between(range(len(stages)), progress, color="#C084FC", alpha=0.16)
        ax.set_ylim(0, 110)
        ax.tick_params(colors="#1A1A2E", labelsize=9)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "chart_timeline.png"), transparent=True)
        plt.close(fig)
        results.append({"url": "/generated/chart_timeline.png", "title": "实施进度", "caption": "分阶段推进"})

    return results


# ==========================================================================
# 单图渲染器：rich_pipeline 走的是这个入口
#   render(chart_dict, out_dir) -> 图片绝对路径 / None
#   chart_dict = {"id":"c1","type":"bar","title":"...","caption":"...","data":{...}}
#
# 配色统一走深色底（#0F1535），和 pptx_builder 的深蓝版式、网页深色主题一致；
# 插到白底 Word 里也能看清（深色卡片）。
# 追加于 2026-09-25 by WorkBuddy：原 render_charts() 保持不动，供旧契约兼容。
# ==========================================================================
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

# ==========================================================================
# 多主题配色：与 pptx_builder 的 THEMES 对齐，图表 PNG 跟随 PPT 主题换系列色。
# 深色底 + 浅色文字统一不变，只有背景色与系列色随主题切换。
# ==========================================================================
_CHART_THEMES = {
    "tech": {"bg": "#0F1535", "series": ["#818CF8", "#22B8CF", "#C084FC", "#F59E0B", "#34D399", "#FB7185", "#A3E635"]},
    "ink": {"bg": "#1B1B1B", "series": ["#5A6B7A", "#8B2E2E", "#B98A3C", "#4A5D4E", "#6B5B73", "#2F4858", "#A65628"]},
    "medical": {"bg": "#09332F", "series": ["#0E9E8C", "#2E86C1", "#45B39D", "#F0B429", "#27AE60", "#5DADE2", "#16A085"]},
    "edu": {"bg": "#4A2410", "series": ["#E2803A", "#F0B429", "#C0563A", "#5B8C5A", "#4A7FB5", "#A463C8", "#D45B5B"]},
    "agri": {"bg": "#1E3D1A", "series": ["#4E8C3A", "#C9A227", "#7BA05B", "#6B8E23", "#3E7C59", "#A0703A", "#2E6B4F"]},
    "finance": {"bg": "#0C1A33", "series": ["#1F3864", "#B8860B", "#2E5C8A", "#C99700", "#40607A", "#8B6914", "#5B7A99"]},
    "craft": {"bg": "#1F2A30", "series": ["#5C6B73", "#E08A38", "#3D5A6C", "#A63A2F", "#7A8B5A", "#C77B3E", "#4A5D63"]},
    "social": {"bg": "#4A2320", "series": ["#D46A5C", "#E4A03C", "#5E8C7E", "#C2564F", "#7B6DA8", "#3E8C86", "#B5713C"]},
    "academic": {"bg": "#00254D", "series": ["#002FA7", "#2E75B6", "#4A7FB5", "#5B8C5A", "#8B6914", "#6B5B73", "#7E93AB"]},
    "cyber": {"bg": "#160826", "series": ["#7C3AED", "#22D3EE", "#A855F7", "#F472B6", "#8B5CF6", "#4B0082", "#F59E0B"]},
}


def set_theme(theme=None):
    """切换图表配色，与 pptx_builder 主题对齐；未知主题回退 tech。"""
    global BG, C1, C2, C3, C4, C5, SERIES_COLORS
    t = _CHART_THEMES.get(str(theme or "").lower()) or _CHART_THEMES["tech"]
    BG = t["bg"]
    s = t["series"]
    C1, C2, C3, C4, C5 = s[0], s[1], s[2], s[3], s[4]
    SERIES_COLORS = list(s)
    return str(theme or "tech").lower()

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


def render(chart, out_dir, theme=None):
    """把一张图表定义渲染成 PNG，返回文件路径；失败返回 None"""
    set_theme(theme)
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


# ---- 兜底（WorkBuddy 加，勿删）-------------------------------------------
# rich_pipeline.py 依赖本文件的 render()。本文件被重写过多次，
# 万一 render() 被覆盖丢失，从独立副本 chart_render_wb.py 自动补回，
# 避免整条富媒体链路因 ImportError 静默失效（表现是 rich_* 全空）。
if "render" not in dir():
    try:
        from chart_render_wb import render  # noqa: F401
        print("[chart_renderer] render 缺失，已从 chart_render_wb 补回")
    except Exception as _e:
        print("[chart_renderer] render 兜底导入失败：", _e)
# ---- 兜底结束 -------------------------------------------------------------
