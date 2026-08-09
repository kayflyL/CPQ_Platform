"""Authentication API — login / me / change own password.

Identity lives in opportunities.feed_users; role key on the same row.
Login issues a JWT (see app.core.security); /me returns the resolved user so
the frontend can build the permission-aware UI (Step C adds permissions).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.repository.feed_user_repo import FeedUserRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _permissions_of(role: Optional[str]) -> list:
    from app.repository.role_repo import RoleRepository
    repo = RoleRepository()
    try:
        return repo.permissions_of(role)
    finally:
        repo.close()


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.post("/login")
def login(body: LoginBody):
    """用户名 + 密码 → JWT + 用户信息。密码错误/禁用/无密码统一 401（不泄露账号状态）。"""
    repo = FeedUserRepository()
    try:
        u = repo.get_by_name_auth(body.username.strip())
        if not u or not verify_password(body.password, u.get("password_hash") or ""):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        if not u.get("is_active", True):
            raise HTTPException(status_code=403, detail="账号已禁用")
        token = create_access_token(u["user_id"], u.get("role") or "member")
        u.pop("password_hash", None)  # 永不把哈希返回给客户端
        return {"token": token, "user": u, "permissions": _permissions_of(u.get("role"))}
    finally:
        repo.close()


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    """返回当前登录用户 + 角色权限（前端鉴权层用）。"""
    return {"user": user, "permissions": _permissions_of(user.get("role"))}


@router.put("/password")
def change_password(body: ChangePasswordBody, user: dict = Depends(get_current_user)):
    """修改自己密码（需原密码）。"""
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    repo = FeedUserRepository()
    try:
        current = repo.get_auth(user["user_id"])
        if not verify_password(body.old_password, current.get("password_hash") or ""):
            raise HTTPException(status_code=400, detail="原密码错误")
        repo.set_password(user["user_id"], hash_password(body.new_password))
        return {"success": True}
    finally:
        repo.close()
