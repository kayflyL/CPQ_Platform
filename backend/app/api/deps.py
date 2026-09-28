"""Auth dependencies — resolve the acting user from a JWT (Authorization: Bearer).

- get_current_user: strict (401 when missing/invalid token).
- AUTH_ENABLED=false (灰度开关): fall back to the legacy 匿名 identity so the
  app keeps working before the frontend login is enforced.

Later steps add require_perms(*keys) here for page/field-level RBAC.
"""
from typing import Optional

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException

from app.core.config import get_settings
from app.core.security import decode_token
from app.repository.feed_user_repo import FeedUserRepository


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def _user_from_token(token: str) -> Optional[dict]:
    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    repo = FeedUserRepository()
    try:
        u = repo.get(user_id)
        if not u or not u.get("is_active", True):
            return None
        return u
    finally:
        repo.close()


def _anonymous() -> dict:
    """Legacy fallback identity (AUTH_ENABLED=false 灰度期)."""
    repo = FeedUserRepository()
    try:
        return repo.get_or_create("匿名")
    finally:
        repo.close()


def get_current_user(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> dict:
    """Strict: resolve user from JWT, 401 when missing/invalid."""
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        return _anonymous()
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    u = _user_from_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return u


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """管理端依赖：仅 admin 角色可访问。"""
    if (user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def _user_permissions(user: Optional[dict]) -> list:
    """按请求惰性解析用户权限并缓存到 user dict，避免同一次请求内反复查库。
    user 由 get_current_user 每次请求重建，权限仍是（该请求时刻）最新值。"""
    if not user:
        return []
    cached = user.get("_permissions")
    if cached is not None:
        return cached
    from app.repository.role_repo import RoleRepository
    repo = RoleRepository()
    try:
        perms = repo.permissions_of(user.get("role"))
    finally:
        repo.close()
    if isinstance(user, dict):
        user["_permissions"] = perms
    return perms


def require_perms(*keys: str):
    """页面级权限依赖工厂：用户角色需含 keys 中任意一个权限 key（any 语义）。
    权限来自 rules.roles（配置驱动，非硬编码）。"""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        perms = set(_user_permissions(user))
        if keys and not any(k in perms for k in keys):
            raise HTTPException(status_code=403, detail="无权限执行此操作")
        return user
    return checker


def field_visible(user: Optional[dict], key: str) -> bool:
    """字段级权限判断：AUTH_ENABLED=false（灰度）恒可见；否则需角色含 key。"""
    from app.core.config import get_settings
    if not get_settings().AUTH_ENABLED:
        return True
    if not user:
        return False
    return key in _user_permissions(user)


def user_has_permission(user: Optional[dict], key: str) -> bool:
    """权限判断（配置驱动）：AUTH_ENABLED=false 灰度期恒放行；否则按角色权限目录判断。"""
    if not key:
        return True
    if not user:
        return False
    from app.core.config import get_settings
    if not get_settings().AUTH_ENABLED:
        return True
    return key in _user_permissions(user)


def user_can_access_opportunity(user: Optional[dict], opportunity: Optional[dict]) -> bool:
    """商机归属判断：全量权限放行；有 owner 以 owner 为准，无 owner 回退销售姓名。"""
    if not user or not opportunity:
        return False
    if user_has_permission(user, "page.opportunities_all"):
        return True
    owner_user_id = opportunity.get("owner_user_id") or ""
    sales_person = opportunity.get("sales_person") or ""
    personal_name = user.get("name") or ""
    if owner_user_id:
        # owner 命中即放行；未命中继续走指派人判断（否则 te/cost/quote 被挡在详情页外）
        if owner_user_id == (user.get("user_id") or ""):
            return True
    elif sales_person and sales_person == personal_name:
        return True
    # 流程任一节点的指派人（含历史/被退回的上游）都可进入详情页：
    # 自己阶段提交后要能回看下游进展，被退回时也要能进来改。
    # 指派存储为 user_id（迁移期兼容姓名字符串），双格式匹配。
    opportunity_id = opportunity.get("opportunity_id") or ""
    if opportunity_id:
        from app.repository.flow_repo import FlowRepository, match_assignee
        flow_repo = FlowRepository()
        try:
            flow = flow_repo.get_flow(opportunity_id)
        finally:
            flow_repo.close()
        if flow:
            uid = user.get("user_id") or ""
            return any(
                match_assignee(v, uid, personal_name)
                for v in (flow.get("assignees") or {}).values()
            )
    return False


def ensure_opportunity_access(opportunity_id: str, user: Optional[dict]) -> dict:
    """读取并校验当前用户对指定商机的访问权，越权抛 403。"""
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        opportunity = repo.get_opportunity(opportunity_id)
    finally:
        repo.close()
    if not opportunity:
        raise HTTPException(status_code=404, detail="商机不存在")
    if not user_can_access_opportunity(user, opportunity):
        raise HTTPException(status_code=403, detail="无权访问该商机")
    return opportunity


def require_opportunity_access(opportunity_id: str, user: dict = Depends(get_current_user)) -> dict:
    ensure_opportunity_access(opportunity_id, user)
    return user


def ensure_quotation_access(quotation_id: str, user: Optional[dict]):
    """校验当前用户对报价单所属商机的访问权，越权抛 403。"""
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    from app.repository.quotation_repo import QuotationRepository
    repo = QuotationRepository()
    try:
        quotation = repo.get_raw_by_id(quotation_id)
    finally:
        repo.close()
    if not quotation:
        raise HTTPException(status_code=404, detail="报价单不存在")
    ensure_opportunity_access(quotation.opportunity_id, user)
    return quotation


def require_quotation_access(quotation_id: str, user: dict = Depends(get_current_user)) -> dict:
    ensure_quotation_access(quotation_id, user)
    return user


def resolve_ws_user(token: Optional[str]) -> Optional[dict]:
    """WebSocket 鉴权：有 token 则解析 JWT；AUTH_ENABLED=false 时回退匿名。"""
    if token:
        return _user_from_token(token)
    if not get_settings().AUTH_ENABLED:
        return _anonymous()
    return None
