"""API endpoints for compatibility rules (兼容性规则引擎).

type: require(必配) / exclude(互斥) / derive(派生) / filter(过滤) / recommend(推荐)
status: draft / testing / active / archived（只有 active 被执行器引用）
body: {when:{all/any:[{field,op,value}]}, then:{action,...}, desc}
"""
from fastapi import APIRouter, HTTPException
from app.repository.compatibility_rule_repo import CompatibilityRuleRepository

router = APIRouter(prefix="/api/compatibility-rules", tags=["compatibility-rules"])

_VALID_STATUS = {"draft", "testing", "active", "archived"}
_VALID_TYPE = {"require", "exclude", "derive", "filter", "recommend"}


@router.get("/")
def list_rules(type: str = None, status: str = None, category: str = None,
               domain: str = "selection"):
    """domain=selection 选型配置页（默认，兼容旧客户端）；domain=requirement 需求分析规则页。"""
    repo = CompatibilityRuleRepository()
    try:
        return {"rules": repo.list(type=type, status=status, category=category, domain=domain)}
    finally:
        repo.close()


# ── 需求知识注入绑定（编辑入口=推理流画布·节点抽屉·规则层） ────────────────────

@router.get("/knowledge/bindings")
def get_knowledge_bindings():
    """规则层绑定面板：全量绑定 + 组清单（每组规则明细 id/name/status + 活跃计数 + 用法行）。
    archived 规则一并返回供灰显（仅 active 可注入）。"""
    from app.services.requirement_knowledge import (
        KNOWLEDGE_GROUPS, _GROUP_USAGE, knowledge_bindings)
    repo = CompatibilityRuleRepository()
    try:
        rules = repo.list(domain="requirement")
    finally:
        repo.close()
    by_group: dict = {g: [] for g in KNOWLEDGE_GROUPS}
    for r in rules:
        cat = str((r.get("category") or "")).strip()
        if cat in by_group:
            by_group[cat].append(r)
    return {"bindings": knowledge_bindings(),
            "groups": [{"name": g,
                        "usage": _GROUP_USAGE.get(g, ""),
                        "count": sum(1 for r in by_group[g] if r.get("status") == "active"),
                        "rules": [{"id": r.get("id"), "name": r.get("name"),
                                   "status": r.get("status")} for r in by_group[g]]}
                       for g in KNOWLEDGE_GROUPS]}


@router.put("/knowledge/bindings")
def put_knowledge_bindings(data: dict):
    """写单节点绑定：{node_key, groups, rule_ids}（组绑定 ∪ 单条勾选）；
    两者皆空 = 该节点解绑。其他节点绑定不动。"""
    from app.services.requirement_knowledge import set_node_bindings
    node_key = str(data.get("node_key") or "").strip()
    groups = data.get("groups")
    if not node_key or not isinstance(groups, list):
        raise HTTPException(400, "Missing fields: node_key, groups (list)")
    rule_ids = data.get("rule_ids") or []
    if not isinstance(rule_ids, list):
        raise HTTPException(400, "Invalid field: rule_ids (list)")
    return {"bindings": set_node_bindings(node_key, groups, rule_ids)}


@router.get("/{rule_id}")
def get_rule(rule_id: int):
    repo = CompatibilityRuleRepository()
    try:
        r = repo.get(rule_id)
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.post("/")
def create_rule(data: dict):
    for k in ("type", "name"):
        if not data.get(k):
            raise HTTPException(400, f"Missing field: {k}")
    if data["type"] not in _VALID_TYPE:
        raise HTTPException(400, f"Invalid type, must be one of {sorted(_VALID_TYPE)}")
    repo = CompatibilityRuleRepository()
    try:
        return repo.create(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: dict):
    repo = CompatibilityRuleRepository()
    try:
        r = repo.update(rule_id, data, operator=data.get("operator", "system"))
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.post("/{rule_id}/status")
def set_status(rule_id: int, data: dict):
    status = data.get("status")
    if status not in _VALID_STATUS:
        raise HTTPException(400, f"Invalid status, must be one of {sorted(_VALID_STATUS)}")
    repo = CompatibilityRuleRepository()
    try:
        r = repo.set_status(rule_id, status, operator=data.get("operator", "system"))
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    repo = CompatibilityRuleRepository()
    try:
        if not repo.delete(rule_id):
            raise HTTPException(404, f"Rule {rule_id} not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/{rule_id}/hit")
def record_hit(rule_id: int):
    """记录规则命中（越跑越聪明）。执行器每次命中调用。"""
    repo = CompatibilityRuleRepository()
    try:
        r = repo.record_hit(rule_id)
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.get("/{rule_id}/stats")
def rule_stats(rule_id: int):
    repo = CompatibilityRuleRepository()
    try:
        return repo.stats(rule_id)
    finally:
        repo.close()
