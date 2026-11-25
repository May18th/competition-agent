# -*- coding: utf-8 -*-
"""后台管理域：/admin 页面、/api/admin/* 接口。

从 app.py 抽出（第 2 阶段重构）。全部路由都挂在 /admin 或 /api/admin 下，
用 blueprint 的 url_prefix 承接，URL 与拆分前逐字一致。

与 app.py 的关系
----------------
少数只被 admin 使用的辅助函数随本文件搬迁；其余共用符号（_NOTICE_FILE /
_VULNS_PAGE_HTML / _friendly_fail_text 等）由 `_from_app()` 在调用时反向取用，
不复制一份——复制会让两处状态各走各的（例如公告文件被改成新路径后一边读到旧值）。

register() 由 app.py 在**所有 before_request 注册之后**调用，否则 /admin 的
鉴权钩子在路由匹配前不会执行。
"""
import csv
import io
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, redirect, make_response, current_app

bp = Blueprint('admin', __name__)


def _from_app(name):
    """取 app.py 里的共用符号（配置文件路径、HTML 片段、鉴权函数等）。

    必须**运行时**取，不能在 import 时 `from backend.app import ...` 拿一份副本：
    副本会把 app.py 后续对全局量的修改（测试里 `app.DB_PATH = 临时库`、
    `patch.object(app, '_require_admin')`）挡在外面，表现为测试改了半天没生效、
    或者鉴权被 patch 掉了接口照旧 401。
    """
    import sys
    for mod_name in ('backend.app', 'app'):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError('app.py 里找不到 %s' % name)


class _Lazy(object):
    """模块级惰性代理：把对 app.py 共用符号的读取推迟到真正使用时。

    直接写 `_require_admin()` 会 NameError（本模块没定义它）；
    在 import 时取副本又会冻结取值。用同名模块级变量指向代理是最小改动方案：
    调用 `_require_admin()` / 读取 `_NOTICE_FILE` 都照原样写，实际每次去 app 取。
    """
    __slots__ = ('_name',)

    def __init__(self, name):
        self._name = name

    def __call__(self, *a, **kw):
        return _from_app(self._name)(*a, **kw)

    def __getattr__(self, item):
        return getattr(_from_app(self._name), item)

    def __iter__(self):
        return iter(_from_app(self._name))

    def __len__(self):
        return len(_from_app(self._name))

    def __contains__(self, item):
        return item in _from_app(self._name)

    def __getitem__(self, k):
        return _from_app(self._name)[k]

    def __str__(self):
        return str(_from_app(self._name))

    def __repr__(self):
        return repr(_from_app(self._name))

    def __eq__(self, other):
        return _from_app(self._name) == other

    def __hash__(self):
        return hash(self._name)

    def __bool__(self):
        return bool(_from_app(self._name))


@bp.route('/api/admin/notice', methods=['POST'])
def admin_notice():
    """后台设置公告开关与内容。"""
    data = request.get_json(force=True, silent=True) or {}
    n = {"active": bool(data.get("active")), "content": str(data.get("content") or "")[:200]}
    try:
        with open(_NOTICE_FILE, "w", encoding="utf-8") as f:
            json.dump(n, f, ensure_ascii=False)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, **n})

def _inject_role_badge(html):
    """把角色徽章注入后台页面：有 nav 就插在 nav 末尾，无 nav（如漏洞库）插到标题后。"""
    # html 可能来自模块级惰性代理（_VULNS_PAGE_HTML / _ADMIN_LOGIN_HTML），
    # 代理对象直接返回给 Flask 会变成 500（响应体不是 str/bytes/dict）。这里落地成真字符串。
    html = str(html)
    badge = _admin_role_badge_html()
    if not badge:
        return html
    if '</nav>' in html:
        html = html.replace('</nav>', badge + '</nav>', 1)
    else:
        html = html.replace('</h1>', '</h1>' + badge, 1)
    # 256.5：演示只读会话隐藏写操作入口（蒸馏按钮所在的 .box），避免评委看到点不了的写按钮
    if _admin_session_role() == 'readonly' and '</body>' in html:
        _hide_js = ('<script>(function(){var b=document.querySelector(".rolebadge");'
                    'if(b&&b.textContent.indexOf("只读")>=0){'
                    'var xs=document.querySelectorAll(".box");'
                    'for(var i=0;i<xs.length;i++){if(xs[i].textContent.indexOf("蒸馏")>=0){xs[i].style.display="none";}}}})();</script>')
        html = html.replace('</body>', _hide_js + '</body>', 1)
    return html

@bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    """后台登录（198 轮）：用户名+密码（bcrypt）校验，成功写 HttpOnly 会话 cookie；连续失败锁定。"""
    payload = request.get_json(silent=True) or request.form or {}
    username = (payload.get('user') or payload.get('username') or '').strip()
    password = (payload.get('password') or payload.get('token') or '').strip()
    ip = _client_ip()
    role, err = _admin_login_verify(username, password, ip)
    if err is not None:
        msg, code = err
        _audit_admin_login(username, ip, False, None)
        return jsonify({"success": False, "error": msg}), code
    exp = time.time() + 8 * 3600
    resp = jsonify({"success": True, "expires_in": 8 * 3600, "role": role})
    resp.set_cookie(_ADMIN_COOKIE_NAME, _ADMIN_SESSION_SIGNER.dumps({"exp": exp, "role": role}),
                    max_age=8 * 3600, httponly=True, samesite='Strict', secure=request.is_secure)
    _audit_admin_login(username, ip, True, role)
    return resp

@bp.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    """后台退出登录：清掉 admin_session 会话 cookie（第二百六十七轮，demo 只读会话要能退出）。"""
    resp = jsonify({"success": True})
    resp.set_cookie(_ADMIN_COOKIE_NAME, '', max_age=0, httponly=True, samesite='Strict', secure=request.is_secure)
    return resp

def _admin_login_verify(username, password, ip):
    """校验账号密码（198 轮：用户名+密码 bcrypt）。
    成功返回 (role, None)，失败返回 (None, (错误信息, http状态码))。"""
    now = time.time()
    if _ADMIN_LOCK.get(ip, 0) > now:
        return None, ("尝试次数过多，请 15 分钟后再试", 429)
    users = _load_admin_users()
    if users:
        hit = next((u for u in users if u.get('user') == username), None)
        if hit:
            try:
                import bcrypt
                if bcrypt.checkpw(password.encode('utf-8'), hit['pass_hash'].encode('utf-8')):
                    _ADMIN_FAILS.pop(ip, None)
                    _role = hit.get('role') or 'admin'
                    # 313 轮：演示账号强制只读（防 .admin_users.json 配错成 admin，双保险）
                    if username in _DEMO_READONLY_USERS:
                        _role = 'readonly'
                    return _role, None
            except Exception:
                pass
        _ADMIN_FAILS[ip] = [t for t in _ADMIN_FAILS.get(ip, []) if now - t < _ADMIN_LOCK_SECONDS] + [now]
        if len(_ADMIN_FAILS[ip]) >= _ADMIN_LOCK_AFTER:
            _ADMIN_LOCK[ip] = now + _ADMIN_LOCK_SECONDS
        return None, ("用户名或密码错误", 401)
    # 回退：无账号体系时，单一口令模式（兼容旧 ADMIN_TOKEN / DEMO_TOKEN 部署）
    if ADMIN_TOKEN and password in {t.strip() for t in ADMIN_TOKEN.split(',') if t.strip()}:
        _ADMIN_FAILS.pop(ip, None)
        return "admin", None
    if DEMO_TOKEN and password in {t.strip() for t in DEMO_TOKEN.split(',') if t.strip()}:
        _ADMIN_FAILS.pop(ip, None)
        return "readonly", None
    _ADMIN_FAILS[ip] = [t for t in _ADMIN_FAILS.get(ip, []) if now - t < _ADMIN_LOCK_SECONDS] + [now]
    if len(_ADMIN_FAILS[ip]) >= _ADMIN_LOCK_AFTER:
        _ADMIN_LOCK[ip] = now + _ADMIN_LOCK_SECONDS
    return None, ("用户名或密码错误", 401)

