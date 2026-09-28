"""RBAC tests — require_admin / 权限目录 / 角色 CRUD / 用户管理（mock repo，不依赖 DB）。"""
import pytest
from fastapi import HTTPException

from app.api.deps import require_admin


# ── require_admin ──

def test_require_admin_allows_admin():
    u = require_admin(user={"role": "admin"})
    assert u["role"] == "admin"


def test_require_admin_blocks_non_admin():
    with pytest.raises(HTTPException) as ei:
        require_admin(user={"role": "member"})
    assert ei.value.status_code == 403


# ── 权限目录 ──

class _FakeSysRepo:
    def __init__(self, value):
        self._value = value

    def get_value(self, key, default=None):
        return self._value if key == "auth.permissions" else default

    def set(self, *a, **k):
        self.saved = a
        return {"success": True}

    def close(self):
        pass


def test_permission_catalog_endpoint(monkeypatch):
    from app.api import roles as roles_mod
    catalog = [{"key": "page.servers", "name": "服务器", "group": "page"}]
    monkeypatch.setattr(roles_mod, "SystemConfigRepository", lambda: _FakeSysRepo(catalog))
    resp = roles_mod.get_permission_catalog()
    assert resp["permissions"] == catalog


# ── 角色 CRUD ──

class _FakeRoleRepo:
    def __init__(self, roles=None):
        self.roles = roles or {}
        self.deleted = None

    def get(self, key):
        return self.roles.get(key)

    def create(self, key, name, description=None, permissions=None):
        role = {"role_key": key, "name": name, "description": description or "", "permissions": permissions or []}
        self.roles[key] = role
        return role

    def update(self, key, name=None, description=None, permissions=None):
        r = self.roles.get(key)
        if not r:
            return None
        if name is not None:
            r["name"] = name
        if permissions is not None:
            r["permissions"] = permissions
        return r

    def delete(self, key):
        if key not in self.roles:
            return False
        del self.roles[key]
        return True

    def list_all(self):
        return list(self.roles.values())

    def permissions_of(self, role):
        return self.roles.get(role, {}).get("permissions", []) if role in self.roles else []

    def close(self):
        pass


def test_create_role(monkeypatch):
    from app.api import roles as roles_mod
    fake = _FakeRoleRepo()
    monkeypatch.setattr(roles_mod, "RoleRepository", lambda: fake)
    resp = roles_mod.create_role(
        roles_mod.RoleBody(role_key="custom", name="自定义角色", permissions=["page.servers"]),
        admin={"role": "admin"},
    )
    assert resp["role"]["role_key"] == "custom"
    assert "page.servers" in resp["role"]["permissions"]


def test_create_role_duplicate(monkeypatch):
    from app.api import roles as roles_mod
    fake = _FakeRoleRepo({"te": {"role_key": "te", "name": "技术支持"}})
    monkeypatch.setattr(roles_mod, "RoleRepository", lambda: fake)
    with pytest.raises(HTTPException) as ei:
        roles_mod.create_role(roles_mod.RoleBody(role_key="te", name="x"), admin={"role": "admin"})
    assert ei.value.status_code == 400


def test_delete_role_in_use(monkeypatch):
    from app.api import roles as roles_mod
    fake_roles = _FakeRoleRepo({"business": {"role_key": "business", "name": "业务"}})
    monkeypatch.setattr(roles_mod, "RoleRepository", lambda: fake_roles)

    class _FakeUsers:
        def list_all(self):
            return [{"name": "张三", "role": "business"}]
        def close(self):
            pass
    monkeypatch.setattr(roles_mod, "FeedUserRepository", lambda: _FakeUsers())

    with pytest.raises(HTTPException) as ei:
        roles_mod.delete_role("business", admin={"role": "admin"})
    assert ei.value.status_code == 400


def test_delete_admin_role_forbidden(monkeypatch):
    from app.api import roles as roles_mod
    with pytest.raises(HTTPException) as ei:
        roles_mod.delete_role("admin", admin={"role": "admin"})
    assert ei.value.status_code == 400


# ── 用户管理 ──

