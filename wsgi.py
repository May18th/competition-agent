"""云端 WSGI 入口（Render / Railway / 云服务器 / Docker 通用）。

本地照旧用 run.py（固定 8080 端口）；云平台的端口由环境变量 PORT 决定，
所以单独开一个入口，避免改动 Codex 负责的 run.py。

为什么必须 workers=1：app.py 的异步任务状态存在内存字典 tasks 里，
多进程会让「提交任务」和「轮询状态」落到不同进程，进度条直接失联。
启动命令参考 Procfile。
"""
import os

# app.py 里有一批相对路径（index.html / uploads / generated / tmp_export），
# 先把工作目录钉到项目根，避免换台机器启动时读不到首页。
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE_DIR)

from app import app  # noqa: E402


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
