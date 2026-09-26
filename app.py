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
import gzip as _gzip
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response, g
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


# ===== gzip 压缩 =====
# 首页 index.html 约 400KB，gzip 后约 100KB，加载快一倍。
# 只压缩文本类响应且 >500 字节；流式预览接口不压缩（避免影响实时性）。
@app.after_request
def _gzip_response(resp):
    if request.path.startswith('/api/speech_stream'):
        return resp
    if getattr(resp, 'direct_passthrough', False):
        return resp
    if resp.headers.get('Content-Encoding'):
        return resp
    if 'gzip' not in (request.headers.get('Accept-Encoding') or '').lower():
        return resp
    ctype = (resp.headers.get('Content-Type') or '').lower()
    if not any(t in ctype for t in ('text/', 'json', 'javascript', 'css', 'svg', 'xml')):
        return resp
    data = resp.get_data()
    if len(data) < 500:
        return resp
    resp.set_data(_gzip.compress(data, 6))
    resp.headers['Content-Encoding'] = 'gzip'
    resp.headers['Content-Length'] = str(len(resp.get_data()))
    resp.headers.setdefault('Vary', 'Accept-Encoding')
    return resp


# ===== 匿名用户隔离（无登录）=====
# 首次访问下发一个长期匿名 cookie（comp_uid），历史记录/反馈按它隔离，
# 让公网随机访客之间看不到彼此的生成记录，同时不做复杂登录系统。
# 注：admin / 导出 / 分享链接仍是全局或 token 校验，范文库按设计保持团队共享。
@app.before_request
def _ensure_uid():
    uid = (request.cookies.get('comp_uid') or '').strip()
    if not uid or len(uid) > 64 or not uid.isalnum():
        uid = uuid.uuid4().hex
    g.uid = uid
    g.uid_is_new = 'comp_uid' not in request.cookies


@app.after_request
def _set_uid_cookie(resp):
    if getattr(g, 'uid_is_new', False):
        resp.set_cookie('comp_uid', g.uid, max_age=60 * 60 * 24 * 365,
                        httponly=True, samesite='Lax')
    return resp


def _current_uid():
    """取当前匿名用户 id；无 cookie 时退回 IP，保证旧前端也能落到一个稳定隔离键。"""
    return getattr(g, 'uid', None) or (request.cookies.get('comp_uid') or '').strip() or \
        (request.remote_addr or 'anon')


# 并发稳定器：限制同时进行的生成任务数，防止多用户同时用把服务压垮
MAX_CONCURRENT_GEN = 4
_active_gen_lock = threading.Lock()
_active_gen_count = 0

# 简单限流：同一 IP 1 分钟最多生成 5 次，防止刷接口（学生项目级防护，无需登录系统）。
# 说明：进程内内存限流，gunicorn 多 worker 时是「每 worker 各自限 5 次」；
# 对当前单机小规模部署足够，若以后上多机/高并发再升级为共享存储（如 Redis）。
_RATE_WINDOW_SEC = 60
_RATE_LIMIT = 5
_rate_lock = threading.Lock()
_rate_hits = {}  # ip -> list[float] 命中时间戳（Unix 秒）


def _client_ip():
    """取客户端 IP，优先信任反代传入的 X-Forwarded-For 首地址。"""
    fwd = (request.headers.get('X-Forwarded-For') or '').strip()
    if fwd:
        return fwd.split(',')[0].strip()
    return (request.remote_addr or 'unknown').strip()


