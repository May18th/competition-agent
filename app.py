"""兼容入口：实际 Flask 应用位于 :mod:`backend.app`。"""

import importlib
import os
import sys


_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

sys.modules[__name__] = importlib.import_module("backend.app")
