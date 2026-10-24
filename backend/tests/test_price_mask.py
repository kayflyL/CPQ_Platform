"""价格掩码测试 — mask_price_fields / mask_part_price_fields / field_visible（mock，不依赖 DB）。"""
import pytest

from app.utils.price_mask import mask_price_fields, mask_part_price_fields


# ── mask_price_fields ──

def test_mask_deep_and_preserve_other_fields():
    obj = {
        "total_price": 123.45,
        "items": [{"base_price": 10, "final_price": 12, "name": "CPU", "qty": 2}],
        "name": "报价单A",
    }
    out = mask_price_fields(obj)
    assert out["total_price"] is None
    assert out["items"][0]["base_price"] is None
    assert out["items"][0]["final_price"] is None
    assert out["items"][0]["name"] == "CPU"
    assert out["items"][0]["qty"] == 2
    assert out["name"] == "报价单A"


def test_mask_does_not_mutate_original():
    obj = {"total_price": 100, "items": [{"base_price": 5}]}
    mask_price_fields(obj)
    assert obj["total_price"] == 100
    assert obj["items"][0]["base_price"] == 5


def test_mask_list_and_non_dict():
    rows = [{"total_price": 1}, {"total_price": 2}]
    out = mask_price_fields(rows)
    assert out[0]["total_price"] is None and out[1]["total_price"] is None
    assert mask_price_fields("plain") == "plain"
    assert mask_price_fields(42) == 42


# ── mask_part_price_fields（配件域：库价/价格历史/快照；不碰 total 等通用键）──

def test_part_mask_strips_library_price_but_keeps_envelope_and_specs():
    rows = [{
        "id": 1, "name": "RTX4090", "category_name": "GPU",
        "latest_price": 11536.83, "latest_currency": "RMB", "latest_date": "2026-10-01",
        "price_history": [{"price": 12000, "price_date": "2026-09-01"}],
        "specs": [{"spec_key": "tdp", "spec_value": "450W"}],
    }]
    out = mask_part_price_fields(rows)
    r = out[0]
    assert r["latest_price"] is None and r["latest_currency"] is None and r["latest_date"] is None
    assert r["price_history"] is None
    assert r["name"] == "RTX4090" and r["specs"][0]["spec_value"] == "450W"


def test_part_mask_keeps_pagination_total():
    data = {"items": [{"unit_price": 5}], "total": 99}
    out = mask_part_price_fields(data)
    assert out["total"] == 99
    assert out["items"][0]["unit_price"] is None


# ── field_visible ──

class _FakeSettings:
    AUTH_ENABLED = True


class _Repo:
    def __init__(self, perms):
        self.perms = perms
    def permissions_of(self, role):
        return self.perms
    def close(self):
        pass


def _patch_settings(monkeypatch, enabled):
    import app.core.config as cfg
    class S:
        AUTH_ENABLED = enabled
    monkeypatch.setattr(cfg, "get_settings", lambda: S())


def test_field_visible_auth_enabled_no_user_false(monkeypatch):
    from app.api import deps
    _patch_settings(monkeypatch, True)
    assert deps.field_visible(None, "field.quote.price") is False


def test_field_visible_disabled_auth_always_true(monkeypatch):
    """灰度（AUTH_ENABLED=false）恒可见，**价格键族除外**：价格 fail-closed，
    灰度期匿名/无授权一律不可见（2026-10-17 定调：被授权的账户可以看，其他都看不了）。"""
    from app.api import deps
    _patch_settings(monkeypatch, False)
    assert deps.field_visible(None, "page.parts") is True
    assert deps.field_visible(None, "field.flow.bom") is True
    assert deps.field_visible(None, "field.quote.price") is False
    assert deps.field_visible(None, "field.parts.price") is False
    assert deps.field_visible(None, "field.opportunity.quote_price") is False
    assert deps.user_has_permission({"name": "匿名"}, "field.quote.price") is False
    assert deps.user_has_permission({"name": "匿名"}, "page.parts") is True


def test_field_visible_role_perms(monkeypatch):
    from app.api import deps
    import app.repository.role_repo as rr
    _patch_settings(monkeypatch, True)
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["field.quote.price"]))
    assert deps.field_visible({"role": "quote"}, "field.quote.price") is True
    assert deps.field_visible({"role": "quote"}, "field.parts.price") is False
    # 2026-10-16 库价门复活：quote 持看价键；te/business 无任何价键；cost 持写价键
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["field.quote.price", "field.parts.price"]))
    assert deps.field_visible({"role": "quote"}, "field.parts.price") is True
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["page.parts", "field.parts.price", "action.parts.price.manage"]))
    assert deps.field_visible({"role": "cost"}, "field.parts.price") is True
    assert deps.field_visible({"role": "cost"}, "action.parts.price.manage") is True
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["page.parts"]))
    assert deps.field_visible({"role": "te"}, "field.parts.price") is False
    assert deps.field_visible({"role": "te"}, "action.parts.price.manage") is False