def _audit_admin_login(username, ip, ok, role):
    """登录审计（195 层6 / 198 轮）：记录用户名+IP+成功/失败+角色。"""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs', '后台审计.md'), 'a', encoding='utf-8') as _f:
            _f.write("%s | login | user=%s | ip=%s | %s | role=%s\n" % (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username or '-', ip,
                'ok' if ok else 'fail', role or '-'))
    except Exception:
        pass

def _admin_login_error_html(errmsg, csrf):
    err = '<div class="err">%s</div>' % errmsg if errmsg else ''
    return _ADMIN_LOGIN_HTML.replace('__ERROR__', err).replace('__CSRF__', csrf)

@bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login_page():
    """管理员登录页（198 轮）：用户名+密码登录入口。"""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        csrf = (request.form.get('csrf') or '').strip()
        try:
            cv = _ADMIN_SESSION_SIGNER.loads(csrf)
            if not (isinstance(cv, dict) and float(cv.get('exp', 0)) > time.time()):
                return _admin_login_error_html('登录已过期，请刷新后重试', _new_admin_csrf()), 400
        except Exception:
            return _admin_login_error_html('登录已过期，请刷新后重试', _new_admin_csrf()), 400
        ip = _client_ip()
        role, err = _admin_login_verify(username, password, ip)
        if err is not None:
            msg, code = err
            _audit_admin_login(username, ip, False, None)
            return _admin_login_error_html(msg, _new_admin_csrf()), code
        exp = time.time() + 8 * 3600
        from flask import redirect
        resp = redirect('/admin')
        resp.set_cookie(_ADMIN_COOKIE_NAME, _ADMIN_SESSION_SIGNER.dumps({"exp": exp, "role": role}),
                        max_age=8 * 3600, httponly=True, samesite='Strict', secure=request.is_secure)
        _audit_admin_login(username, ip, True, role)
        return resp
    return _admin_login_error_html('', _new_admin_csrf())

def _new_admin_csrf():
    return _ADMIN_SESSION_SIGNER.dumps({"csrf": True, "exp": time.time() + 600})

@bp.route('/admin')
def admin_home():
    """管理后台 · 总览首页：关键数字一屏看完，再点进详细面板 / 监视。"""
    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    total_gen = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_gen = c.execute(
        "SELECT COUNT(*) FROM history WHERE created_time LIKE ?", (today + "%",)).fetchone()[0]
    avg_row = c.execute("SELECT AVG(rating), COUNT(*) FROM history WHERE rating > 0").fetchone()
    avg_rating = round(avg_row[0], 2) if avg_row and avg_row[0] is not None else 0
    rated_count = avg_row[1] if avg_row else 0
    fail_total = c.execute("SELECT COUNT(*) FROM gen_failures WHERE status='open'").fetchone()[0]
    success_rate = round(total_gen * 100.0 / (total_gen + fail_total), 1) if (total_gen + fail_total) else 100.0
    feedback_total = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    open_issue = c.execute("SELECT COUNT(*) FROM issues WHERE status='open'").fetchone()[0]
    open_issue_rows = c.execute(
        "SELECT id, kind, source, content, created_time FROM issues "
        "WHERE status='open' ORDER BY id DESC LIMIT 5").fetchall()
    recent_fb = c.execute(
        "SELECT content, created_time FROM feedback ORDER BY id DESC LIMIT 4").fetchall()
    recent_fail = c.execute(
        "SELECT error, detail, error_msg, created_time FROM gen_failures WHERE status='open' ORDER BY id DESC LIMIT 4").fetchall()
    conn.close()

    fb_rows = "".join(
        '<li><span class="t">%s</span>%s</li>'
        % (r["created_time"] or "", _html_escape(r["content"] or ""))
        for r in recent_fb) or '<li class="e">暂无反馈</li>'
    fail_rows = "".join(
        '<li><span class="t">%s</span>%s</li>'
        % (r["created_time"] or "", _html_escape(_friendly_fail_text(r)))
        for r in recent_fail) or '<li class="e">暂无失败</li>'
    issue_rows = "".join(
        '<li><span class="t">#%s · %s · %s</span>%s</li>'
        % (r["id"], _html_escape(r["kind"] or ""), r["created_time"] or "",
           _html_escape(r["content"] or ""))
        for r in open_issue_rows) or '<li class="e">暂无待处理的反馈</li>'

    return _inject_role_badge("""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>科创赛事助手 · 管理后台</title>
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
.box li .t{display:block;font-size:12px;color:#64748b;margin-bottom:2px}
.box li.e{color:#64748b;text-align:center;padding:16px}
.more{margin-top:18px;font-size:14px}
.more a{color:#4f46e5;text-decoration:none;font-weight:600}
<link rel="stylesheet" href="/static/wbbtn-admin.css?v=20260929an"></style></head><body><div class="wrap">
<nav class="nav"><img src="/static/logo.png" alt="科创赛事助手" style="height:26px;vertical-align:middle;margin-right:8px"><a href="/admin" class="active">🏠 概览</a><a href="/admin/panel">📊 明细数据</a><a href="/admin/llm-usage">💸 模型花费</a><a href="/monitor">🟢 实时状态</a><a href="/">↩ 主站</a></nav>
<h1>科创赛事助手 · 管理后台</h1>
<div class="sub">关键数字都在这一页，想看得更细进「明细数据」或「实时状态」</div>
<div class="hero">
<div class="h"><div class="n">%d</div><div class="l">累计出稿</div></div>
<div class="h"><div class="n">%d</div><div class="l">今天出稿</div></div>
<div class="h"><div class="n %s">%s/5分</div><div class="l">用户评分（%d 人评过）</div></div>
<div class="h"><div class="n %s">%s%%</div><div class="l" title="算的是「成功出稿」占「有过记录的生成」的比例">出稿成功率</div></div>
<div class="h"><div class="n %s">%d</div><div class="l">待处理反馈</div></div>
<div class="h"><div class="n">%d</div><div class="l">反馈总数</div></div>
</div>
<div class="cols">
<div class="box"><h2>最近的反馈</h2><ul>%s</ul></div>
<div class="box"><h2>最近失败（为什么没出稿）</h2><ul>%s</ul></div>
</div>
<div class="box" style="margin-top:14px"><h2>待处理的反馈（%d）</h2><ul>%s</ul></div>
<div class="more"><a href="/admin/panel">查看完整数据面板 →</a></div>
<div class="box" style="margin-top:14px"><h2>🩺 系统自动体检</h2>
<div id="insightGaps" style="font-size:13px;color:#64748b">还缺资料的赛事：加载中…</div>
<div id="insightFeedback" style="font-size:13px;color:#64748b;margin-top:6px">反馈最多的类型：—</div>
<div id="insightScore" style="font-size:13px;color:#64748b;margin-top:6px">最常丢分的地方：—</div>
<div id="insightFail" style="font-size:13px;color:#64748b;margin-top:6px">最常见的失败原因：—</div>
</div>
<div class="box" style="margin-top:14px"><h2>📈 图表</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;" id="vizGrid">
<div><div style="font-size:12px;color:#64748b;margin-bottom:4px;">每天出稿多少（近 14 天）</div><div id="vizTrend" style="height:210px;"></div></div>
<div><div style="font-size:12px;color:#64748b;margin-bottom:4px;">智能评分分布</div><div id="vizScore" style="height:210px;"></div></div>
<div><div style="font-size:12px;color:#64748b;margin-bottom:4px;">反馈类型</div><div id="vizFeedback" style="height:210px;"></div></div>
<div><div style="font-size:12px;color:#64748b;margin-bottom:4px;">用户打星（1-5 星）</div><div id="vizRating" style="height:210px;"></div></div>
</div>
<div id="vizFail" style="margin-top:10px;font-size:13px;color:#64748b;">失败比例：加载中…</div>
</div>
<script src="/static/echarts.min.js"></script>
<script>
var ADMIN_T=(new URLSearchParams(location.search)).get('token')||'';function AF(url,opts){opts=opts||{};opts.headers=opts.headers||{};if(ADMIN_T){opts.headers['X-Admin-Token']=ADMIN_T;}return fetch(url,opts);}
function loadInsights(){AF('/api/competition/gaps').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightGaps');if(j.success){el.textContent='还缺资料的赛事：'+j.summary;if(j.total>0){el.style.color='#d97706';}}else{el.textContent='还缺资料的赛事：读取失败';}});AF('/api/feedback/priority').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightFeedback');if(j.success&&j.items&&j.items.length){el.textContent='反馈最多的类型：'+j.items.slice(0,3).map(function(x){return x.category+'('+x.count+'条)';}).join('、');}else{el.textContent='反馈最多的类型：暂无反馈';}});AF('/api/score/diagnosis').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightScore');if(j.success&&j.diagnosis_text){el.textContent='最常丢分的地方：'+j.diagnosis_text;}else{el.textContent='最常丢分的地方：暂无足够评分数据';}});AF('/api/failure/patterns').then(function(r){return r.json()}).then(function(j){var el=document.getElementById('insightFail');if(j.success&&j.patterns&&j.patterns.length){el.textContent='最常见的失败原因：'+j.patterns.slice(0,3).map(function(x){return x.code+'×'+x.count;}).join('、');}else{el.textContent='最常见的失败原因：暂无失败';}});}
loadInsights();
function loadViz(){
    AF('/api/admin/stats').then(function(r){return r.json()}).then(function(j){
        if(!j||!j.success)return;
        var el=document.getElementById('vizFail');
        if(el)el.textContent='失败比例：'+(j.failure?(''+j.failure.failed+'/'+j.failure.total+'（'+j.failure.rate+'%%）'):'—');
        if(!window.echarts)return;
        var dark={color:['#818cf8','#c084fc','#22d3ee','#f59e0b','#f87171','#34d399']};
        // 生成趋势
        try{
            var t=echarts.init(document.getElementById('vizTrend'),dark);
            t.setOption({grid:{left:36,right:10,top:16,bottom:24},xAxis:{type:'category',data:j.trend.map(function(x){return x.date.slice(5);}),axisLabel:{color:'#64748b',fontSize:10}},yAxis:{type:'value',axisLabel:{color:'#64748b',fontSize:10},splitLine:{lineStyle:{color:'rgba(148,163,255,.12)'}}},series:[{type:'line',smooth:true,data:j.trend.map(function(x){return x.count;}),areaStyle:{opacity:.15},itemStyle:{color:'#818cf8'}}]});
        }catch(e){}
        // 评分分布
        try{
            var s=echarts.init(document.getElementById('vizScore'),dark);
            s.setOption({grid:{left:36,right:10,top:16,bottom:24},xAxis:{type:'category',data:j.score_buckets.map(function(x){return x.range;}),axisLabel:{color:'#64748b',fontSize:10}},yAxis:{type:'value',axisLabel:{color:'#64748b',fontSize:10},splitLine:{lineStyle:{color:'rgba(148,163,255,.12)'}}},series:[{type:'bar',data:j.score_buckets.map(function(x){return x.count;}),barWidth:'55%%',itemStyle:{color:'#c084fc',borderRadius:[5,5,0,0]}}]});
        }catch(e){}
        // 反馈分类
        try{
            var f=echarts.init(document.getElementById('vizFeedback'),dark);
            f.setOption({tooltip:{trigger:'item'},legend:{bottom:0,textStyle:{color:'#64748b',fontSize:10}},series:[{type:'pie',radius:['40%%','65%%'],center:['50%%','45%%'],data:j.feedback.map(function(x){return {name:x.category,value:x.count};}),label:{color:'#cbd5e1',fontSize:10}}]});
        }catch(e){}
        // 用户评分
        try{
            var rr=echarts.init(document.getElementById('vizRating'),dark);
            rr.setOption({grid:{left:36,right:10,top:16,bottom:24},xAxis:{type:'category',data:j.rating.map(function(x){return x.rating+'星';}),axisLabel:{color:'#64748b',fontSize:10}},yAxis:{type:'value',axisLabel:{color:'#64748b',fontSize:10},splitLine:{lineStyle:{color:'rgba(148,163,255,.12)'}}},series:[{type:'bar',data:j.rating.map(function(x){return x.count;}),barWidth:'50%%',itemStyle:{color:'#22d3ee',borderRadius:[5,5,0,0]}}]});
        }catch(e){}
        window.addEventListener('resize',function(){try{t.resize();s.resize();f.resize();rr.resize();}catch(e){}});
    });
}
loadViz();
</script>
</div></body></html>""" % (
        total_gen, today_gen,
        "good" if avg_rating >= 4 else ("bad" if avg_rating and avg_rating < 3 else ""),
        avg_rating, rated_count,
        "good" if success_rate >= 95 else ("bad" if success_rate < 80 else ""),
        success_rate,
        "bad" if open_issue else "good", open_issue,
        feedback_total, fb_rows, fail_rows,
        open_issue, issue_rows))

