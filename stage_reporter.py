"""阶段上报独立模块（app.py 与 competition_agents.py 共享，避免循环导入）。

app.py 与 competition_agents.py 互相 import 会循环导入，所以把「任务状态」和「阶段上报」
下沉到这个零依赖模块，两边都只依赖本模块：

- app.py：创建任务条目、标记当前任务 id、读取 tasks 返回给前端；
- competition_agents.py：每个 Agent 节点调用 report_stage(stage) 上报阶段。
"""
import time

# 所有异步任务的状态字典（key=task_id，value 结构见 app.py 的 generate_async）
tasks = {}

# 当前正在执行的任务 id（app.py 的 worker 线程内设置）
_current_task_id = None


def set_current_task(task_id):
    """标记当前正在执行的任务（app.py 的 worker 线程调用）。"""
    global _current_task_id
    _current_task_id = task_id


def clear_current_task():
    """清除当前任务标记（worker 线程结束时调用）。"""
    global _current_task_id
    _current_task_id = None


def report_stage(stage):
    """上报当前阶段（competition_agents.py 的 Agent 节点调用）。"""
    tid = _current_task_id
    t = tasks.get(tid) if tid else None
    if isinstance(t, dict):
        t["stage"] = stage
        t["updated_at"] = time.time()
