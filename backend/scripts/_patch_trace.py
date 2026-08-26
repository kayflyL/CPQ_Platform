# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "capability_executor.py")
text = io.open(path, encoding="utf-8").read()

# 1) 加 trace_kind 映射 helper，改签名
old_sig = "def _trace_preview(node_type: str, ctx: dict, payload: Optional[dict] = None):"
new_sig = '''def _trace_kind_for(node_id: Optional[str], node_type: str) -> str:
    """节点 id → 画布回填的 trace_kind（新 AI 链节点用 agent 类型，靠 id 区分产出）。"""
    if node_id:
        _map = {
            "need_analysis": "requirement_slots",
            "model_choice": "model_choice",
            "parts_proposal": "parts_proposal",
            "bom_assemble": "bom_scheme",
        }
        if str(node_id) in _map:
            return _map[str(node_id)]
    return node_type


def _trace_preview(node_type: str, ctx: dict, payload: Optional[dict] = None, node_id: Optional[str] = None):'''
assert old_sig in text, "sig anchor missing"
text = text.replace(old_sig, new_sig, 1)

# 2) 插入 trace_kind 计算 + 新节点分支，放在 input_preview 初始化之后、node_type=="input" 之前
old_start = '''    input_preview: dict[str, Any] = {}
    output_preview: dict[str, Any] = {}
    artifact: Optional[dict] = None
    summary = ""

    if node_type == "input":'''
new_start = '''    input_preview: dict[str, Any] = {}
    output_preview: dict[str, Any] = {}
    artifact: Optional[dict] = None
    summary = ""
    trace_kind = _trace_kind_for(node_id, node_type)

    if trace_kind == "requirement_slots":
        snap = ctx.get("requirement") if isinstance(ctx.get("requirement"), dict) else {}
        input_preview = {"requirement_text": str(ctx.get("requirement_text") or "")[:200]}
        output_preview = {"requirement": snap, "summary": str(ctx.get("normalized_text") or "")[:200]}
        artifact = {"kind": "requirement_slots", "title": "线索登记表", "data": snap}
        summary = "已理解需求并冻结线索登记表"
    elif trace_kind == "model_choice":
        mc = ctx.get("model_choice") if isinstance(ctx.get("model_choice"), dict) else {}
        cands = mc.get("candidates") or ctx.get("baselines") or ctx.get("candidates") or []
        rec = mc.get("recommended") if isinstance(mc.get("recommended"), dict) else mc.get("recommended")
        output_preview = {
            "candidates": _brief_list(cands, 5),
            "recommended": (rec or {}).get("name") if isinstance(rec, dict) else rec,
            "reason": str(mc.get("reason") or "")[:200],
        }
        artifact = {"kind": "model_choice", "title": "机型决策", "data": output_preview}
        summary = "已从在售目录选出机型"
    elif trace_kind == "parts_proposal":
        pp = ctx.get("parts_proposal") if isinstance(ctx.get("parts_proposal"), dict) else {}
        parts = pp.get("parts") or ctx.get("parts") or []
        by_cat = pp.get("by_category") or {}
        output_preview = {"parts_count": len(parts), "parts": _brief_list(parts, 8), "by_category": by_cat}
        artifact = {"kind": "parts_proposal", "title": "配件决策", "data": output_preview}
        summary = "已规划内存 / 硬盘 / GPU / 网卡等配件"
    elif trace_kind == "bom_scheme":
        plans = ctx.get("plans") or []
        bom = ctx.get("bom_scheme") if isinstance(ctx.get("bom_scheme"), dict) else {}
        cost = ctx.get("bom_cost") if isinstance(ctx.get("bom_cost"), dict) else {}
        output_preview = {
            "plans_count": len(plans),
            "total_cost": cost.get("total_cost"),
            "bom_scheme": bom,
        }
        artifact = {"kind": "bom_scheme", "title": "BOM 方案", "data": bom or {"plans_count": len(plans)}}
        summary = f"已组装 {len(plans)} 个候选方案"
    elif node_type == "input":'''
assert old_start in text, "start anchor missing"
text = text.replace(old_start, new_start, 1)

# 3) 调用点传 node_id
old_c1 = "        input_preview, _, _, _ = _trace_preview(node_type, ctx)"
new_c1 = "        input_preview, _, _, _ = _trace_preview(node_type, ctx, node_id=node_id)"
old_c2 = "        _, output_preview, artifact, summary = _trace_preview(node_type, ctx, payload)"
new_c2 = "        _, output_preview, artifact, summary = _trace_preview(node_type, ctx, payload, node_id=node_id)"
assert old_c1 in text and old_c2 in text
text = text.replace(old_c1, new_c1, 1).replace(old_c2, new_c2, 1)

io.open(path, "w", encoding="utf-8").write(text)
print("capability_executor trace patched OK")
