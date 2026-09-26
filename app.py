"""
科创赛事多智能体协同创作助手 - Flask Web 界面
"""
# ⚠️ 启动入口约定（防回归，勿删）：
# 本文件只定义 Flask app 与路由，【禁止】在文件中间或末尾写
#   if __name__ == '__main__': app.run(...)
# 本地启动用 run.py，云端用 gunicorn wsgi:app。
# 一旦把启动块写回中间，其后的 @app.route 都不会被注册（本地直跑会 404）。
import threading
import uuid
import time
import io
import os
import sqlite3
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document
from competition_agents import fast_app, deep_app, CompetitionState
from stage_reporter import (tasks, set_current_task, clear_current_task,
                            report_stage as _report_stage, stage_meta, TaskCancelled,
                            get_speech_stream, clear_speech_stream, set_partial)
import progress
import app_log


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


def _seed_kb_if_needed():
    """首次部署时自动灌入种子范文。

    背景：competition.db 在 .gitignore 里，新环境 git pull 后 kb_samples 表是空的
    （kb_samples 模块导入时会自动建表，所以不报错），结果是 RAG 静默失效——
    界面正常、检索无报错，但永远命中不了任何范文。这里保证任何新环境起来就有基础范文。

    幂等：用 kb_meta.seed_stamp 记录已导入的种子指纹，重复启动不会重复插入；
    用户手动删光范文也不会被强行灌回。
    """
    try:
        import json as _json
        import hashlib
        from kb_samples import add_sample

        seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "knowledge_base", "seed_samples.json")
        if not os.path.exists(seed_path):
            return
        with open(seed_path, "rb") as f:
            raw = f.read()
        data = _json.loads(raw.decode("utf8"))
        stamp = hashlib.md5(raw).hexdigest()[:8] + ":" + str(len(data))

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS kb_meta (k TEXT PRIMARY KEY, v TEXT)")
        row = c.execute("SELECT v FROM kb_meta WHERE k='seed_stamp'").fetchone()
        if row and row[0] == stamp:
            conn.close()
            return

        n = 0
        for it in data:
            try:
                add_sample(it["content"], ",".join(it.get("tags", [])),
                           source=it.get("source", "种子"),
                           score=it.get("score", 0),
                           type="范文",
                           summary=it.get("summary", ""))
                n += 1
            except Exception:
                pass
        c.execute("INSERT OR REPLACE INTO kb_meta (k, v) VALUES ('seed_stamp', ?)", (stamp,))
        conn.commit()
        conn.close()
        print("🌱 范文库种子已导入 %d 段（stamp=%s）" % (n, stamp))
    except Exception as e:
        # 种子导入失败不能影响服务启动
        print("⚠️ 范文库种子导入失败（不影响启动）: %s" % e)


_seed_kb_if_needed()
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
def _build_docx(title, text, doc_type='report', subtitle=None,
                school=None, team=None, advisor=None, competition_name=None):
    """统一走 docx_render 渲染器（格式层，WorkBuddy 已交付）。"""
    from docx_render import build_docx
    show_school_advisor = True
    if competition_name:
        try:
            from competition_agents import get_competition_profile
            if get_competition_profile(competition_name).get("double_blind"):
                show_school_advisor = False
        except Exception:
            pass
    return build_docx(
        title, text,
        subtitle=subtitle,
        doc_type=doc_type,
        school=school, team=team, advisor=advisor,
        show_school_advisor=show_school_advisor,
    )


def _official_chapter_titles(competition_name):
    """读取结构化配置里的官方申报书章节标题列表（导出时用于自动排序）。"""
    if not competition_name:
        return []
    try:
        from competition_agents import get_competition_profile
        return get_competition_profile(competition_name).get("chapters") or []
    except Exception:
        return []


