"""启动脚本（本地开发入口）

⚠️ 必须从 backend/ 目录内启动（或让本脚本的 chdir 兜底）：
competition.db / uploads / generated / tmp_export 都按「当前工作目录」定位，
2026-09-30 前后端分离重构后，这些运行时文件全部归属 backend/。
"""
import os
import sys

# Windows 默认 GBK 无法编码启动日志中的中文/符号；统一用 UTF-8 输出，
# 避免服务尚未启动就因一条日志触发 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 无论从哪里敲 python run.py，都把工作目录钉到 backend/，
# 保证 CWD 相对路径（db/uploads/generated/tmp_export/.env）落在正确位置。
_BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE)
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from app import app  # noqa: E402  (chdir 必须先于 import app)

if __name__ == '__main__':
    print("=" * 60)
    print("科创赛事多智能体协同创作助手 - Web 版")
    print("前端: ../frontend/index.html + static/")
    print("浏览器打开: http://127.0.0.1:8080")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
