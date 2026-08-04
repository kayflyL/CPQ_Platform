"""API endpoints for reasoning flow (推理流可视化配置).

P0：直接改 active 流的 node_config（立即生效）；版本切版 API 预留给二期 draft 试错流程。
三层兜底在 run_pipeline（DB 异常回退模块常量），API 层不兜底。
"""
import logging
from fastapi import APIRouter, HTTPException
from app.repository.reasoning_flow_repo import ReasoningFlowRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reasoning-flow", tags=["reasoning-flow"])

_VALID_NODE_KEYS = {"extract", "select_baseline", "match_kp", "compose", "review", "condition", "ask_user", "clarity_check", "budget_check", "scene_analysis", "cond_scene", "normalize_input", "confirm_series", "llm_understand", "slot_validate", "confirm", "llm_ask", "llm_audit"}


def _is_valid_node_key(key: str) -> bool:
    """节点 key 校验：固定 key（extract/scene_analysis/…）或画布 palette 新增节点的后缀 id
    （addNode 生成 extract_1 / scene_analysis_2，executor 按节点 id 读 config）。
    只认合法 base 类型，防止任意 key 写入。"""
    if key in _VALID_NODE_KEYS:
        return True
    base = key.rsplit("_", 1)[0]
    return base in _VALID_NODE_KEYS


@router.get("/")
def get_active():
    """取 active 流（含 graph + node_configs 按 node_key 索引）。无 active 返回 {flow: null}。"""
    repo = ReasoningFlowRepository()
    try:
        return {"flow": repo.get_active_flow()}
    finally:
        repo.close()


# 带 LLM 开关的节点类型（enable_llm 开关在这些节点上生效）
LLM_NODE_TYPES = {"llm_understand", "llm_audit", "llm"}


@router.get("/llm-nodes")
def list_llm_nodes():
    """列出 active 流中所有带 LLM 开关的节点（llm_understand/llm_audit/llm）及当前开关状态。

    供需求分析页「LLM 节点」按钮：一次看清哪些节点挂了 LLM、各自开关状态。
    """
    repo = ReasoningFlowRepository()
    try:
        f = repo.get_active_flow()
        if not f:
            return {"nodes": []}
        cfg_map = f.get("node_configs") or {}
        out = []
        for n in (f.get("graph") or {}).get("nodes") or []:
            ntype = n.get("type") or n.get("id")
            if ntype in LLM_NODE_TYPES:
                cfg = cfg_map.get(n.get("id")) or {}
                out.append({
                    "id": n.get("id"),
                    "type": ntype,
                    "label": n.get("label") or n.get("id"),
                    "enable_llm": bool(cfg.get("enable_llm")),
                })
        return {"nodes": out}
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
    if not _is_valid_node_key(node_key):
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
    - force_complete 默认 True（跳过反问、一键出方案）；前端可传 False 测反问补全（unclear/partial 会暂停在 ask_user）。
    - 不回退 linear fallback：调试工具，图执行的报错原样暴露给用户看（仅包一层 except 返回 error+events）。
    - 明细全从 ctx 取（step_done 的 payload 是摘要级，明细在 ctx.kp_by_model / ctx.plans）。
    """
    text = (body or {}).get("requirement_text")
    if not text:
        raise HTTPException(400, "Missing requirement_text")
    budget = (body or {}).get("explicit_budget")
    force_complete = bool((body or {}).get("force_complete", True))
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
    initial_ctx = {"budget": budget, "force_complete": force_complete}
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
