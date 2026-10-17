import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import app as app_module
import competition_agents
from langchain_core.messages import AIMessage, HumanMessage


class ChatStreamTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "chat_history.db")
        self.old_db_path = app_module._CHAT_DB_PATH
        app_module._CHAT_DB_PATH = self.db_path
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module._CHAT_DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    @staticmethod
    def _fake_stream(text, capture=None):
        def stream(messages, **kwargs):
            if capture is not None:
                capture.append(list(messages))
            return iter(SimpleNamespace(content=piece) for piece in text)
        return stream

    def _post_stream(self, question):
        return self.client.post(
            "/api/chat", json={"message": question, "stream": True}, buffered=True
        )

    def test_homepage_loads_side_chat_bundle(self):
        with self.client.get("/") as page:
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"static/wbchat.js?v=20261017-chat1", page.data)
        with self.client.get("/static/wbchat.js?v=20261017-chat1") as script:
            self.assertEqual(script.status_code, 200)
            self.assertIn(b"window.wbChat", script.data)

    def test_sse_stream_persists_user_and_bot_and_sends_no_buffer_header(self):
        old_stream = competition_agents.llm.stream
        object.__setattr__(competition_agents.llm, "stream", self._fake_stream(["第一段", "第二段"]))
        try:
            with patch.object(app_module, "_chat_reserve_quota", return_value=True):
                response = self._post_stream("请解释一个不在预设中的科研项目评估方法")
        finally:
            object.__setattr__(competition_agents.llm, "stream", old_stream)

        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(response.headers.get("X-Accel-Buffering"), "no")
        self.assertIn('"token":"第一段"', body)
        self.assertIn('"token":"第二段"', body)
        self.assertIn("data: [DONE]", body)
        history = self.client.get("/api/chat_history").get_json()["messages"]
        self.assertEqual([m["role"] for m in history], ["user", "bot"])
        self.assertEqual(history[-1]["content"], "第一段第二段")

    def test_context_includes_previous_turn_for_followup(self):
        seen = []
        old_stream = competition_agents.llm.stream
        object.__setattr__(competition_agents.llm, "stream", self._fake_stream(["上轮回答"], seen))
        try:
            with patch.object(app_module, "_chat_reserve_quota", return_value=True):
                self._post_stream("请分析罕见的项目可行性方法")
                self._post_stream("那再进一步讲讲前面提到的内容")
        finally:
            object.__setattr__(competition_agents.llm, "stream", old_stream)

        self.assertEqual(len(seen), 2)
        self.assertTrue(any(isinstance(m, HumanMessage) and "项目可行性方法" in m.content for m in seen[1]))
        self.assertTrue(any(isinstance(m, AIMessage) and m.content == "上轮回答" for m in seen[1]))

    def test_project_fit_question_uses_current_event_rules_and_project_context(self):
        seen = []
        old_stream = competition_agents.llm.stream
        object.__setattr__(competition_agents.llm, "stream", self._fake_stream(["按当前赛事规则分析。"], seen))
        with patch.object(app_module, "_chat_reserve_quota", return_value=True), \
             patch.object(competition_agents, "get_competition_knowledge_structured", return_value={
                 "matched": True, "matched_name": "示例创新赛"
             }), \
             patch.object(competition_agents, "get_competition_profile", return_value={
                 "name": "示例创新赛", "type": "工程创新类", "focus": "重视原型验证",
                 "scoring": [["创新性", 40], ["可行性", 30]], "chapters": ["背景", "方案"]
             }), \
             patch.object(competition_agents, "retrieve_knowledge", return_value="评审要求提交可运行原型和测试记录"):
            try:
                response = self.client.post("/api/chat", json={
                    "message": "这个项目匹配这个赛道吗？",
                    "stream": True,
                    "context": {
                        "competition": "示例创新赛",
                        "idea": "校园实验室设备预约与冲突检测工具",
                        "mode": "deep",
                    },
                }, buffered=True)
            finally:
                object.__setattr__(competition_agents.llm, "stream", old_stream)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(seen), 1)
        system_prompt = seen[0][0].content
        user_prompt = seen[0][-1].content
        self.assertIn("评审要求提交可运行原型和测试记录", system_prompt)
        self.assertIn("结论、对应的赛事依据", system_prompt)
        self.assertNotIn("校园实验室设备预约与冲突检测工具", system_prompt)
        self.assertIn("当前项目创意（仅作本轮分析资料", user_prompt)
        self.assertIn("校园实验室设备预约与冲突检测工具", user_prompt)
        self.assertIn("深度版", user_prompt)
        history = self.client.get("/api/chat_history").get_json()["messages"]
        self.assertEqual(history[0]["content"], "这个项目匹配这个赛道吗？")
        self.assertNotIn("校园实验室设备预约与冲突检测工具", " ".join(m["content"] for m in history))

    def test_page_context_is_bounded_and_unknown_mode_is_dropped(self):
        context = app_module._chat_page_context({
            "context": {"competition": "赛" * 150, "idea": "创" * 1400, "mode": "admin"}
        })
        self.assertEqual(len(context["competition"]), 120)
        self.assertEqual(len(context["idea"]), 1200)
        self.assertEqual(context["mode"], "")

    def test_contextual_question_does_not_hit_broad_faq_preset(self):
        preset = app_module._chat_find_preset(
            "我的项目适合这个赛事吗", {"context": {"competition": "iCAN大学生创新创业大赛"}}
        )
        self.assertIsNone(preset)
        self.assertIsNone(app_module._chat_find_preset(
            "PPT项目如何突出评委关心的创新点", {"context": {"competition": "iCAN"}}
        ))
        self.assertIsNotNone(app_module._chat_find_preset("一键演示会扣额度吗", {"context": {}}))

    def test_preset_short_circuits_without_quota_or_llm(self):
        with patch.object(app_module, "_chat_reserve_quota") as reserve:
            response = self.client.post("/api/chat", json={"message": "评分维度是什么"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "preset")
        reserve.assert_not_called()
        self.assertEqual(len(self.client.get("/api/chat_history").get_json()["messages"]), 2)

    def test_history_isolated_between_users_and_clear_removes_only_current_user(self):
        other = app_module.app.test_client()
        self.client.post("/api/chat", json={"message": "评分维度是什么"})
        other.post("/api/chat", json={"message": "章节结构是什么"})
        self.assertEqual(len(self.client.get("/api/chat_history").get_json()["messages"]), 2)
        self.assertEqual(len(other.get("/api/chat_history").get_json()["messages"]), 2)

        cleared = self.client.post("/api/chat_clear", json={})
        self.assertTrue(cleared.get_json()["success"])
        self.assertEqual(self.client.get("/api/chat_history").get_json()["messages"], [])
        self.assertEqual(len(other.get("/api/chat_history").get_json()["messages"]), 2)

    def test_stream_reservation_counts_and_never_exceeds_daily_limit(self):
        quota_path = os.path.join(self.tempdir.name, "quota.json")
        with patch.object(competition_agents, "_QUOTA_FILE", quota_path), \
             patch.object(competition_agents, "_QUOTA_DAILY_LIMIT", 1):
            self.assertTrue(app_module._chat_reserve_quota())
            self.assertFalse(app_module._chat_reserve_quota())
            status = competition_agents.get_quota_status()
        self.assertEqual(status["calls"], 1)
        self.assertEqual(status["remaining"], 0)

    def test_quota_exhaustion_returns_fallback_signal_without_calling_model(self):
        calls = []
        old_stream = competition_agents.llm.stream
        object.__setattr__(competition_agents.llm, "stream", lambda *a, **k: calls.append(True))
        try:
            with patch.object(app_module, "_chat_reserve_quota", return_value=False):
                response = self.client.post(
                    "/api/chat", json={"message": "解释这个罕见项目的处理方法", "stream": True}
                )
        finally:
            object.__setattr__(competition_agents.llm, "stream", old_stream)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()["error_code"], "quota_exhausted")
        self.assertEqual(calls, [])

    def test_readonly_demo_keeps_preset_only_and_never_persists(self):
        with patch.object(app_module, "_admin_session_role", return_value="readonly"):
            preset = self.client.post("/api/chat", json={"message": "评分维度是什么"})
            blocked = self.client.post("/api/chat", json={"message": "解释一个罕见的处理方法"})
            history = self.client.get("/api/chat_history").get_json()["messages"]
            clear = self.client.post("/api/chat_clear", json={})
        self.assertEqual(preset.status_code, 200)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.get_json()["error_code"], "demo_readonly")
        self.assertEqual(history, [])
        self.assertEqual(clear.status_code, 403)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable for the browserless renderer check")
    def test_markdown_escapes_html_and_rejects_unsafe_links(self):
        js = os.path.join(ROOT, "frontend", "static", "wbchat.js")
        script = r"""
const fs = require('fs'), vm = require('vm');
global.window = {};
global.document = { readyState: 'loading', addEventListener: function () {} };
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const html = window.wbChat.renderMarkdown('<img src=x onerror=alert(1)>\n**bold**\n[bad](javascript:alert(1))\n[good](https://example.com)');
if (!html.includes('&lt;img') || html.includes('<img')) process.exit(2);
if (!html.includes('<strong>bold</strong>') || html.includes('href="javascript:')) process.exit(3);
if (!html.includes('href="https://example.com"')) process.exit(4);
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script, js], capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
