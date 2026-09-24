"""
科创赛事多智能体协同创作助手 - Flask Web 界面
"""
import threading
import uuid
import time
import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document
from competition_agents import fast_app, deep_app, CompetitionState


app = Flask(__name__)

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

def load_history():
    if os.path.exists(app.config['HISTORY_FILE']):
        with open(app.config['HISTORY_FILE'], 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(history):
    with open(app.config['HISTORY_FILE'], 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


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
    history = load_history()
    # 只返回摘要，不返回完整数据
    summary = [{"id": h["id"], "time": h["time"], "competition_name": h["competition_name"], "idea": h["idea"], "score": h["score"]} for h in history]
    return jsonify({"success": True, "history": summary})


@app.route('/api/history/<int:history_id>')
def get_history_detail(history_id):
    history = load_history()
    for h in history:
        if h["id"] == history_id:
            return jsonify({"success": True, "data": h["data"]})
    return jsonify({"success": False, "error": "记录不存在"})


@app.route('/api/generate', methods=['POST'])
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
            "idea_score": 0,
            "idea_feedback": "",
            "score": 0,
            "approved": False
        }

        mode = data.get("mode", "fast")
        if mode == "deep":
            result = deep_app.invoke(state)
        else:
            result = fast_app.invoke(state)

        history = load_history()
        history_item = {
            "id": int(datetime.now().timestamp() * 1000),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "competition_name": data.get("competition_name", ""),
            "idea": data.get("idea", "")[:50],
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
                "revision_count": result.get("revision_count", "")
            }
        }
        history.insert(0, history_item)
        if len(history) > 20:
            history = history[:20]
        save_history(history)

    return {
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
        "revision_count": result.get("revision_count", 0)
    }


def _friendly_error(e):
    err = str(e).lower()
    if "timeout" in err or "timed out" in err:
        return "模型响应超时，请稍后重试"
    if "429" in err or "rate" in err or "too many" in err:
        return "请求过于频繁，请稍后再试"
    if "401" in err or "auth" in err or "api key" in err:
        return "模型接口鉴权失败，请检查 DEEPSEEK_API_KEY"
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


@app.route('/api/generate_async', methods=['POST'])
def generate_async():
    data = request.json or {}
    task_id = uuid.uuid4().hex
    tasks[task_id] = {"status": "running", "updated_at": time.time()}

    def worker():
        try:
            rd = _run_generation(data)
            tasks[task_id] = {"status": "done", "data": rd, "updated_at": time.time()}
        except Exception as e:
            import traceback
            traceback.print_exc()
            tasks[task_id] = {"status": "error", "error": _friendly_error(e), "detail": str(e), "updated_at": time.time()}

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route('/api/status/<task_id>')
def get_task_status(task_id):
    t = tasks.get(task_id)
    if not t:
        return jsonify({"success": False, "error": "任务不存在或已过期"})
    resp = {"success": True, "status": t["status"], "updated_at": t["updated_at"]}
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
    return send_file(zippath, as_attachment=True, download_name='科创赛事项目材料包.zip', mimetype='application/zip')

