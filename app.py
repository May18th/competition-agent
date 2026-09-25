"""
科创赛事多智能体协同创作助手 - Flask Web 界面
"""
import threading
import uuid
import time
import io
import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document
from competition_agents import fast_app, deep_app, CompetitionState


app = Flask(__name__)
START_TIME = time.time()

# ===== 媒体模块（表格 / 图表 / PPT）=====
# 由 media_routes.py 提供，WorkBuddy 注册。
# ⚠️ 改 app.py 时请不要删这段，删了前端的图表和 PPT 下载会 404。
try:
    from media_routes import media_bp
    app.register_blueprint(media_bp)
    print("✅ 媒体模块已注册：/api/media/*")
except Exception as _media_err:
    print("⚠️ 媒体模块注册失败：", _media_err)
# ===== 媒体模块结束 =====


# ============ 初始化数据库 ============
DB_PATH = os.path.join(os.path.dirname(__file__), "competition.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 历史记录表
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  competition_name TEXT,
                  idea TEXT,
                  mode TEXT,
                  result_data TEXT,
                  created_time TEXT)''')
    conn.commit()
    conn.close()

init_db()
print("✅ SQLite数据库已初始化")
lock = threading.Lock()
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HISTORY_FILE'] = 'history.json'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 存储最新结果
latest_result = None

# 历史记录
import json
from datetime import datetime

def _row_to_item(row):
    rid, comp, idea, mode, result_data, created_time = row
    try:
        data = json.loads(result_data)
    except Exception:
        data = {}
    return {
        "id": rid, "time": created_time, "competition_name": comp,
        "idea": idea, "mode": mode, "score": data.get("score", ""), "data": data,
    }


def load_history(limit=200, offset=0, q=None):
    """从 SQLite 读取历史记录（新的在前），返回兼容旧接口的 list"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    sql = "SELECT id, competition_name, idea, mode, result_data, created_time FROM history"
    params = []
    if q:
        sql += " WHERE competition_name LIKE ? OR idea LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


def count_history(q=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if q:
        c.execute("SELECT COUNT(*) FROM history WHERE competition_name LIKE ? OR idea LIKE ?", (f"%{q}%", f"%{q}%"))
    else:
        c.execute("SELECT COUNT(*) FROM history")
    total = c.fetchone()[0]
    conn.close()
    return total


def save_history_item(item):
    """插入一条历史记录到 SQLite，返回新 id"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO history (competition_name, idea, mode, result_data, created_time)
                 VALUES (?, ?, ?, ?, ?)''',
              (item.get("competition_name", ""), item.get("idea", ""), item.get("mode", ""),
               json.dumps(item.get("data", {}), ensure_ascii=False),
               item.get("time", datetime.now().strftime("%Y-%m-%d %H:%M"))))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def _migrate_history_json():
    """一次性把 history.json 迁移到 SQLite（仅当 SQLite 为空）"""
    json_path = app.config['HISTORY_FILE']
    if not os.path.exists(json_path):
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM history")
    has_data = c.fetchone()[0] > 0
    conn.close()
    if has_data:
        return
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            items = json.load(f)
        for item in reversed(items):  # JSON 新在前，SQLite 按 id 递增（旧在前），反序插入保持时间顺序
            save_history_item(item)
        print(f"✅ 已从 history.json 迁移 {len(items)} 条历史到 SQLite")
    except Exception as e:
        print(f"⚠️ 历史迁移失败：{e}")


_migrate_history_json()


# ============ 网页界面 ============


