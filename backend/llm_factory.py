# -*- coding: utf-8 -*-
"""统一模型入口。

生成链路固定使用原有 DeepSeek，不接入外部 Agent 平台或可变的兼容端点。
模型名仍可通过 ``DEEPSEEK_MODEL`` 调整，便于服务器切换同一提供方的正式模型。
"""
import os

from langchain_deepseek import ChatDeepSeek


def _thinking_kwargs():
    """2026-10-14：deepseek-flash 默认「思考模式」，实测 100 输出 token 里 74 个是
    reasoning（按输出价计费），正文只剩 26 个 —— 钱烧在思考上、正文被截断。
    申报书生成是长文创作，不需要推理链，默认关闭；需要时设 DEEPSEEK_THINKING=enabled。
    """
    if (os.getenv("DEEPSEEK_THINKING") or "disabled").strip().lower() != "enabled":
        return {"thinking": {"type": "disabled"}}
    return {}


def build_chat_model(*, temperature=0.4, max_tokens=4096, request_timeout=120,
                     max_retries=2, frequency_penalty=None, presence_penalty=None):
    kwargs = {
        # 2026-10-14 统一到 deepseek-flash（官方在售两款中最便宜的一档）：
        # 输出 4 元/百万 vs pro 13.5；输入未命中 1 元 vs pro 4.5；缓存命中 0.02 vs 0.15。
        # deepseek-chat 已是旧名（官方定价页不再列出），仍可用 DEEPSEEK_MODEL 覆盖。
        "model": os.getenv("DEEPSEEK_MODEL") or "deepseek-flash",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "request_timeout": request_timeout,
        "max_retries": max_retries,
        # thinking 必须走 extra_body（进 request body）；model_kwargs 会被当成
        # SDK 顶层参数传给 Completions.create()，实测报 unexpected keyword 'thinking'。
        "extra_body": _thinking_kwargs(),
    }
    if frequency_penalty is not None:
        kwargs["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        kwargs["presence_penalty"] = presence_penalty
    return ChatDeepSeek(**kwargs)

