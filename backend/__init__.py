"""后端源码包。

【不要在这里往 sys.path 插 backend/ 目录】
曾经这行 `sys.path.insert(0, BACKEND_DIR)` 让包内裸导入（`import competition_agents`）
能直接命中磁盘文件，于是同一个 .py 被加载成两个模块对象：
`backend.competition_agents` 与 `competition_agents` 各有一把 _quota_lock、
一个 _LLM_GATE（并发上限翻倍）、一份 _llm_fail_count（失败降级失效）、
各自累计 token 用量。包内导入一律写 `backend.xxx`，外部入口走仓库根的 shim。

项目根目录仍是运行工作目录（相对路径靠调用方 chdir），此处不做路径改写。
"""
