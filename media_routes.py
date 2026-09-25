# -*- coding: utf-8 -*-
"""
media_routes.py —— 媒体蓝图（表格 / 图表 / PPT）

对外接口：
  POST /api/media/build          提交任务，异步生成图表 + PPT + 富格式 Word
  GET  /api/media/status/<tid>   轮询进度与产物清单
  GET  /api/media/file/<tid>/<name>  预览或下载某个产物
  POST /api/media/docx           把任意一段文本导出成带真表格的 Word（可插图）

本文件只通过 Flask Blueprint 挂载，不改动 app.py 的既有路由。
注册方式见项目根的 patch_register_media.py。

作者：WorkBuddy（阿渡）  2026-09-25
"""
import os
import io
import re
import time
import uuid
import threading

from flask import Blueprint, request, jsonify, send_file

import media_factory as mf
import deck_agent

media_bp = Blueprint("media", __name__, url_prefix="/api/media")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "media_out")
os.makedirs(OUT_DIR, exist_ok=True)

_tasks = {}
_lock = threading.Lock()

CHART_TITLES = {
    "radar": "项目综合评分雷达图",
    "competitor": "竞品能力对比",
    "finance": "三年财务预测",
    "timeline": "项目实施计划（甘特图）",
    "budget": "预算构成占比",
}

# 产物保留数量，防止磁盘无限增长
MAX_TASKS = 30


def _safe_filename(name):
    name = re.sub(r"[\\/:*?\"<>|]+", "_", str(name))
    return name[:80]


def render_charts(visuals):
    """把 visuals 数据渲染成 PNG，返回 {key: bytes}"""
    charts = {}
    v = visuals or {}

    r = v.get("radar") or {}
    if r.get("labels") and r.get("values"):
        try:
            charts["radar"] = mf.chart_score_radar(r["labels"], r["values"], "项目综合评分雷达图")
        except Exception:
            pass

    c = v.get("competitor") or {}
    if c.get("items") and c.get("metrics") and c.get("matrix"):
        try:
            charts["competitor"] = mf.chart_competitor(c["items"], c["metrics"], c["matrix"],
                                                       "竞品能力对比（满分 10 分）")
        except Exception:
            pass

    f = v.get("finance") or {}
    if f.get("years") and f.get("revenue"):
        try:
            unit = f.get("unit") or "万元"
            charts["finance"] = mf.chart_finance(f["years"], f.get("revenue"), f.get("cost"),
                                                 f.get("profit"), unit,
                                                 f"三年财务预测（单位：{unit}）")
        except Exception:
            pass

    t = v.get("timeline") or {}
    if t.get("phases"):
        try:
            charts["timeline"] = mf.chart_timeline(t["phases"], t.get("start_week"),
                                                   t.get("end_week"),
                                                   "项目实施计划（甘特图）")
        except Exception:
            pass

    b = v.get("budget") or {}
    if b.get("labels") and b.get("values"):
        try:
            charts["budget"] = mf.chart_budget(b["labels"], b["values"], "预算构成占比")
        except Exception:
            pass

    return {k: v for k, v in charts.items() if v}


