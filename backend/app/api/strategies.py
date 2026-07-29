"""API endpoints for strategy center (策略中心)。

domain: requirement / selection / pricing / market
status: draft / testing / active / archived（只有 active 被业务引用）
"""
from fastapi import APIRouter, HTTPException
from app.repository.strategy_repo import StrategyRepository

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

_VALID_STATUS = {"draft", "testing", "active", "archived"}
_VALID_DOMAIN = {"requirement", "selection", "pricing", "market"}


@router.get("/")
def list_strategies(domain: str = None, status: str = None, type: str = None):
    repo = StrategyRepository()
    try:
        return {"strategies": repo.list(domain=domain, status=status, type=type)}
    finally:
        repo.close()


@router.get("/{strategy_id}")
def get_strategy(strategy_id: int):
    repo = StrategyRepository()
    try:
        s = repo.get(strategy_id)
        if not s:
            raise HTTPException(404, f"Strategy {strategy_id} not found")
        return s
    finally:
        repo.close()


@router.post("/")
def create_strategy(data: dict):
    for k in ("domain", "type", "name"):
        if not data.get(k):
            raise HTTPException(400, f"Missing field: {k}")
    if data["domain"] not in _VALID_DOMAIN:
        raise HTTPException(400, f"Invalid domain, must be one of {sorted(_VALID_DOMAIN)}")
    repo = StrategyRepository()
    try:
        return repo.create(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/{strategy_id}")
def update_strategy(strategy_id: int, data: dict):
    repo = StrategyRepository()
    try:
        s = repo.update(strategy_id, data, operator=data.get("operator", "system"))
        if not s:
            raise HTTPException(404, f"Strategy {strategy_id} not found")
        return s
    finally:
        repo.close()


@router.post("/{strategy_id}/status")
def set_status(strategy_id: int, data: dict):
    status = data.get("status")
    if status not in _VALID_STATUS:
        raise HTTPException(400, f"Invalid status, must be one of {sorted(_VALID_STATUS)}")
    repo = StrategyRepository()
    try:
        s = repo.set_status(strategy_id, status, operator=data.get("operator", "system"))
        if not s:
            raise HTTPException(404, f"Strategy {strategy_id} not found")
        return s
    finally:
        repo.close()


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: int):
    repo = StrategyRepository()
    try:
        if not repo.delete(strategy_id):
            raise HTTPException(404, f"Strategy {strategy_id} not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/{strategy_id}/usage")
def record_usage(strategy_id: int, data: dict):
    """引用埋点：记录某商机/报价引用了这条策略。"""
    repo = StrategyRepository()
    try:
        return repo.record_usage(
            strategy_id,
            version=data.get("version"),
            ref_type=data.get("ref_type"),
            ref_id=data.get("ref_id"),
            operator=data.get("operator", "system"),
        )
    finally:
        repo.close()


@router.get("/{strategy_id}/usage")
def usage_stats(strategy_id: int):
    repo = StrategyRepository()
    try:
        return repo.usage_stats(strategy_id)
    finally:
        repo.close()