# ============ API ============
def _build_docx(title, text):
    """统一 docx 排版：微软雅黑、页边距、标题层级、正文缩进"""
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import re
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.font.size = Pt(11)
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.8)
    h = doc.add_heading('', 0)
    run = h.add_run(title)
    run.font.name = '微软雅黑'
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x66, 0x7e, 0xea)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        line = re.sub(r'\*(.*?)\*', r'\1', line)
        line = re.sub(r'`([^`]+)`', r'\1', line)
        if line.startswith('#'):
            level = min(line.count('#'), 4)
            clean_line = line.lstrip('#').strip()
            p = doc.add_heading('', level=level)
            run = p.add_run(clean_line)
            run.font.name = '微软雅黑'
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x4a, 0x55, 0xb8)
            run.font.size = Pt(16 if level == 1 else (14 if level == 2 else 12))
        elif line.startswith(('- ', '• ', '· ')):
            p = doc.add_paragraph(line[2:], style='List Bullet')
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.first_line_indent = Cm(0)
        else:
            p = doc.add_paragraph(line)
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.first_line_indent = Cm(0.74)
            p.paragraph_format.space_after = Pt(6)
    return doc


@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f: return f.read()


@app.route('/api/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有文件"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "没有选择文件"})
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    text = ""
    if filename.lower().endswith('.pdf'):
        reader = PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    elif filename.lower().endswith('.docx'):
        from docx import Document
        doc = Document(filepath)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif filename.lower().endswith('.txt'):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f2:
            text = f2.read()
    else:
        return jsonify({"success": False, "error": "不支持的文件格式，请上传PDF/DOCX/TXT"})
    import re
    text = re.sub(r'\n\s*\n', '\n', text).strip()
    return jsonify({"success": True, "text": text[:20000]})


@app.route('/api/export_word', methods=['POST'])
def export_word():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    title = data.get('title', '导出文档')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document()
    # 设置默认字体为微软雅黑
    style = doc.styles['Normal']
    style.font.name = '微软雅黑'
    style.font.size = Pt(11)
    # 页边距
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.8)
    # 大标题
    h = doc.add_heading('', 0)
    run = h.add_run(title)
    run.font.name = '微软雅黑'
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x66, 0x7e, 0xea)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    import re
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        # 清理markdown符号
        line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        line = re.sub(r'\*(.*?)\*', r'\1', line)
        line = re.sub(r'`([^`]+)`', r'\1', line)
        if line.startswith('#'):
            level = min(line.count('#'), 4)
            clean_line = line.lstrip('#').strip()
            p = doc.add_heading('', level=level)
            run = p.add_run(clean_line)
            run.font.name = '微软雅黑'
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x4a, 0x55, 0xb8)
            if level == 1:
                run.font.size = Pt(16)
            elif level == 2:
                run.font.size = Pt(14)
            else:
                run.font.size = Pt(12)
        elif line.startswith(('- ', '• ', '· ')):
            p = doc.add_paragraph(line[2:], style='List Bullet')
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.first_line_indent = Cm(0)
        else:
            p = doc.add_paragraph(line)
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.first_line_indent = Cm(0.74)
            p.paragraph_format.space_after = Pt(6)
    filepath = 'tmp_export_single.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/export_defense')
def export_defense():
    data = request.json
    text = data.get('text', '')
    title = data.get('title', '答辩问题预测与答题思路')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    doc = _build_docx(title, text)
    filepath = '答辩问题.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/export_ppt')
def export_ppt():
    data = request.json
    text = data.get('text', '')
    title = data.get('title', '路演 PPT 大纲')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    doc = _build_docx(title, text)
    filepath = 'PPT大纲.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/export_competitor')
def export_competitor():
    data = request.json
    text = data.get('text', '')
    title = data.get('title', '竞品分析报告')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    doc = _build_docx(title, text)
    filepath = '竞品分析.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/export_business')
def export_business():
    data = request.json
    text = data.get('text', '')
    title = data.get('title', '商业模式分析报告')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    doc = _build_docx(title, text)
    filepath = '商业模式.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/history')
def get_history():
    limit = max(1, min(int(request.args.get("limit", 20)), 100))
    offset = max(0, int(request.args.get("offset", 0)))
    q = request.args.get("q", "").strip()
    history = load_history(limit=limit, offset=offset, q=q)
    total = count_history(q)
    # 只返回摘要，不返回完整数据
    summary = [{"id": h["id"], "time": h["time"], "competition_name": h["competition_name"], "idea": h["idea"], "score": h["score"]} for h in history]
    return jsonify({"success": True, "history": summary, "total": total, "limit": limit, "offset": offset})


