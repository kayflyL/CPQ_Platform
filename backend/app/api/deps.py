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
    """管理端依赖：仅 admin 角色可访问（Step D 升级为配置驱动 require_perms）。"""
    if (user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def get_current_user_optional(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Optional[dict]:
    """Lenient: resolve user from JWT, None when absent/invalid."""
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        return _anonymous()
    token = _extract_bearer(authorization)
    if not token:
        return None
    return _user_from_token(token)
