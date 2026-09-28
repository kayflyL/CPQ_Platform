# -*- coding: utf-8 -*-
"""机型锁定工具（choose_model）：从系统候选池锁定一个机型，池外拒绝。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

from app.services.skill_memory import _slots_view
from app.services.skill_tool_context import TOOL_CTX


def tool_select_model(args: dict) -> dict:
    """【需求分析流程工具】机型选配节点的大脑回合：从引擎候选池锁定一个机型（接地）。

    候选池由引擎确定性构建（登记表信号 × 在售目录，engine_ctx.baselines_pool 经
    TOOL_CTX 下发），这里只做池内校验 + 落槽：id 精确或名称忽略大小写精确命中，
    池外型号一律拒绝（B2：LLM 只在事实源给定的取值域内决策）。锁定后由引擎重跑
    确定性阶段校验（显式命中候选池）并携带 AI 理由；大脑不调用 → 引擎弹机型选项卡。
    """
    ctx = TOOL_CTX.get()
    if not ctx.get("task_active"):
        return {"ok": False, "error": "task_not_active",
                "hint": "配置任务未开始（机型锁定仅在需求分析流程内可用）"}
    pool = ctx.get("model_pool")
    if not isinstance(pool, list) or not pool:
        return {"ok": False, "error": "empty_pool",
                "hint": "当前没有候选机型池（引擎未给出候选），请向客户澄清需求信号"}
    name = str((args or {}).get("model") or "").strip()
    mid = str((args or {}).get("model_id") or "").strip()
    reason = str((args or {}).get("reason") or "").strip()
    if not name and not mid:
        return {"ok": False, "error": "invalid_args",
                "hint": "model（机型名）或 model_id 至少提供一个，取值必须来自候选池"}
    hit = None
    for c in pool:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("server_model_id") or c.get("id") or "").strip()
        cname = str(c.get("name") or "").strip()
        if (mid and cid and cid == mid) or (name and cname and cname.lower() == name.lower()):
            hit = c
            break
    if hit is None:
        return {"ok": False, "error": "not_in_pool",
                "hint": "所选机型不在候选池内，只能从候选池里选",
                "candidates": [str(c.get("name") or "") for c in pool if isinstance(c, dict)][:8]}
    # 与引擎/工具共享同一 ext 对象（副本会丢落表——同 fill_requirement 的 09-02 实测坑）
    ext = ctx.get("ext")
    if not isinstance(ext, dict):
        ext = {}
        ctx["ext"] = ext
    save = ctx.get("save")
    if callable(save):
        save()
    return {"ok": True,
            "selected": {"model_id": str(hit.get("server_model_id") or hit.get("id") or ""),
                         "name": str(hit.get("name") or "")},
            "reason": reason,
            "message": f"已锁定机型 {hit.get('name')}",
            "current": _slots_view(ext)}
