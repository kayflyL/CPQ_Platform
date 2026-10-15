"""报价行价时点锚 _stamp_price_set_at 纯函数测试（不依赖 DB）。

规则：只管 KP 行；旧行找不到同件=新行锚 now；找得到且 base_price 没变沿用旧锚，变了盖 now。
"""
import pytest

from app.repository.quotation_repo import _stamp_price_set_at


def _kp(config="CFG1", catalogue="Xeon-6430", cat="cpu", price=100.0, stamp=None):
    return {"config_name": config, "category": "Key Parts", "catalogue": catalogue,
            "part_category": cat, "base_price": price, "price_set_at": stamp}


def test_new_row_gets_now():
    new = _kp(price=120.0)
    _stamp_price_set_at([], new, "2026-10-09T10:00:00")
    assert new["price_set_at"] == "2026-10-09T10:00:00"


def test_unchanged_price_keeps_old_stamp():
    old = [_kp(price=100.0, stamp="2026-05-01T09:00:00")]
    new = _kp(price=100.0)
    _stamp_price_set_at(old, new, "2026-10-09T10:00:00")
    assert new["price_set_at"] == "2026-05-01T09:00:00"


def test_changed_price_gets_now():
    old = [_kp(price=100.0, stamp="2026-05-01T09:00:00")]
    new = _kp(price=123.45)
    _stamp_price_set_at(old, new, "2026-10-09T10:00:00")
    assert new["price_set_at"] == "2026-10-09T10:00:00"


def test_changed_price_without_old_stamp_uses_now_for_next_diff():
    old = [_kp(price=100.0, stamp=None)]
    new = _kp(price=100.0)
    _stamp_price_set_at(old, new, "2026-10-09T10:00:00")
    assert new["price_set_at"] is None


def test_matching_normalizes_case_and_whitespace():
    old = [_kp(catalogue=" XEON-6430 ", cat="CPU", price=100.0, stamp="2026-05-01T09:00:00")]
    new = _kp(catalogue="xeon-6430", cat="cpu", price=100.0)
    _stamp_price_set_at(old, new, "2026-10-09T10:00:00")
    assert new["price_set_at"] == "2026-05-01T09:00:00"


def test_same_model_rows_paired_in_order():
    old = [_kp(price=100.0, stamp="2026-01-01T00:00:00"),
           _kp(price=200.0, stamp="2026-02-02T00:00:00")]
    new_a = _kp(price=100.0)
    new_b = _kp(price=300.0)  # 改价
    _stamp_price_set_at(old, new_a, "2026-10-09T10:00:00")
    _stamp_price_set_at(old, new_b, "2026-10-09T10:00:00")
    assert new_a["price_set_at"] == "2026-01-01T00:00:00"
    assert new_b["price_set_at"] == "2026-10-09T10:00:00"


def test_non_kp_row_untouched():
    row = {"config_name": "CFG1", "category": "Warranty", "catalogue": "质保", "base_price": 50.0}
    _stamp_price_set_at([], row, "2026-10-09T10:00:00")
    assert "price_set_at" not in row


def test_different_config_is_not_same_part():
    old = [_kp(config="CFG1", price=100.0, stamp="2026-01-01T00:00:00")]
    new = _kp(config="CFG2", price=100.0)
    _stamp_price_set_at(old, new, "2026-10-09T10:00:00")
    assert new["price_set_at"] == "2026-10-09T10:00:00"


def test_old_item_consumed_no_double_match():
    old = [_kp(price=100.0, stamp="2026-01-01T00:00:00")]
    new_a = _kp(price=100.0)
    new_b = _kp(price=100.0)  # 新增的第二行，无旧行对应
    _stamp_price_set_at(old, new_a, "2026-10-09T10:00:00")
    _stamp_price_set_at(old, new_b, "2026-10-09T10:00:00")
    assert new_a["price_set_at"] == "2026-01-01T00:00:00"
    assert new_b["price_set_at"] == "2026-10-09T10:00:00"
