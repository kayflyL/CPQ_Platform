"""API endpoints for reasoning flow (推理流可视化配置).

P0：直接改 active 流的 node_config（立即生效）；版本切版 API 预留给二期 draft 试错流程。
三层兜底在 run_pipeline（DB 异常回退模块常量），API 层不兜底。
"""
import asyncio
import logging
import uuid
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.assistant_hub import assistant_hub

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reasoning-flow", tags=["reasoning-flow"])

_VALID_NODE_KEYS = {
    # v12 单路能力链（画布 palette 可拖，2026-08-09 补：此前缺这些 key 会导致抽屉保存 400）
    "understand", "gap_analyze", "scene_decide", "model_reason", "kp_reason",
    "spec_compliance", "audit_fix", "llm_confirm", "text_clean", "llm_agent",
    # 旧 palette / 历史节点（保留兼容）
    "extract", "select_baseline", "match_kp", "compose", "review", "condition",
    "ask_user", "clarity_check", "budget_check", "scene_analysis", "cond_scene",
    "normalize_input", "confirm_series", "llm_understand", "slot_validate", "confirm",
    "llm_ask", "llm_audit",
}


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


# ── 流式试运行（2026-08：画布右侧栏「完成一步显示一步」）─────────────────────
# 复用 assistant_hub 房间：POST /test-run/start 只注册 run_id（不立即跑），
# 第一个 WS 订阅者连上 /test-run-ws/{run_id} 后才启动后台任务——保证首个节点 step_start
# 不被 WS 连接竞态漏掉；随后 step_start/step_done/need_input/candidates_ready 实时推送，
# 结束后广播终态（ext/kp_by_model/plans/awaiting_input）。

_pending_runs: dict = {}  # run_id -> {text, budget, force_complete, flow}


async def _stream_test_run(run_id: str, text: str, budget: float, force_complete: bool, flow: dict) -> None:
    async def _broadcast(payload: dict):
        payload.setdefault("run_id", run_id)
        await assistant_hub.broadcast(run_id, payload)

    try:
        # 预置全部将执行步骤为 pending（condition 静默路由、extract 仅 AI 失效才跑 → 不预置，跑到了再懒创建）
        steps = [
            {"key": n.get("id"), "label": n.get("label") or n.get("id")}
            for n in (flow.get("graph") or {}).get("nodes") or []
            if (n.get("type") or "") not in ("condition", "extract")
        ]
        await _broadcast({"type": "pipeline_start", "steps": steps})
        from app.services.reasoning_executor import run_graph_executor
        initial_ctx = {"budget": budget, "force_complete": force_complete}
        ctx = await run_graph_executor("test-run", text, flow, _broadcast, initial_ctx=initial_ctx)
        awaiting = bool(ctx.get("awaiting_input"))
        await _broadcast({
            "type": "pipeline_paused" if awaiting else "pipeline_done",
            "ext": ctx.get("ext") or {},
            "kp_by_model": ctx.get("kp_by_model") or {},
            "plans": ctx.get("plans") or [],
            "awaiting_input": awaiting,
        })
    except Exception as e:
        logger.exception("流式试运行失败 run_id=%s", run_id)
        await _broadcast({"type": "error", "message": f"试运行失败：{e}"})


@router.post("/test-run/start")
async def test_run_start(body: dict):
    """流式试运行：注册 run_id 并后台启动图执行器，事件经 WS /test-run-ws/{run_id} 实时推送。
    返回 {run_id}；与旧 /test-run（一次性返回）并存，画布试运行改用本端点逐步显示。"""
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
    run_id = f"tr_{uuid.uuid4().hex[:12]}"
    _pending_runs[run_id] = {
        "text": text, "budget": budget, "force_complete": force_complete, "flow": flow,
    }
    return {"run_id": run_id}


@router.websocket("/test-run-ws/{run_id}")
async def test_run_ws(ws: WebSocket, run_id: str):
    """订阅某次流式试运行的事件（连接即收，入站消息忽略）。
    首个订阅者连上时启动后台任务，确保从头订阅（不漏首个 step_start）。"""
    await assistant_hub.connect(ws, run_id)
    params = _pending_runs.pop(run_id, None)
    if params:
        asyncio.create_task(_stream_test_run(
            run_id, params["text"], params["budget"], params["force_complete"], params["flow"],
        ))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await assistant_hub.disconnect(ws)
