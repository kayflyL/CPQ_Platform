"""RBAC admin API — 权限目录 / 角色 CRUD / 用户管理。

- 权限目录：system_config.auth.permissions（管理员可增删 key）
- 角色：rules.roles（role_key / name / permissions）
- 用户：feed_users（分配角色 / 启停用 / 重置密码 / 新建）
管理接口均需 admin 角色（Step D 会升级为配置驱动的 require_perms）。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.repository.feed_user_repo import FeedUserRepository
from app.repository.role_repo import RoleRepository
from app.repository.system_config_repo import SystemConfigRepository

router = APIRouter(tags=["rbac"])

_PERMISSION_CATALOG_KEY = "auth.permissions"


# ── 权限目录 ──

@router.get("/api/auth/permissions")
def get_permission_catalog():
    """权限目录：所有可分配权限 key 的说明（页面/字段两级分组）。"""
    repo = SystemConfigRepository()
    try:
        catalog = repo.get_value(_PERMISSION_CATALOG_KEY, [])
        return {"permissions": catalog if isinstance(catalog, list) else []}
    finally:
        repo.close()


class PermissionCatalogBody(BaseModel):
    permissions: List[dict]


@router.put("/api/auth/permissions")
def set_permission_catalog(body: PermissionCatalogBody, admin: dict = Depends(require_admin)):
    """管理员维护权限目录（增删权限 key）。"""
    repo = SystemConfigRepository()
    try:
        repo.set(_PERMISSION_CATALOG_KEY, body.permissions, type="json", description="权限目录")
        return {"success": True, "permissions": body.permissions}
    finally:
        repo.close()


# ── 角色 ──

@router.get("/api/admin/roles")
def list_roles(admin: dict = Depends(require_admin)):
    repo = RoleRepository()
    try:
        return {"roles": repo.list_all()}
    finally:
        repo.close()


class RoleBody(BaseModel):
    role_key: str
    name: str
    description: Optional[str] = None
    permissions: List[str] = []


@router.post("/api/admin/roles")
def create_role(body: RoleBody, admin: dict = Depends(require_admin)):
    key = (body.role_key or "").strip()
    if not key or not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="角色 key 和名称不能为空")
    repo = RoleRepository()
    try:
        if repo.get(key):
            raise HTTPException(status_code=400, detail=f"角色 {key} 已存在")
        role = repo.create(key, body.name, body.description, body.permissions)
        return {"role": role}
    finally:
        repo.close()


@router.put("/api/admin/roles/{role_key}")
def update_role(role_key: str, body: RoleBody, admin: dict = Depends(require_admin)):
    repo = RoleRepository()
    try:
        role = repo.update(role_key, name=body.name, description=body.description, permissions=body.permissions)
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"role": role}
    finally:
        repo.close()


@router.delete("/api/admin/roles/{role_key}")
def delete_role(role_key: str, admin: dict = Depends(require_admin)):
    if role_key == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员角色")
    repo = RoleRepository()
    try:
        # 有用户在使用该角色时禁止删除
        users = FeedUserRepository().list_all()
        in_use = [u["name"] for u in users if (u.get("role") or "") == role_key]
        if in_use:
            raise HTTPException(status_code=400, detail=f"该角色仍在使用中（{len(in_use)} 个用户），请先改绑用户")
        if not repo.delete(role_key):
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True}
    finally:
        repo.close()


# ── 用户管理 ──

@router.get("/api/admin/users")
def list_users(admin: dict = Depends(require_admin)):
    repo = FeedUserRepository()
    try:
        users = repo.list_all()
        # 附角色名
        roles = {r["role_key"]: r["name"] for r in RoleRepository().list_all()}
        for u in users:
            u["role_name"] = roles.get(u.get("role"), u.get("role") or "")
        return {"users": users}
    finally:
        repo.close()


class CreateUserBody(BaseModel):
    name: str
    password: str
    role: str = "member"
    email: Optional[str] = None


@router.post("/api/admin/users")
def create_user(body: CreateUserBody, admin: dict = Depends(require_admin)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(body.password or "") < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    repo = FeedUserRepository()
    try:
        if repo.get_by_name(name):
            raise HTTPException(status_code=400, detail=f"用户 {name} 已存在")
        u = repo.create_user(name=name, role=body.role or "member",
                             password_hash=hash_password(body.password), email=body.email)
        return {"user": u}
    finally:
        repo.close()


class UpdateUserBody(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    name: Optional[str] = None


@router.put("/api/admin/users/{user_id}")
def update_user(user_id: str, body: UpdateUserBody, admin: dict = Depends(require_admin)):
    repo = FeedUserRepository()
    try:
        current = repo.get(user_id)
        if not current:
            raise HTTPException(status_code=404, detail="用户不存在")
        if body.role is not None:
            repo.update_role(user_id, body.role)
        if body.is_active is not None:
            repo.update_active(user_id, body.is_active)
        if body.password is not None:
            if len(body.password) < 6:
                raise HTTPException(status_code=400, detail="密码至少 6 位")
            repo.set_password(user_id, hash_password(body.password))
        if body.name is not None and body.name.strip() and body.name.strip() != current["name"]:
            repo.update_name(user_id, body.name.strip())
        return {"success": True}
    finally:
        repo.close()
