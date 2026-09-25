"""阶段上报独立模块（app.py 与 competition_agents.py 共享，避免循环导入）。

app.py 与 competition_agents.py 互相 import 会循环导入，所以把「任务状态」和「阶段上报」
下沉到这个零依赖模块，两边都只依赖本模块：

- app.py：创建任务条目、标记当前任务 id、读取 tasks 返回给前端；
- competition_agents.py：每个 Agent 节点调用 report_stage(stage) 上报阶段。
"""

# ---- 阶段元数据表（中文文案 + 完成百分比）----
# 代号与《协作_进度条stage约定.md》第四节**完全一致**，由这个文件统一维护。
# 前端不要自己再写一份中文映射，直接用 /api/status 返回的 stage_label 和 pct。
STAGE_META = {
    "start":          ("正在启动",              2),
    "parsing_rules":  ("解析赛事评分规则",       8),
    "similarity":     ("检索同质化项目",        16),
    "idea_scoring":   ("评估创意与一句话定位",  25),
    "analysis":       ("综合分析赛题与方案",    36),
    "rich_assets":    ("生成图表与 PPT 素材",   46),   # 仅深度版
    "writing":        ("撰写申报书正文",        58),
    "judging":        ("模拟评委打分",          70),
    "expert_review":  ("多专家模拟评审",        74),   # 仅深度版
    "diagnosis":      ("诊断申报书短板",        78),
    "revision":       ("按意见定向改写",        84),   # 仅低分迭代时出现
    "defense":        ("预测答辩问题",          90),
    "ppt":            ("生成 PPT 大纲",         95),
    "speech":         ("撰写路演演讲稿",        98),
    "done":           ("全部完成",             100),
    "error":          ("生成中断",              -1),
}


def stage_meta(stage):
    """取 (中文文案, 百分比)。未登记的代号原样返回，前端自行降级显示。"""
    return STAGE_META.get(stage, (stage, 0))


import time

# 所有异步任务的状态字典（key=task_id，value 结构见 app.py 的 generate_async）
tasks = {}

# 当前正在执行的任务 id（app.py 的 worker 线程内设置）
_current_task_id = None

# 已取消的任务 id 集合（单一真相源，progress.py 转发到这里）
_cancelled = set()


class TaskCancelled(Exception):
    """生成被用户取消，用于中断 langgraph 节点循环。"""


def set_current_task(task_id):
    """标记当前正在执行的任务（app.py 的 worker 线程调用）。"""
    global _current_task_id
    _current_task_id = task_id


def clear_current_task():
    """清除当前任务标记（worker 线程结束时调用）。"""
    global _current_task_id
    _current_task_id = None


def current_task_id():
    """返回当前正在执行的任务 id（供 Agent 内部读取，用于流式缓冲区）。"""
    return _current_task_id


def set_partial(partial):
    """把当前任务的已产出字段写进 tasks['partial']，供 /api/status 流式下发。"""
    tid = _current_task_id
    if tid and tid in tasks:
        tasks[tid]["partial"] = partial
        tasks[tid]["updated_at"] = time.time()


# 演讲稿流式缓冲区（task_id -> 已生成的文本，供前端实时预览）
_speech_stream = {}


def set_speech_stream(task_id, text):
    _speech_stream[task_id] = text


def get_speech_stream(task_id):
    return _speech_stream.get(task_id, "")


def clear_speech_stream(task_id):
    _speech_stream.pop(task_id, None)


def cancel_task(task_id):
    """标记取消：report_stage 会抛 TaskCancelled 中断生成。"""
    _cancelled.add(task_id)
    t = tasks.get(task_id)
    if isinstance(t, dict):
        t["status"] = "cancelled"
        t["updated_at"] = time.time()


def is_cancelled(task_id=None):
    """检查任务是否已取消（不传则查当前任务）。"""
    tid = task_id or _current_task_id
    return bool(tid) and tid in _cancelled


def clear_cancel(task_id):
    """清除取消标记。"""
    _cancelled.discard(task_id)


def report_stage(stage):
    """上报当前阶段（competition_agents.py 的 Agent 节点调用）。"""
    tid = _current_task_id
    if tid and tid in _cancelled:
        raise TaskCancelled()
    t = tasks.get(tid) if tid else None
    if isinstance(t, dict):
        t["stage"] = stage
        t["updated_at"] = time.time()
