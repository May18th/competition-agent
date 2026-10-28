"""兼容入口：实际多智能体编排位于 :mod:`backend.competition_agents`。"""

import importlib
import os
import sys


_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

sys.modules[__name__] = importlib.import_module("backend.competition_agents")
