"""Vercel Serverless 入口（仅用于让 Vercel 停止误判为 Node/Next.js）。

⚠️ 不建议真的把本项目部署到 Vercel，原因见 部署说明.md：
本项目要写本地文件、要跑数分钟的长任务、异步进度存在内存字典里，
这三点跟 Vercel 的 Serverless 模型天生冲突。
本文件只能保证「构建通过」，运行时大概率仍是 500。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from app import app  # noqa: E402  Vercel Python runtime 会自动识别 WSGI 变量 app