def _normalize_heading_title(s):
    """把「一、项目概述 / (1)项目概述 / 项目概述」归一成可用于匹配的关键词串。"""
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def _reorder_markdown_by_chapters(text, ordered_titles):
    """按官方章节顺序重排 Markdown 正文，缺省部分保持原有先后追加到末尾。

    只做标题块级别的排序，不拆段、不改内容；拿不到任何标题就原样返回。
    """
    if not text or not ordered_titles:
        return text
    order_keys = [_normalize_heading_title(t) for t in ordered_titles if _normalize_heading_title(t)]
    if not order_keys:
        return text

    # 切成「标题块」：每个 ## 标题到下一个 ## 标题之间的内容
    blocks = []
    cur = {"head": None, "body": []}
    for line in text.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m and m.group(1).startswith("##"):
            if cur["head"] is not None or cur["body"]:
                blocks.append(cur)
            cur = {"head": m.group(2).strip(), "body": []}
        else:
            cur["body"].append(line)
    if cur["head"] is not None or cur["body"]:
        blocks.append(cur)

    if not any(b["head"] for b in blocks):
        return text

    def match_index(head):
        h = _normalize_heading_title(head or "")
        if not h:
            return -1
        for i, key in enumerate(order_keys):
            # 官方章节标题较长，允许包含关系命中，避免「技术方案与系统架构」和「技术方案」串位
            if h == key or (len(key) >= 4 and key in h):
                return i
        return -1

    ordered = sorted(blocks, key=lambda b: (
        0 if match_index(b["head"]) >= 0 else 1,
        match_index(b["head"]) if match_index(b["head"]) >= 0 else 9999,
    ))

    out_lines = []
    for b in ordered:
        if b["head"] is not None:
            out_lines.append("## " + b["head"])
        out_lines.extend(b["body"])
        if out_lines and out_lines[-1] != "":
            out_lines.append("")
    return "\n".join(out_lines).rstrip() + "\n"


@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        resp = make_response(f.read())
    # 防浏览器缓存旧版前端（本次「进度条卡死」的根治）
    resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    return resp


def _assess_and_summarize(text, max_len=4000):
    """一次 LLM 调用：生成一句话摘要 + 质量评分 + 主要问题。返回 (summary, score, reason)。"""
    import re
    try:
        from competition_agents import llm
        from langchain_core.messages import HumanMessage
        prompt = f"""请对下面这份材料做两件事，只输出一个 JSON（不要任何解释文字）：

1. summary：用一句话（60字内）概括核心内容；
2. score：质量分（0-100），判断是否达到「高分范文」水准。评分维度各25分：结构完整性（章节齐全、无空表格/占位）、数据支撑（有具体数字/来源/测算，不是"千亿级""显著提升"这种空话）、具体性（技术/功能/商业模式落到细节）、逻辑一致性（口径统一、无矛盾）；
3. reason：一句话点出最需要改的问题（没问题就写"无明显硬伤"）。

格式：{{"summary":"...","score":82,"reason":"..."}}

材料：
{(text or "")[:max_len]}
"""
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = (resp.content or "").strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            import json as _json
            d = _json.loads(m.group(0))
            summary = str(d.get("summary", "")).strip()[:60]
            score = max(0, min(100, int(d.get("score", 0))))
            reason = str(d.get("reason", "")).strip()[:80]
            return summary, score, reason
        return (text or "")[:60], 0, "评估失败"
    except Exception as e:
        print(f"[kb] 摘要与质量评估失败：{e}")
        app_log.warn("kb", f"摘要与质量评估失败：{e}")
        return ((text or "")[:60] + "…") if len(text or "") > 60 else (text or ""), 0, "评估失败"


def _record_upload(text, source_name="", force_fanwen=False):
    """把用户上传的文本自动记录进记忆库（去重 + 自动打标签 + 质量评估 + 摘要）。"""
    if not text or not text.strip():
        return
    try:
        from kb_samples import find_by_content, add_sample
        from kb_retrieve import extract_keywords
        existing = find_by_content(text)
        if existing is not None:
            print(f"[kb] 跳过重复上传内容 #{existing}")
            return
        tags = extract_keywords(text)
        if not tags:
            tags = ["材料"]
        summary, score, reason = _assess_and_summarize(text)
        if force_fanwen:
            # 官方获奖作品：绕过启发式打分，强制归为范文
            mem_type, score = "范文", 90
        else:
            # 质量门：≥75 分才归为「范文」，否则归「材料」
            mem_type = "范文" if score >= 75 else "材料"
        sid, _ = add_sample(text.strip(), tags, source=source_name or "用户上传",
                            type=mem_type, summary=summary, score=score)
        print(f"[kb] 已记录上传 #{sid}，类型={mem_type}，质量={score}分，摘要={summary}，理由={reason}")
    except Exception as e:
        print(f"[kb] 记录上传失败（不影响主流程）：{e}")
        app_log.warn("kb", f"记录上传失败：{e}")


