# -*- coding: utf-8 -*-
"""失败模式库：从 gen_failures 归纳错误类型、频次、建议修复，喂给动态监视/自动改。"""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "competition.db")

FIX_SUGGESTIONS = {
    "rate_limit": "请求太频繁，触发 DeepSeek 限流/并发闸；加退避重试或降低并发",
    "timeout": "LLM 超时，检查网络，或调大 request_timeout / 精简 prompt 长度",
    "insufficient_balance": "DeepSeek 账户余额不足，需要充值",
    "quota_exceeded": "当日调用额度用完，明天再试或调大 QUOTA_DAILY_LIMIT",
    "auth_error": "API Key 无效或过期，检查 DEEPSEEK_API_KEY",
    "internal_error": "通用内部错误，看 detail 里的堆栈定位具体模块",
}


def classify_error(error="", detail=""):
    """把错误文本归类成稳定错误码（与 app._error_code 同口径）。"""
    t = ("%s %s" % (error or "", detail or "")).lower()
    if "429" in t or "rate" in t or "too many" in t:
        return "rate_limit"
    if "timeout" in t or "timed out" in t:
        return "timeout"
    if "insufficient balance" in t or "余额不足" in t or "payment required" in t or "402" in t:
        return "insufficient_balance"
    if "quota" in t or "配额" in t or "上限" in t:
        return "quota_exceeded"
    if "401" in t or "auth" in t or "api key" in t:
        return "auth_error"
    return "internal_error"


def get_failure_patterns(limit=20):
    """聚合 gen_failures 成失败模式列表（按出现次数降序）。"""
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT error, detail, error_code, created_time FROM gen_failures "
            "ORDER BY id DESC LIMIT 500").fetchall()
        conn.close()
    except Exception:
        return []
    agg = {}
    for r in rows:
        code = (r["error_code"] or "") or classify_error(r["error"], r["detail"])
        d = agg.setdefault(code, {
            "code": code, "count": 0, "last_seen": "", "sample": "",
            "fix": FIX_SUGGESTIONS.get(code, ""),
        })
        d["count"] += 1
        if not d["last_seen"]:
            d["last_seen"] = r["created_time"] or ""
            d["sample"] = (r["error"] or "")[:140]
    return sorted(agg.values(), key=lambda x: -x["count"])[:limit]
