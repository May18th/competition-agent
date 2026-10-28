"""后端源码包。

保留项目根目录作为运行工作目录，兼容现有相对路径与部署入口。
"""

import os
import sys


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