@app.route('/api/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有文件"})
    file = request.files['file']
    raw_name = file.filename or ''
    purpose = (request.form.get('purpose') or 'draft').strip()
    competition_name = (request.form.get('competition_name') or '').strip()
    if raw_name == '':
        return jsonify({"success": False, "error": "没有选择文件"})
    # ★ 坑：secure_filename 会把中文字符全部剔除，纯中文文件名《申报书草稿.pdf》
    #   会变成 "pdf"，导致 endswith('.pdf') 判断失败 → 前端一直「上传失败」。
    #   改为：扩展名单独取，主体名过滤后兜底，再加时间戳防重名。
    ext = os.path.splitext(raw_name)[1].lower()
    # 手机端（尤其微信内置浏览器）容易只让选图片/视频，这里把提示写清楚，别只说"不支持"
    if ext in ('.jpg', '.jpeg', '.png', '.heic', '.gif', '.webp', '.mp4', '.mov', '.avi'):
        return jsonify({"success": False, "error": "图片/视频读不出文字：请在 Safari 里点「浏览」选文件 App 里的 PDF 或 Word，或把文字直接粘贴到草稿框"})
    if ext not in ('.pdf', '.docx', '.txt', '.md'):
        return jsonify({"success": False, "error": "不支持的文件格式（" + (ext or '无扩展名') + "），请上传 PDF / DOCX / TXT / MD"})
    base = secure_filename(os.path.splitext(raw_name)[0]) or 'upload'
    filename = base + '_' + str(int(time.time())) + ext
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    text = ""
    try:
        if ext == '.pdf':
            reader = PdfReader(filepath)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif ext == '.docx':
            from docx import Document
            doc = Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:  # .txt / .md
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f2:
                text = f2.read()
    except Exception as e:
        return jsonify({"success": False, "error": "文件解析失败：" + str(e)[:120]})
    import re
    text = re.sub(r'\n\s*\n', '\n', text).strip()
    if not text:
        return jsonify({"success": False,
                        "error": "没能从文件里提取到文字（扫描版/图片型 PDF 提取不了），请直接把文字粘贴到草稿框"})
    if purpose == 'reference':
        try:
            from competition_agents import save_official_doc
            ok = save_official_doc(competition_name, text)
            return jsonify({"success": True, "text": text[:20000],
                            "purpose": "reference", "saved": ok,
                            "competition_name": competition_name})
        except Exception as e:
            app_log.warn("kb", f"保存官方资料失败：{e}")
    elif purpose == 'fanwen':
        # 真实获奖稿：绕过启发式打分，强制归为「范文」（见材料清单 P0）
        _record_upload(text, raw_name, force_fanwen=True)
        return jsonify({"success": True, "text": text[:20000], "purpose": "fanwen"})
    _record_upload(text, raw_name)
    return jsonify({"success": True, "text": text[:20000]})


@app.route('/api/export_word', methods=['POST'])
def export_word():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    title = data.get('title', '导出文档')
    charts = data.get('charts') or []
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    chapter_order = data.get('chapter_order')
    if not chapter_order and data.get('competition_name'):
        chapter_order = _official_chapter_titles(data.get('competition_name'))
    if chapter_order:
        text = _reorder_markdown_by_chapters(text, chapter_order)
    doc = _build_docx(
        title, text,
        doc_type=data.get('doc_type', 'report'),
        subtitle=data.get('competition_name'),
        school=data.get('school'),
        team=data.get('team'),
        advisor=data.get('advisor'),
        competition_name=data.get('competition_name'),
    )
    if charts:
        try:
            from docx_charts import inject_charts
            inject_charts(doc, charts)
        except Exception as e:
            print(f"[export_word] 图表插入失败（不影响导出）：{e}")
    filepath = 'tmp_export_single.docx'
    doc.save(filepath)
    return send_file(filepath, as_attachment=True, download_name=title + '.docx')


@app.route('/api/export_pdf', methods=['POST'])
def export_pdf():
    """把申报书/说明书 Markdown 导出为 PDF（iCAN 提交用，A4 中文）"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    title = data.get('title', '申报书')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    chapter_order = data.get('chapter_order')
    if not chapter_order and data.get('competition_name'):
        chapter_order = _official_chapter_titles(data.get('competition_name'))
    if chapter_order:
        text = _reorder_markdown_by_chapters(text, chapter_order)
    try:
        from pdf_render import render_markdown_to_pdf
        filepath = 'tmp_export.pdf'
        render_markdown_to_pdf(text, filepath, title=title)
    except Exception as e:
        return jsonify({"error": f"PDF 生成失败：{e}"}), 500
    return send_file(filepath, as_attachment=True, download_name=title + '.pdf')


@app.route('/api/export_defense')
def export_defense():
    data = request.json
    text = data.get('text', '')
    title = data.get('title', '答辩问题预测与答题思路')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    doc = _build_docx(title, text, doc_type='analysis')
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
    doc = _build_docx(title, text, doc_type='outline')
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
    doc = _build_docx(title, text, doc_type='analysis')
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
    doc = _build_docx(title, text, doc_type='analysis')
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


def _parse_expert_review(text):
    """把 expert_review 的 JSON 字符串解析成 dict；失败返回 None"""
    if not text:
        return None
    import json as _json
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        return _json.loads(t)
    except Exception:
        return None


# 前端「流动式输出」需要下发的字段：与 index.html 的 _STREAM_MAP 对齐
_PARTIAL_FIELDS = [
    "parsed_rules", "similarity_report", "idea_feedback",
    "competitor_analysis", "business_model", "risk_analysis", "tech_solution",
    "implementation_plan", "social_value", "project_summary",
    "proposal", "proposal_outline", "judge_feedback", "proposal_analysis",
    "defense_questions", "ppt_outline", "speech_script", "one_liner",
]


def _emit_partial(full_state):
    """把已产出的字段写进当前任务的 partial，供 /api/status 流式下发。"""
    if not isinstance(full_state, dict):
        return
    partial = {k: full_state[k] for k in _PARTIAL_FIELDS if full_state.get(k)}
    if partial:
        set_partial(partial)


def _run_graph(app, state):
    """逐步执行 LangGraph 工作流，每步把已产出字段写进 partial；返回最终 state。"""
    result = None
    try:
        for chunk in app.stream(state, stream_mode="values"):
            result = chunk
            _emit_partial(chunk)
    except Exception:
        # 流式兜底：一个 chunk 都没拿到才退回 invoke（避免重复生成），否则直接上抛
        if result is None:
            result = app.invoke(state)
        else:
            raise
    return result


def _strip_identifying_text(t):
    """剔除文本里的院校名称、指导教师姓名（高置信度模式，后处理兜底）。"""
    import re
    if not t:
        return t
    # 指导教师 + 姓名（含职称）
    t = re.sub(
        r'(指导老师|指导教师)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}(?:教授|副教授|讲师|博士|主任|老师)?',
        '指导教师（隐去）', t)
    # 院校全称（高置信度，避免误伤「大学生」「商学院」等）
    t = re.sub(r'[\u4e00-\u9fa5]{2,4}(?:大学|学校)', '（隐去）', t)
    # 学院：只认较长校名（如「职业技术学院」「文理学院」），避开「商学院」等院系
    t = re.sub(r'[\u4e00-\u9fa5]{4,8}学院', '（隐去）', t)
    return t


def _strip_identifying_info(obj):
    """递归剔除身份信息：字符串过滤，dict/list 递归，其余原样。"""
    if isinstance(obj, str):
        return _strip_identifying_text(obj)
    if isinstance(obj, dict):
        return {k: _strip_identifying_info(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_identifying_info(x) for x in obj]
    return obj


def _ensure_risk_notice(text):
    """在申报书末尾追加统一的风险提示（AI 生成初稿声明），已存在则不重复追加。"""
    notice = "\n\n风险提示：本内容为 AI 生成初稿，请替换真实项目数据后提交。"
    t = (text or "").rstrip()
    if "风险提示" in t:
        return text
    return t + notice


def _run_generation(data):
    """执行生成流水线（加锁、存历史），返回结果 data dict；出错抛异常"""
    with lock:
        idea = data.get("idea", "")
        proposal_draft = data.get("proposal_draft", "")
        mode = data.get("mode", "fast")

        state: CompetitionState = {
            "competition_name": data.get("competition_name", ""),
            "rule_content": data.get("rule_content", ""),
            "idea": idea,
            "proposal_draft": proposal_draft,
            "user_keywords": data.get("keywords", ""),
            "outline_requirement": data.get("outline_requirement") or [],
            "scoring_weights": data.get("scoring_weights") or [],
            "humanize": data.get("humanize", "standard"),
            # 档位标记：简洁版=fast / 深度版=deep。competition_agents 里的
            # _spec_for / _tier_hint 依赖它决定输出规格，漏掉会默认按 deep 处理，
            # 导致简洁版的评委/诊断/答辩也写得又长又慢，失去两档差异。
            "tier": "deep" if mode == "deep" else "fast",
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
            "proposal_outline": "",
            "proposal_selfcheck": "",
            "judge_feedback": "",
            "judge_scores": [],
            "expert_review": "",
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

        if mode == "deep":
            result = _run_graph(deep_app, state)
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
            result = _run_graph(fast_app, state)

        # 统一在申报书末尾追加「风险提示」声明，保证简洁版 / 深度版最终提交稿都带
        result["proposal"] = _ensure_risk_notice(result.get("proposal", ""))

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
                "proposal_outline": result.get("proposal_outline", ""),
                "proposal_selfcheck": result.get("proposal_selfcheck", ""),
                "judge_feedback": result.get("judge_feedback", ""),
                "judge_scores": result.get("judge_scores", []),
                "expert_review": result.get("expert_review", ""),
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
        history_item["data"] = _strip_identifying_info(history_item["data"])
        save_history_item(history_item)

    try:
        from competition_agents import check_proposal_completeness
        completeness = check_proposal_completeness(result.get("proposal", ""), data.get("mode", "fast"))
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
        "proposal_outline": result.get("proposal_outline", ""),
        "proposal_selfcheck": result.get("proposal_selfcheck", ""),
        "judge_feedback": result.get("judge_feedback", ""),
        "judge_scores": result.get("judge_scores", []),
        "theme": (rich_deck or {}).get("theme", data.get("theme") or "tech") if isinstance(rich_deck, dict) else (data.get("theme") or "tech"),
        "expert_review": _parse_expert_review(result.get("expert_review", "")) or result.get("expert_review", ""),
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

    payload = _strip_identifying_info(payload)
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
    """⚠️ 已废弃：请改用 /api/generate_async + /api/status 轮询。保留仅为兼容旧前端。"""
    data = request.json or {}
    try:
        result_data = _run_generation(data)
        return jsonify({"success": True, "data": result_data, "deprecated": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": _friendly_error(e), "detail": str(e)})


# ---- 异步任务阶段上报 ----
# 用途：让 /api/status/<task_id> 能吐出「当前跑到哪一步」，前端据此渲染真实步骤。
# 调用方式（供 _run_generation / 各 Agent 内部使用）：
#     from app import _report_stage
#     _report_stage("parsing_rules")
# 约定阶段名见《协作_进度条stage约定.md》。
# tasks / report_stage / set_current_task / clear_current_task 已下沉到 stage_reporter.py（零依赖）。


@app.route('/api/generate_async', methods=['POST'])
def generate_async():
    data = request.json or {}
    task_id = uuid.uuid4().hex
    tasks[task_id] = {"status": "running", "stage": "start", "updated_at": time.time(),
                      "mode": data.get("mode", "fast")}

    def worker():
        set_current_task(task_id)          # 让 report_stage 知道往哪个任务写
        try:
            rd = _run_generation(data)
            if progress.is_cancelled(task_id):
                return
            progress.mark_done(task_id, data=rd)
        except TaskCancelled:
            print(f"[generate_async] 任务 {task_id} 已取消")
        except Exception as e:
            import traceback
            traceback.print_exc()
            app_log.error("generate", f"task={task_id[:8]} {_friendly_error(e)} | {traceback.format_exc(limit=2)}")
            progress.mark_error(task_id, error=_friendly_error(e), detail=str(e))
        finally:
            clear_speech_stream(task_id)
            clear_current_task()

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route('/api/cancel/<task_id>', methods=['POST'])
def cancel_generation(task_id):
    progress.cancel(task_id)
    return jsonify({"success": True, "cancelled": True, "eta_note": "最迟约 1 分钟内停止"})


@app.route('/api/status/<task_id>')
def get_task_status(task_id):
    t = tasks.get(task_id)
    if not t:
        return jsonify({"success": False, "error": "任务不存在或已过期"})
    # 兜底超时：running 且 10 分钟没任何更新，判定为卡死，避免前端无限等待
    if t.get("status") == "running" and (time.time() - t.get("updated_at", 0)) > 600:
        t["status"] = "error"
        t["error"] = "任务超时，请重试"
        t["stage"] = "error"
        t["updated_at"] = time.time()
    _stage = t.get("stage", "start")
    _label, _pct = stage_meta(_stage)
    resp = {
        "success": True,
        "status": t["status"],
        "stage": _stage,
        "stage_label": _label,
        "pct": _pct,
        "partial": t.get("partial"),
        "updated_at": t["updated_at"]
    }
    if t["status"] == "done":
        resp["data"] = t["data"]
    elif t["status"] == "error":
        resp["error"] = t["error"]
        resp["detail"] = t.get("detail")
    return jsonify(resp)


@app.route('/api/speech_stream/<task_id>')
def speech_stream(task_id):
    """演讲稿流式预览：返回当前已生成的演讲稿片段。"""
    return jsonify({"success": True, "text": get_speech_stream(task_id)})





@app.route('/api/export_all')
def export_all():
    import zipfile
    import io
    from docx_render import build_docx
    
    # 拿最新的历史记录
    history = load_history()
    if not history:
        return jsonify({"success": False, "error": "没有可导出的记录"})
    
    latest = history[0]
    data = latest["data"]
    
    # 要导出的文件列表（减少到 5 个核心文件，更快）；第三个元素为 doc_type
    files_to_export = [
        ("1_申报书全文.docx", data.get("proposal", ""), 'default'),
        ("2_竞品与商业模式.docx", data.get("competitor_analysis", "") + "\n\n" + data.get("business_model", ""), 'analysis'),
        ("3_风险分析与评委意见.docx", data.get("risk_analysis", "") + "\n\n" + data.get("judge_feedback", ""), 'analysis'),
        ("4_答辩问题预测.docx", data.get("defense_questions", ""), 'analysis'),
        ("5_PPT大纲.docx", data.get("ppt_outline", ""), 'outline'),
    ]
    
    # 直接在内存里打包，不写临时文件，速度快很多
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:  # 不压缩，直接打包
        for filename, text, doc_type in files_to_export:
            if not text or not text.strip():
                continue
            
            # 统一走 docx_render 渲染器（真表格 + 标准格式 + 封面目录页码）
            title = filename.replace('.docx', '')
            doc = build_docx(title, text, doc_type=doc_type)
            docx_buf = io.BytesIO()
            doc.save(docx_buf)
            docx_buf.seek(0)
            zf.writestr(filename, docx_buf.read())
    
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='科创赛事材料包.zip', mimetype='application/zip')

@app.route('/api/export_original_format', methods=['POST'])
def export_original_format():
    """B 链路：用户上传已有申报表 → AI 改内容 → 导出。
    mode=keep     (默认) 保留原格式排版，只原位换字
    mode=reformat        按申报书标准重新排版（用户主动勾选才走）
    """
    original_file = request.files.get('original_file')
    optimized_text = request.form.get('optimized_text', '')
    mode = request.form.get('mode', 'keep')
    title = request.form.get('title', '项目申报书')
    school = request.form.get('school')
    team = request.form.get('team')
    advisor = request.form.get('advisor')
    
    if not original_file:
        return jsonify({"success": False, "error": "没有原文件"})
    if not optimized_text.strip():
        return jsonify({"success": False, "error": "优化内容为空"})
    
    try:
        original_bytes = original_file.read()
        if mode == 'reformat':
            # A 链路：按申报书标准重排（封面 + 目录 + 页码）
            import io as _io
            from docx_render import build_docx
            doc = build_docx(title, optimized_text, doc_type='default',
                             school=school, team=team, advisor=advisor)
            buf = _io.BytesIO()
            doc.save(buf)
            buf.seek(0)
            fname = '申报书_标准排版.docx'
        else:
            # B 链路：原位换字，格式排版一律不动
            from docx_inplace import apply_content_keep_style
            buf, report = apply_content_keep_style(original_bytes, optimized_text)
            print('[export_original_format] 替换报告:', report)
            fname = '优化后的申报书.docx'

        return send_file(
            buf, as_attachment=True, download_name=fname,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"导出失败：{str(e)}"})


@app.route('/api/upload_file', methods=['POST'])
def upload_file():
    import os
    from werkzeug.utils import secure_filename
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有文件"})
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"success": False, "error": "没有文件"})
    purpose = (request.form.get('purpose') or 'draft').strip()
    
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
            # 多模态识别暂未接入（claude_llm 已注释），先明确提示而不是 ImportError
            return jsonify({"success": False, "error": "暂不支持图片识别，请导出为 PDF 或文字后重试"})
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
        if purpose == 'fanwen':
            _record_upload(text, file.filename, force_fanwen=True)
        else:
            _record_upload(text, file.filename)
        return jsonify({"success": True, "text": text})
    except Exception as e:
        return jsonify({"success": False, "error": f"文件解析失败：{str(e)}"})


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
    # 加固：内容全空时不能静默返回一个空 zip（22 字节）还告诉用户成功，
    # 否则用户下载到空包毫不知情。这里明确报错。
    valid = [m for m in mappings if m[2] and str(m[2]).strip()]
    if not valid:
        return jsonify({
            "error": "没有可打包的内容：未收到任何正文数据，请先生成一次再打包。",
            "hint": "该接口需要扁平字段（parsed_rules/proposal/ppt_outline 等），"
                    "而非 /api/history 返回的列表摘要。"
        }), 400
    skipped = [m[0] for m in mappings if not (m[2] and str(m[2]).strip())]
    if skipped:
        print("[export_zip] 内容为空已跳过 %d 项：%s" % (len(skipped), ", ".join(skipped)))

    tmpdir = 'tmp_export'
    os.makedirs(tmpdir, exist_ok=True)
    zippath = os.path.join(tmpdir, '科创赛事项目材料包.zip')

    # 素材打包里的申报书也要按官方章节排序 / 走 iCAN 双盲，
    # 否则单独下载是官方顺序、打包里又是另一套顺序，用户会以为系统不稳定。
    comp = (data.get('competition_name') or '').strip()

    def build_doc(title, text):
        dt = 'outline' if ('大纲' in title or 'PPT' in title) else ('default' if '申报书' in title else 'analysis')
        tt = text
        is_prop = ('申报书' in title)
        if comp and is_prop:
            order = _official_chapter_titles(comp)
            if order:
                tt = _reorder_markdown_by_chapters(tt, order)
        return _build_docx(title, tt, doc_type=dt,
                           subtitle=comp if is_prop else None,
                           school=data.get('school'),
                           team=data.get('team'),
                           advisor=data.get('advisor'),
                           competition_name=comp if is_prop else None)

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


@app.route('/api/competition_profiles')
def competition_profiles():
    """返回结构化比赛配置：章节顺序/评分重点/类型/提示词侧重/字数要求。"""
    try:
        from competition_agents import get_competition_profiles
        return jsonify({"success": True, "competitions": get_competition_profiles()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/competition/index')
def competition_index():
    """动态赛事索引：直接解析 data/*.txt，返回与 static/competition_index.json 同构的数据。

    这样改完 txt 不需要重跑 scripts/build_comp_index.py，前端可优先调接口、失败回退静态 JSON。
    """
    try:
        import importlib.util
        _script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "scripts", "build_comp_index.py")
        spec = importlib.util.spec_from_file_location("build_comp_index_dyn", _script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return jsonify({"success": True, **mod.build_index()})
    except Exception as e:
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


# ============ 范文库管理接口 ============

# ---- 范文自动评分（队友上传场景）----
_FILLER_WORDS = ["致力于", "旨在", "赋能", "打造生态", "全方位", "一体化",
                 "深度融合", "着力", "积极推动", "显著提升"]
_EVIDENCE_WORDS = ["试点", "问卷", "访谈", "注册", "用户", "留存", "转化", "付费",
                   "成本", "收入", "准确率", "覆盖", "合作", "反馈", "测试"]
_HONEST_WORDS = ["尚未", "仅", "局限", "不足", "风险", "待验证", "建议转人工",
                 "暂未", "未实现", "难点"]
_NUM_RE = None


def _auto_score(content):
    """给上传的范文自动打质量分（0-100），启发式，不调 LLM。

    为什么需要：前端上传时不传 score，入库就是 0 分——列表显示「0 分」、
    按 score DESC 排序永远垫底；一旦将来按「>=75 才算范文」过滤，
    队友手工传的范文会全部失效（这才是最坏的情况）。

    判据来自高分申报书的真实特征：
      加分 = 数据化表述（核心）+ 具体证据 + 敢写局限 + 分点结构 + 长度适中
      扣分 = 空话套话 + 过短/过长
    """
    global _NUM_RE
    import re
    if _NUM_RE is None:
        _NUM_RE = re.compile(r'\d+(?:\.\d+)?\s*(?:%|％|人|次|万|元|个|天|月|年|'
                             r'分|秒|家|所|台|条|张|款|名|户)')
    text = (content or '').strip()
    n = len(text)
    # 基础 40 + 各项上限 53 = 93 封顶（对齐种子范文人工标的最高分 93，
    # 避免高质量范文全挤在 100 分而失去排序意义）
    score = 40.0

    # 1) 长度：种子范文是 300-560 字，这是最合适的片段长度
    if 300 <= n <= 700:
        score += 15
    elif (150 <= n < 300) or (700 < n <= 1200):
        score += 8
    elif n < 100:
        score -= 20
    elif n > 1500:
        score -= 10

    # 2) 数据化表述：高分稿最核心特征（"注册2431人"而非"用户很多"）
    score += min(len(_NUM_RE.findall(text)), 6) * 3

    # 3) 具体证据/细节
    score += min(sum(1 for w in _EVIDENCE_WORDS if w in text), 5) * 2

    # 4) 诚实：主动写局限是高分稿的标志，通篇吹牛反而像 AI
    if any(w in text for w in _HONEST_WORDS):
        score += 6

    # 5) 空话套话
    score -= min(sum(1 for w in _FILLER_WORDS if w in text), 3) * 5

    # 6) 分点结构
    if re.search(r'(第[一二三四五六七八九]|首先|其次|最后|其一|其二|[0-9][\.、])', text):
        score += 4

    return int(max(0, min(100, round(score))))


def _auto_summary(content, limit=42):
    """自动摘要：取首个完整句子，兜底截断。"""
    text = (content or '').strip().replace('\n', ' ')
    if not text:
        return ''
    for sep in ('。', '！', '？', '；'):
        i = text.find(sep)
        if 12 <= i <= limit + 20:
            return text[:i + 1]
    return text[:limit] + ('…' if len(text) > limit else '')


@app.route('/api/kb/add', methods=['POST'])
def kb_add():
    data = request.get_json(force=True, silent=True) or {}
    content = data.get('content', '')
    tags = data.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    if not content.strip():
        return jsonify({"success": False, "error": "内容为空"}), 400

    # 未显式指定 score/type 时自动判定（队友手工上传的常规路径）
    score = data.get('score')
    stype = data.get('type')
    auto_scored = score is None
    if auto_scored:
        score = _auto_score(content)
    if not stype:
        stype = '范文' if int(score or 0) >= 75 else '材料'
    summary = data.get('summary') or _auto_summary(content)

    try:
        from kb_samples import add_sample
        sid, is_new = add_sample(content, tags, source=data.get('source', ''),
                                 score=score, type=stype, summary=summary)
        return jsonify({"success": True, "id": sid, "duplicate": not is_new,
                        "score": score, "type": stype, "auto_scored": auto_scored})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kb/list')
def kb_list():
    tag = request.args.get('tag', '')
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100
    try:
        from kb_samples import list_samples
        items = list_samples(tag=tag or None, limit=limit)
        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kb/delete/<int:sample_id>', methods=['DELETE'])
def kb_delete(sample_id):
    try:
        from kb_samples import delete_sample
        ok = delete_sample(sample_id)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kb/tags')
def kb_tags():
    try:
        from kb_samples import get_all_tags
        d = get_all_tags()
        return jsonify({"success": True, "module": d["module"], "track": d["track"], "feature": d["feature"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/kb/search')
def kb_search():
    """按关键词真实检索（走 kb_retrieve，与生成时同一套逻辑），供前端检索测试用。

    /api/kb/list?tag= 是精确标签过滤，用户输入「苏轼文旅」命中不了标签「文化文旅」，
    所以单独开这个接口：先 extract_keywords 抽标签，再 search_samples 检索。
    """
    q = request.args.get('keywords', '') or request.args.get('q', '')
    module = request.args.get('module', '')
    try:
        from kb_retrieve import extract_keywords, search_samples
        kws = extract_keywords(q)
        ref = search_samples(kws, module or None)
        return jsonify({"success": True, "keywords": kws,
                        "ref": ref, "hits": len(ref or "")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============ 运行日志 / 错误报告（Codex 后端接口 + WorkBuddy 前端面板）============

@app.route('/api/logs')
def api_logs():
    level = request.args.get('level', '')
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100
    return jsonify({
        "success": True,
        "logs": app_log.get_logs(level or None, limit),
        "error_count": app_log.error_count(),
    })


@app.route('/api/logs/report')
def api_logs_report():
    errors = app_log.get_logs("ERROR", 50)
    lines = ["# 运行错误报告", "", "最近错误 %d 条：" % len(errors), ""]
    for x in errors:
        lines.append("- [%s] [%s] %s" % (x["time"], x["source"], x["message"]))
        for lesson in app_log.match_lessons(x["message"]):
            lines.append("    ↳ 可能相关踩坑：%s —— %s" % (lesson["title"], lesson["summary"]))
    lines.append("")
    lines.append("---")
    lines.append("（由 /api/logs/report 自动生成，可直接转发给 Codex / WorkBuddy 排查）")
    return jsonify({"success": True, "report": "\n".join(lines), "errors": errors})


@app.route('/api/lessons')
def api_lessons():
    q = request.args.get('q', '')
    lessons = app_log.match_lessons(q) if q else app_log.LESSONS
    return jsonify({"success": True, "lessons": lessons, "total": len(lessons)})


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    import traceback
    app_log.error("http", "%s %s: %s | %s"
                  % (request.path, type(e).__name__, e, traceback.format_exc(limit=2)))
    return jsonify({"success": False, "error": _friendly_error(e), "detail": str(e)}), 500
