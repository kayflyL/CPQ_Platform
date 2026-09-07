"""API endpoints for reasoning flow (推理流可视化配置).

P0：直接改 active 流的 node_config（立即生效）；版本切版 API 预留给二期 draft 试错流程。
三层兜底在 run_skill_plan（DB 异常回退模块常量），API 层不兜底。
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.repository.reasoning_flow_repo import ReasoningFlowRepository

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


@router.get("/l6-preview")
def l6_preview(model: str = Query("")):
    """机型选配节点目标层预览：指定机型的 BOM 模板求值 → 基础机箱 L6 配置行（真实求值链路）。

    与方案配置页 L6 部分同源（同一模板求值代码）；机型阶段无配件无信号 = 基础机箱，
    配件选配与选型规则调整后，L6 在 BOM 组装阶段会变化（最终以组装节点为准）。
    模板缺失回退基准配置行并标注来源。"""
    name = (model or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="model 不能为空")
    from app.repository.server_catalog_repo import ServerCatalogRepository
    from app.repository.base_config_repo import BaseConfigRepository
    cat_repo = ServerCatalogRepository()
    try:
        target = next((m for m in cat_repo.list_models() if m.get("name") == name), None)
    finally:
        pass  # ServerCatalogRepository 无需关闭（与 skill_chat 用法一致）
    if not target:
        raise HTTPException(status_code=404, detail=f"机型不存在：{name}")
    base_id = target.get("base_config_id")
    bc_repo = BaseConfigRepository()
    bc = next((c for c in bc_repo.list() if c.get("id") == base_id), None)
    template_id = (bc or {}).get("bom_template_id")
    rows, source = [], "基准配置行"
    if template_id and base_id:
        try:
            from app.services.bom_template_eval import eval_l6_rows
            rows = eval_l6_rows(int(template_id), int(base_id), [], {}) or []
            source = f"BOM 模板求值（模板 {template_id}）· 基础机箱"
        except Exception:
            logger.exception("机箱表模板求值失败 model=%s", name)
            rows = []
    if not rows and base_id:
        from app.repository.bom_case_repo import _l6_rows_from_base_config
        rows = _l6_rows_from_base_config(base_id)
    return {"model": name, "base_config_id": base_id, "template_id": template_id,
            "source": source, "rows": rows}


@router.get("/candidate-resolvers")
def candidate_resolvers():
    """候选池数据源注册表（抽屉资源与权限层"数据源"下拉的数据源）。"""
    from app.services.part_selector import CANDIDATE_RESOLVERS, DEFAULT_RESOLVER
    return {"resolvers": [{"name": name, "description": str(e.get("description") or ""),
                           "is_default": name == DEFAULT_RESOLVER}
                          for name, e in CANDIDATE_RESOLVERS.items()]}


@router.get("/_debug/asyncio-tasks")
async def debug_asyncio_tasks():
    """临时诊断（挂死排查）：转储主事件循环上所有未完成任务的协程挂起点。稳定后删。"""
    import asyncio
    import traceback
    out = []
    for task in asyncio.all_tasks():
        if task.done():
            continue
        try:
            stack = task.get_stack()
            frames = "".join(traceback.format_list(stack))[-1600:] if stack else ""
        except Exception:
            frames = "<stack unavailable>"
        fut = getattr(task, "_fut_waiter", None)
        out.append({"task": repr(task)[:120],
                    "fut_waiter": type(fut).__name__ if fut is not None else "",
                    "frames": frames})
    return {"count": len(out), "tasks": out}


@router.get("/kp-preview")
def kp_preview(limit_per_category: int = Query(2)):
    """配件选配节点目标层预览：KP 配件库真实料号样例行（按类目轮询取样）。

    行形状 = 登记占位行（category/name/request_spec/qty/specs），前端按目标层列契约
    （from/fallback）即时整形——改契约列，预览表头/取值即时跟随，所见即所出。
    """
    from app.services.part_selector import list_kp_categories
    from app.repository.kp_repo import KPRepository
    try:
        per = max(1, min(5, int(limit_per_category or 2)))
    except (TypeError, ValueError):
        per = 2
    repo = KPRepository()
    rows: list = []
    try:
        for cat in list_kp_categories():
            db_cat = str(cat.get("db_category") or "")
            if not db_cat:
                continue
            try:
                parts = repo.get_by_category_with_specs(db_cat) or []
            except Exception:
                continue
            for p in parts[:per]:
                specs = p.get("specs")
                rows.append({
                    "category": db_cat,
                    "name": str(p.get("model") or ""),
                    "request_spec": "",
                    "qty": 1,
                    "specs": specs if isinstance(specs, dict) else {},
                })
    finally:
        repo.close()
    return {"source": "KP 配件库样例（真实料号，非运行数据）", "rows": rows}


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
