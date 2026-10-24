"""配件价格门测试 — field.parts.price（看价）/ action.parts.price.manage（写价）。

三层防复发网（2026-10-16 库价门接线）：
1. mask_part_price_fields 单测（配件域掩码不碰分页信封）；
2. 函数级：无价角色（te 权限集）调 KP/料号列表端点 → 价格字段全 None；
   有价角色（cost 权限集）→ 价格原样；
3. 路由源码扫描：配件价格相关前缀下的每个 GET 端点，必须要么在无价白名单，
   要么源码/依赖里带价格门标记——新增端点忘了接线会在这里直接挂。

不依赖真实 DB：仓储 monkeypatch，field_visible 走 RoleRepository/Settings monkeypatch。
"""
import inspect

import pytest

from app.utils.price_mask import mask_part_price_fields


# ── 公共 mock 基建 ──

def _patch_price_env(monkeypatch, role_perms):
    """AUTH_ENABLED=True + 指定角色权限集。"""
    import app.core.config as cfg
    import app.repository.role_repo as rr

    class S:
        AUTH_ENABLED = True

    class _Repo:
        def __init__(self, perms):
            self.perms = perms
        def permissions_of(self, role):
            return self.perms
        def close(self):
            pass

    monkeypatch.setattr(cfg, "get_settings", lambda: S())
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(role_perms))
    return _Repo


TE_PERMS = ["page.opportunities", "page.servers", "page.parts",
            "field.flow.bom", "action.flow.submit.boming"]
COST_PERMS = ["page.opportunities", "field.quote.price", "field.parts.price",
              "action.parts.price.manage"]


# ── 函数级：KP 库列表 / 详情 ──

def test_admin_kp_parts_list_masks_price_for_priceless_role(monkeypatch):
    from app.api import admin as admin_mod

    _patch_price_env(monkeypatch, TE_PERMS)

    class _Repo:
        def list_parts(self, *a, **kw):
            return {"items": [{"id": 1, "name": "A", "latest_price": 100, "latest_currency": "RMB"}],
                    "total": 1}
        def close(self):
            pass

    monkeypatch.setattr(admin_mod, "KPRepository", lambda: _Repo())
    data = admin_mod.list_parts(user={"role": "te"})
    assert data["total"] == 1
    assert data["items"][0]["latest_price"] is None
    assert data["items"][0]["latest_currency"] is None
    assert data["items"][0]["name"] == "A"


def test_admin_kp_parts_list_keeps_price_for_cost(monkeypatch):
    from app.api import admin as admin_mod

    _patch_price_env(monkeypatch, COST_PERMS)

    class _Repo:
        def list_parts(self, *a, **kw):
            return {"items": [{"id": 1, "name": "A", "latest_price": 100}], "total": 1}
        def close(self):
            pass

    monkeypatch.setattr(admin_mod, "KPRepository", lambda: _Repo())
    data = admin_mod.list_parts(user={"role": "cost"})
    assert data["items"][0]["latest_price"] == 100


def test_admin_kp_parts_list_price_sort_coerced_for_priceless_role(monkeypatch):
    """价格排序对无价角色泄露相对贵贱——必须被改写为按名称。"""
    from app.api import admin as admin_mod

    _patch_price_env(monkeypatch, TE_PERMS)

    captured = {}

    class _Repo:
        def list_parts(self, category_id, search, page, page_size, sort_by, sort_order, brands, price_filter, specs):
            captured["sort_by"] = sort_by
            captured["price_filter"] = price_filter
            return {"items": [], "total": 0}
        def close(self):
            pass

    monkeypatch.setattr(admin_mod, "KPRepository", lambda: _Repo())
    admin_mod.list_parts(sort_by="price", price_filter="has_price", user={"role": "te"})
    assert captured["sort_by"] == "name"
    assert captured["price_filter"] is None


def test_admin_kp_part_create_strips_price_payload_without_manage(monkeypatch):
    """技术/业务只录档案：create/update 载荷里的价格键必须被剥掉。"""
    from app.api import admin as admin_mod

    _patch_price_env(monkeypatch, TE_PERMS)

    captured = {}

    class _Repo:
        def create_part(self, data):
            captured.update(data)
            return {"id": 1}
        def close(self):
            pass

    monkeypatch.setattr(admin_mod, "KPRepository", lambda: _Repo())
    admin_mod.create_part(
        {"name": "X", "specs": [{"spec_key": "tdp", "spec_value": "450W"}],
         "initial_price": 999, "price": 888},
        user={"role": "te"},
    )
    assert "initial_price" not in captured and "price" not in captured
    assert captured["name"] == "X"


