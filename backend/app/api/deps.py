"""Auth dependencies — resolve the acting user from a JWT (Authorization: Bearer).

- get_current_user: strict (401 when missing/invalid token).
- get_current_user_optional: lenient (None when absent) — for endpoints that
  attribute work to a user but still work anonymously.
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


def require_perms(*keys: str):
    """页面级权限依赖工厂：用户角色需含 keys 中任意一个权限 key（any 语义）。
    权限来自 rules.roles（配置驱动，非硬编码）。"""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        from app.repository.role_repo import RoleRepository
        repo = RoleRepository()
        try:
            perms = set(repo.permissions_of(user.get("role")))
        finally:
            repo.close()
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
    from app.repository.role_repo import RoleRepository
    repo = RoleRepository()
    try:
        return key in repo.permissions_of(user.get("role"))
    finally:
        repo.close()


def get_current_user_optional(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Optional[dict]:
    """Lenient: resolve user from JWT, None when absent/invalid."""
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        return _anonymous()
    token = _extract_bearer(authorization)
    if not token:
        return None
    return _user_from_token(token)
