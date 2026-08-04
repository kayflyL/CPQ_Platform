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
def list_rules(type: str = None, status: str = None, category: str = None):
    repo = CompatibilityRuleRepository()
    try:
        return {"rules": repo.list(type=type, status=status, category=category)}
    finally:
        repo.close()


@router.post("/reset")
def reset_rules():
    """清空并重置为默认规则（规则版本迭代后让用户一键更新到最新 seed）。返回插入条数。"""
    repo = CompatibilityRuleRepository()
    try:
        count = repo.reset_to_defaults()
        return {"reset": True, "count": count}
    finally:
        repo.close()


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
