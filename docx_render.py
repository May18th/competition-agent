"""兼容入口：实际 DOCX 渲染实现位于 :mod:`backend.docx_render`。"""

import importlib
import os
import sys


# 只保证「仓库根」在搜索路径上（`backend` 作为包名要被找到），
# 【不能】把 backend/ 目录本身插进来：那会让裸 `import competition_agents`
# 从磁盘再加载一份，和 `backend.competition_agents` 变成两个对象。
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

sys.modules[__name__] = importlib.import_module("backend.docx_render")
