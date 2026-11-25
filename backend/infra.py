# -*- coding: utf-8 -*-
"""基础设施层：数据库连接、匿名用户标识、限流、后台鉴权、错误归类。

从 app.py 抽出（第 1 阶段重构）。这些符号被 100 多处调用，是 app.py 里唯一的
横切耦合；独立成模块后，后续拆出的 blueprint 只需 `from infra import ...`，
不必依赖 app 本身。

路径注意：本文件与 app.py 同目录，所以 `os.path.dirname(__file__)` 的结果不变，
DB_PATH 与 .uid_secret 的定位和重构前完全一致。
"""
import os
import sqlite3
import sys
import threading
import time
import secrets as _secrets

from flask import request, jsonify, g
from itsdangerous import URLSafeSerializer


def _load_uid_secret():
    _p = os.getenv("COMPETITION_UID_SECRET_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), '.data', '.uid_secret')
    try:
        with open(_p, encoding='utf-8') as _f:
            _s = _f.read().strip()
        if _s:
            return _s
    except FileNotFoundError:
        pass
    _s = _secrets.token_hex(32)
    try:
        with open(_p, 'w', encoding='utf-8') as _f:
            _f.write(_s)
    except Exception:
        pass
    return _s


def _current_uid():
    """取当前匿名用户 id；无 cookie 时退回 IP，保证旧前端也能落到一个稳定隔离键。"""
    return getattr(g, 'uid', None) or (request.cookies.get('comp_uid') or '').strip() or \
        (request.remote_addr or 'anon')


def _require_uid():
    """硬鉴权（196 轮 C2/C4/C5/C3）：无有效 comp_uid 签名 cookie 时返回 401。

    与「软隔离」的区别：软隔离是无 cookie 时给个临时 uid 返回空数据（HTTP 仍 200）；
    硬鉴权是直接 401，明确拒绝匿名访问用户归属类接口（历史/导出/上传）。
    前端首次进页面时 HTML 响应已下发签名 cookie，后续请求带 cookie 通过，不受影响。
    """
    if not getattr(g, 'uid_authenticated', False):
        resp = jsonify({"success": False, "error": "未登录（缺少有效的用户标识）"})
        resp.status_code = 401
        return resp
    return None


# 简单限流：同一 IP 1 分钟最多生成 5 次，防止刷接口（学生项目级防护，无需登录系统）。
# 说明：进程内内存限流，gunicorn 多 worker 时是「每 worker 各自限 5 次」；
# 对当前单机小规模部署足够，若以后上多机/高并发再升级为共享存储（如 Redis）。
_RATE_WINDOW_SEC = 60
_RATE_LIMIT = 5
_rate_lock = threading.Lock()
_rate_hits = {}  # ip -> list[float] 命中时间戳（Unix 秒）


def _client_ip():
    """取客户端真实 IP。

    只在本机反代（nginx）转发时才采信 X-Real-IP —— 这个头由 nginx 用 $remote_addr
    覆盖写入，客户端自己发无效。X-Forwarded-For 一律不采信：nginx 用的是
    $proxy_add_x_forwarded_for（追加语义），客户端伪造的值会排在最前面，
    直接取首地址等于把限流键交给攻击者（2026-11-25 实测：伪造该头可完全绕过限流）。
    """
    remote = (request.remote_addr or '').strip()
    if remote in ('127.0.0.1', '::1', 'localhost'):
        real = (request.headers.get('X-Real-IP') or '').strip()
        if real:
            return real
    return remote or 'unknown'


def _rate_hit(name, key, limit, window):
    """通用滑动窗口计数：返回 True 表示该桶已超限。"""
    now = time.time()
    with _rate_lock:
        bucket = _rate_hits.setdefault(name, {})
        hits = [t for t in bucket.get(key, []) if now - t < window]
        if len(hits) >= limit:
            bucket[key] = hits
            return True
        hits.append(now)
        bucket[key] = hits
        # 桶过多时顺手清理，避免内存缓慢增长
        if len(bucket) > 5000:
            for k in [k for k in list(bucket) if not [t for t in bucket[k] if now - t < window]]:
                bucket.pop(k, None)
        return False


def _rate_limited(name='gen', limit=_RATE_LIMIT, window=_RATE_WINDOW_SEC, ip_limit=None):
    """双桶限流：用户桶 + IP 桶，任一超限即拒；超限返回 True，否则 False。

    为什么必须双桶：只用 uid 桶，清掉 cookie 就重置计数（2026-11-25 实测：
    换 cookie 连打 6 次生成接口全部通过）；只用 IP 桶，校园网 NAT 后几百人共用
    一个出口会成片误伤。两桶都过、且 IP 桶阈值放宽（默认 uid 的 12 倍，不低于 60），
    既能挡住换 cookie 的脚本，也不牵连共享出口的正常用户。
    """
    if ip_limit is None:
        ip_limit = max(limit * 20, 60)
    try:
        uid = _current_uid()
    except Exception:
        uid = ''
    # 无 cookie 时 _current_uid 会退回 request.remote_addr —— 经 nginx 反代后这个值
    # 永远是 127.0.0.1，所有匿名请求会挤进同一个桶、凑够 limit 次后全部被拒。
    # 这里换成真实出口 IP 建桶，让无 cookie 的请求按各自 IP 分开计。
    if uid in ('', 'anon', '127.0.0.1', '::1', 'localhost'):
        uid = 'ip:' + _client_ip()
    if uid and _rate_hit(name + ':u', uid, limit, window):
        return True
    ip = _client_ip()
    if ip and _rate_hit(name + ':i', ip, ip_limit, window):
        return True
    return False


# 后台/管理接口鉴权：配置 ADMIN_TOKEN 后，需在请求头带 X-Admin-Token 才能访问。
# 未配置时【默认拒绝】（fail-closed）——不再「未配置即开放」，杜绝后台裸奔（194 轮 C1）。
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()


# 管理会话（194/195 轮）：登录成功写 HttpOnly 签名 cookie，8 小时有效；连续 5 次失败锁 15 分钟。
_ADMIN_COOKIE_NAME = 'admin_session'
_ADMIN_SESSION_SIGNER = URLSafeSerializer(_load_uid_secret(), salt='admin-session')


def _admin_session_valid():
    raw = (request.cookies.get(_ADMIN_COOKIE_NAME) or '').strip()
    if not raw:
        return False
    try:
        val = _ADMIN_SESSION_SIGNER.loads(raw)
        if isinstance(val, dict) and float(val.get('exp', 0)) > time.time():
            return True
    except Exception:
        pass
    return False


def _admin_session_role():
    """当前登录会话角色：'admin' / 'readonly'；无效或未登录返回 None。"""
    raw = (request.cookies.get(_ADMIN_COOKIE_NAME) or '').strip()
    if not raw:
        return None
    try:
        val = _ADMIN_SESSION_SIGNER.loads(raw)
        if isinstance(val, dict) and float(val.get('exp', 0)) > time.time():
            return val.get('role') or ('readonly' if val.get('demo') else 'admin')
    except Exception:
        pass
    return None


def _require_admin():
    """管理接口鉴权；通过返回 None，拒绝返回带 401 的 Response。

    支持登录会话 cookie，或 X-Admin-Token 请求头（登录页提交后由前端带）。
    已移除 ?token= URL 传参（194 轮 C6：token 走 URL 会留痕于日志/Referer，泄露凭据）。
    口令支持逗号分隔多个值，只认环境变量 ADMIN_TOKEN（去掉旧版硬编码弱口令，避免明文泄密）。
    """
    if _admin_session_valid():
        return None
    if not ADMIN_TOKEN:
        resp = jsonify({"success": False, "error": "后台未配置鉴权口令（ADMIN_TOKEN 未设置），已拒绝访问"})
        resp.status_code = 401
        return resp
    tok = (request.headers.get("X-Admin-Token") or "").strip()
    valid = {t.strip() for t in ADMIN_TOKEN.split(",") if t.strip()}
    if tok in valid:
        return None
    resp = jsonify({"success": False, "error": "无权限，需要登录或 X-Admin-Token"})
    resp.status_code = 401
    return resp


# ============ 初始化数据库 ============
DB_PATH = os.path.abspath(os.getenv("COMPETITION_DB_PATH") or
                          os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", ".data", "competition.db"))


def get_db():
    """统一 SQLite 连接：timeout=5 秒，写锁冲突时等待而非秒抛 database is locked。

    路径在**每次调用时**解析，不闭包捕获模块级 DB_PATH：测试与运维脚本惯用
    `app.DB_PATH = 临时库` 把连接切到隔离库，若这里写死读 infra 的全局变量，
    重绑就静默失效、数据写进真实库（第 1 阶段重构时踩过，已回滚一次）。
    解析顺序：调用方模块上的 DB_PATH → 本模块的 DB_PATH。
    """
    _path = None
    _caller = sys.modules.get('__main__')
    for _name in ('backend.app', 'app'):
        _mod = sys.modules.get(_name)
        if _mod is not None:
            _caller = _mod
            break
    if _caller is not None:
        _path = getattr(_caller, 'DB_PATH', None)
    return sqlite3.connect(_path or DB_PATH, timeout=5)


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