@app.route('/api/history/<int:history_id>')
def get_history_detail(history_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT result_data FROM history WHERE id = ?", (history_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "记录不存在"})
    try:
        data = json.loads(row[0])
    except Exception:
        data = {}
    return jsonify({"success": True, "data": data})


@app.route('/api/history/<int:history_id>', methods=['DELETE'])
def delete_history(history_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE id = ?", (history_id,))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    if deleted:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "记录不存在"}), 404


tasks = {}


def _run_generation(data):
    """执行生成流水线（加锁、存历史），返回结果 data dict；出错抛异常"""
    with lock:
        idea = data.get("idea", "")
        proposal_draft = data.get("proposal_draft", "")

        state: CompetitionState = {
            "competition_name": data.get("competition_name", ""),
            "rule_content": data.get("rule_content", ""),
            "idea": idea,
            "proposal_draft": proposal_draft,
            "parsed_rules": "",
            "similarity_report": "",
            "competitor_analysis": "",
            "business_model": "",
            "risk_analysis": "",
            "tech_solution": "",
            "implementation_plan": "",
            "social_value": "",
            "project_summary": "",
            "proposal": "",
            "judge_feedback": "",
            "proposal_analysis": "",
            "defense_questions": "",
            "ppt_outline": "",
            "speech_script": "",
            "one_liner": "",
            "rich_media": "",
            "idea_score": 0,
            "idea_feedback": "",
            "score": 0,
            "approved": False,
            "iterate": bool(data.get("iterate", False))
        }

        mode = data.get("mode", "fast")
        if mode == "deep":
            result = deep_app.invoke(state)
            # 深度版追加：自动生成表格 / 图表 / 路演PPT（失败不阻断主流程）
            try:
                from rich_pipeline import build_rich_assets
                rich = build_rich_assets(result, data.get("competition_name", ""), idea, data.get("theme"))
                result["rich_charts"] = rich.get("charts") or {}
                result["rich_tables"] = rich.get("tables") or []
                result["rich_deck"] = rich.get("deck")
            except Exception as e:
                print(f"[rich] 富媒体生成失败（不影响正文）：{e}")
        else:
            result = fast_app.invoke(state)

        # ===== 富媒体解析（表格/图表/PPT）：三种来源统一归一，失败不阻断 =====
        # 来源1：rich_pipeline 直接写在 result 上的三个字段（当前主链路）
        # 来源2：result["rich_media"] 的 JSON 字符串（兼容旧写法）
        # 来源3：已经渲染好的 [{url,title,caption}] 列表（直接透传）
        rich_tables = []
        rich_deck = None
        rich_charts = []
        try:
            _charts_raw = result.get("rich_charts")
            rich_tables = result.get("rich_tables") or []
            rich_deck = result.get("rich_deck")

            if not (rich_tables or rich_deck):
                import json as _json
                _rm = (result.get("rich_media") or "").strip()
                if _rm.startswith("```"):
                    _rm = _rm.strip("`")
                    if _rm.lower().startswith("json"):
                        _rm = _rm[4:]
                if _rm:
                    _d = _json.loads(_rm)
                    rich_tables = _d.get("tables") or []
                    rich_deck = _d.get("deck")
                    _charts_raw = _d.get("charts") or _charts_raw

            if isinstance(_charts_raw, dict) and _charts_raw:
                from chart_renderer import render_charts
                rich_charts = render_charts(_charts_raw)
            elif isinstance(_charts_raw, list):
                rich_charts = _charts_raw
        except Exception as _re:
            print(f"[rich] 富媒体解析失败（不影响正文）：{_re}")
        # ===== 富媒体解析结束 =====

        history_item = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "competition_name": data.get("competition_name", ""),
            "idea": data.get("idea", "")[:50],
            "mode": data.get("mode", "fast"),
            "score": result.get("score", ""),
            "data": {
                "parsed_rules": result.get("parsed_rules", ""),
                "similarity_report": result.get("similarity_report", ""),
                "competitor_analysis": result.get("competitor_analysis", ""),
                "business_model": result.get("business_model", ""),
                "risk_analysis": result.get("risk_analysis", ""),
                "tech_solution": result.get("tech_solution", ""),
                "implementation_plan": result.get("implementation_plan", ""),
                "social_value": result.get("social_value", ""),
                "project_summary": result.get("project_summary", ""),
                "proposal_analysis": result.get("proposal_analysis", ""),
                "proposal": result.get("proposal", ""),
                "judge_feedback": result.get("judge_feedback", ""),
                "defense_questions": result.get("defense_questions", ""),
                "ppt_outline": result.get("ppt_outline", ""),
                "speech_script": result.get("speech_script", ""),
                "one_liner": result.get("one_liner", ""),
                "idea_score": result.get("idea_score", ""),
                "idea_feedback": result.get("idea_feedback", ""),
                "score": result.get("score", ""),
                "revision_count": result.get("revision_count", ""),
                "rich_charts": rich_charts,
                "rich_tables": result.get("rich_tables", []),
                "rich_deck": result.get("rich_deck")
            }
        }
        save_history_item(history_item)

    try:
        from competition_agents import check_proposal_completeness
        completeness = check_proposal_completeness(result.get("proposal", ""))
    except Exception:
        completeness = {"ok": True, "missing": [], "detail": {}, "chars": 0}

    payload = {
        "parsed_rules": result.get("parsed_rules", ""),
        "similarity_report": result.get("similarity_report", ""),
        "competitor_analysis": result.get("competitor_analysis", ""),
        "business_model": result.get("business_model", ""),
        "risk_analysis": result.get("risk_analysis", ""),
        "tech_solution": result.get("tech_solution", ""),
        "implementation_plan": result.get("implementation_plan", ""),
        "social_value": result.get("social_value", ""),
        "project_summary": result.get("project_summary", ""),
        "proposal": result.get("proposal", ""),
        "judge_feedback": result.get("judge_feedback", ""),
        "proposal_analysis": result.get("proposal_analysis", ""),
        "defense_questions": result.get("defense_questions", ""),
        "ppt_outline": result.get("ppt_outline", ""),
        "speech_script": result.get("speech_script", ""),
        "one_liner": result.get("one_liner", ""),
        "idea_score": result.get("idea_score", 0),
        "idea_feedback": result.get("idea_feedback", ""),
        "score": result.get("score", 0),
        "revision_count": result.get("revision_count", 0),
        "rich_charts": rich_charts,
        "rich_tables": rich_tables,
        "rich_deck": rich_deck,
        "completeness": completeness
    }

    return payload


def _friendly_error(e):
    err = str(e).lower()
    if "timeout" in err or "timed out" in err:
        return "模型响应超时，请稍后重试"
    if "429" in err or "rate" in err or "too many" in err:
        return "请求过于频繁，请稍后再试"
    if "401" in err or "auth" in err or "api key" in err:
        return "模型接口鉴权失败，请检查 DEEPSEEK_API_KEY"
    if "402" in err or "insufficient balance" in err or "payment required" in err or "余额不足" in err:
        return "DeepSeek 账户余额不足，请充值后重试（充值后无需重启服务）"
    if "上限" in err or "配额" in err or "quota" in err:
        return "今日调用次数已达上限，请明天再试或联系管理员调整额度"
    return "生成失败，请稍后重试"


@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json or {}
    try:
        result_data = _run_generation(data)
        return jsonify({"success": True, "data": result_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": _friendly_error(e), "detail": str(e)})


# ---- 异步任务阶段上报 ----
# 用途：让 /api/status/<task_id> 能吐出「当前跑到哪一步」，前端据此渲染真实步骤。
# 调用方式（供 _run_generation / 各 Agent 内部使用）：
#     from app import _report_stage
#     _report_stage("parsing_rules")
# 约定阶段名：parsing_rules / similarity / writing / judging / revision / rich_assets
# 不调用也能正常工作，只是 stage 停留在 start。
_CURRENT_TASK = {"id": None}


def _report_stage(stage):
    tid = _CURRENT_TASK.get("id")
    t = tasks.get(tid) if tid else None
    if isinstance(t, dict):
        t["stage"] = stage
        t["updated_at"] = time.time()


@app.route('/api/generate_async', methods=['POST'])
def generate_async():
    data = request.json or {}
    task_id = uuid.uuid4().hex
    tasks[task_id] = {"status": "running", "stage": "start", "updated_at": time.time()}

    def worker():
        _CURRENT_TASK["id"] = task_id          # 让 _report_stage 知道往哪个任务写
        try:
            rd = _run_generation(data)
            _report_stage("done")
            tasks[task_id] = {"status": "done", "data": rd, "stage": "done", "updated_at": time.time()}
        except Exception as e:
            import traceback
            traceback.print_exc()
            tasks[task_id] = {"status": "error", "error": _friendly_error(e),
                              "detail": str(e), "stage": "error", "updated_at": time.time()}
        finally:
            _CURRENT_TASK["id"] = None

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route('/api/status/<task_id>')
def get_task_status(task_id):
    t = tasks.get(task_id)
    if not t:
        return jsonify({"success": False, "error": "任务不存在或已过期"})
    resp = {"success": True, "status": t["status"], "stage": t.get("stage"), "updated_at": t["updated_at"]}
    if t["status"] == "done":
        resp["data"] = t["data"]
    elif t["status"] == "error":
        resp["error"] = t["error"]
        resp["detail"] = t.get("detail")
    return jsonify(resp)





@app.route('/api/export_all')
def export_all():
    import zipfile
    import io
    
    # 拿最新的历史记录
    history = load_history()
    if not history:
        return jsonify({"success": False, "error": "没有可导出的记录"})
    
    latest = history[0]
    data = latest["data"]
    
    # 要导出的文件列表（减少到 5 个核心文件，更快）
    files_to_export = [
        ("1_申报书全文.docx", data.get("proposal", "")),
        ("2_竞品与商业模式.docx", data.get("competitor_analysis", "") + "\n\n" + data.get("business_model", "")),
        ("3_风险分析与评委意见.docx", data.get("risk_analysis", "") + "\n\n" + data.get("judge_feedback", "")),
        ("4_答辩问题预测.docx", data.get("defense_questions", "")),
        ("5_PPT大纲.docx", data.get("ppt_outline", "")),
    ]
    
    # 直接在内存里打包，不写临时文件，速度快很多
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:  # 不压缩，直接打包
        for filename, text in files_to_export:
            if not text or not text.strip():
                continue
            
            # 快速生成 Word：直接加文本，不解析 Markdown
            docx_buf = io.BytesIO()
            doc = Document()
            # 设置默认字体
            from docx.shared import Pt
            style = doc.styles['Normal']
            style.font.name = '宋体'
            style.font.size = Pt(12)
            # 加标题
            doc.add_heading(filename.replace('.docx', ''), 0)
            # 按段落写，更美观
            import re
            clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
            clean_text = re.sub(r'^#+\s*', '', clean_text, flags=re.MULTILINE)
            for para in clean_text.split('\n\n'):
                if para.strip():
                    doc.add_paragraph(para.strip())
            doc.save(docx_buf)
            docx_buf.seek(0)
            zf.writestr(filename, docx_buf.read())
    
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='科创赛事材料包.zip', mimetype='application/zip')

@app.route('/api/export_original_format', methods=['POST'])
def export_original_format():
    from docx import Document
    import io
    import re
    
    # 拿用户上传的原文件和优化后的内容
    original_file = request.files.get('original_file')
    optimized_text = request.form.get('optimized_text', '')
    
    if not original_file:
        return jsonify({"success": False, "error": "没有原文件"})
    
    try:
        doc = Document(io.BytesIO(original_file.read()))
        
        # 简单处理：替换段落里的文字，保留格式
        paragraphs = optimized_text.split('\n')
        para_idx = 0
        for para in doc.paragraphs:
            if para_idx < len(paragraphs) and paragraphs[para_idx].strip():
                # 保留原来的样式，只改文字
                for run in para.runs:
                    run.text = ''
                if para.runs:
                    para.runs[0].text = paragraphs[para_idx].strip()
                else:
                    para.add_run(paragraphs[para_idx].strip())
            para_idx += 1
        
        # 保存
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name='优化后的申报书.docx', mimetype='application/docx')
    except Exception as e:
        return jsonify({"success": False, "error": f"导出失败：{str(e)}"})


@app.route('/api/upload_file', methods=['POST'])
def upload_file():
    import os
    from werkzeug.utils import secure_filename
    file = request.files['file']
    if not file:
        return jsonify({"success": False, "error": "没有文件"})
    
    filename = secure_filename(file.filename)
    ext = filename.split('.')[-1].lower()
    text = ""
    
    try:
        if ext == 'pdf':
            import pdfplumber
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                    tables = page.extract_tables()
                    for table in tables:
                        text += "\n[表格数据]\n"
                        for row in table:
                            text += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
                    # 提取PDF里的图片，用Claude识别
                    if page.images:
                        text += "\n[检测到页面含图片/图表]\n"
        elif ext in ['jpg', 'jpeg', 'png']:
            # 图片直接用Claude多模态识别
            import base64
            from langchain_core.messages import HumanMessage
            from competition_agents import claude_llm
            
            img_base64 = base64.b64encode(file.read()).decode('utf-8')
            response = claude_llm.invoke([
                HumanMessage(content=[
                    {"type": "text", "text": "请详细描述这张图片里的所有内容，包括文字、图表数据、标题、关键数字，把图片里的信息都提取出来。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ])
            ])
            text = response.content
        elif ext == 'txt':
            text = file.read().decode('utf-8')
        elif ext == 'docx':
            from docx import Document
            import io
            doc = Document(io.BytesIO(file.read()))
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text.strip() + "\n"
            for table in doc.tables:
                text += "\n[表格数据]\n"
                for row in table.rows:
                    text += " | ".join([cell.text.strip() for cell in row.cells]) + "\n"
        else:
            return jsonify({"success": False, "error": "不支持的文件格式"})
        
        # 清理多余空行，把连续多个换行合并成两个
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        return jsonify({"success": True, "text": text})
    except Exception as e:
        return jsonify({"success": False, "error": f"文件解析失败：{str(e)}"})


# ============ 启动 ============
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 科创赛事多智能体协同创作助手 - Web 版")
    print("=" * 60)
    print("📱 浏览器打开: http://127.0.0.1:8080")
    print("=" * 60)
    app.run(debug=True, port=8080)


@app.route('/api/export_zip', methods=['POST'])
def export_zip():
    import zipfile, os, re
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from flask import send_file, jsonify
    data = request.get_json(force=True, silent=True) or {}
    mappings = [
        ("01_赛事规则解析报告.docx", "赛事规则解析报告", data.get('parsed_rules', '')),
        ("02_创意同质化检测报告.docx", "创意同质化检测报告", data.get('similarity_report', '')),
        ("03_项目申报书全文.docx", "项目申报书全文", data.get('proposal', '')),
        ("04_申报书诊断分析.docx", "申报书诊断分析", data.get('proposal_analysis', '')),
        ("05_评委评审意见.docx", "评委评审意见", data.get('judge_feedback', '')),
    ]
    if data.get('competitor_analysis'):
        mappings.append(("06_竞品分析报告.docx", "竞品分析报告", data['competitor_analysis']))
    if data.get('business_model'):
        mappings.append(("07_商业模式分析.docx", "商业模式分析", data['business_model']))
    if data.get('risk_analysis'):
        mappings.append(("08_风险评估报告.docx", "风险评估报告", data['risk_analysis']))
    if data.get('defense_questions'):
        mappings.append(("09_答辩问题预测.docx", "答辩问题预测", data['defense_questions']))
    if data.get('ppt_outline'):
        mappings.append(("10_PPT大纲.docx", "PPT大纲", data['ppt_outline']))
    tmpdir = 'tmp_export'
    os.makedirs(tmpdir, exist_ok=True)
    zippath = os.path.join(tmpdir, '科创赛事项目材料包.zip')
    
    def build_doc(title, text):
        doc = Document()
        style = doc.styles['Normal']
        style.font.name = '微软雅黑'
        style.font.size = Pt(11)
        for section in doc.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(2.8)
            section.right_margin = Cm(2.8)
        h = doc.add_heading('', 0)
        run = h.add_run(title)
        run.font.name = '微软雅黑'
        run.font.size = Pt(20)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x66, 0x7e, 0xea)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph()
        for line in text.split('\n'):
            line = line.strip()
            if not line: continue
            line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            line = re.sub(r'\*(.*?)\*', r'\1', line)
            line = re.sub(r'`([^`]+)`', r'\1', line)
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                clean_line = line.lstrip('#').strip()
                p = doc.add_heading('', level=level)
                run = p.add_run(clean_line)
                run.font.name = '微软雅黑'
                run.font.bold = True
                run.font.color.rgb = RGBColor(0x4a, 0x55, 0xb8)
                run.font.size = Pt(16 if level == 1 else (14 if level == 2 else 12))
            elif line.startswith(('- ', '• ', '· ')):
                p = doc.add_paragraph(line[2:], style='List Bullet')
                p.paragraph_format.line_spacing = 1.5
            else:
                p = doc.add_paragraph(line)
                p.paragraph_format.line_spacing = 1.5
                p.paragraph_format.first_line_indent = Cm(0.74)
                p.paragraph_format.space_after = Pt(6)
        return doc
    
    with zipfile.ZipFile(zippath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, title, text in mappings:
            if not text or not text.strip(): continue
            doc = build_doc(title, text)
            tmppath = os.path.join(tmpdir, filename)
            doc.save(tmppath)
            zf.write(tmppath, filename)
        # ---- 深度版附加：数据图表 docx + 路演 PPT pptx ----
        try:
            charts = data.get('rich_charts') or []
            if charts:
                from docx.shared import Inches as _Inches
                cdoc = Document()
                ch = cdoc.add_heading('', 0)
                crun = ch.add_run('项目数据图表')
                crun.font.name = '微软雅黑'
                crun.font.size = Pt(20)
                crun.font.bold = True
                crun.font.color.rgb = RGBColor(0x66, 0x7e, 0xea)
                ch.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cdoc.add_paragraph()
                for c in charts:
                    img = os.path.join('generated', os.path.basename(c.get('url', '')))
                    if c.get('title'):
                        p = cdoc.add_paragraph()
                        r = p.add_run(c['title'])
                        r.font.bold = True
                        r.font.size = Pt(13)
                    if os.path.exists(img):
                        cdoc.add_picture(img, width=_Inches(5.9))
                    if c.get('caption'):
                        cap = cdoc.add_paragraph(c['caption'])
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cpath = os.path.join(tmpdir, '11_项目数据图表.docx')
                cdoc.save(cpath)
                zf.write(cpath, '11_项目数据图表.docx')
        except Exception as e:
            print(f"[export_zip] 图表docx失败: {e}")
        try:
            deck = data.get('rich_deck')
            if deck:
                from pptx_builder import build_deck
                deck = dict(deck)
                # 前端手动选的主题/模板优先于自动推断（与 /api/export_pptx 行为保持一致）
                if data.get('theme'):
                    deck['theme'] = data['theme']
                if data.get('variant'):
                    deck['variant'] = data['variant']
                deck['project'] = deck.get('project') or (data.get('idea', '') or '科创项目')[:30]
                tmap = {t.get('id'): t for t in (data.get('rich_tables') or [])}
                for s in deck.get('slides', []):
                    if isinstance(s, dict) and isinstance(s.get('table'), str):
                        s['table'] = tmap.get(s['table'])
                chart_paths = {}
                for c in (data.get('rich_charts') or []):
                    img = os.path.join('generated', os.path.basename(c.get('url', '')))
                    if os.path.exists(img):
                        chart_paths[c.get('id')] = img
                build_deck(deck, os.path.join(tmpdir, '12_路演PPT.pptx'), chart_paths)
                zf.write(os.path.join(tmpdir, '12_路演PPT.pptx'), '12_路演PPT.pptx')
        except Exception as e:
            print(f"[export_zip] PPT失败: {e}")
    return send_file(zippath, as_attachment=True, download_name='科创赛事项目材料包.zip', mimetype='application/zip')


# ============ 富媒体：图表图片 & PPT 导出 ============
@app.route('/generated/<path:filename>')
def generated_file(filename):
    from flask import send_from_directory
    return send_from_directory('generated', filename)


@app.route('/api/knowledge_status')
def knowledge_status():
    """返回比赛知识库收录状态 + 每个文件的格式校验结果"""
    try:
        from competition_agents import get_knowledge_status
        return jsonify({"success": True, **get_knowledge_status()})
    except Exception as e:
        print(f"[knowledge] 状态读取失败：{e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/quota')
def quota():
    """返回今日 LLM 调用配额使用情况"""
    try:
        from competition_agents import get_quota_status
        return jsonify({"success": True, **get_quota_status()})
    except Exception as e:
        print(f"[quota] 状态读取失败：{e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/health')
def health():
    """健康检查：服务状态、运行时长、知识库数量、今日配额、最近生成时间"""
    try:
        from competition_agents import competition_knowledge, get_quota_status
        knowledge_count = len(competition_knowledge)
        quota = get_quota_status()
    except Exception:
        knowledge_count = 0
        quota = {}
    latest = load_history(limit=1)
    return jsonify({
        "success": True,
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "knowledge_count": knowledge_count,
        "quota": quota,
        "history_count": count_history(),
        "last_generation_time": latest[0]["time"] if latest else None,
    })


@app.route('/api/ppt_themes')
def ppt_themes():
    """返回可用主题与版式模板清单，供前端下拉选择"""
    try:
        import pptx_builder
        if hasattr(pptx_builder, "list_themes"):
            return jsonify({"success": True, **pptx_builder.list_themes()})
    except Exception as e:
        print(f"[themes] 读取失败：{e}")
    return jsonify({"success": False, "themes": []})


@app.route('/api/export_pptx', methods=['POST'])
def export_pptx():
    """导出自动生成的路演 PPT（.pptx）"""
    data = request.get_json(force=True, silent=True) or {}
    deck = data.get('deck')
    if not deck or not deck.get('slides'):
        return jsonify({"error": "没有可导出的PPT数据，请先用深度版生成"}), 400
    try:
        from pptx_builder import build_deck
        deck = dict(deck)
        # 前端选了主题/模板时，覆盖 deck 内置值（手动优先于自动推断）
        if data.get("theme"):
            deck["theme"] = data["theme"]
        if data.get("variant"):
            deck["variant"] = data["variant"]
        deck['project'] = deck.get('project') or (data.get('idea', '') or '科创项目')[:30]
        deck.setdefault('one_liner', data.get('one_liner', ''))
        deck.setdefault('competition', data.get('competition', ''))
        deck.setdefault("theme", "tech")
        deck.setdefault("variant", "v1")
        deck.setdefault('theme', data.get('theme') or 'tech')
        deck.setdefault('variant', data.get('variant') or 'v1')
        # 解析表格 id 引用（"t1" -> 实体表格）
        tmap = {t.get('id'): t for t in (data.get('tables') or [])}
        for s in deck.get('slides', []):
            if isinstance(s, dict) and isinstance(s.get('table'), str):
                s['table'] = tmap.get(s['table'])
        chart_paths = {}
        for c in (data.get('charts') or []):
            img = os.path.join('generated', os.path.basename(c.get('url', '')))
            if os.path.exists(img):
                chart_paths[c.get('id')] = img
        os.makedirs('generated', exist_ok=True)
        out = os.path.join('generated', '_deck_export.pptx')
        build_deck(deck, out, chart_paths)
        title = (deck.get('project') or '路演PPT').replace('/', '_')[:40]
        return send_file(out, as_attachment=True, download_name=f'{title}-路演PPT.pptx',
                         mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"PPT导出失败：{e}"}), 500