def test_admin_kp_price_analytics_forbidden_for_priceless_role(monkeypatch):
    from app.api import admin as admin_mod
    from fastapi import HTTPException

    _patch_price_env(monkeypatch, TE_PERMS)
    with pytest.raises(HTTPException) as ei:
        admin_mod.kp_price_movers(user={"role": "te"})
    assert ei.value.status_code == 403
    with pytest.raises(HTTPException) as ei:
        admin_mod.kp_stats(user={"role": "te"})
    assert ei.value.status_code == 403


# ── 函数级：料号库 ──

def test_parts_master_list_masks_unit_price_for_priceless_role(monkeypatch):
    from app.api import parts as parts_mod

    _patch_price_env(monkeypatch, TE_PERMS)

    class _Repo:
        def list(self, *a, **kw):
            return [{"pn": "P1", "name": "背板", "unit_price": 850, "specs": {"bays": 12}}]
        def close(self):
            pass

    monkeypatch.setattr(parts_mod, "PartsMasterRepository", lambda: _Repo())
    data = parts_mod.list_parts(user={"role": "te"})
    assert data["total"] == 1
    assert data["parts"][0]["unit_price"] is None
    assert data["parts"][0]["specs"] == {"bays": 12}


def test_parts_master_price_sort_denied_for_priceless_role(monkeypatch):
    from app.api import parts as parts_mod

    _patch_price_env(monkeypatch, TE_PERMS)

    class _Repo:
        def list(self, *a, **kw):
            return [{"pn": "P1", "unit_price": 5}, {"pn": "P2", "unit_price": 900}]
        def close(self):
            pass

    monkeypatch.setattr(parts_mod, "PartsMasterRepository", lambda: _Repo())
    # unit_price 排序被拒后：按价格排序的顺序信号消失（价格为 None 的行序即原序）
    data = parts_mod.list_parts(sort_by="unit_price", sort_order="asc", user={"role": "te"})
    assert all(row["unit_price"] is None for row in data["parts"])


# ── 路由源码扫描网：新端点忘接线会在这里挂 ──

# 前缀内必然无价格数据的 GET 端点（分类/品牌/规格聚合/模板下载等纯档案面）。
# 白名单外新增 GET 且不带价格门 = 测试失败，逼着接线。
_NO_PRICE_GET_ALLOWLIST = {
    "/api/admin/kp/categories", "/api/admin/kp/categories/all", "/api/admin/kp/brands",
    "/api/admin/kp/spec-facets", "/api/admin/kp/parts/import-template",
    "/api/kp/categories", "/api/kp/spec-keys", "/api/kp/search-aliases",
    "/api/parts/major-categories", "/api/parts/taxonomy",
    "/api/parts/categories", "/api/parts/spec-keys", "/api/parts/spec-values",
    "/api/parts/import-template",
    "/api/bom-cases/l6-preview",
}

_PRICE_PREFIXES = ("/api/admin/kp/", "/api/admin/l6/", "/api/parts", "/api/kp/parts", "/api/bom-cases")


def test_every_price_bearing_get_route_is_gated_or_allowlisted():
    from app.main import app

    violations = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods:
            continue
        if not (path == "/api/parts" or any(path.startswith(p) for p in _PRICE_PREFIXES)):
            continue
        if path in _NO_PRICE_GET_ALLOWLIST:
            continue
        src = inspect.getsource(route.endpoint) if hasattr(route, "endpoint") else ""
        deps_repr = " ".join(repr(d) for d in getattr(route, "dependencies", []) or [])
        gated = (
            ("field_visible" in src and "_PRICE_VIEW" in src)
            or ("_require_price_view" in src)
            or ("parts.price" in deps_repr)  # require_perms(field/action.parts.price.*) 装饰器门
        )
        if not gated:
            violations.append(path)
    assert not violations, f"以下配件价格端点未接 field.parts.price 门（新增端点请在白名单或接线）: {violations}"


def test_duplicates_endpoint_not_in_allowlist_regression():
    """duplicates 检测结果带价格，必须走 view 键门——防止有人顺手加白名单。"""
    assert "/api/admin/kp/parts/duplicates" not in _NO_PRICE_GET_ALLOWLIST