def _worker(task_id, state):
    try:
        with _lock:
            _tasks[task_id] = {"status": "running", "stage": "正在提取结构化数据",
                               "updated_at": time.time()}

        plan = deck_agent.build_media_plan(state)
        visuals = plan.get("visuals") or {}
        deck = plan.get("deck") or {}

        with _lock:
            _tasks[task_id]["stage"] = "正在绘制图表"

        charts = render_charts(visuals)

        task_dir = os.path.join(OUT_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        chart_list = []
        for key, png in charts.items():
            fname = f"chart_{key}.png"
            with open(os.path.join(task_dir, fname), "wb") as f:
                f.write(png)
            chart_list.append({
                "key": key,
                "title": CHART_TITLES.get(key, key),
                "url": f"/api/media/file/{task_id}/{fname}",
            })

        # PPT
        with _lock:
            _tasks[task_id]["stage"] = "正在生成 PPT"
        ppt_name = f"{_safe_filename(deck.get('title') or '路演PPT')}.pptx"
        ppt_bytes = mf.build_pptx(deck, charts, out_path=os.path.join(task_dir, ppt_name))
        ppt_url = f"/api/media/file/{task_id}/{ppt_name}"

        # 富格式 Word（申报书 + 图表）
        with _lock:
            _tasks[task_id]["stage"] = "正在生成 Word"
        chart_items = [(charts.get(k), CHART_TITLES.get(k, k)) for k in ("competitor", "finance", "timeline")]
        docx_bytes = mf.build_rich_docx(
            title=deck.get("title") or "项目申报材料",
            text=state.get("proposal") or "",
            chart_items=[c for c in chart_items if c[0]],
            subtitle=state.get("one_liner") or "",
        )
        docx_name = "申报书_带图表版.docx"
        with open(os.path.join(task_dir, docx_name), "wb") as f:
            f.write(docx_bytes)

        # 清理旧任务
        with _lock:
            try:
                dirs = sorted([d for d in os.listdir(OUT_DIR)],
                              key=lambda d: os.path.getmtime(os.path.join(OUT_DIR, d)))
                for d in dirs[:-MAX_TASKS]:
                    _tasks.pop(d, None)
                    import shutil
                    shutil.rmtree(os.path.join(OUT_DIR, d), ignore_errors=True)
            except Exception:
                pass

        with _lock:
            _tasks[task_id] = {
                "status": "done",
                "stage": "完成",
                "updated_at": time.time(),
                "charts": chart_list,
                "ppt": {"name": ppt_name, "url": ppt_url, "size": len(ppt_bytes)},
                "docx": {"name": docx_name, "url": f"/api/media/file/{task_id}/{docx_name}",
                         "size": len(docx_bytes)},
                "slides": len(deck.get("slides") or []),
                "title": deck.get("title"),
                "subtitle": deck.get("subtitle"),
                "fallback_reason": plan.get("fallback_reason"),
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _lock:
            _tasks[task_id] = {"status": "error", "stage": "失败",
                               "error": str(e)[:200], "updated_at": time.time()}


@media_bp.route("/build", methods=["POST"])
def build():
    data = request.get_json(force=True, silent=True) or {}
    if not (data.get("proposal") or data.get("idea")):
        return jsonify({"success": False, "error": "缺少项目内容，请先生成深度版结果"}), 400

    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = {"status": "running", "stage": "排队中", "updated_at": time.time()}
    threading.Thread(target=_worker, args=(task_id, data), daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@media_bp.route("/status/<task_id>")
def status(task_id):
    t = _tasks.get(task_id)
    if not t:
        return jsonify({"success": False, "error": "任务不存在或已过期"})
    resp = {"success": True, "status": t.get("status"), "stage": t.get("stage")}
    for k in ("charts", "ppt", "docx", "slides", "title", "subtitle", "fallback_reason", "error"):
        if k in t:
            resp[k] = t[k]
    return jsonify(resp)


@media_bp.route("/file/<task_id>/<path:filename>")
def media_file(task_id, filename):
    task_dir = os.path.join(OUT_DIR, _safe_filename(task_id))
    if not os.path.isdir(task_dir):
        return jsonify({"success": False, "error": "任务不存在"}), 404
    path = os.path.join(task_dir, filename)
    if not os.path.isfile(path):
        return jsonify({"success": False, "error": "文件不存在"}), 404

    as_attachment = request.args.get("dl") == "1"
    if filename.lower().endswith(".png"):
        return send_file(path, mimetype="image/png",
                         as_attachment=as_attachment,
                         download_name=filename)
    return send_file(path, as_attachment=True, download_name=filename)


@media_bp.route("/docx", methods=["POST"])
def export_docx_rich():
    """把一段文本导出成带真表格的 Word；task_id 存在时会附带该任务的图表"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "")
    title = data.get("title", "导出文档")
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400

    chart_items = []
    task_id = data.get("task_id")
    if task_id:
        task_dir = os.path.join(OUT_DIR, _safe_filename(task_id))
        for key in ("competitor", "finance", "timeline", "radar", "budget"):
            p = os.path.join(task_dir, f"chart_{key}.png")
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    chart_items.append((f.read(), CHART_TITLES.get(key, key)))

    docx_bytes = mf.build_rich_docx(title, text,
                                    chart_items=chart_items if data.get("with_charts") else None,
                                    subtitle=data.get("subtitle"))
    return send_file(io.BytesIO(docx_bytes), as_attachment=True,
                     download_name=f"{_safe_filename(title)}.docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
