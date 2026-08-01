"""API endpoints for reasoning flow (推理流可视化配置).

P0：直接改 active 流的 node_config（立即生效）；版本切版 API 预留给二期 draft 试错流程。
三层兜底在 run_pipeline（DB 异常回退模块常量），API 层不兜底。
"""
import logging
from fastapi import APIRouter, HTTPException
from app.repository.reasoning_flow_repo import ReasoningFlowRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reasoning-flow", tags=["reasoning-flow"])

_VALID_NODE_KEYS = {"extract", "select_baseline", "match_kp", "compose", "review", "condition", "llm"}


@router.get("/")
def get_active():
    """取 active 流（含 graph + node_configs 按 node_key 索引）。无 active 返回 {flow: null}。"""
    repo = ReasoningFlowRepository()
    try:
        return {"flow": repo.get_active_flow()}
    finally:
        repo.close()


@router.get("/versions")
def list_versions():
    repo = ReasoningFlowRepository()
    try:
        return {"versions": repo.list_versions()}
    finally:
        repo.close()


@router.put("/graph")
def update_graph(data: dict):
    """改 active 流图结构（一期改坐标/标签；二期拖拽编排接 stencil+dnd）。"""
    graph = data.get("graph")
    if not isinstance(graph, dict):
        raise HTTPException(400, "Missing graph")
    repo = ReasoningFlowRepository()
    try:
        f = repo.get_active_flow()
        if not f:
            raise HTTPException(404, "No active reasoning flow")
        return repo.upsert_graph(f["id"], graph, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/nodes/{node_key}")
def update_node(node_key: str, data: dict):
    """改 active 流某节点 config（立即生效：下次推理即用新参数）。"""
    if node_key not in _VALID_NODE_KEYS:
        raise HTTPException(400, f"Invalid node_key: {node_key}")
    config = data.get("config")
    if not isinstance(config, dict):
        raise HTTPException(400, "Missing config")
    repo = ReasoningFlowRepository()
    try:
        f = repo.get_active_flow()
        if not f:
            raise HTTPException(404, "No active reasoning flow")
        return repo.upsert_node_config(f["id"], node_key, config, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.post("/versions/{flow_id}/activate")
def activate(flow_id: int, data: dict = None):
    repo = ReasoningFlowRepository()
    try:
        f = repo.activate(flow_id, operator=(data or {}).get("operator", "system"))
        if not f:
            raise HTTPException(404, f"Flow {flow_id} not found")
        return f
    finally:
        repo.close()


@router.post("/test-run")
async def test_run(body: dict):
    """试运行 playground：输入需求文本（+可选预算），同步跑 active flow 图执行器，
    返回每步事件 + ext/kp_by_model/plans 明细。供策略中心画布编辑器交互测试。

    - 不绑商机（opportunity_id 传占位 "test-run"——run_graph_executor 内部从不引用它）。
    - force_complete=True 让 clarity_check 直接走选型、跳过反问，一步出结果。
    - 不回退 linear fallback：调试工具，图执行的报错原样暴露给用户看（仅包一层 except 返回 error+events）。
    - 明细全从 ctx 取（step_done 的 payload 是摘要级，明细在 ctx.kp_by_model / ctx.plans）。
    """
    text = (body or {}).get("requirement_text")
    if not text:
        raise HTTPException(400, "Missing requirement_text")
    budget = (body or {}).get("explicit_budget")
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow()
    finally:
        repo.close()
    if not flow:
        raise HTTPException(400, "无 active 推理流，请先在画布配置节点")

    events: list = []

    async def _collect(payload: dict):
        events.append(payload)

    from app.services.reasoning_executor import run_graph_executor
    initial_ctx = {"budget": budget, "force_complete": True}
    try:
        ctx = await run_graph_executor(
            "test-run", text, flow, _collect, initial_ctx=initial_ctx
        )
    except Exception as e:
        logger.exception("test-run 图执行失败")
        return {"error": str(e), "events": events}

    return {
        "events": events,
        "ext": ctx.get("ext") or {},
        "kp_by_model": ctx.get("kp_by_model") or {},
        "plans": ctx.get("plans") or [],
        "awaiting_input": bool(ctx.get("awaiting_input")),
    }