@bp.route('/admin/panel')
def admin_dashboard():
    """极简后台页：纯展示，不做登录。总生成次数 / 满意度平均分 / 最近反馈。"""
    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # 第三百二十轮：时间段选择器（今日/近3天/近7天/近30天/全部）
    _range = (request.args.get("range") or "all").strip().lower()
    _now = datetime.now()
    if _range == "today":
        _since = _now.strftime("%Y-%m-%d")
    elif _range == "3d":
        _since = (_now - timedelta(days=2)).strftime("%Y-%m-%d")
    elif _range == "7d":
        _since = (_now - timedelta(days=6)).strftime("%Y-%m-%d")
    elif _range == "30d":
        _since = (_now - timedelta(days=29)).strftime("%Y-%m-%d")
    else:
        _range = "all"
        _since = None

    def _h(where="", params=()):
        """给带 created_time 列的查询追加时间段过滤（无时间段时不追加）。"""
        if not _since:
            return where, params
        if where:
            return where + " AND created_time >= ?", params + (_since,)
        return " WHERE created_time >= ?", (_since,)

    _range_opts = "".join(
        '<option value="%s"%s>%s</option>' % (v, " selected" if v == _range else "", label)
        for v, label in (("all", "全部"), ("today", "今日"), ("3d", "近3天"), ("7d", "近7天"), ("30d", "近30天")))
    _range_ui = ('<div style="margin:10px 0;font-size:13px;color:#64748b">统计时间段：'
                 '<select onchange="location.href=\'/admin/panel?range=\'+this.value">%s</select></div>' % _range_opts)

    _w, _p = _h()
    total_gen = c.execute("SELECT COUNT(*) FROM history" + _w, _p).fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_gen = c.execute(
        "SELECT COUNT(*) FROM history WHERE created_time LIKE ?", (today + "%",)).fetchone()[0]
    _w, _p = _h(" WHERE rating > 0")
    avg_row = c.execute(
        "SELECT AVG(rating), COUNT(*) FROM history" + _w, _p).fetchone()
    avg_rating = round(avg_row[0], 2) if avg_row and avg_row[0] is not None else 0
    rated_count = avg_row[1] if avg_row else 0
    _w, _p = _h()
    feedback_total = c.execute("SELECT COUNT(*) FROM feedback" + _w, _p).fetchone()[0]
    # 112 轮：取消「只能看 10 条」——改成可翻页查看全部反馈。
    # 204 轮：默认每页 10 条（原 50 条太多，27 条挤一页）；页码走 query string，上限 500。
    try:
        _fb_limit = int(request.args.get("fblimit", 10))
    except Exception:
        _fb_limit = 10
    _fb_limit = max(10, min(500, _fb_limit))
    try:
        _fb_page = int(request.args.get("fbpage", 1))
    except Exception:
        _fb_page = 1
    # 173 轮：列表头补「类型筛选 / 排序 / 每页」三个下拉。
    # 关键：筛选后的总数必须用筛选结果重算（fb_total），不能拿全局 feedback_total 算页数——
    # 否则筛选到「只有 2 条」时仍按 27 条分 3 页，第 2 页起就是空白页（172 轮同一类毛病的另一半）。
    _fb_cat = (request.args.get("fbcat") or "").strip()
    _fb_sort = (request.args.get("fbsort") or "new").strip()
    _fb_cat_opts = [r[0] for r in c.execute(
        "SELECT DISTINCT category FROM feedback WHERE category IS NOT NULL "
        "AND TRIM(category) != '' ORDER BY category").fetchall()]
    if _fb_cat and _fb_cat not in _fb_cat_opts:
        _fb_cat = ""                      # 非法/已不存在的分类一律回退到「全部」，不报错
    _fb_where = " WHERE category = ?" if _fb_cat else ""
    _fb_order = "id ASC" if _fb_sort == "old" else "id DESC"
    _fb_params = (_fb_cat,) if _fb_cat else ()
    fb_total = c.execute(
        "SELECT COUNT(*) FROM feedback" + _fb_where, _fb_params).fetchone()[0]
    _fb_pages = max(1, (fb_total + _fb_limit - 1) // _fb_limit)
    _fb_page = max(1, min(_fb_pages, _fb_page))
    feedbacks = c.execute(
        "SELECT id, history_id, content, created_time, category FROM feedback"
        + _fb_where + " ORDER BY " + _fb_order + " LIMIT ? OFFSET ?",
        _fb_params + (_fb_limit, (_fb_page - 1) * _fb_limit)).fetchall()
    # 反馈本身不带评分；若它关联了某次生成，就把用户那次打的星一并显示（能看出好评/差评）
    _fb_rating = {}
    _fb_hids = [int(r["history_id"]) for r in feedbacks
                if r["history_id"] and str(r["history_id"]).isdigit()]
    if _fb_hids:
        try:
            _ph = ",".join("?" * len(_fb_hids))
            for _hr in c.execute(
                    "SELECT id, rating FROM history WHERE id IN (%s)" % _ph,
                    tuple(_fb_hids)).fetchall():
                if _hr["rating"]:
                    _fb_rating[int(_hr["id"])] = int(_hr["rating"])
        except Exception:
            pass
    # 满意度分布（1-5 星）
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    _w, _p = _h(" WHERE rating > 0")
    for r, n in c.execute(
            "SELECT rating, COUNT(*) FROM history" + _w + " GROUP BY rating", _p).fetchall():
        rating_dist[int(r)] = n
    # 生成趋势（最近 14 天）
    _w, _p = _h()
    trend = c.execute(
        "SELECT substr(created_time,1,10) d, COUNT(*) n FROM history" + _w +
        " GROUP BY d ORDER BY d DESC LIMIT 7", _p).fetchall()
    # 赛事分布（Top 8）：空/空白/脏值（如 "x"）赛事名归并到「未指定赛事」，避免图表出现异常标签
    _w, _p = _h()
    _comp_raw = c.execute(
        "SELECT competition_name, COUNT(*) n FROM history" + _w + " GROUP BY competition_name", _p).fetchall()
    _comp_agg = {}
    for _name, _cnt in _comp_raw:
        _key = (_name or "").strip()
        if not _key or len(_key) <= 1 or _key.lower() in ("x", "null", "none", "undefined", "nan", "n/a"):
            _key = "未指定赛事"
        _comp_agg[_key] = _comp_agg.get(_key, 0) + _cnt
    comp_dist = sorted(_comp_agg.items(), key=lambda x: (-x[1], x[0]))[:8]
    # 反馈分类聚合
    _w, _p = _h()
    fb_cat = c.execute(
        "SELECT category, COUNT(*) n FROM feedback" + _w + " GROUP BY category ORDER BY n DESC", _p).fetchall()
    # 评估指标：平均耗时 / 成功率 / 评审引擎平均分
    _w, _p = _h(" WHERE duration > 0")
    avg_dur = c.execute("SELECT AVG(duration) FROM history" + _w, _p).fetchone()[0]
    avg_dur = round(avg_dur, 1) if avg_dur else 0
    _w, _p = _h()
    succ_total = c.execute("SELECT COUNT(*) FROM history" + _w, _p).fetchone()[0]
    _w, _p = _h(" WHERE status='open'")
    fail_total = c.execute("SELECT COUNT(*) FROM gen_failures" + _w, _p).fetchone()[0]
    success_rate = round(succ_total * 100.0 / (succ_total + fail_total), 1) if (succ_total + fail_total) else 100.0
    _w, _p = _h(" WHERE json_extract(result_data,'$.score') IS NOT NULL")
    judge_avg = c.execute(
        "SELECT AVG(CAST(json_extract(result_data,'$.score') AS REAL)) FROM history" + _w, _p).fetchone()[0]
    judge_avg = round(judge_avg, 1) if judge_avg else 0
    _w, _p = _h(" WHERE status='open'")
    open_issues = c.execute(
        "SELECT id, kind, source, content, created_time FROM issues" + _w + " ORDER BY id DESC LIMIT 15", _p).fetchall()
    conn.close()

    # 今日大模型调用额度（第二百五十四轮：统一走 get_quota_status，避免硬编码 500
    # 与 env 的 QUOTA_DAILY_LIMIT 不一致，导致数据面板/动态监视/health 三处口径打架）
    quota_remaining = 0
    try:
        from backend.competition_agents import get_quota_status
        quota_remaining = int(get_quota_status().get("remaining", 0) or 0)
    except Exception:
        pass

    # 111/112 轮：反馈区从「原生 li 平铺」升级为卡片化（分类色块 + 时间人话化 +
    # 关联星级 + 超长截断悬停看全文 + hover 高亮）。内容一律 _html_escape 防注入。
    fb_items = []
    for r in feedbacks:
        _cat = (r["category"] or "其他").strip() or "其他"
        _stars = ""
        _hid = r["history_id"]
        if _hid and str(_hid).isdigit() and int(_hid) in _fb_rating:
            _n = _fb_rating[int(_hid)]
            _stars = ('<span class="fbstar" title="该次生成用户打了 %d 星">%s</span>'
                      % (_n, "★" * _n + "☆" * (5 - _n)))
        _txt = _html_escape(r["content"] or "")
        fb_items.append(
            '<li class="fbcard">'
            '<div class="fbmeta">'
            '<span class="fbid">#%s</span>'
            '<span class="fbcat %s">%s</span>'
            '<span class="fbtime">%s</span>%s'
            '</div>'
            '<div class="fbtext" title="%s">%s</div>'
            '</li>'
            % (r["id"], _fb_cat_cls(_cat), _html_escape(_cat),
               _fb_time_fmt(r["created_time"]), _stars, _txt, _txt))
    fb_html = "".join(fb_items) or '<li class="empty">暂无反馈</li>'

    # 翻页控件（页码越界已在上面 clamp，不会出现空白页）
    if fb_total:
        _dis = lambda at_edge: " fbpg dis" if at_edge else " fbpg"
        # 翻页必须带上当前筛选条件，否则点「下一页」就把筛选丢了
        _qcat = _html_escape(_fb_cat)
        _qs = "&amp;fblimit=%d&amp;fbsort=%s&amp;fbcat=%s" % (
            _fb_limit, _html_escape(_fb_sort), _qcat)
        fb_pager = (
            '<div class="fbpager">'
            '<a class="%s" href="?fbpage=1%s">首页</a>'
            '<a class="%s" href="?fbpage=%d%s">上一页</a>'
            '<span class="fbnow">第 %d / %d 页 · 共 %d 条</span>'
            '<a class="%s" href="?fbpage=%d%s">下一页</a>'
            '<a class="%s" href="?fbpage=%d%s">末页</a>'
            '</div>'
            % (_dis(_fb_page <= 1).strip(), _qs,
               _dis(_fb_page <= 1).strip(), _fb_page - 1, _qs,
               _fb_page, _fb_pages, fb_total,
               _dis(_fb_page >= _fb_pages).strip(), _fb_page + 1, _qs,
               _dis(_fb_page >= _fb_pages).strip(), _fb_pages, _qs))
    else:
        fb_pager = ""
    # 标题里的条数先拼好再进模板：这个 HTML 整段用 % 格式化，直接在模板里写 %d
    # 会跟后面的参数元组错位（静默错列，极难发现）
    # 173 轮：标题带计数徽标（已有）+ 右侧筛选表单；选完自动提交（onchange），一行搞定不用点按钮
    fb_count_hint = ("<span class='fbcount'>%d</span>" % fb_total) if fb_total else ""
    _cat_sel = "".join(
        '<option value="%s"%s>%s</option>'
        % (_html_escape(x), " selected" if x == _fb_cat else "", _html_escape(x))
        for x in _fb_cat_opts)
    _fb_filter = (
        '<form class="fbfilter" method="get" action="/admin/panel">'
        '<select name="fbcat" onchange="this.form.submit()">'
        '<option value="">全部类型</option>%s</select>'
        '<select name="fbsort" onchange="this.form.submit()">'
        '<option value="new"%s>最新在前</option>'
        '<option value="old"%s>最早在前</option></select>'
        '<select name="fblimit" onchange="this.form.submit()">%s</select>'
        '<noscript><button type="submit">应用</button></noscript>'
        '</form>'
        % (_cat_sel,
           " selected" if _fb_sort != "old" else "",
           " selected" if _fb_sort == "old" else "",
           "".join('<option value="%d"%s>每页 %d 条</option>'
                   % (n, " selected" if n == _fb_limit else "", n)
                   for n in (10, 20, 50, 100))))
    fb_title = ("<div class=\"fbtitle\">全部反馈%s%s</div>"
                % (fb_count_hint, _fb_filter))

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

    # 生成趋势（最近 7 天，正序显示；0 值也占位，避免只渲染有数据的一天）
    _trend_map = {d: n for d, n in trend}
    _trend_full = []
    for _i in range(6, -1, -1):
        _d = (_now - timedelta(days=_i)).strftime("%Y-%m-%d")
        _trend_full.append((_d, _trend_map.get(_d, 0)))
    max_t = max([n for _, n in _trend_full]) or 1
    trend_bars = []
    for d, n in _trend_full:
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
    issues_html = "".join(issue_items) or '<li class="empty">暂无待处理的反馈</li>'

    html = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>科创赛事助手 · 后台数据</title>
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
li .t{font-size:12px;color:#6b7280;margin-bottom:4px}
li.empty{color:#6b7280;text-align:center;padding:22px}
.box{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:14px}
.barrow{display:flex;align-items:center;gap:10px;margin:7px 0}
.barrow .bl{width:160px;font-size:13px;color:#374151;text-align:right;flex-shrink:0;word-break:break-word;line-height:1.35}
.barrow .btrack{flex:1;background:#eef0f4;border-radius:6px;height:14px;overflow:hidden}
.barrow .bfill{display:block;height:100%%;background:linear-gradient(90deg,#2563eb,#60a5fa);border-radius:6px}
.barrow .bn{width:34px;font-size:13px;color:#6b7280;flex-shrink:0}
.trend{display:flex;align-items:flex-end;gap:12px;height:130px;padding-top:6px}
.tcol{flex:1;display:flex;flex-direction:column;align-items:center}
.tcol .tv{font-size:11px;color:#6b7280}
.tcol .tbar{width:100%%;height:80px;display:flex;align-items:flex-end}
.tcol .tfill{width:100%%;background:#2563eb;border-radius:4px 4px 0 0;min-height:2px}
.tcol .td{font-size:10px;color:#6b7280;margin-top:4px}
.chip{display:inline-block;background:#eef2ff;color:#2563eb;border-radius:999px;padding:4px 12px;font-size:13px;margin:3px 6px 3px 0}
.empty{color:#6b7280;text-align:center;padding:16px}
/* 111/112 轮：反馈卡片化。白卡+圆角+淡阴影+hover 高亮，分类色块拉齐视觉层级 */
.fblist{list-style:none;padding:0;margin:0}
.fbcard{background:#fff;border-radius:10px;padding:12px 14px;margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);transition:box-shadow .15s,transform .15s}
.fbcard:hover{box-shadow:0 4px 12px rgba(0,0,0,.10);transform:translateY(-1px)}
.fbmeta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;color:#6b7280;margin-bottom:6px}
.fbid{color:#6b7280;font-variant-numeric:tabular-nums}
.fbcat{border-radius:999px;padding:2px 9px;font-size:12px;font-weight:600;white-space:nowrap}
.fbcat-good{background:#dcfce7;color:#15803d}
.fbcat-idea{background:#dbeafe;color:#1d4ed8}
.fbcat-bug{background:#fee2e2;color:#b91c1c}
.fbcat-warn{background:#fef3c7;color:#b45309}
.fbcat-other{background:#f1f5f9;color:#475569}
.fbstar{color:#f59e0b;letter-spacing:1px}
/* 173 轮：列表头 = 标题+计数徽标+筛选表单一行，窄屏自动换行不溢出 */
.fbtitle{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.fbcount{display:inline-block;min-width:22px;padding:1px 8px;border-radius:999px;
    background:#e0f2fe;color:#0369a1;font-size:12px;font-weight:700;text-align:center}
.fbfilter{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.fbfilter select{font-size:12px;padding:4px 8px;border:1px solid #dbe3ee;border-radius:7px;
    background:#fff;color:#374151;cursor:pointer;max-width:44vw}
.fbfilter select:hover{border-color:#64748b}
@media (max-width:640px){
    .fbcard{padding:10px 11px}
    .fbmeta{gap:5px;flex-wrap:wrap}
    .fbtext{font-size:13px;line-height:1.6}
    /* ⚠ 这段 CSS 处在「整页 HTML 走百分号运算符格式化」的字符串里：
       任何百分号（含注释正文里的举例）都必须写两个，否则百分号后面那个字符会被当格式符、
       页面直接 500。本注释因此连举例都不写这个符号。 */
    .fbfilter{margin-left:0;width:100%%}
    .fbfilter select{flex:1 1 30%%;max-width:none}
    .fbpager a,.fbpager .fbnow{font-size:12px}
}
/* 超长正文截到 4 行，完整内容走 title 悬停，避免单条反馈把整页撑长 */
.fbtext{font-size:14px;color:#1f2937;word-break:break-word;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;line-height:1.6}
.fbpager{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px;font-size:13px}
.fbpager .fbpg{background:#fff;color:#374151;text-decoration:none;padding:6px 12px;border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.fbpager .fbpg.dis{opacity:.45;pointer-events:none}
.fbpager .fbnow{color:#6b7280}
.nav{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.nav a{background:#fff;color:#374151;text-decoration:none;padding:8px 14px;border-radius:8px;font-size:14px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.nav a.active{background:#2563eb;color:#fff}
<link rel="stylesheet" href="/static/wbbtn-admin.css?v=20260929an"></style></head><body><div class="wrap">
<nav class="nav"><img src="/static/logo.png" alt="科创赛事助手" style="height:26px;vertical-align:middle;margin-right:8px"><a href="/admin">🏠 概览</a><a href="/admin/panel" class="active">📊 明细数据</a><a href="/admin/llm-usage">💸 模型花费</a><a href="/monitor">🟢 实时状态</a><a href="/">↩ 主站</a></nav>
<h1>科创赛事助手 · 后台数据</h1>
<div class="banner">🟢 服务运行正常</div>
%s
<div class="cards">
<div class="card"><div class="num">%d</div><div class="label">累计出稿</div></div>
<div class="card"><div class="num">%d</div><div class="label">今天出稿</div></div>
<div class="card"><div class="num">%d</div><div class="label">今天还能出稿</div></div>
<div class="card"><div class="num">%s/5分</div><div class="label">满意度平均分（%d 人打分）</div></div>
<div class="card"><div class="num">%d</div><div class="label">反馈总数</div></div>
<div class="card"><div class="num">%ss</div><div class="label">平均一份要多久</div></div>
<div class="card"><div class="num">%s%%</div><div class="label" title="成功率 = 成功记录数 ÷（成功记录数 + 未处理失败数）">生成成功率</div></div>
<div class="card"><div class="num">%s/100分</div><div class="label">评审引擎平均分</div></div>
</div>
<div class="box">
<h2 style="margin-top:0">用户打星分布</h2>
%s
</div>
<div class="box">
<h2 style="margin-top:0">每天出稿多少（最近 7 天）</h2>
<div class="trend">%s</div>
</div>
<div class="box comp-dist">
<h2 style="margin-top:0">各赛事出稿量</h2>
%s
<div style="font-size:11px;color:#6b7280;margin-top:8px">注：「未指定赛事」为历史记录中未选择赛事的数据，不计入具体赛事。</div>
</div>
<div class="box">
<h2 style="margin-top:0">反馈类型</h2>
%s
</div>
<div class="box">
<h2 style="margin-top:0">待处理的反馈（按内容自动分给前端 / 后端）</h2>
<ul>%s</ul>
</div>
<h2 style="margin-top:0">%s</h2>
<ul class="fblist">%s</ul>
%s
<div style="margin-top:14px"><a href="/api/feedback/export" style="color:#2563eb">⬇ 下载全部反馈 Excel</a></div>
</div></body></html>""" % (_range_ui, total_gen, today_gen, quota_remaining, avg_rating,
                              rated_count, feedback_total, avg_dur, success_rate,
                              judge_avg, rating_bars_html, trend_html, comp_html,
                              cat_html, issues_html, fb_title, fb_html, fb_pager)
    return _inject_role_badge(html)

@bp.route('/api/admin/issues/<int:issue_id>/status', methods=['POST'])
def issue_status(issue_id):
    """第三百一十七/三百七十六轮：工单状态流转 + 处理说明 + 管理员回复。
    走 /api/admin/ 前缀，已被 _admin_guard 统一鉴权（仅管理员可改，演示只读 403）。"""
    data = request.get_json(silent=True) or {}
    status = str(data.get('status') or '').strip()
    if status not in ('open', 'processing', 'resolved'):
        return jsonify({"success": False, "error": "无效状态"}), 400
    resolution = str(data.get('resolution') or '').strip()
    reply = str(data.get('reply') or '').strip()
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT id FROM issues WHERE id=?", (issue_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "这条反馈不存在"}), 404
    _now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if status == 'resolved':
        c.execute("UPDATE issues SET status='resolved', resolved_time=?, resolution=?, reply=? WHERE id=?",
                  (_now, resolution, reply, issue_id))
    else:
        c.execute("UPDATE issues SET status=?, resolution=?, reply=?, resolved_time=NULL WHERE id=?",
                  (status, resolution, reply, issue_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "id": issue_id, "status": status})

@bp.route('/api/admin/quota')
def admin_quota():
    """额度监视（第九十一轮）：今日 quota + 近 7 日每日生成数（近似调用活跃度）。"""
    try:
        from backend.competition_agents import get_quota_status
        q = get_quota_status()
        calls = int(q.get("calls") or 0)
        limit = int(q.get("limit") or 0)
        percent = round(calls * 100.0 / limit, 1) if limit else 0
        conn = get_db()
        c = conn.cursor()
        rows = c.execute(
            "SELECT substr(created_time,1,10) AS d, COUNT(*) AS n FROM history "
            "WHERE created_time >= date('now','-7 day') GROUP BY d ORDER BY d").fetchall()
        conn.close()
        day_map = {r[0]: r[1] for r in rows}
        daily = []
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily.append({"date": day, "count": day_map.get(day, 0)})
        return jsonify({
            "success": True, "calls": calls, "limit": limit,
            "remaining": max(0, limit - calls), "percent": percent,
            "exceeded": calls >= limit, "daily": daily,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/admin/llm-usage')
def admin_llm_usage_page():
    """Token 用量看板（数据来自 /api/admin/llm-usage 与 .../per-generation）。"""
    return current_app.send_static_file('admin-llm-usage.html')

@bp.route('/api/admin/llm-usage')
def admin_llm_usage():
    auth = _require_admin()
    if auth:
        return auth
    try:
        import backend.competition_agents as _agents
        from backend.llm_usage_store import aggregate_usage
        days = request.args.get("days", default=30, type=int)
        limit = request.args.get("limit", default=20, type=int)
        return jsonify({"success": True, **aggregate_usage(
            _agents._LLM_USAGE_DB_PATH, days=days, limit=limit)})
    except Exception as exc:
        print("[llm_usage] aggregate failed: %s" % exc)
        return jsonify({"success": False, "error": "Token 统计暂不可用"}), 500

@bp.route('/api/admin/llm-usage/per-generation')
def admin_llm_usage_per_generation():
    """单次生成口径：一次生成到底调了几次模型、烧了多少 token。

    与 /api/admin/llm-usage（总量口径）互补：总量说明规模，分布说明单次成本。
    只统计带 task_id 的记录，样本量见 summary.task_count。
    """
    auth = _require_admin()
    if auth:
        return auth
    try:
        import backend.competition_agents as _agents
        from backend.llm_usage_store import aggregate_tasks, per_generation_summary
        days = request.args.get("days", default=30, type=int)
        return jsonify({
            "success": True,
            "summary": per_generation_summary(_agents._LLM_USAGE_DB_PATH, days=days),
            "tasks": aggregate_tasks(_agents._LLM_USAGE_DB_PATH, days=days, limit=50),
        })
    except Exception as exc:
        print("[llm_usage] per-generation failed: %s" % exc)
        return jsonify({"success": False, "error": "单次成本统计暂不可用"}), 500

@bp.route('/api/admin/runs')
def admin_generation_runs():
    """生成运行清单：每次生成用的代码版本、知识库快照、模型、token、质检与导出结果。

    代码版本 = app.py / competition_agents.py / quality_gate.py 的内容哈希，
    改过任何一行 prompt 就会变；知识库快照 = 赛事档案与规则文本的路径+大小+时间指纹。
    """
    auth = _require_admin()
    if auth:
        return auth
    try:
        from backend.run_registry import code_version, kb_snapshot, recent_runs
        limit = request.args.get("limit", default=50, type=int)
        return jsonify({"success": True, "code_version": code_version(),
                        "kb_snapshot": kb_snapshot(),
                        "runs": recent_runs(DB_PATH, limit=limit)})
    except Exception as exc:
        print("[run_registry] list failed: %s" % exc)
        return jsonify({"success": False, "error": "运行清单暂不可用"}), 500

@bp.route('/api/admin/stats')
def admin_stats():
    """后台可视化数据：生成趋势 / 失败率 / 反馈分类 / 评分分布 / 智能评分分布。"""
    auto_resolve_failures()
    try:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        trend = c.execute(
            "SELECT substr(created_time,1,10) AS d, COUNT(*) AS n FROM history "
            "WHERE created_time >= date('now','-14 day') GROUP BY d ORDER BY d").fetchall()
        recent_failures = c.execute(
            "SELECT task_id, type, path, error, detail, created_time, count, "
            "stage, error_code, error_msg FROM gen_failures "
            "WHERE status='open' ORDER BY id DESC LIMIT 10").fetchall()
        total = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        failed = c.execute("SELECT COUNT(*) FROM gen_failures WHERE status='open'").fetchone()[0]
        mode_rows = c.execute("SELECT mode, COUNT(*) AS n FROM history GROUP BY mode").fetchall()
        # 第一百四十三轮：排除 duration≤1s 测试异常样本，用中位数口径，不被个别极值拉偏
        _durs = [r[0] for r in c.execute("SELECT duration FROM history WHERE duration > 1").fetchall()]
        avg_dur = sorted(_durs)[len(_durs) // 2] if _durs else 0
        fb = c.execute(
            "SELECT category, COUNT(*) AS n FROM feedback GROUP BY category ORDER BY n DESC").fetchall()
        rating = c.execute(
            "SELECT rating, COUNT(*) AS n FROM history WHERE rating > 0 "
            "GROUP BY rating ORDER BY rating").fetchall()
        scores = c.execute("SELECT result_data FROM history").fetchall()
        conn.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    buckets = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    for r in scores:
        try:
            d = json.loads(r["result_data"])
            s = d.get("score")
            if s is None:
                continue
            s = float(s)
        except Exception:
            continue
        if s < 60:
            buckets["0-59"] += 1
        elif s < 70:
            buckets["60-69"] += 1
        elif s < 80:
            buckets["70-79"] += 1
        elif s < 90:
            buckets["80-89"] += 1
        else:
            buckets["90-100"] += 1

    # 生成趋势 14 天全序列补零（无数据日期补 0，含今日实时点）
    trend_map = {r["d"]: r["n"] for r in trend}
    trend_full = []
    for i in range(13, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend_full.append({"date": day, "count": trend_map.get(day, 0)})
    recent_failures_list = [{
        "time": r["created_time"], "type": r["type"] or "generate",
        "path": r["path"] or "", "error": r["error"], "detail": r["detail"],
        "task_id": r["task_id"] or "", "count": r["count"] or 1,
        "stage": r["stage"] or "", "error_code": r["error_code"] or "",
        "error_msg": r["error_msg"] or "",
    } for r in recent_failures]

    denom = total + failed
    mode_breakdown = {r["mode"] or "unknown": r["n"] for r in mode_rows}
    success_rate = round(total * 100.0 / denom, 1) if denom else 100.0
    avg_duration = round(avg_dur, 1) if avg_dur else 0
    return jsonify({
        "success": True,
        "total": total,
        "mode_breakdown": mode_breakdown,
        "fast_count": mode_breakdown.get("fast", 0),
        "deep_count": mode_breakdown.get("deep", 0),
        "avg_duration": avg_duration,
        "success_rate": success_rate,
        "trend": trend_full,
        "failure": {"total": denom, "failed": failed,
                    "rate": round(failed * 100.0 / denom, 1) if denom else 0},
        "recent_failures": recent_failures_list,
        "feedback": [{"category": r["category"], "count": r["n"]} for r in fb],
        "rating": [{"rating": r["rating"], "count": r["n"]} for r in rating],
        "score_buckets": [{"range": k, "count": v} for k, v in buckets.items()],
    })

@bp.route('/admin/report')
def admin_report():
    """测试数据报告：一键出统计表 + 图，答辩直接打印 / 截图贴 PPT。"""
    try:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        failed = c.execute("SELECT COUNT(*) FROM gen_failures WHERE status='open'").fetchone()[0]
        mode_rows = c.execute("SELECT mode, COUNT(*) AS n FROM history GROUP BY mode").fetchall()
        avg_dur = c.execute("SELECT AVG(duration) FROM history WHERE duration > 0").fetchone()[0]
        fb = c.execute("SELECT category, COUNT(*) AS n FROM feedback GROUP BY category ORDER BY n DESC").fetchall()
        scores = c.execute("SELECT result_data FROM history").fetchall()
        conn.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    buckets = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    for r in scores:
        try:
            s = float(json.loads(r["result_data"]).get("score"))
        except Exception:
            continue
        if s < 60:
            buckets["0-59"] += 1
        elif s < 70:
            buckets["60-69"] += 1
        elif s < 80:
            buckets["70-79"] += 1
        elif s < 90:
            buckets["80-89"] += 1
        else:
            buckets["90-100"] += 1

    mode_bd = {r["mode"] or "unknown": r["n"] for r in mode_rows}
    denom = total + failed
    success_rate = round(total * 100.0 / denom, 1) if denom else 100.0
    avg_duration = round(avg_dur, 1) if avg_dur else 0

    score_json = json.dumps([{"range": k, "count": v} for k, v in buckets.items()], ensure_ascii=False)
    feedback_json = json.dumps([{"name": r["category"], "value": r["n"]} for r in fb], ensure_ascii=False)
    mode_json = json.dumps([{"name": k, "value": v} for k, v in mode_bd.items()], ensure_ascii=False)

    html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>测试数据报告</title>
<script src="/static/echarts.min.js"></script>
<style>
body{font-family:"Microsoft YaHei",sans-serif;background:#0b1020;color:#e5e7eb;margin:0;padding:24px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:22px;margin:0 0 18px;color:#fff}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px}
.card{flex:1 1 150px;background:#151b2e;border:1px solid #26304a;border-radius:10px;padding:14px;text-align:center}
.card .num{font-size:26px;font-weight:700;color:#22d3ee}
.card .label{font-size:12px;color:#64748b;margin-top:4px}
.chart{height:300px;background:#151b2e;border:1px solid #26304a;border-radius:10px;margin-bottom:14px;padding:8px}
.bar{display:flex;justify-content:flex-end;gap:10px;margin-bottom:14px}
button{background:#22d3ee;color:#050816;border:none;padding:10px 18px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
<link rel="stylesheet" href="/static/wbbtn-admin.css?v=20260929an"></style></head><body>
<div class="wrap">
<h1>科创赛事助手 · 测试数据</h1>
<div class="cards">
<div class="card"><div class="num">""" + str(total) + """</div><div class="label">累计出稿</div></div>
<div class="card"><div class="num">""" + str(mode_bd.get("fast", 0)) + """</div><div class="label">简洁版</div></div>
<div class="card"><div class="num">""" + str(mode_bd.get("deep", 0)) + """</div><div class="label">深度版</div></div>
<div class="card"><div class="num">""" + str(avg_duration) + """s</div><div class="label">平均一份要多久</div></div>
<div class="card"><div class="num">""" + str(success_rate) + """%</div><div class="label">出稿成功率（样本有限）</div></div>
</div>
<div class="bar"><button onclick="window.print()">打印 / 存 PDF</button></div>
<div id="scoreChart" class="chart"></div>
<div id="feedbackChart" class="chart"></div>
</div>
<script>
var SCORE = """ + score_json + """;
var FEEDBACK = """ + feedback_json + """;
var MODE = """ + mode_json + """;
function bar(id, title, data, color){var c=echarts.init(document.getElementById(id));c.setOption({title:{text:title,textStyle:{color:'#e5e7eb',fontSize:14}},grid:{left:40,right:20,top:40,bottom:30},xAxis:{type:'category',data:data.map(function(d){return d.range||d.name;}),axisLabel:{color:'#64748b'}},yAxis:{type:'value',axisLabel:{color:'#64748b'}},series:[{type:'bar',data:data.map(function(d){return d.count||d.value;}),itemStyle:{color:color||'#22d3ee'}}]});}
bar('scoreChart','智能评分分布',SCORE,'#22d3ee');
bar('feedbackChart','反馈类型',FEEDBACK,'#a78bfa');
</script>
</body></html>"""
    return _inject_role_badge(html)

@bp.route('/api/admin/audit')
def api_admin_audit():
    """第二百一十一轮 D：审计日志查询（仅 admin 可见）。读 docs/后台审计.md 最近 N 行。"""
    _a = _require_admin()
    if _a is not None:
        return _a
    try:
        limit = min(int(request.args.get("limit", 200)), 2000)
    except (TypeError, ValueError):
        limit = 200
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs', '后台审计.md')
    if not os.path.isfile(p):
        return jsonify({"success": True, "audit": [], "total": 0})
    try:
        with open(p, encoding='utf-8') as f:
            lines = [l.rstrip('\n') for l in f if l.strip()]
    except Exception:
        return jsonify({"success": True, "audit": [], "total": 0})
    return jsonify({"success": True, "audit": lines[-limit:], "total": len(lines)})

@bp.route('/api/admin/textcheck')
def api_admin_textcheck():
    """第二百一十三轮：文案自查工具（admin）——扫全站常见不一致/错别字，返回命中位置。"""
    _a = _require_admin()
    if _a is not None:
        return _a
    # 词表：(正确写法, 疑似错误写法)
    _rules = [
        ("科创赛事助手", "赛创助手"),
        ("科创赛事助手", "赛创赛事助手"),
        ("简洁版", "简洁快速版"),
        ("评审引擎", "模拟评委"),
        ("多智能体协作", "AI 生成"),
    ]
    _files = ["index.html", "static/app.js", "static/style.css", "static/wbconst.js"]
    _hits = []
    for _fname in _files:
        _p = os.path.join(_FRONTEND_DIR, _fname)
        if not os.path.isfile(_p):
            continue
        try:
            with open(_p, encoding='utf-8') as _f:
                _lines = _f.read().splitlines()
        except Exception:
            continue
        for _i, _ln in enumerate(_lines, 1):
            for _correct, _wrong in _rules:
                if _wrong in _ln:
                    _hits.append({"file": _fname, "line": _i,
                                  "wrong": _wrong, "correct": _correct,
                                  "snippet": _ln.strip()[:80]})
                    break
    return jsonify({"success": True, "hits": _hits, "total": len(_hits)})

@bp.route('/api/admin/alert_status')
def alert_status():
    """第三百七十七轮：监控告警——额度/失败率/工单滞留三类阈值。"""
    try:
        from backend.competition_agents import get_quota_status
        _q = get_quota_status()
        _ratio = _q.get('calls', 0) / max(_q.get('limit', 1), 1)
    except Exception:
        _ratio = 0
    conn = get_db()
    succ = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    fail = conn.execute("SELECT COUNT(*) FROM gen_failures WHERE status='open'").fetchone()[0]
    stale = conn.execute("SELECT COUNT(*) FROM issues WHERE status='open' AND created_time < datetime('now','-2 day')").fetchone()[0]
    conn.close()
    _fr = fail / (succ + fail) if (succ + fail) else 0
    return jsonify({"success": True, "alerts": {
        "quota_low": {"triggered": _ratio >= 0.9, "detail": "今天还能出稿，只剩 %.0f%% 的量" % max(0, (1 - _ratio) * 100)},
        "fail_rate_high": {"triggered": _fr > 0.2, "detail": "最近的生成里有 %.1f%% 没成功" % (_fr * 100)},
        "issue_stale": {"triggered": stale > 0, "detail": "%d 条反馈压了超过 48 小时" % stale}}})

@bp.route('/api/admin/diagnose')
def diagnose():
    """第三百九十二轮：服务诊断——核心接口 ping 状态与耗时。"""
    import time as _t
    items = []
    with app.test_client() as c:
        for name, path in (("health", "/api/health"), ("user_state", "/api/user_state"),
                            ("history", "/api/history"), ("feedback", "/api/feedback"),
                            ("quota", "/api/quota")):
            _t0 = _t.time()
            try:
                r = c.get(path)
                items.append({"name": name, "status": "ok" if r.status_code < 400 else "error",
                              "code": r.status_code, "latency_ms": int((_t.time() - _t0) * 1000)})
            except Exception:
                items.append({"name": name, "status": "error", "code": None,
                              "latency_ms": int((_t.time() - _t0) * 1000)})
    mem = {"total": -1, "used": -1, "percent": -1}
    try:
        import psutil
        _m = psutil.virtual_memory()
        mem = {"total": _m.total, "used": _m.used, "percent": _m.percent}
    except Exception:
        pass
    return jsonify({"success": True, "items": items, "memory": mem})

@bp.route('/api/admin/export_csv')
def export_csv():
    """第三百七十九轮：数据导出 CSV——生成记录/反馈/工单三张表。"""
    import csv, io
    from flask import Response
    table = (request.args.get('table') or 'history').strip()
    _days = {'3d': 2, '7d': 6, '30d': 29}.get((request.args.get('range') or '').strip())
    conn = get_db()
    conn.row_factory = sqlite3.Row
    _where, _params = "", []
    if _days is not None:
        _since = (datetime.now() - timedelta(days=_days)).strftime('%Y-%m-%d')
        _where, _params = " WHERE created_time >= ?", [_since]
    if table == 'feedback':
        rows = conn.execute("SELECT id, history_id, content, category, created_time FROM feedback" + _where, _params).fetchall()
        header = ["id", "history_id", "content", "category", "created_time"]
    elif table == 'issues':
        rows = conn.execute("SELECT id, kind, source, content, status, created_time FROM issues" + _where, _params).fetchall()
        header = ["id", "kind", "source", "content", "status", "created_time"]
    else:
        rows = conn.execute("SELECT id, competition_name, idea, mode, duration, status, created_time FROM history" + _where, _params).fetchall()
        header = ["id", "competition_name", "idea", "mode", "duration", "status", "created_time"]
    conn.close()
    _buf = io.StringIO()
    _w = csv.writer(_buf)
    _w.writerow(header)
    for r in rows:
        _w.writerow([r[k] for k in header])
    return Response(_buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=%s.csv" % table})

@bp.route('/admin/vulns')
def admin_vulns_page():
    """漏洞库后台页：统计卡片 + 修复进度 + 归因/责任分布条形图 + 可展开改状态的表格。

    页面自身不带 token（所有数据来自 admin 鉴权的 /api/vulns* 接口），
    接口返 401/403 时由页面弹出 token 输入框，token 只存浏览器本机。
    """
    return _inject_role_badge(_VULNS_PAGE_HTML)


# ---- app.py 共用符号的惰性绑定（见 _Lazy 注释）----
ADMIN_TOKEN = _Lazy('ADMIN_TOKEN')
DB_PATH = _Lazy('DB_PATH')
DEMO_TOKEN = _Lazy('DEMO_TOKEN')
_ADMIN_COOKIE_NAME = _Lazy('_ADMIN_COOKIE_NAME')
_ADMIN_FAILS = _Lazy('_ADMIN_FAILS')
_ADMIN_LOCK = _Lazy('_ADMIN_LOCK')
_ADMIN_LOCK_AFTER = _Lazy('_ADMIN_LOCK_AFTER')
_ADMIN_LOCK_SECONDS = _Lazy('_ADMIN_LOCK_SECONDS')
_ADMIN_LOGIN_HTML = _Lazy('_ADMIN_LOGIN_HTML')
_ADMIN_SESSION_SIGNER = _Lazy('_ADMIN_SESSION_SIGNER')
_DEMO_READONLY_USERS = _Lazy('_DEMO_READONLY_USERS')
_FRONTEND_DIR = _Lazy('_FRONTEND_DIR')
_NOTICE_FILE = _Lazy('_NOTICE_FILE')
_VULNS_PAGE_HTML = _Lazy('_VULNS_PAGE_HTML')
_admin_role_badge_html = _Lazy('_admin_role_badge_html')
_admin_session_role = _Lazy('_admin_session_role')
_client_ip = _Lazy('_client_ip')
_fb_cat_cls = _Lazy('_fb_cat_cls')
_fb_time_fmt = _Lazy('_fb_time_fmt')
_friendly_fail_text = _Lazy('_friendly_fail_text')
_html_escape = _Lazy('_html_escape')
_load_admin_users = _Lazy('_load_admin_users')
_require_admin = _Lazy('_require_admin')
auto_resolve_failures = _Lazy('auto_resolve_failures')
get_db = _Lazy('get_db')


def register(app):
    app.register_blueprint(bp)
    return app
