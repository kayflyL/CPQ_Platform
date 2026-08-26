"""API endpoints for reasoning flow (推理流可视化配置).

P0：直接改 active 流的 node_config（立即生效）；版本切版 API 预留给二期 draft 试错流程。
三层兜底在 run_pipeline（DB 异常回退模块常量），API 层不兜底。
"""
import asyncio
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.assistant_hub import assistant_hub

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reasoning-flow", tags=["reasoning-flow"])

_VALID_NODE_KEYS = {
    "input",
    # 通用能力节点类型
    "agent", "ask", "rule", "transform", "branch", "assemble", "output", "orchestrator",
    # 需求分析业务链（对齐商机详情页真实步骤）
    "agent_fill", "orchestrator",
    "model_reason", "kp_reason",
    "compose",
    "condition",
}


def _is_valid_node_key(key: str) -> bool:
    """节点 key 校验：当前能力链 key（agent_fill/model_reason/…）或画布 palette 新增节点的后缀 id
    （addNode 生成 extract_1 / scene_analysis_2，executor 按节点 id 读 config）。
    只认合法 base 类型，防止任意 key 写入。"""
    if key in _VALID_NODE_KEYS:
        return True
    base = key.rsplit("_", 1)[0]
    return base in _VALID_NODE_KEYS


def _flow_for_skill(repo: ReasoningFlowRepository, skill_key: Optional[str]) -> Optional[dict]:
    """取指定技能的 active flow；若技能 flow 尚不存在，则按默认图建一份。"""
    return repo.ensure_skill_flow(skill_key or "requirement_analysis")


@router.get("/")
def get_active(skill_key: Optional[str] = Query(default=None)):
    """取 active 流（含 graph + node_configs 按 node_key 索引）。无 active 返回 {flow: null}。"""
    repo = ReasoningFlowRepository()
    try:
        return {"flow": _flow_for_skill(repo, skill_key)}
    finally:
        repo.close()


@router.get("/versions")
def list_versions(skill_key: Optional[str] = Query(default=None)):
    repo = ReasoningFlowRepository()
    try:
        return {"versions": repo.list_versions(skill_key)}
    finally:
        repo.close()


@router.put("/graph")
def update_graph(data: dict, skill_key: Optional[str] = Query(default=None)):
    """改 active 流图结构（一期改坐标/标签；二期拖拽编排接 stencil+dnd）。"""
    graph = data.get("graph")
    if not isinstance(graph, dict):
        raise HTTPException(400, "Missing graph")
    repo = ReasoningFlowRepository()
    try:
        f = _flow_for_skill(repo, skill_key)
        if not f:
            raise HTTPException(404, "No active reasoning flow")
        return repo.upsert_graph(f["id"], graph, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/nodes/{node_key}")
def update_node(node_key: str, data: dict, skill_key: Optional[str] = Query(default=None)):
    """改 active 流某节点 config（立即生效：下次推理即用新参数）。
    data 可同时带 label：仅更新图节点展示名，不进入 config。"""
    if not _is_valid_node_key(node_key):
        raise HTTPException(400, f"Invalid node_key: {node_key}")
    config = data.get("config")
    if not isinstance(config, dict):
        raise HTTPException(400, "Missing config")
    label = data.get("label")
    repo = ReasoningFlowRepository()
    try:
        f = _flow_for_skill(repo, skill_key)
        if not f:
            raise HTTPException(404, "No active reasoning flow")
        if isinstance(label, str) and label.strip():
            if repo.update_node_label(f["id"], node_key, label.strip(), operator=data.get("operator", "system")) is None:
                raise HTTPException(404, f"Node not found in active graph: {node_key}")
        if str(f.get("skill_key") or f.get("name") or "") == "requirement_analysis":
            from app.services import reasoning_node_contract
            config = reasoning_node_contract.override_only(node_key, config)
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
async def test_run(body: dict, skill_key: Optional[str] = Query(default=None)):
    """试运行 playground：输入需求文本（+可选预算），同步跑 active flow 图执行器，
    返回每步事件 + ext/kp_by_model/plans 明细。供策略中心画布编辑器交互测试。

    - 不绑商机（opportunity_id 传占位 "test-run"）。
    - 走 run_fixed_workflow（固定专家流程）：按图确定性执行，仅 agent_fill 信息不足时反问中断。
    - force_complete 默认 True（跳过反问、一键出方案）；前端可传 False 测反问补全。
    - 不回退 linear fallback：调试工具，报错原样暴露给用户看（仅包一层 except 返回 error+events）。
    - 明细全从 ctx 取（step_done 的 payload 是摘要级，明细在 ctx.kp_by_model / ctx.plans）。
    """
    text = (body or {}).get("requirement_text")
    if not text:
        raise HTTPException(400, "Missing requirement_text")
    budget = (body or {}).get("explicit_budget")
    force_complete = bool((body or {}).get("force_complete", True))
    repo = ReasoningFlowRepository()
    try:
        flow = _flow_for_skill(repo, skill_key)
    finally:
        repo.close()
    if not flow:
        raise HTTPException(400, "无 active 推理流，请先在画布配置节点")

    events: list = []

    async def _collect(payload: dict):
        events.append(payload)

    from app.services.capability_executor import run_fixed_workflow
    from app.services.portal_flow_adapter import build_preview_bom_scheme
    initial_ctx = {"budget": budget, "force_complete": force_complete}
    try:
        ctx = await run_fixed_workflow(
            "test-run", text, flow, _collect, initial_ctx=initial_ctx
        )
    except Exception as e:
        logger.exception("test-run orchestrator 执行失败")
        return {"error": str(e), "events": events}

    return {
        "events": events,
        "ext": ctx.get("ext") or {},
        "kp_by_model": ctx.get("kp_by_model") or {},
        "plans": ctx.get("plans") or [],
        "bom_scheme": build_preview_bom_scheme(ctx),
        "awaiting_input": bool(ctx.get("awaiting_input")),
        "timings": ctx.get("timings") or {},
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
        from app.services.capability_executor import run_fixed_workflow
        from app.services.portal_flow_adapter import build_preview_bom_scheme
        initial_ctx = {"budget": budget, "force_complete": force_complete}
        ctx = await run_fixed_workflow("test-run", text, flow, _broadcast, initial_ctx=initial_ctx)
        awaiting = bool(ctx.get("awaiting_input"))
        await _broadcast({
            "type": "pipeline_paused" if awaiting else "pipeline_done",
            "ext": ctx.get("ext") or {},
            "kp_by_model": ctx.get("kp_by_model") or {},
            "plans": ctx.get("plans") or [],
            "bom_scheme": build_preview_bom_scheme(ctx),
            "awaiting_input": awaiting,
        })
    except Exception as e:
        logger.exception("流式试运行失败 run_id=%s", run_id)
        await _broadcast({"type": "error", "message": f"试运行失败：{e}"})


@router.post("/test-run/start")
async def test_run_start(body: dict, skill_key: Optional[str] = Query(default=None)):
    """流式试运行：注册 run_id 并后台启动图执行器，事件经 WS /test-run-ws/{run_id} 实时推送。
    返回 {run_id}；与旧 /test-run（一次性返回）并存，画布试运行改用本端点逐步显示。"""
    text = (body or {}).get("requirement_text")
    if not text:
        raise HTTPException(400, "Missing requirement_text")
    budget = (body or {}).get("explicit_budget")
    force_complete = bool((body or {}).get("force_complete", True))
    repo = ReasoningFlowRepository()
    try:
        flow = _flow_for_skill(repo, skill_key)
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
