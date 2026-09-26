# -*- coding: utf-8 -*-
"""应用运行日志：内存环形缓冲，供 /api/logs 随时查看最近的错误/告警。"""
import time
from collections import deque

_MAX = 300
_logs = deque(maxlen=_MAX)


def log(level, source, message):
    _logs.append({
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": str(level).upper(),
        "source": str(source or "app"),
        "message": str(message)[:300],
    })


def info(source, message):
    log("INFO", source, message)


def warn(source, message):
    log("WARN", source, message)


def error(source, message):
    log("ERROR", source, message)


def get_logs(level=None, limit=100):
    items = list(_logs)
    if level:
        items = [x for x in items if x["level"] == str(level).upper()]
    return items[-int(limit):]


def error_count(last_seconds=None):
    items = list(_logs)
    errors = [x for x in items if x["level"] == "ERROR"]
    if last_seconds is None:
        return len(errors)
    now = time.time()
    return sum(1 for x in errors if (now - x["ts"]) <= last_seconds)


# ---- 踩坑库：每条含标题、类别、关键词（用于自动匹配报错）、一句话结论 ----
LESSONS = [
    {"title": "app.py 启动块位置", "category": "后端",
     "keywords": ["启动块", "app.run", "404", "路由不注册", "__main__"],
     "summary": "别在 app.py 中间写 if __name__=='__main__'，否则后面路由 404；本地用 run.py、云端用 gunicorn wsgi:app"},
    {"title": "并行节点丢数据", "category": "后端",
     "keywords": ["并行", "丢数据", "字段丢失", "覆盖", "merge"],
     "summary": "并行节点必须返回增量（return {key: value}），不能返回整份 state"},
    {"title": "模块顶层缺 import", "category": "后端",
     "keywords": ["NameError", "not defined", "re.search", "import"],
     "summary": "用到标准库先确认顶层已 import；否则函数内 import"},
    {"title": "matplotlib 3.10 兼容", "category": "图表",
     "keywords": ["clip_path", "set_clip_path", "ax.pie", "expected 3", "matplotlib"],
     "summary": "clip_path 用 RGBA 蒙版；ax.pie 在 autopct=None 时只返回 2 元组"},
    {"title": "字形缺失", "category": "图表",
     "keywords": ["Glyph", "missing", "方框", "字形", "字体"],
     "summary": "别用冷门 Unicode 符号（✦），换安全字符"},
    {"title": "深度分析没传给 writer", "category": "后端",
     "keywords": ["分析", "writer", "竞品", "商业模式", "零贡献", "融入"],
     "summary": "分析结果要显式拼进 writer 的 prompt，不能只写「请融入」"},
    {"title": "重输出全文拖慢", "category": "后端",
     "keywords": ["全文", "重输出", "太慢", "190s", "token", "超时"],
     "summary": "自检/摘要只输出补丁清单或一句话，别重输出整篇"},
    {"title": "DeepSeek 限流", "category": "后端",
     "keywords": ["限流", "429", "rate", "并发", "排队", "quota"],
     "summary": "加信号量限峰值并发；任务级加锁串行化"},
    {"title": "知识库文件名匹配", "category": "知识库",
     "keywords": ["知识库", "读不到", "文件名", "txt", "匹配", "下拉"],
     "summary": "文件名必须是下拉选项的连续子串，且 EXPECTED_COMPETITIONS 与下拉对齐"},
    {"title": "范文质量门", "category": "记忆库",
     "keywords": ["范文", "质量", "评分", "材料", "score"],
     "summary": "LLM 质量分 ≥75 才归范文，否则归材料；生成只注入范文"},
    {"title": "去重用哈希", "category": "记忆库",
     "keywords": ["去重", "重复", "哈希", "hash", "content_hash"],
     "summary": "归一化后算 MD5 查重，别用整串相等"},
    {"title": "innerHTML 未转义", "category": "前端",
     "keywords": ["innerHTML", "XSS", "转义", "_esc", "破版"],
     "summary": "动态文本走 textContent 或 _esc() 转义"},
    {"title": "空值保护缺失", "category": "前端",
     "keywords": ["forEach", "null", "undefined", "空值", "缺失", "Cannot read"],
     "summary": "渲染前判空，字段缺失就隐藏面板不影响其它"},
    {"title": "死代码引用缺失 id", "category": "前端",
     "keywords": ["getElementById", "id", "不存在", "null", "style"],
     "summary": "写完核对 JS 引用 id vs HTML 定义 id，别留死代码"},
    {"title": "进程抢 8080", "category": "部署",
     "keywords": ["8080", "端口", "监听", "进程", "时好时坏"],
     "summary": "启动前确认 8080 只有一个监听进程，杀干净再重启"},
    {"title": "本地与公网不同步", "category": "部署",
     "keywords": ["公网", "本地", "超时", "404", "health", "ECS"],
     "summary": "改完分别验本地和公网；ECS 要 git pull + restart"},
    {"title": "欠费 ECS 停机", "category": "部署",
     "keywords": ["欠费", "停机", "ECS", "超时", "实例"],
     "summary": "HTTP 超时先查阿里云实例状态，欠费要先充值启动"},
    {"title": "BOM 问题", "category": "协作",
     "keywords": ["BOM", "ufeff", "编码", "gbk", "utf-8"],
     "summary": "一律 UTF-8 无 BOM；发现 BOM 剥掉前 3 字节"},
    {"title": "文件互相覆盖", "category": "协作",
     "keywords": ["覆盖", "旧副本", "同步", "Copy-Item", "diff"],
     "summary": "收到「我这边没有 X」先 diff；改完拷回对方目录并通知"},
]


def match_lessons(text, limit=3):
    """按关键词把一段报错/日志匹配到踩坑库，返回命中的坑。"""
    t = (text or "").lower()
    hits = []
    for l in LESSONS:
        if any(k.lower() in t for k in l["keywords"]):
            hits.append(l)
    return hits[:limit]
