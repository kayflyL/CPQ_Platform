"""API endpoints for requirement rules (需求分析规则库)。

type: clarity (明确度判定) / budget (预算映射)（旧 rebuttal/workload 已随目录驱动引导删除）
status: draft / testing / active / archived（只有 active 被 pipeline 引用）
"""
from fastapi import APIRouter, HTTPException
from app.repository.requirement_rule_repo import RequirementRuleRepository

router = APIRouter(prefix="/api/requirement-rules", tags=["requirement-rules"])

_VALID_STATUS = {"draft", "testing", "active", "archived"}
_VALID_TYPE = {"clarity", "budget"}


@router.get("/")
def list_rules(type: str = None, status: str = None):
    repo = RequirementRuleRepository()
    try:
        return {"rules": repo.list(type=type, status=status)}
    finally:
        repo.close()


@router.post("/reset")
def reset_rules():
    """清空并重置为默认规则（规则版本迭代后让用户一键更新到最新 seed）。返回插入条数。"""
    repo = RequirementRuleRepository()
    try:
        count = repo.reset_to_defaults()
        return {"reset": True, "count": count}
    finally:
        repo.close()


@router.get("/{rule_id}")
def get_rule(rule_id: int):
    repo = RequirementRuleRepository()
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
    repo = RequirementRuleRepository()
    try:
        return repo.create(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/{rule_id}")
def update_rule(rule_id: int, data: dict):
    repo = RequirementRuleRepository()
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
    repo = RequirementRuleRepository()
    try:
        r = repo.set_status(rule_id, status, operator=data.get("operator", "system"))
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    repo = RequirementRuleRepository()
    try:
        if not repo.delete(rule_id):
            raise HTTPException(404, f"Rule {rule_id} not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/{rule_id}/hit")
def record_hit(rule_id: int):
    """记录规则命中（越跑越聪明）。pipeline 每次命中调用。"""
    repo = RequirementRuleRepository()
    try:
        r = repo.record_hit(rule_id)
        if not r:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return r
    finally:
        repo.close()


@router.get("/{rule_id}/stats")
def rule_stats(rule_id: int):
    repo = RequirementRuleRepository()
    try:
        return repo.stats(rule_id)
    finally:
        repo.close()


# ===== 样本（反哺 / LLM 语料） =====
@router.get("/{rule_id}/samples")
def list_samples(rule_id: int, enabled: bool = None):
    repo = RequirementRuleRepository()
    try:
        return {"samples": repo.list_samples(rule_id=rule_id, enabled=enabled)}
    finally:
        repo.close()


@router.post("/{rule_id}/samples")
def add_sample(rule_id: int, data: dict):
    data["rule_id"] = rule_id
    repo = RequirementRuleRepository()
    try:
        return repo.add_sample(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/samples/{sample_id}")
def update_sample(sample_id: int, data: dict):
    repo = RequirementRuleRepository()
    try:
        s = repo.update_sample(sample_id, data, operator=data.get("operator", "system"))
        if not s:
            raise HTTPException(404, f"Sample {sample_id} not found")
        return s
    finally:
        repo.close()


@router.delete("/samples/{sample_id}")
def delete_sample(sample_id: int):
    repo = RequirementRuleRepository()
    try:
        if not repo.delete_sample(sample_id):
            raise HTTPException(404, f"Sample {sample_id} not found")
        return {"success": True}
    finally:
        repo.close()
