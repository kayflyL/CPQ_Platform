"""价格掩码测试 — mask_price_fields / field_visible（mock，不依赖 DB）。"""
import pytest

from app.utils.price_mask import mask_price_fields


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
    from app.api import deps
    _patch_settings(monkeypatch, False)
    assert deps.field_visible(None, "field.quote.price") is True


def test_field_visible_role_perms(monkeypatch):
    from app.api import deps
    import app.repository.role_repo as rr
    _patch_settings(monkeypatch, True)
    monkeypatch.setattr(rr, "RoleRepository", lambda: _Repo(["field.quote.price"]))
    assert deps.field_visible({"role": "quote"}, "field.quote.price") is True
    assert deps.field_visible({"role": "quote"}, "field.parts.price") is False
