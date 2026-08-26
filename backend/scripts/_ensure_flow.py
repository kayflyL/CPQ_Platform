# -*- coding: utf-8 -*-
import json, os, sys
ROOT = r"D:\CPQ_Platform_V1\backend"
sys.path.insert(0, ROOT)
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
repo = ReasoningFlowRepository()
try:
    flow = repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
    g = flow.get("graph") or {}
    print("nodes:", [n.get("id") for n in g.get("nodes") or []])
    cfg = flow.get("node_configs") or {}
    print("cfg keys:", sorted(cfg.keys()))
    print("model_choice tools:", cfg.get("model_choice", {}).get("enabled_tools"))
finally:
    repo.close()