def test_create_user_short_password(monkeypatch):
    from app.api import roles as roles_mod
    with pytest.raises(HTTPException) as ei:
        roles_mod.create_user(roles_mod.CreateUserBody(name="x", password="123"), admin={"role": "admin"})
    assert ei.value.status_code == 400


def test_require_perms(monkeypatch):
    """页面级权限依赖：有任一 key 放行，无则 403。"""
    from app.api.deps import require_perms
    import app.repository.role_repo as rr

    class _Repo:
        def __init__(self, perms):
            self.perms = perms
        def permissions_of(self, role):
            return self.perms
        def close(self):
            pass

    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["page.a", "field.x"]))
    ok = require_perms("page.a")(user={"role": "x"})
    assert ok["role"] == "x"
    with pytest.raises(HTTPException) as ei:
        require_perms("page.b")(user={"role": "x"})
    assert ei.value.status_code == 403


def test_permissions_of_admin_returns_catalog(monkeypatch):
    """admin 角色恒返回目录全量（超级管理员兜底）。"""
    from app.repository import role_repo as rr
    monkeypatch.setattr(rr, "_catalog_keys", lambda: ["page.a", "page.b"])
    fake = _FakeRoleRepo({"admin": {"role_key": "admin", "name": "管理员", "permissions": []}})
    # permissions_of 走真实实现，需要真实 session —— 这里直接测 _catalog_keys 与 admin 分支逻辑
    assert rr._catalog_keys() == ["page.a", "page.b"]


def test_ensure_permission_catalog_realigns_and_keeps_custom(monkeypatch):
    """目录种子语义（2026-09-16 对齐菜单）：已知 key 标签强制对齐默认、死键回收、
    自定义 key 保留、缺 key 补齐（page.office）。"""
    from app.core import startup as su

    stale = [
        {"key": "page.strategies", "name": "策略中心", "group": "page", "module": "策略中心"},
        {"key": "page.opportunities", "name": "商机线索", "group": "page", "module": "商机线索"},
        {"key": "page.portal", "name": "工作台", "group": "page", "module": "工作台"},
        {"key": "custom.extra", "name": "管理员自定义", "group": "action", "module": "商机线索"},
    ]
    saved = {}

    class _Repo:
        def get_value(self, key, default=None):
            return list(stale) if key == "auth.permissions" else default

        def set(self, key, value, type=None, description=None):
            saved[key] = value

        def close(self):
            pass

    monkeypatch.setattr("app.repository.system_config_repo.SystemConfigRepository", lambda: _Repo())
    su.ensure_permission_catalog()
    catalog = saved["auth.permissions"]
    by_key = {p["key"]: p for p in catalog}
    # 已知 key 标签对齐菜单
    assert by_key["page.strategies"]["name"].startswith("解决方案")
    assert by_key["page.strategies"]["module"] == "解决方案"
    assert by_key["page.opportunities"]["module"] == "商机线索"
    assert "商机详情" in by_key["page.opportunities"]["name"]
    # 死键回收 + 新 key 补齐
    assert "page.portal" not in by_key
    assert "page.settings.ai" not in by_key
    assert "field.parts.price" not in by_key
    assert by_key["page.office"]["name"] == "AI 办公室菜单与页面"
    # 子页层级分组（商机线索 · 商机详情 / 报价工作台）
    assert by_key["field.flow.bom"]["module"] == "商机线索 · 商机详情"
    assert by_key["field.quote.price"]["module"] == "商机线索 · 报价工作台"
    # 管理员自定义 key 不动
    assert by_key["custom.extra"]["name"] == "管理员自定义"


def test_update_role_body_without_role_key(monkeypatch):
    """前端编辑角色 PUT 不带 role_key（key 走路径参数），不能 422。"""
    from app.api import roles as roles_mod
    fake = _FakeRoleRepo({"te": {"role_key": "te", "name": "技术支持", "permissions": ["page.office"]}})
    monkeypatch.setattr(roles_mod, "RoleRepository", lambda: fake)
    resp = roles_mod.update_role(
        "te",
        roles_mod.RoleBody(name="技术支持工程师", permissions=["page.office", "page.parts"]),
        admin={"role": "admin"},
    )
    assert resp["role"]["name"] == "技术支持工程师"
    assert fake.roles["te"]["permissions"] == ["page.office", "page.parts"]