def _rate_limited():
    """检查并记录一次生成请求；超过限流返回 True，否则返回 False。"""
    ip = _client_ip()
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_hits.get(ip, []) if now - t < _RATE_WINDOW_SEC]
        if len(hits) >= _RATE_LIMIT:
            _rate_hits[ip] = hits
            return True
        hits.append(now)
        _rate_hits[ip] = hits
        # 键过多时顺手清理，避免内存缓慢增长
        if len(_rate_hits) > 5000:
            for k in list(_rate_hits.keys()):
                _rate_hits[k] = [t for t in _rate_hits[k] if now - t < _RATE_WINDOW_SEC]
                if not _rate_hits[k]:
                    del _rate_hits[k]
        return False

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
    # WAL 模式：多用户并发读写时减少锁冲突，降低"database is locked"崩溃
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    # 历史记录表
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  competition_name TEXT,
                  idea TEXT,
                  mode TEXT,
                  result_data TEXT,
                  created_time TEXT,
                  rating INTEGER DEFAULT 0)''')
    # 旧库迁移：给已有的 history 表补 rating 列（CREATE IF NOT EXISTS 不会改老表结构）
    cols = [r[1] for r in c.execute("PRAGMA table_info(history)").fetchall()]
    if "rating" not in cols:
        c.execute("ALTER TABLE history ADD COLUMN rating INTEGER DEFAULT 0")
    if "duration" not in cols:
        c.execute("ALTER TABLE history ADD COLUMN duration REAL DEFAULT 0")
    if "status" not in cols:
        c.execute("ALTER TABLE history ADD COLUMN status TEXT DEFAULT 'success'")
    if "user_id" not in cols:
        c.execute("ALTER TABLE history ADD COLUMN user_id TEXT DEFAULT ''")
    # 用户反馈表：结果页打分旁的文本框，纯文本收集，不做通知/回复系统
    c.execute('''CREATE TABLE IF NOT EXISTS feedback
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  history_id INTEGER,
                  content TEXT NOT NULL,
                  created_time TEXT,
                  category TEXT DEFAULT '其他')''')
    # 旧库迁移：给 feedback 表补 category 列
    fb_cols = [r[1] for r in c.execute("PRAGMA table_info(feedback)").fetchall()]
    if "category" not in fb_cols:
        c.execute("ALTER TABLE feedback ADD COLUMN category TEXT DEFAULT '其他'")
    if "user_id" not in fb_cols:
        c.execute("ALTER TABLE feedback ADD COLUMN user_id TEXT DEFAULT ''")
    # 生成失败记录表（用于算成功率 + 动态监视）
    c.execute('''CREATE TABLE IF NOT EXISTS gen_failures
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id TEXT, error TEXT, detail TEXT, created_time TEXT)''')
    # 问题工单表：自动路由（前端/后端），可标记解决并留解决说明
    c.execute('''CREATE TABLE IF NOT EXISTS issues
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  kind TEXT, source TEXT, content TEXT, created_time TEXT,
                  status TEXT DEFAULT 'open', resolved_time TEXT, resolution TEXT DEFAULT '')''')
    # 临时分享链接表：token -> 历史记录，7 天过期，无需登录即可看结果
    c.execute('''CREATE TABLE IF NOT EXISTS shares
                 (token TEXT PRIMARY KEY,
                  history_id INTEGER,
                  created_time TEXT,
                  expires_time TEXT)''')
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
# 生成并发闸：允许最多 3 个生成任务同时进行（原来 Lock 只有 1 个，多用户会排长队）。
# 大模型调用另有 _LLM_GATE(4) 限流 + SQLite WAL 并发写，3 个并行是稳定与速度的平衡点。
lock = threading.Semaphore(3)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HISTORY_FILE'] = 'history.json'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 上传文件上限 20MB，防超大文件把服务压垮

# 存储最新结果
latest_result = None

# 历史记录
import json
from datetime import datetime

def _row_to_item(row):
    rid, comp, idea, mode, result_data, created_time, rating = row
    try:
        data = json.loads(result_data)
    except Exception:
        data = {}
    return {
        "id": rid, "time": created_time, "competition_name": comp,
        "idea": idea, "mode": mode, "score": data.get("score", ""), "data": data,
        "rating": rating or 0,
    }


def load_history(limit=200, offset=0, q=None, uid=None):
    """从 SQLite 读取历史记录（新的在前），返回兼容旧接口的 list。

    uid 传入时只返回该匿名用户自己的记录；不传则返回全部（供 admin/健康检查用）。
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    sql = "SELECT id, competition_name, idea, mode, result_data, created_time, rating FROM history"
    params = []
    conds = []
    if q:
        conds.append("(competition_name LIKE ? OR idea LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if uid:
        conds.append("user_id = ?")
        params.append(uid)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


def count_history(q=None, uid=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    conds, params = [], []
    if q:
        conds.append("(competition_name LIKE ? OR idea LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if uid:
        conds.append("user_id = ?")
        params.append(uid)
    sql = "SELECT COUNT(*) FROM history"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    c.execute(sql, params)
    total = c.fetchone()[0]
    conn.close()
    return total


def save_history_item(item):
    """插入一条历史记录到 SQLite，返回新 id"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO history (competition_name, idea, mode, result_data, created_time, duration, status, user_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (item.get("competition_name", ""), item.get("idea", ""), item.get("mode", ""),
               json.dumps(item.get("data", {}), ensure_ascii=False),
               item.get("time", datetime.now().strftime("%Y-%m-%d %H:%M")),
               item.get("duration", 0), item.get("status", "success"),
               item.get("user_id", "")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    # 新增历史记录后触发各类「历史数据范式」自动蒸馏检查（各有阈值 + 冷却，不够就休眠）
    try:
        from distill_scheduler import maybe_auto_distill
        for _kind in ("judge", "analysis", "deck_speech", "similarity"):
            maybe_auto_distill(_kind)
    except Exception:
        pass
    return new_id


def record_gen_failure(task_id, error, detail=""):
    """记录一次生成失败（用于成功率统计 + 动态监视）。"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO gen_failures (task_id, error, detail, created_time) VALUES (?, ?, ?, ?)",
                  (str(task_id or "")[:32], str(error or "")[:200], str(detail or "")[:500],
                   datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        create_issue("backend", "error", error)
    except Exception:
        pass


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
def _is_double_blind(competition_name):
    """该赛事是否双盲评审（封面不能出现学校 / 单位 / 指导老师）。"""
    if not competition_name:
        return False
    try:
        from competition_agents import get_competition_profile
        return bool(get_competition_profile(competition_name).get("double_blind"))
    except Exception:
        return False


def _mask_double_blind(text, school=None, advisor=None):
    """双盲赛事的正文脱敏：学校名 →「本校」，指导老师姓名 →「指导老师」。

    只隐封面是不够的 —— 正文里写一句「依托 XX 大学实验室」评委照样能认出学校，
    所以要连正文一起处理。只动学校 / 导师这两个字段命中的字符串，不碰其它内容。
    """
    if not text:
        return text
    out = str(text)
    if school:
        s = str(school).strip()
        # 正文里常写简称（「中南」而不是「中南大学」），所以全称和去后缀的核心词都要替换
        cands = {s}
        core = re.sub(r'(大学|学院|学校|职业技术学院|高等专科学校|附中|中学)$', '', s)
        if len(core) >= 2:
            cands.add(core)
        for c in sorted([x for x in cands if x], key=len, reverse=True):
            out = out.replace(c, '本校')
    if advisor:
        a = str(advisor).strip()
        name = re.sub(r'(老师|教授|副教授|讲师|导师)$', '', a)
        title = r'(指导老师|指导教师|导师|教授)'
        # A. 称谓后面已经跟着姓名（「指导老师张伟」「指导教师李伟教授」）→ 只保留称谓，
        #    不能整段换成「指导老师」，否则变成「指导老师指导老师」
        for pat in ([a] if a else []) + ([name] if len(name) >= 2 else []):
            out = re.sub(title + r'[ \t]*' + re.escape(pat) + r'[ \t]*(老师|教授|导师)?', r'\1', out)
        # B. 其余位置（「李伟认为」「李伟老师指出」）→ 换成称谓。
        #    必须带可选称谓一起吃掉再替换，否则「李伟老师」会先被 replace 成
        #    「指导老师老师」，多出一个「老师」
        if len(name) >= 2:
            out = re.sub(re.escape(name) + r'[ \t]*(老师|教授|导师)?', '指导老师', out)
        if a and a != name:
            out = out.replace(a, '指导老师')
    # 兜底：显式写「指导老师：XXX」的整行，无论 XXX 是不是上面那个字段都隐掉
    out = re.sub(r'^([>\-\s\*]*)(指导老师|指导教师|导师)[ \t]*[：:].*$',
                 r'\1\2：（按双盲评审要求隐去）', out, flags=re.M)
    return out


def _build_docx(title, text, doc_type='report', subtitle=None,
                school=None, team=None, advisor=None, competition_name=None):
    """统一走 docx_render 渲染器（格式层，WorkBuddy 已交付）。"""
    from docx_render import build_docx
    text = _strip_identifying_text(text or "")
    show_school_advisor = True
    if _is_double_blind(competition_name):
        show_school_advisor = False
        text = _mask_double_blind(text, school=school, advisor=advisor)
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
    """把用户上传的文本自动记录进记忆库（去重 + 自动打标签 + 质量评估 + 摘要）。

    版权整改：不再自动把上传内容归为「范文」，一律按「材料」入库（官方规则/评分/模板）。
    收集他人获奖原文需原作者书面授权，另行人工处理。
    """
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
        # 只保留「材料」（官方公开资料）；不再自动升为「范文」
        mem_type = "材料"
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
    if ext == '.doc':
        return jsonify({"success": False, "error": "旧版 .doc 读不了：请在 Word 里「另存为 .docx」再上传，或把内容另存为 TXT / PDF"})
    if ext not in ('.pdf', '.docx', '.txt', '.md'):
        return jsonify({"success": False, "error": "不支持的文件格式（" + (ext or '无扩展名') + "），请上传 PDF / DOCX / TXT / MD"})

    # 大小校验：先看 Content-Length 快速拦截，再按实际字节数兜底（防超大文件压内存）
    if request.content_length and request.content_length > MAX_UPLOAD_SIZE + 1024 * 1024:
        return jsonify({"success": False, "error": "文件过大（上限 20MB），请压缩或拆分后再传"})
    data_bytes = file.read(MAX_UPLOAD_SIZE + 1)
    if len(data_bytes) > MAX_UPLOAD_SIZE:
        return jsonify({"success": False, "error": "文件过大（上限 20MB），请压缩或拆分后再传"})
    # 内容校验：扩展名和真实文件头要匹配，防止把可执行文件改名成 .pdf/.docx 绕过
    head = data_bytes[:8]
    if ext == '.pdf' and not data_bytes.lstrip()[:5].startswith(b'%PDF-'):
        return jsonify({"success": False, "error": "文件内容不是有效的 PDF，请确认后重新上传"})
    if ext == '.docx' and head[:2] != b'PK':
        return jsonify({"success": False, "error": "文件内容不是有效的 Word(.docx)，请确认后重新上传"})
    if ext in ('.txt', '.md') and b'\x00' in data_bytes[:4096]:
        return jsonify({"success": False, "error": "文件内容不是纯文本，请另存为 TXT / Markdown 后重新上传"})

    base = secure_filename(os.path.splitext(raw_name)[0]) or 'upload'
    filename = base + '_' + str(int(time.time())) + ext
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(filepath, 'wb') as f:
        f.write(data_bytes)
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
        # 版权整改：不再收集他人获奖原文（需原作者书面授权），一律按「材料」入库
        _record_upload(text, raw_name)
        return jsonify({"success": True, "text": text[:20000], "purpose": "fanwen",
                        "note": "已按官方资料入库；收集他人范文需原作者书面授权"})
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
    text = _strip_identifying_text(text)
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
    project = _project_name_hint(data)
    competition = data.get('competition_name') or ''
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(project, competition, title, '.docx'))


@app.route('/api/export_pdf', methods=['POST'])
def export_pdf():
    """把申报书/说明书 Markdown 导出为 PDF（iCAN 提交用，A4 中文）"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    title = data.get('title', '申报书')
    if not text.strip():
        return jsonify({"error": "内容为空"}), 400
    text = _strip_identifying_text(text)
    chapter_order = data.get('chapter_order')
    if not chapter_order and data.get('competition_name'):
        chapter_order = _official_chapter_titles(data.get('competition_name'))
    if chapter_order:
        text = _reorder_markdown_by_chapters(text, chapter_order)
    # PDF 不走 _build_docx，双盲脱敏要在这里单独做一遍，否则封面省了正文照样漏
    if _is_double_blind(data.get('competition_name')):
        text = _mask_double_blind(text,
                                  school=data.get('school'),
                                  advisor=data.get('advisor'))
    try:
        from pdf_render import render_markdown_to_pdf
        filepath = 'tmp_export.pdf'
        render_markdown_to_pdf(text, filepath, title=title)
    except Exception as e:
        return jsonify({"error": f"PDF 生成失败：{e}"}), 500
    project = _project_name_hint(data)
    competition = data.get('competition_name') or ''
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(project, competition, title, '.pdf'))


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
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(_project_name_hint(data), data.get('competition_name') or '', '答辩问题', '.docx'))


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
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(_project_name_hint(data), data.get('competition_name') or '', 'PPT大纲', '.docx'))


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
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(_project_name_hint(data), data.get('competition_name') or '', '竞品分析', '.docx'))


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
    return send_file(filepath, as_attachment=True,
                     download_name=_export_filename(_project_name_hint(data), data.get('competition_name') or '', '商业模式', '.docx'))


@app.route('/api/history')
def get_history():
    limit = max(1, min(int(request.args.get("limit", 20)), 100))
    offset = max(0, int(request.args.get("offset", 0)))
    q = request.args.get("q", "").strip()
    uid = _current_uid()
    history = load_history(limit=limit, offset=offset, q=q, uid=uid)
    total = count_history(q, uid=uid)
    # 只返回摘要，不返回完整数据
    summary = [{"id": h["id"], "time": h["time"], "competition_name": h["competition_name"],
                "idea": h["idea"], "score": h["score"], "rating": h.get("rating", 0)} for h in history]
    return jsonify({"success": True, "history": summary, "total": total, "limit": limit, "offset": offset})


@app.route('/api/history/groups')
def history_groups():
    """按比赛类型自动分组的历史记录（前端下拉按比赛过滤用）。"""
    history = load_history(limit=500, uid=_current_uid())
    groups = {}
    for h in history:
        comp = (h.get("competition_name") or "未标注比赛").strip()
        groups.setdefault(comp, []).append({
            "id": h["id"], "time": h["time"], "idea": h["idea"],
            "score": h["score"], "rating": h.get("rating", 0),
        })
    result = [{"competition": k, "count": len(v), "items": v} for k, v in groups.items()]
    result.sort(key=lambda x: -x["count"])
    return jsonify({"success": True, "groups": result, "total": len(history)})


def _html_esc(s):
    return (str(s or '')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _share_page(title, comp, idea, body_html):
    t = _html_esc(title)
    c = _html_esc(comp)
    css = ("body{font-family:'Microsoft YaHei',sans-serif;max-width:860px;margin:0 auto;padding:24px;"
           "line-height:1.85;color:#1f2a4d;background:#fafbfe}"
           "h1{font-size:24px;margin-bottom:8px}"
           ".meta{color:#6b7a99;font-size:13px;margin-bottom:20px}"
           "h2{font-size:18px;margin:22px 0 8px;border-left:4px solid #5b6ee1;padding-left:10px}"
           "h3{font-size:15px;margin:16px 0 6px}"
           "p{margin:8px 0;white-space:pre-wrap}"
           "hr{border:none;border-top:1px solid #e2e7f2;margin:16px 0}")
    return ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>" + t + "</title><style>" + css + "</style></head><body>"
            "<h1>" + t + "</h1><div class='meta'>" + c + "</div>" + body_html + "</body></html>")


def _md_to_html(t):
    out, buf = [], []
    for line in (t or '').split(chr(10)):
        s = _html_esc(line.rstrip())
        if not s.strip():
            if buf:
                out.append('<p>' + '<br>'.join(buf) + '</p>')
                buf = []
            continue
        if s.startswith('### '):
            if buf:
                out.append('<p>' + '<br>'.join(buf) + '</p>'); buf = []
            out.append('<h3>' + s[4:] + '</h3>')
        elif s.startswith('## '):
            if buf:
                out.append('<p>' + '<br>'.join(buf) + '</p>'); buf = []
            out.append('<h2>' + s[3:] + '</h2>')
        elif s.startswith('# '):
            if buf:
                out.append('<p>' + '<br>'.join(buf) + '</p>'); buf = []
            out.append('<h1>' + s[2:] + '</h1>')
        elif s.strip() == '---':
            if buf:
                out.append('<p>' + '<br>'.join(buf) + '</p>'); buf = []
            out.append('<hr>')
        else:
            buf.append(s)
    if buf:
        out.append('<p>' + '<br>'.join(buf) + '</p>')
    return ''.join(out)


@app.route('/api/share/<int:history_id>', methods=['POST'])
def create_share(history_id):
    import secrets
    from datetime import timedelta
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM history WHERE id=?", (history_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"success": False, "error": "记录不存在"}), 404
    token = secrets.token_urlsafe(8)
    now = datetime.now()
    expires = now + timedelta(days=7)
    c.execute("INSERT OR REPLACE INTO shares (token, history_id, created_time, expires_time) VALUES (?,?,?,?)",
              (token, history_id, now.strftime("%Y-%m-%d %H:%M"), expires.strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "token": token, "url": "/share/" + token,
                    "expires": expires.strftime("%Y-%m-%d %H:%M")})


@app.route('/share/<token>')
def view_share(token):
    from datetime import datetime as _dt
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT history_id, expires_time FROM shares WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return _share_page("链接不存在或已失效", "", "", "<p>该分享链接无效。</p>"), 404
    history_id, expires_time = row
    try:
        if _dt.now() > _dt.strptime(expires_time, "%Y-%m-%d %H:%M"):
            return _share_page("链接已过期", "", "", "<p>该分享链接已过期，请联系分享者重新生成。</p>"), 410
    except Exception:
        pass
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT competition_name, idea, result_data FROM history WHERE id=?", (history_id,))
    hr = c.fetchone()
    conn.close()
    if not hr:
        return _share_page("记录不存在", "", "", "<p>该记录已删除。</p>"), 404
    comp, idea, result_data = hr
    data = {}
    try:
        data = json.loads(result_data)
    except Exception:
        data = {}
    title = data.get("one_liner") or idea or comp or "科创项目分享"
    proposal = data.get("proposal") or ""
    body = _md_to_html(proposal)
    return _share_page(title, comp, idea, body)


@app.route('/api/history/<int:history_id>')
def get_history_detail(history_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT result_data, rating FROM history WHERE id = ? AND user_id = ?",
              (history_id, _current_uid()))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "记录不存在"})
    try:
        data = json.loads(row[0])
    except Exception:
        data = {}
    return jsonify({"success": True, "data": data, "rating": row[1] or 0})


@app.route('/api/history/<int:history_id>/rate', methods=['POST'])
def rate_history(history_id):
    """给某条历史记录打 1-5 星（覆盖式保存，存 SQLite）。"""
    payload = request.get_json(silent=True) or {}
    try:
        rating = int(payload.get("rating"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "评分必须是 1-5 的整数"}), 400
    if rating < 1 or rating > 5:
        return jsonify({"success": False, "error": "评分必须是 1-5 的整数"}), 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE history SET rating = ? WHERE id = ? AND user_id = ?",
              (rating, history_id, _current_uid()))
    conn.commit()
    updated = c.rowcount
    conn.close()
    if not updated:
        return jsonify({"success": False, "error": "记录不存在"}), 404
    return jsonify({"success": True, "id": history_id, "rating": rating})


@app.route('/api/feedback', methods=['POST'])
def add_feedback():
    """收集用户反馈：结果页文本框 + 提交按钮，纯文本入库，后台直接看。"""
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "error": "反馈内容不能为空"}), 400
    if len(content) > 2000:
        content = content[:2000]
    history_id = payload.get("history_id")
    try:
        history_id = int(history_id) if history_id not in (None, "") else None
    except (TypeError, ValueError):
        history_id = None
    category = _categorize_feedback(content)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO feedback (history_id, content, created_time, category, user_id) VALUES (?, ?, ?, ?, ?)",
              (history_id, content, datetime.now().strftime("%Y-%m-%d %H:%M"), category, _current_uid()))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    if category in ("问题反馈", "吐槽"):
        create_issue(_classify_issue(content), "feedback", content)
    return jsonify({"success": True, "id": new_id, "category": category})


@app.route('/api/feedback')
def list_feedback():
    """后台查看全部反馈（最新的在前，封顶 500 条）。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, history_id, content, created_time, category FROM feedback "
        "ORDER BY id DESC LIMIT 500").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    return jsonify({"success": True, "feedback": items, "total": len(items)})


@app.route('/api/feedback/export')
def export_feedback():
    """一键导出全部反馈为格式化 Excel（表头加粗底色、列宽自适应、冻结表头、斑马纹）。"""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, history_id, content, created_time, category FROM feedback ORDER BY id ASC").fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "用户反馈"

    headers = ["提交时间", "反馈内容", "分类", "关联历史ID"]
    header_fill = PatternFill("solid", fgColor="2563EB")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    zebra_fill = PatternFill("solid", fgColor="F3F4F6")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for i, r in enumerate(rows, start=2):
        vals = [r["created_time"] or "",
                r["content"] or "",
                r["category"] or "其他",
                r["history_id"] if r["history_id"] is not None else ""]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=i, column=col, value=v)
            cell.border = border
            cell.font = Font(size=11)
            cell.alignment = Alignment(vertical="top", wrap_text=(col == 2))
            if i % 2 == 0:
                cell.fill = zebra_fill

    if not rows:
        ws.cell(row=2, column=2, value="暂无反馈")

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 56
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 14
    ws.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = "用户反馈_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=fname)


@app.route('/admin')
def admin_home():
    """管理后台 · 总览首页：关键数字一屏看完，再点进详细面板 / 监视。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    total_gen = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_gen = c.execute(
        "SELECT COUNT(*) FROM history WHERE created_time LIKE ?", (today + "%",)).fetchone()[0]
    avg_row = c.execute("SELECT AVG(rating), COUNT(*) FROM history WHERE rating > 0").fetchone()
    avg_rating = round(avg_row[0], 2) if avg_row and avg_row[0] is not None else 0
    rated_count = avg_row[1] if avg_row else 0
    fail_total = c.execute("SELECT COUNT(*) FROM gen_failures").fetchone()[0]
    success_rate = round(total_gen * 100.0 / (total_gen + fail_total), 1) if (total_gen + fail_total) else 100.0
    feedback_total = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    open_issue = c.execute("SELECT COUNT(*) FROM issues WHERE status='open'").fetchone()[0]
    recent_fb = c.execute(
        "SELECT content, created_time FROM feedback ORDER BY id DESC LIMIT 4").fetchall()
    recent_fail = c.execute(
        "SELECT error, created_time FROM gen_failures ORDER BY id DESC LIMIT 4").fetchall()
    conn.close()

    fb_rows = "".join(
        '<li><span class="t">%s</span>%s</li>'
        % (r["created_time"] or "", _html_escape(r["content"] or ""))
        for r in recent_fb) or '<li class="e">暂无反馈</li>'
    fail_rows = "".join(
        '<li><span class="t">%s</span>%s</li>'
        % (r["created_time"] or "", _html_escape(r["error"] or ""))
        for r in recent_fail) or '<li class="e">暂无失败</li>'

    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>赛创助手 · 管理后台</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:linear-gradient(160deg,#eef2ff,#f8fafc);color:#111827;margin:0;padding:32px 18px;line-height:1.6}
.wrap{max-width:880px;margin:0 auto}
.nav{display:flex;gap:8px;margin-bottom:22px;flex-wrap:wrap}
.nav a{background:#fff;color:#475569;text-decoration:none;padding:9px 16px;border-radius:10px;font-size:14px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.nav a.active{background:#4f46e5;color:#fff}
h1{font-size:24px;margin:0 0 4px}
.sub{color:#64748b;font-size:14px;margin-bottom:20px}
.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:22px}
.h{background:#fff;border-radius:14px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.h .n{font-size:32px;font-weight:800;color:#4f46e5}
.h .n.good{color:#059669}.h .n.bad{color:#e11d48}
.h .l{font-size:13px;color:#64748b;margin-top:5px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.cols{grid-template-columns:1fr}}
.box{background:#fff;border-radius:14px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.box h2{font-size:15px;margin:0 0 10px;color:#111827}
.box ul{list-style:none;padding:0;margin:0}
.box li{font-size:14px;padding:8px 0;border-bottom:1px solid #f1f5f9}
.box li:last-child{border-bottom:none}
.box li .t{display:block;font-size:12px;color:#94a3b8;margin-bottom:2px}
.box li.e{color:#94a3b8;text-align:center;padding:16px}
.more{margin-top:18px;font-size:14px}
.more a{color:#4f46e5;text-decoration:none;font-weight:600}
</style></head><body><div class="wrap">
<nav class="nav"><a href="/admin" class="active">🏠 总览</a><a href="/admin/panel">📊 数据面板</a><a href="/monitor">🔴 动态监视</a><a href="/">↩ 主站</a></nav>
<h1>赛创助手 · 管理后台</h1>
<div class="sub">一眼掌握整体运行情况，详细数据进「数据面板」或「动态监视」</div>
<div class="hero">
<div class="h"><div class="n">%d</div><div class="l">总生成次数</div></div>
<div class="h"><div class="n">%d</div><div class="l">今日生成</div></div>
<div class="h"><div class="n %s">%s</div><div class="l">满意度平均分（%d 人打分）</div></div>
<div class="h"><div class="n %s">%s%%</div><div class="l">生成成功率</div></div>
<div class="h"><div class="n %s">%d</div><div class="l">待处理工单</div></div>
<div class="h"><div class="n">%d</div><div class="l">反馈总数</div></div>
</div>
<div class="cols">
<div class="box"><h2>最近反馈</h2><ul>%s</ul></div>
<div class="box"><h2>最近失败</h2><ul>%s</ul></div>
</div>
<div class="more"><a href="/admin/panel">查看完整数据面板 →</a></div>
<div class="box" style="margin-top:14px"><h2>🧠 写作范式蒸馏</h2>
<p style="font-size:13px;color:#64748b;margin:0 0 10px">从当前范文库重新提炼「获奖写法共性规律」，注入生成 prompt（约耗 1 次 LLM 调用）。</p>
<button id="distillBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer">重新蒸馏</button>
<span id="distillMsg" style="margin-left:10px;font-size:13px;color:#059669"></span>
</div>
<div class="box" style="margin-top:14px"><h2>🎤 答辩范式蒸馏</h2>
<p style="font-size:13px;color:#64748b;margin:0 0 10px">从高频答辩题库提炼「评委必问套路 + 回答框架」，注入答辩生成。</p>
<button id="distillDefenseBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer">重新蒸馏答辩范式</button>
<span id="distillDefenseMsg" style="margin-left:10px;font-size:13px;color:#059669"></span>
</div>
<div class="box" style="margin-top:14px"><h2>⚖️ 评委评分范式蒸馏</h2>
<p style="font-size:13px;color:#64748b;margin:0 0 10px">从历史生成的多专家评审记录提炼「高频扣分点 + 三视角常挑的毛病」，注入评委打分。</p>
<button id="distillJudgeBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer">重新蒸馏评委范式</button>
<span id="distillJudgeMsg" style="margin-left:10px;font-size:13px;color:#059669"></span>
</div>
<div class="box" style="margin-top:14px"><h2>📐 分析/PPT·演讲稿/同质化范式</h2>
<button id="distillAnalysisBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer">分析范式</button>
<span id="distillAnalysisMsg" style="margin-left:8px;font-size:13px;color:#059669"></span>
<button id="distillDeckBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer;margin-left:10px">PPT/演讲稿</button>
<span id="distillDeckMsg" style="margin-left:8px;font-size:13px;color:#059669"></span>
<button id="distillSimBtn" style="background:#4f46e5;color:#fff;border:none;padding:10px 18px;border-radius:10px;font-size:14px;cursor:pointer;margin-left:10px">同质化</button>
<span id="distillSimMsg" style="margin-left:8px;font-size:13px;color:#059669"></span>
</div>
<div class="box" style="margin-top:14px"><h2>📊 数据洞察（自动扫描）</h2>
<div id="insightGaps" style="font-size:13px;color:#64748b">赛事资料缺口：加载中…</div>
<div id="insightFeedback" style="font-size:13px;color:#64748b;margin-top:6px">反馈优先级：—</div>
<div id="insightScore" style="font-size:13px;color:#64748b;margin-top:6px">评分弱项：—</div>
<div id="insightFail" style="font-size:13px;color:#64748b;margin-top:6px">失败模式：—</div>
</div>
<script>
function bindDistill(btnId,msgId,url,okText){var b=document.getElementById(btnId),m=document.getElementById(msgId);b.onclick=function(){b.disabled=true;m.textContent='蒸馏中…';m.style.color='#64748b';fetch(url,{method:'POST'}).then(function(r){return r.json()}).then(function(j){b.disabled=false;if(j.success){m.textContent=okText(j);m.style.color='#059669';}else{m.textContent='失败：'+(j.error||'未知错误');m.style.color='#e11d48';}}).catch(function(e){b.disabled=false;m.textContent='失败：'+e;m.style.color='#e11d48';});};}
bindDistill('distillBtn','distillMsg','/api/distill',function(j){return '完成：用了 '+j.samples_used+' 条范文、'+j.global_count+' 条全局规则';});
bindDistill('distillDefenseBtn','distillDefenseMsg','/api/distill/defense',function(j){return '完成：用了 '+j.questions_used+' 道题、'+j.pattern_count+' 条必问套路';});
bindDistill('distillJudgeBtn','distillJudgeMsg','/api/distill/judge',function(j){return '完成：提炼 '+j.criticism_count+' 条高频扣分点';});
bindDistill('distillAnalysisBtn','distillAnalysisMsg','/api/distill/analysis',function(j){return '完成：竞品/商业/风险/技术要点已更新';});
bindDistill('distillDeckBtn','distillDeckMsg','/api/distill/deck_speech',function(j){return '完成：PPT结构+演讲稿套路已更新';});
bindDistill('distillSimBtn','distillSimMsg','/api/distill/similarity',function(j){return '完成：提炼 '+j.angle_count+' 个撞车角度';});
function loadInsights(){fetch('/api/competition/gaps').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightGaps');if(j.success){el.textContent='赛事资料缺口：'+j.summary;if(j.total>0){el.style.color='#d97706';}}else{el.textContent='赛事资料缺口：读取失败';}});fetch('/api/feedback/priority').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightFeedback');if(j.success&&j.items&&j.items.length){el.textContent='反馈优先级：'+j.items.slice(0,3).map(function(x){return x.category+'('+x.count+'条)';}).join('、');}else{el.textContent='反馈优先级：暂无反馈';}});fetch('/api/score/diagnosis').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightScore');if(j.success&&j.diagnosis_text){el.textContent='评分弱项：'+j.diagnosis_text;}else{el.textContent='评分弱项：暂无足够评分数据';}});fetch('/api/failure/patterns').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightFail');if(j.success&&j.patterns&&j.patterns.length){el.textContent='失败模式：'+j.patterns.slice(0,3).map(function(x){return x.code+'×'+x.count;}).join('、');}else{el.textContent='失败模式：暂无失败';}});}
loadInsights();
</script>
</div></body></html>""" % (
        total_gen, today_gen,
        "good" if avg_rating >= 4 else ("bad" if avg_rating and avg_rating < 3 else ""),
        avg_rating, rated_count,
        "good" if success_rate >= 95 else ("bad" if success_rate < 80 else ""),
        success_rate,
        "bad" if open_issue else "good", open_issue,
        feedback_total, fb_rows, fail_rows)


@app.route('/admin/panel')
def admin_dashboard():
    """极简后台页：纯展示，不做登录。总生成次数 / 满意度平均分 / 最近反馈。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    total_gen = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_gen = c.execute(
        "SELECT COUNT(*) FROM history WHERE created_time LIKE ?", (today + "%",)).fetchone()[0]
    avg_row = c.execute(
        "SELECT AVG(rating), COUNT(*) FROM history WHERE rating > 0").fetchone()
    avg_rating = round(avg_row[0], 2) if avg_row and avg_row[0] is not None else 0
    rated_count = avg_row[1] if avg_row else 0
    feedback_total = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    feedbacks = c.execute(
        "SELECT content, created_time FROM feedback ORDER BY id DESC LIMIT 10").fetchall()
    # 满意度分布（1-5 星）
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r, n in c.execute(
            "SELECT rating, COUNT(*) FROM history WHERE rating > 0 GROUP BY rating").fetchall():
        rating_dist[int(r)] = n
    # 生成趋势（最近 14 天）
    trend = c.execute(
        "SELECT substr(created_time,1,10) d, COUNT(*) n FROM history "
        "GROUP BY d ORDER BY d DESC LIMIT 7").fetchall()
    # 赛事分布（Top 8）
    comp_dist = c.execute(
        "SELECT competition_name, COUNT(*) n FROM history "
        "GROUP BY competition_name ORDER BY n DESC, competition_name LIMIT 8").fetchall()
    # 反馈分类聚合
    fb_cat = c.execute(
        "SELECT category, COUNT(*) n FROM feedback GROUP BY category ORDER BY n DESC").fetchall()
    # 评估指标：平均耗时 / 成功率 / AI 评委平均分
    avg_dur = c.execute("SELECT AVG(duration) FROM history WHERE duration > 0").fetchone()[0]
    avg_dur = round(avg_dur, 1) if avg_dur else 0
    succ_total = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    fail_total = c.execute("SELECT COUNT(*) FROM gen_failures").fetchone()[0]
    success_rate = round(succ_total * 100.0 / (succ_total + fail_total), 1) if (succ_total + fail_total) else 100.0
    judge_avg = c.execute(
        "SELECT AVG(CAST(json_extract(result_data,'$.score') AS REAL)) FROM history "
        "WHERE json_extract(result_data,'$.score') IS NOT NULL").fetchone()[0]
    judge_avg = round(judge_avg, 1) if judge_avg else 0
    open_issues = c.execute(
        "SELECT id, kind, source, content, created_time FROM issues "
        "WHERE status='open' ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()

    # 今日大模型调用额度
    quota_calls = 0
    try:
        with open(os.path.join(os.path.dirname(__file__), "quota.json"),
                  encoding="utf-8") as _f:
            _q = json.load(_f)
        if _q.get("date") == today:
            quota_calls = int(_q.get("calls", 0) or 0)
    except Exception:
        pass
    quota_limit = 500
    quota_remaining = max(0, quota_limit - quota_calls)

    fb_items = []
    for r in feedbacks:
        fb_items.append('<li><div class="t">%s</div><div>%s</div></li>'
                        % (r["created_time"] or "", _html_escape(r["content"] or "")))
    fb_html = "".join(fb_items) or '<li class="empty">暂无反馈</li>'

    # 满意度分布条
    max_r = max(rating_dist.values()) or 1
    rating_bars = []
    for star in range(5, 0, -1):
        n = rating_dist.get(star, 0)
        pct = int(n * 100 / max_r) if n else 0
        rating_bars.append(
            '<div class="barrow"><span class="bl">%d 星</span>'
            '<span class="btrack"><span class="bfill" style="width:%d%%"></span></span>'
            '<span class="bn">%d</span></div>' % (star, pct, n))
    rating_bars_html = "".join(rating_bars)

    # 生成趋势（最近 14 天，正序显示）
    trend = list(reversed(trend))
    max_t = max([n for _, n in trend]) if trend else 0
    trend_bars = []
    for d, n in trend:
        h = int(n * 100 / max_t) if max_t else 0
        label = d[5:] if len(d) >= 10 else d
        trend_bars.append(
            '<div class="tcol"><div class="tv">%d</div>'
            '<div class="tbar"><div class="tfill" style="height:%d%%"></div></div>'
            '<div class="td">%s</div></div>' % (n, h, label))
    trend_html = "".join(trend_bars) or '<div class="empty">暂无数据</div>'

    # 赛事分布（Top 8）
    max_c = max([n for _, n in comp_dist]) if comp_dist else 0
    comp_bars = []
    for name, n in comp_dist:
        pct = int(n * 100 / max_c) if max_c else 0
        comp_bars.append(
            '<div class="barrow"><span class="bl">%s</span>'
            '<span class="btrack"><span class="bfill" style="width:%d%%"></span></span>'
            '<span class="bn">%d</span></div>' % (_html_escape(name), pct, n))
    comp_html = "".join(comp_bars) or '<div class="empty">暂无数据</div>'

    # 反馈分类
    cat_total = sum(n for _, n in fb_cat) or 0
    cat_chips = []
    for cat, n in fb_cat:
        cat_chips.append('<span class="chip">%s · %d</span>' % (_html_escape(cat), n))
    cat_html = "".join(cat_chips) or '<div class="empty">暂无反馈</div>'

    # 待处理问题工单
    issue_items = []
    for it in open_issues:
        kind_label = "前端" if it["kind"] == "frontend" else "后端"
        kind_color = "#d97706" if it["kind"] == "frontend" else "#2563eb"
        issue_items.append(
            '<li><div class="t">#%d · <span style="color:%s">%s</span> · %s</div>'
            '<div>%s</div></li>'
            % (it["id"], kind_color, kind_label, it["created_time"] or "",
               _html_escape(it["content"] or "")))
    issues_html = "".join(issue_items) or '<li class="empty">暂无待处理问题</li>'

    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>赛创助手 · 后台数据</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1a1a2e;margin:0;padding:30px 18px;line-height:1.6}
.wrap{max-width:760px;margin:0 auto}
h1{font-size:22px;margin:0 0 18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:22px}
.card{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.num{font-size:26px;font-weight:700;color:#2563eb}
.label{font-size:12px;color:#6b7280;margin-top:4px}
.banner{background:#ecfdf5;border:1px solid #a7f3d0;color:#047857;border-radius:10px;padding:12px 14px;font-size:15px;font-weight:600;margin-bottom:16px}
h2{font-size:16px;margin:18px 0 10px}
ul{list-style:none;padding:0;margin:0}
li{background:#fff;border-radius:10px;padding:11px 13px;margin-bottom:8px;font-size:14px}
li .t{font-size:12px;color:#9ca3af;margin-bottom:4px}
li.empty{color:#9ca3af;text-align:center;padding:22px}
.box{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px}
.barrow{display:flex;align-items:center;gap:10px;margin:7px 0}
.barrow .bl{width:110px;font-size:13px;color:#374151;text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.barrow .btrack{flex:1;background:#eef0f4;border-radius:6px;height:14px;overflow:hidden}
.barrow .bfill{display:block;height:100%%;background:linear-gradient(90deg,#2563eb,#60a5fa);border-radius:6px}
.barrow .bn{width:34px;font-size:13px;color:#6b7280;flex-shrink:0}
.trend{display:flex;align-items:flex-end;gap:12px;height:130px;padding-top:6px}
.tcol{flex:1;display:flex;flex-direction:column;align-items:center}
.tcol .tv{font-size:11px;color:#6b7280}
.tcol .tbar{width:100%%;height:80px;display:flex;align-items:flex-end}
.tcol .tfill{width:100%%;background:#2563eb;border-radius:4px 4px 0 0;min-height:2px}
.tcol .td{font-size:10px;color:#9ca3af;margin-top:4px}
.chip{display:inline-block;background:#eef2ff;color:#2563eb;border-radius:999px;padding:4px 12px;font-size:13px;margin:3px 6px 3px 0}
.empty{color:#9ca3af;text-align:center;padding:16px}
.nav{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.nav a{background:#fff;color:#374151;text-decoration:none;padding:8px 14px;border-radius:8px;font-size:14px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.nav a.active{background:#2563eb;color:#fff}
</style></head><body><div class="wrap">
<nav class="nav"><a href="/admin">🏠 总览</a><a href="/admin/panel" class="active">📊 数据面板</a><a href="/monitor">🔴 动态监视</a><a href="/">↩ 主站</a></nav>
<h1>赛创助手 · 后台数据</h1>
<div class="banner">🟢 服务运行正常</div>
<div class="cards">
<div class="card"><div class="num">%d</div><div class="label">总生成次数</div></div>
<div class="card"><div class="num">%d</div><div class="label">今日生成</div></div>
<div class="card"><div class="num">%d</div><div class="label">今日剩余额度</div></div>
<div class="card"><div class="num">%s</div><div class="label">满意度平均分（%d 人打分）</div></div>
<div class="card"><div class="num">%d</div><div class="label">反馈总数</div></div>
<div class="card"><div class="num">%ss</div><div class="label">平均生成耗时</div></div>
<div class="card"><div class="num">%s%%</div><div class="label">生成成功率</div></div>
<div class="card"><div class="num">%s</div><div class="label">AI 评委平均分</div></div>
</div>
<div class="box">
<h2 style="margin-top:0">满意度分布</h2>
%s
</div>
<div class="box">
<h2 style="margin-top:0">生成趋势（最近 7 天）</h2>
<div class="trend">%s</div>
</div>
<div class="box">
<h2 style="margin-top:0">赛事分布（Top 8）</h2>
%s
</div>
<div class="box">
<h2 style="margin-top:0">反馈分类</h2>
%s
</div>
<div class="box">
<h2 style="margin-top:0">待处理问题工单（自动路由给前端 / 后端）</h2>
<ul>%s</ul>
</div>
<h2>最近 10 条反馈</h2>
<ul>%s</ul>
<div style="margin-top:14px"><a href="/api/feedback/export" style="color:#2563eb">⬇ 下载全部反馈 Excel</a></div>
</div></body></html>""" % (total_gen, today_gen, quota_remaining, avg_rating,
                              rated_count, feedback_total, avg_dur, success_rate,
                              judge_avg, rating_bars_html, trend_html, comp_html,
                              cat_html, issues_html, fb_html)
    return html


def _html_escape(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


@app.route('/monitor')
def monitor():
    """动态监视页：自动刷新，实时看服务状态 / 最近生成 / 失败 / 额度。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    recent_gen = c.execute(
        "SELECT competition_name, mode, duration, status, created_time FROM history "
        "ORDER BY id DESC LIMIT 12").fetchall()
    recent_fail = c.execute(
        "SELECT error, created_time FROM gen_failures ORDER BY id DESC LIMIT 12").fetchall()
    total_gen = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    fail_total = c.execute("SELECT COUNT(*) FROM gen_failures").fetchone()[0]
    conn.close()

    uptime = int(time.time() - START_TIME)
    up_h, up_m = divmod(uptime // 60, 60)
    quota = {"remaining": 0, "limit": 500}
    try:
        from competition_agents import get_quota_status
        quota = get_quota_status()
    except Exception:
        pass

    gen_rows = "".join(
        '<tr><td>%s</td><td>%s</td><td>%s</td><td>%ss</td></tr>'
        % (_html_escape(r["competition_name"] or "—"), r["mode"] or "—",
           r["status"] or "success", r["duration"] if r["duration"] else 0)
        for r in recent_gen) or '<tr><td colspan="4" class="e">暂无生成记录</td></tr>'
    fail_rows = "".join(
        '<tr><td>%s</td><td>%s</td></tr>'
        % (r["created_time"] or "", _html_escape(r["error"] or ""))
        for r in recent_fail) or '<tr><td colspan="2" class="e">暂无失败记录</td></tr>'

    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>赛创助手 · 动态监视</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#0f1535;color:#e9eefc;margin:0;padding:26px 18px;line-height:1.6}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:20px;margin:0 0 6px}
.sub{font-size:12px;color:#93a0c4;margin-bottom:18px}
.stat{display:inline-block;background:#18224a;border-radius:10px;padding:12px 18px;margin:0 8px 8px 0}
.stat b{font-size:22px;color:#22d3ee}
.stat span{font-size:12px;color:#93a0c4;margin-left:6px}
h2{font-size:15px;margin:22px 0 8px;color:#22d3ee}
table{width:100%%;border-collapse:collapse;background:#141d42;border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;font-size:13px;text-align:left;border-bottom:1px solid #233059}
th{background:#1b2650;color:#93a0c4;font-weight:600}
.e{color:#6b7899;text-align:center;padding:18px}
.green{color:#34d399}.red{color:#fb7185}
.nav{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.nav a{background:#18224a;color:#93a0c4;text-decoration:none;padding:8px 14px;border-radius:8px;font-size:14px}
.nav a.active{background:#22d3ee;color:#0b1026}
</style></head><body><div class="wrap">
<nav class="nav"><a href="/admin">🏠 总览</a><a href="/admin/panel">📊 数据面板</a><a href="/monitor" class="active">🔴 动态监视</a><a href="/">↩ 主站</a></nav>
<h1>🔴 赛创助手 · 动态监视</h1>
<div class="sub">每 15 秒自动刷新 · 运行时长 %d 小时 %d 分 · 本页由后端实时读库</div>
<div>
<div class="stat"><b>%d</b><span>总生成</span></div>
<div class="stat"><b class="%s">%d</b><span>失败</span></div>
<div class="stat"><b>%d / %d</b><span>今日额度</span></div>
</div>
<h2>最近生成</h2>
<table><tr><th>赛事</th><th>档位</th><th>状态</th><th>耗时</th></tr>%s</table>
<h2>最近失败</h2>
<table><tr><th>时间</th><th>错误</th></tr>%s</table>
</div></body></html>""" % (up_h, up_m, total_gen,
                              "red" if fail_total else "green", fail_total,
                              quota.get("remaining", 0), quota.get("limit", 500),
                              gen_rows, fail_rows)


def _categorize_feedback(content):
    """按关键词给反馈打标签（免费、即时，不用调 LLM）。"""
    t = content or ""
    neg = ["难用", "垃圾", "无语", "失望", "烦死", "太差"]
    bug = ["报错", "错误", "打不开", "失败", "卡", "慢", "崩", "404", "500", "闪退",
           "乱码", "不能用", "不行", "无响应", "空白"]
    sugg = ["建议", "希望", "能不能", "加", "优化", "最好", "要是", "期待", "想要", "改进"]
    praise = ["好", "不错", "满意", "赞", "棒", "厉害", "好用", "喜欢", "方便", "感谢"]
    if any(k in t for k in neg):
        return "吐槽"
    if any(k in t for k in bug):
        return "问题反馈"
    if any(k in t for k in sugg):
        return "功能建议"
    if any(k in t for k in praise):
        return "好评"
    return "其他"


def _classify_issue(content):
    """把问题路由到前端还是后端。"""
    t = content or ""
    fe = ["页面", "按钮", "显示", "界面", "前端", "手机", "浏览器", "布局", "样式",
          "点不动", "看不到", "空白", "弹窗", "导航", "引导", "排版"]
    be = ["生成", "报错", "接口", "数据库", "速度", "慢", "404", "500", "崩溃", "超时",
          "输出", "内容", "图表", "导出", "PPT", "答辩", "评委", "api"]
    f = sum(1 for k in fe if k in t)
    b = sum(1 for k in be if k in t)
    if f > b:
        return "frontend"
    if b > f:
        return "backend"
    return "backend"


def create_issue(kind, source, content):
    """自动建一条问题工单（路由给前端/后端），幂等去重（内容 hash 相同不重复）。"""
    try:
        import hashlib
        h = hashlib.md5((content or "").strip().encode("utf-8")).hexdigest()[:16]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        row = c.execute("SELECT id FROM issues WHERE content=?", (content,)).fetchone()
        if row:
            conn.close()
            return None
        c.execute("INSERT INTO issues (kind, source, content, created_time, status) VALUES (?, ?, ?, ?, 'open')",
                  (kind, source, content, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except Exception:
        return None


@app.route('/api/history/<int:history_id>', methods=['DELETE'])
def delete_history(history_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (history_id, _current_uid()))
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
    """脱敏兜底：剔除院校、指导教师/负责人姓名、手机号、邮箱、身份证等身份信息。"""
    import re
    if not t:
        return t
    # 手机号 / 座机
    t = re.sub(r'1[3-9]\d{9}', '（手机号隐去）', t)
    t = re.sub(r'0\d{2,3}[- ]?\d{7,8}', '（电话隐去）', t)
    # 邮箱
    t = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '（邮箱隐去）', t)
    # 身份证号（18 位）
    t = re.sub(r'\b\d{17}[\dXx]\b', '（身份证号隐去）', t)
    # 指导教师 / 负责人 + 姓名（含职称）
    t = re.sub(
        r'(指导老师|指导教师|负责人|队长|联系人)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}(?:教授|副教授|讲师|博士|主任|老师)?',
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


def _run_generation(data):
    """执行生成流水线（加锁、存历史），返回结果 data dict；出错抛异常"""
    with lock:
        t0 = time.time()
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
                try:
                    from chart_renderer_pro import render_charts
                except Exception:
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
            "duration": round(time.time() - t0, 1),
            "status": "success",
            "user_id": data.get("_user_id", ""),
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
    # 正文字数（去掉 Markdown 标记的有效字数，用户一眼看到写了多少字）
    try:
        from competition_agents import _cjk_len
        proposal_chars = _cjk_len(result.get("proposal", ""))
    except Exception:
        proposal_chars = len(re.sub(r'\s', '', result.get("proposal", "") or ""))
    similarity = _similarity_check(result.get("proposal", ""))
    # 从创意提取关键词，自动填申报书关键词栏
    keywords = _extract_keywords_llm(result.get("idea") or data.get("idea") or "")

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
        "proposal_chars": proposal_chars,
        "similarity": similarity,
        "keywords": keywords,
        "completeness": completeness
    }

    payload = _strip_identifying_info(payload)
    return payload


def _similarity_check(text):
    """简单重复率初检：与本地范文库做字符 5-gram 重叠率，返回百分比。

    这是「本地初检」，只和知识库里收录的范文对比，不等同于知网/全网正式查重。
    """
    try:
        from kb_samples import list_samples
        samples = list_samples(limit=500)
        refs = [s.get('content', '') for s in samples if s.get('content')]
        if not refs or not (text or '').strip():
            return {"percent": 0.0, "checked": len(refs), "note": "本地初检，非正式查重"}
        n = 5

        def _ngrams(s):
            s = re.sub(r'\s+', '', s)
            return set(s[i:i + n] for i in range(len(s) - n + 1))

        tg = _ngrams(text)
        if not tg:
            return {"percent": 0.0, "checked": len(refs), "note": "本地初检，非正式查重"}
        rg = set()
        for r in refs:
            rg |= _ngrams(r)
        overlap = len(tg & rg)
        percent = round(overlap / len(tg) * 100, 1)
        return {"percent": percent, "checked": len(refs), "note": "本地初检，非正式查重"}
    except Exception as e:
        print(f"[similarity] 检测失败：{e}")
        return {"percent": None, "checked": 0, "note": "检测失败"}


def _extract_keywords_llm(idea):
    """从创意描述里提取 3-5 个关键词（技术领域/应用场景/核心功能），用于申报书关键词栏。"""
    if not idea or not idea.strip():
        return []
    try:
        from competition_agents import llm
        from langchain_core.messages import HumanMessage
        prompt = ("从下面这段创意描述里提取 3-5 个最能代表项目的关键词"
                  "（技术领域、应用场景、核心功能、服务对象等）。\n"
                  "只输出关键词本身，用中文顿号「、」分隔，不要编号、不要任何解释。\n\n"
                  f"创意：{idea[:1200]}")
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = (resp.content or '').strip()
        kws = [k.strip() for k in re.split(r'[、,，;；\n]+', raw) if k.strip()]
        return kws[:5]
    except Exception as e:
        print(f"[keywords] 提取失败：{e}")
        return []


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


def _error_code(e):
    """根据异常返回稳定的错误码，前端据此分支处理，不再靠匹配文字。"""
    err = str(e).lower()
    if "timeout" in err or "timed out" in err:
        return "timeout"
    if "429" in err or "rate" in err or "too many" in err:
        return "rate_limit"
    if "401" in err or "auth" in err or "api key" in err:
        return "auth_error"
    if "402" in err or "insufficient balance" in err or "payment required" in err or "余额不足" in err:
        return "insufficient_balance"
    if "上限" in err or "配额" in err or "quota" in err:
        return "quota_exceeded"
    return "internal_error"


def _safe_filename_part(s):
    """清洗文件名片段：去非法字符、压缩空白、去首尾分隔符。"""
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', str(s or ''))
    s = re.sub(r'\s+', ' ', s).strip(' _-')
    return s


def _export_filename(project, competition, doc_name, ext):
    """拼「项目名_比赛名_文档类型.ext」的下载文件名。"""
    project = _safe_filename_part((project or '')[:30])
    competition = _safe_filename_part((competition or '')[:30])
    doc_name = _safe_filename_part(doc_name)
    parts = [p for p in (project, competition, doc_name) if p]
    return ('_'.join(parts) or '导出文件') + ext


def _project_name_hint(data):
    """从请求里尽力取「项目名/创意」，导出文件命名用；取不到再从历史兜底。"""
    for k in ('project_name', 'project', 'idea'):
        v = (data or {}).get(k)
        if v and str(v).strip():
            return str(v).strip()
    try:
        h = load_history(limit=1, uid=_current_uid())
        if h and h[0].get('idea'):
            return str(h[0]['idea']).strip()
    except Exception:
        pass
    return ''


@app.route('/api/generate', methods=['POST'])
def generate():
    """⚠️ 已废弃：请改用 /api/generate_async + /api/status 轮询。保留仅为兼容旧前端。"""
    if _rate_limited():
        return jsonify({"success": False,
                        "error": "生成太频繁，请 1 分钟后再试（同一网络每分钟最多生成 5 次）"}), 429
    data = request.json or {}
    data["_user_id"] = _current_uid()
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


def _start_generation(data):
    """启动一个异步生成任务。返回 (task_id, None) 或 (None, error_json)。"""
    global _active_gen_count
    # 在请求上下文里把匿名用户 id 固化进任务参数，供后台线程写历史记录时使用
    data["_user_id"] = _current_uid()
    if _rate_limited():
        return None, jsonify({"success": False,
                              "error": "生成太频繁，请 1 分钟后再试（同一网络每分钟最多生成 5 次）"})
    # 稳定器：并发生成任务达到上限就拒绝，避免瞬时洪峰把服务压垮
    with _active_gen_lock:
        if _active_gen_count >= MAX_CONCURRENT_GEN:
            return None, jsonify({"success": False,
                                  "error": "当前生成人数较多，请稍后 1 分钟再试"})
        _active_gen_count += 1
    task_id = uuid.uuid4().hex
    tasks[task_id] = {"status": "running", "stage": "start", "updated_at": time.time(), "start_time": time.time(),
                      "mode": data.get("mode", "fast"), "data": data}

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
            code = _error_code(e)
            msg = _friendly_error(e)
            app_log.error("generate", f"task={task_id[:8]} {msg} | {traceback.format_exc(limit=2)}")
            record_gen_failure(task_id, msg, str(e))
            progress.mark_error(task_id, error=msg, detail=str(e))
            tasks[task_id]["error_code"] = code
        finally:
            clear_speech_stream(task_id)
            clear_current_task()
            with _active_gen_lock:
                _active_gen_count = max(0, _active_gen_count - 1)

    threading.Thread(target=worker, daemon=True).start()
    return task_id, None


@app.route('/api/generate_async', methods=['POST'])
def generate_async():
    data = request.json or {}
    task_id, err = _start_generation(data)
    if err is not None:
        return err, 429
    return jsonify({"success": True, "task_id": task_id})


@app.route('/api/retry/<task_id>', methods=['POST'])
def retry_generation(task_id):
    """用上次的参数直接重跑一遍，用户不用重新输入创意。"""
    t = tasks.get(task_id)
    if not t or not t.get("data"):
        # 任务字典里没有参数（可能服务重启或任务被清理），退回历史记录兜底
        return jsonify({"success": False, "error": "任务参数已丢失，请重新提交创意"}), 404
    # 允许对失败/超时/已完成的任务都重跑；数据里带一个来源标记便于日志排查
    data = dict(t["data"])
    data.setdefault("_retry_from", task_id)
    task_id2, err = _start_generation(data)
    if err is not None:
        return err, 429
    return jsonify({"success": True, "task_id": task_id2})


_RESTYLE_STYLES = {
    "formal": "正式公文风（庄重规范、多用书面语、结构清晰、避免口语与夸张表述）",
    "academic": "学术严谨风（逻辑严密、用词精准、客观严谨、强调研究方法与数据支撑）",
    "startup": "创业融资风（突出商业价值、市场机会、增长潜力与团队执行力，面向投资人）",
}


@app.route('/api/restyle', methods=['POST'])
def restyle():
    """多风格一键切换：把整份申报书改写成目标语言风格，不动章节结构与数据。"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    style = data.get('style', 'formal')
    if not text or not text.strip():
        return jsonify({"success": False, "error": "内容为空"}), 400
    if style not in _RESTYLE_STYLES:
        return jsonify({"success": False, "error": "未知风格"}), 400
    try:
        from competition_agents import llm
        from langchain_core.messages import HumanMessage
        desc = _RESTYLE_STYLES[style]
        prompt = f"""请把下面这份申报书整体改写成【{desc}】的风格。

硬性要求：
1. 保留所有章节标题、层级结构、数字、数据、占位符【待你填写：xxx】原样不变；
2. 只改语言风格与表述方式，不改内容事实、不改章节顺序、不增删任何要点；
3. 篇幅与原文相当，不要扩写或缩水；
4. 直接输出改写后的完整正文，不要任何解释说明。

原文：
{text[:14000]}
"""
        resp = llm.invoke([HumanMessage(content=prompt)])
        return jsonify({"success": True, "text": resp.content, "style": style})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e), "error_code": _error_code(e)}), 500


@app.route('/api/proofread', methods=['POST'])
def proofread():
    """错别字/语法检测：返回标错位置和修正建议（LLM 校对）。"""
    data = request.get_json(force=True, silent=True) or {}
    text = data.get('text', '')
    if not text or not text.strip():
        return jsonify({"success": False, "error": "内容为空"}), 400
    try:
        from competition_agents import llm
        from langchain_core.messages import HumanMessage
        import json as _json
        prompt = ("你是中文文本校对专家。请找出下面文本里的错别字、语法错误、标点误用、语句不通顺等问题。\n"
                  "对每个问题输出：原文片段、问题类型、修正建议。\n\n"
                  "只输出 JSON 数组，格式：\n"
                  '[{"original":"错误原文","type":"错别字/语法/标点/语句不通","suggestion":"修正建议"}]\n'
                  "没有发现问题就输出 []。不要输出 JSON 以外的任何文字。\n\n"
                  f"文本：\n{text[:8000]}")
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = (resp.content or '').strip()
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        issues = []
        if m:
            try:
                issues = _json.loads(m.group(0))
                if not isinstance(issues, list):
                    issues = []
            except Exception:
                issues = []
        return jsonify({"success": True, "issues": issues, "count": len(issues)})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e), "error_code": _error_code(e)}), 500


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
        t["error_code"] = "timeout"
        t["stage"] = "error"
        t["updated_at"] = time.time()
    _stage = t.get("stage", "start")
    _label, _pct = stage_meta(_stage)
    # 流式增量：前端传 cursor={字段:已见长度}，这里只回「新增后缀」，避免每次轮询都拉全量正文。
    # 不传 cursor 时退回全量 partial，兼容旧前端。
    _cursor = {}
    _cursor_raw = request.args.get("cursor", "").strip()
    if _cursor_raw:
        try:
            import json as _json_cursor
            _c = _json_cursor.loads(_cursor_raw)
            if isinstance(_c, dict):
                _cursor = {str(k): int(v or 0) for k, v in _c.items()}
        except Exception:
            _cursor = {}
    _partial = t.get("partial") or {}
    if _cursor:
        _delta = {}
        for _f, _txt in _partial.items():
            _txt = _txt or ""
            _prev = _cursor.get(_f, 0)
            if len(_txt) > _prev:
                _delta[_f] = _txt[_prev:]
        _partial = _delta
    # 预计剩余时间：按阶段进度百分比外推（已完成比例 -> 剩余比例）
    _eta = 0
    if t.get("status") == "running" and _pct and _pct > 0:
        _start = t.get("start_time") or t.get("updated_at") or time.time()
        _elapsed = max(0.0, time.time() - _start)
        _eta = int(_elapsed * (100 - _pct) / _pct)
    resp = {
        "success": True,
        "status": t["status"],
        "stage": _stage,
        "stage_label": _label,
        "pct": _pct,
        "eta_seconds": _eta,
        "partial": _partial,
        "updated_at": t["updated_at"]
    }
    if t["status"] == "done":
        resp["data"] = t["data"]
    elif t["status"] == "error":
        resp["error"] = t["error"]
        resp["detail"] = t.get("detail")
        resp["error_code"] = t.get("error_code", "internal_error")
    return jsonify(resp)


@app.route('/api/stream/<task_id>')
def stream_generation(task_id):
    """SSE 流式输出：生成过程边生成边推送，前端 EventSource 接打字机效果。

    事件约定：
      event: stage    data: {"stage": <阶段代号>, "status": <状态>}
      event: partial  data: {"field": <字段名>, "delta": <本段新增文本>}
      event: done     data: {"status": "done|error|cancelled", ...}
    轮询 /api/status 仍保留，作为 SSE 断开时的兜底。
    """
    from flask import Response, stream_with_context
    import json as _json

    def gen():
        t = tasks.get(task_id)
        if not t:
            yield 'event: error\ndata: {"error":"任务不存在或已过期"}\n\n'
            return
        sent = {}          # field -> 上次已推送的完整内容
        last_stage = None
        while True:
            t = tasks.get(task_id)
            if not t:
                break
            stage = t.get('stage', 'start')
            if stage != last_stage:
                last_stage = stage
                yield 'event: stage\ndata: %s\n\n' % _json.dumps(
                    {"stage": stage, "status": t.get("status")}, ensure_ascii=False)
            partial = t.get('partial') or {}
            for field, text in partial.items():
                text = text or ''
                prev = sent.get(field, '')
                if text == prev:
                    continue
                # 逐段增量推送（打字机），字段被整体重写时才退化为全量
                delta = text[len(prev):] if text.startswith(prev) else text
                sent[field] = text
                yield 'event: partial\ndata: %s\n\n' % _json.dumps(
                    {"field": field, "delta": delta}, ensure_ascii=False)
            status = t.get('status')
            if status in ('done', 'error', 'cancelled'):
                payload = {"status": status}
                if status == 'done':
                    payload["data"] = t.get("data")
                else:
                    payload["error"] = t.get("error")
                    payload["error_code"] = t.get("error_code", "internal_error")
                yield 'event: done\ndata: %s\n\n' % _json.dumps(payload, ensure_ascii=False)
                break
            time.sleep(0.3)

    return Response(stream_with_context(gen()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no',
                             'Connection': 'keep-alive'})


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
    history = load_history(uid=_current_uid())
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
    project = latest.get("idea") or data.get("idea") or ''
    competition = latest.get("competition_name") or data.get("competition_name") or ''
    return send_file(buf, as_attachment=True,
                     download_name=_export_filename(project, competition, '材料包', '.zip'),
                     mimetype='application/zip')

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
    zippath = os.path.join(tmpdir, '项目材料包.zip')

    # 素材打包里的申报书也要按官方章节排序 / 走 iCAN 双盲，
    # 否则单独下载是官方顺序、打包里又是另一套顺序，用户会以为系统不稳定。
    comp = (data.get('competition_name') or '').strip()
    # 前端打包时把本轮的图表一起带过来（rich_charts），申报书正文里才插得进图
    charts_in = data.get('rich_charts') or []

    def build_doc(title, text):
        dt = 'outline' if ('大纲' in title or 'PPT' in title) else ('default' if '申报书' in title else 'analysis')
        tt = text
        is_prop = ('申报书' in title)
        if comp and is_prop:
            order = _official_chapter_titles(comp)
            if order:
                tt = _reorder_markdown_by_chapters(tt, order)
        d = _build_docx(title, tt, doc_type=dt,
                        subtitle=comp if is_prop else None,
                        school=data.get('school'),
                        team=data.get('team'),
                        advisor=data.get('advisor'),
                        competition_name=comp if is_prop else None)
        # 打包里的申报书同样要插图：不然单独下载有图、打包里没图，用户会以为系统不稳。
        # 图表文件是本轮生成时落在 generated/ 下的，前端通过 rich_charts 传回来。
        if is_prop and charts_in:
            try:
                from docx_charts import inject_charts
                inject_charts(d, charts_in)
            except Exception as e:
                print(f"[export_zip] 申报书插图失败（不影响导出）：{e}")
        return d

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
    project = data.get('idea') or data.get('project_name') or ''
    competition = data.get('competition_name') or ''
    return send_file(zippath, as_attachment=True,
                     download_name=_export_filename(project, competition, '材料包', '.zip'),
                     mimetype='application/zip')


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
        project = deck.get('project') or data.get('idea') or _project_name_hint(data) or '路演PPT'
        competition = deck.get('competition') or data.get('competition_name') or ''
        return send_file(out, as_attachment=True,
                         download_name=_export_filename(project, competition, '路演PPT', '.pptx'),
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

    # 版权整改：不再自动把上传内容归为「范文」，只允许「材料/模板」
    score = data.get('score')
    stype = data.get('type')
    auto_scored = score is None
    if auto_scored:
        score = _auto_score(content)
    if not stype or stype == '范文':
        stype = '材料'
    elif stype not in ('材料', '模板'):
        stype = '材料'
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


@app.route('/api/distill', methods=['POST'])
def distill_paradigm():
    """后台一键重新蒸馏写作范式：读当前范文库，用 LLM 提炼共性规律写回 writing_paradigm.json。

    成功后注入生成 prompt 的写作范式立即更新；失败返回错误且不覆盖旧范式。
    """
    try:
        from kb_distill import distill_from_samples
        result = distill_from_samples()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/distill/defense', methods=['POST'])
def distill_defense_paradigm():
    """从答辩题库蒸馏「答辩范式」写回 defense_paradigm.json。"""
    try:
        from kb_distill import distill_defense
        result = distill_defense()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/distill/judge', methods=['POST'])
def distill_judge_paradigm():
    """从历史评审记录蒸馏「评委评分范式」写回 judge_paradigm.json。"""
    try:
        from kb_distill import distill_judge
        result = distill_judge()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/distill/analysis', methods=['POST'])
def distill_analysis_paradigm():
    try:
        from kb_distill import distill_analysis
        result = distill_analysis()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/distill/deck_speech', methods=['POST'])
def distill_deck_speech_paradigm():
    try:
        from kb_distill import distill_deck_speech
        result = distill_deck_speech()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/distill/similarity', methods=['POST'])
def distill_similarity_paradigm():
    try:
        from kb_distill import distill_similarity
        result = distill_similarity()
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": _friendly_error(e)}), 500


@app.route('/api/failure/patterns')
def failure_patterns():
    try:
        from failure_patterns import get_failure_patterns
        return jsonify({"success": True, "patterns": get_failure_patterns()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback/priority')
def feedback_priority_api():
    try:
        from insights import feedback_priority
        return jsonify({"success": True, "items": feedback_priority()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/score/diagnosis')
def score_diagnosis_api():
    try:
        from insights import score_diagnosis
        return jsonify({"success": True, **score_diagnosis()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/competition/gaps')
def competition_gaps_api():
    try:
        from competition_rules import competition_gap_report
        return jsonify({"success": True, **competition_gap_report()})
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
