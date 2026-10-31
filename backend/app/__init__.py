# -*- coding: utf-8 -*-
"""app 包引导：把仓库根目录放进 sys.path，使根级 ai_office 引擎包可导入。

引擎住在仓库根的 ai-office/（2026-11-01 目录拆分，位置即法律——
边界守卫 ai_office/engine_boundary.py 按位置执法）。本引导让任何启动方式
（uvicorn/launcher/脚本）都不需要额外 PYTHONPATH；进程拆分后这里退役。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENGINE = os.path.join(_ROOT, "ai-office")
if _ENGINE not in sys.path:
    sys.path.insert(0, _ENGINE)
