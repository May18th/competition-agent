# -*- coding: utf-8 -*-
"""多智能体消息编排层。

这里不持有任何业务正文的可变引用。Agent 之间只通过 MessageBus 交换
JSON 可序列化快照，便于重试、回放和后台审计；具体 Agent 仍由
``competition_agents`` 注册，编排层不把检索/写作实现写死在路由里。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import threading
import time
import uuid
from collections import deque


_MAX_EVENTS = 4000
_events = deque(maxlen=_MAX_EVENTS)
_states = {}
_lock = threading.RLock()


@dataclass(frozen=True)
class AgentMessage:
    task_id: str
    message_id: str
    sender: str
    recipient: str
    kind: str
    payload: dict
    round: int
    created_at: str


class MessageBus:
    """进程内消息总线；生产环境可替换为 Redis/队列实现而不改 Agent。"""

    def publish(self, task_id, sender, recipient, kind, payload=None, round_no=0):
        msg = AgentMessage(
            task_id=str(task_id), message_id=uuid.uuid4().hex[:16],
            sender=str(sender), recipient=str(recipient), kind=str(kind),
            payload=deepcopy(payload or {}), round=int(round_no or 0),
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        with _lock:
            _events.append({"event": "message", **asdict(msg)})
        return msg

    def event(self, task_id, agent, status, detail=None, round_no=0, attempt=0):
        item = {
            "event": "state", "task_id": str(task_id), "agent": str(agent),
            "status": str(status), "detail": deepcopy(detail or {}),
            "round": int(round_no or 0), "attempt": int(attempt or 0),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with _lock:
            _events.append(item)
        return item


bus = MessageBus()


def _safe_detail(value, limit=500):
    if isinstance(value, dict):
        return {str(k): _safe_detail(v, limit) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [_safe_detail(v, limit) for v in value[:20]]
    text = str(value or "")
    return text[:limit]


def _state(task_id):
    with _lock:
        return _states.setdefault(str(task_id), {
            "task_id": str(task_id), "status": "created", "round": 0,
            "agents": {}, "updated_at": time.time(),
        })


class AgentOrchestrator:
    """生成任务的轮次调度器。

    ``begin`` 拆解任务并发出检索请求；``before_graph``/``after_graph``
    把现有 LangGraph 当作独立 Agent 集合接入；质量不足时由
    ``request_revision`` 发起第二轮回调。所有状态变化都会进入日志面板。
    """

    def __init__(self, task_id, data):
        self.task_id = str(task_id)
        self.data = deepcopy(data or {})
        self.round = 0
        _state(self.task_id)

    def _set(self, agent, status, detail=None, attempt=0):
        st = _state(self.task_id)
        st["status"] = status
        st["round"] = self.round
        st["updated_at"] = time.time()
        st["agents"].setdefault(agent, {}).update({
            "status": status, "attempt": attempt,
            "round": self.round, "updated_at": st["updated_at"],
        })
        bus.event(self.task_id, agent, status, _safe_detail(detail), self.round, attempt)

    def _send(self, sender, recipient, kind, payload=None):
        return bus.publish(self.task_id, sender, recipient, kind,
                           _safe_detail(payload), self.round)

    def begin(self):
        self.round = 1
        self._set("planner", "running", {"phase": "decompose"})
        plan = self.decompose()
        self._send("planner", "retrieval", "task_plan", {"steps": plan})
        self._set("planner", "done", {"steps": len(plan)})
        self._set("retrieval", "queued", {"reason": "按赛事规则与创意检索证据"})
        self._set("writer", "queued", {"reason": "等待检索包与规则包"})
        self._set("reviewer", "queued", {"reason": "等待首稿"})
        return plan

    def decompose(self):
        mode = "deep" if self.data.get("mode") == "deep" else "fast"
        return [
            {"agent": "retrieval", "action": "读取官方规则与可追溯范文", "round": 1},
            {"agent": "evidence", "action": "整理用户事实并标记待核实字段", "round": 1},
            {"agent": "writer", "action": "依据规则、证据和风格生成首稿", "round": 1},
            {"agent": "reviewer", "action": "按评审门槛检查内容、数据和结构", "round": 1},
            {"agent": "writer", "action": "按反馈只修订薄弱模块", "round": 2 if mode == "deep" else 1},
        ]

    def before_graph(self, competition_name, idea):
        self._set("retrieval", "running", {"query": str(idea or "")[:160]}, 1)
        self._send("retrieval", "rule_parser", "rules_request", {
            "competition_name": competition_name, "query": str(idea or "")[:300],
        })
        self._send("retrieval", "writer", "evidence_request", {
            "competition_name": competition_name, "source_policy": "official_or_user_provided",
        })

    def retrieval_round(self, competition_name, idea):
        """独立 RAG Agent 的一轮检索；结果只以消息快照交给编排器。"""
        try:
            from chroma_retriever import search
            result = search(competition_name, idea, top_k=5)
        except Exception as exc:
            result = {"documents": [], "metadatas": [], "backend": "unavailable", "error": str(exc)}
        docs = result.get("documents") or []
        self.retrieval_result(bool(docs), len(docs))
        self._send("retrieval", "planner", "retrieval_result", {
            "backend": result.get("backend"), "sources": len(docs),
            "previews": [str(x)[:180] for x in docs[:3]],
        })
        return result

    def retrieval_result(self, matched=False, sources=0):
        self._set("retrieval", "done", {"matched": bool(matched), "sources": int(sources or 0)})
        self._send("retrieval", "writer", "evidence_packet", {
            "matched": bool(matched), "sources": int(sources or 0),
            "note": "未提供来源的数据必须标记为待核实",
        })
        self._set("writer", "running", {"input": "rules + evidence_packet"})

    def writer_result(self, chars=0):
        self._set("writer", "done", {"chars": int(chars or 0)})
        self._send("writer", "reviewer", "draft_ready", {"chars": int(chars or 0)})
        self._set("reviewer", "running", {"input": "draft_ready"})

    def review_result(self, score=0, approved=False, issues=None):
        issues = list(issues or [])[:8]
        self._set("reviewer", "done", {"score": score, "approved": bool(approved), "issues": issues})
        return bool(approved), issues

    def request_revision(self, issues):
        self.round += 1
        self._send("reviewer", "writer", "revision_request", {"issues": issues})
        self._set("writer", "running", {"round": self.round, "reason": "reviewer_callback"})

    def finish(self, status="done", detail=None):
        self._set("orchestrator", status, detail or {})

    def fail(self, detail=None):
        """把异常路径中的未闭合 Agent 状态收束为 error。

        生成线程可能在 LangGraph 或模型调用中途抛错，主任务会被记录为失败，
        但编排器此前的 running/queued 状态若不收束，后台日志会误显示为仍在
        执行。这里仅更新状态事件，不触碰正文或任务结果。
        """
        st = _state(self.task_id)
        # 失败收束通常由生成线程新建一个编排器实例触发，沿用已有状态的
        # 轮次，避免异常日志突然回到 round=0，破坏后台回放顺序。
        self.round = int(st.get("round") or self.round or 0)
        for agent, info in list(st.get("agents", {}).items()):
            if info.get("status") in ("running", "queued"):
                info.update({"status": "error", "updated_at": time.time()})
                bus.event(self.task_id, agent, "error", _safe_detail(detail), self.round)
        self.finish("error", detail or {})


def get_events(task_id=None, limit=200):
    with _lock:
        items = list(_events)
    if task_id:
        items = [x for x in items if x.get("task_id") == str(task_id)]
    return items[-max(1, min(int(limit or 200), _MAX_EVENTS)):]


def get_task_states(limit=100):
    with _lock:
        values = list(_states.values())
    return values[-max(1, min(int(limit or 100), 500)):]


def clear_task(task_id):
    with _lock:
        _states.pop(str(task_id), None)
