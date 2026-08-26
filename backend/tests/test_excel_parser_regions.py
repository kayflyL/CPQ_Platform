"""ExcelParser region-key driven behavior tests."""
import pandas as pd
from unittest.mock import MagicMock

from app.engine.excel_parser import ExcelParser


def _parser(regions, rules=None):
    parser = ExcelParser(MagicMock())
    parser._parse_regions = regions
    parser._parse_field_rules = rules or []
    return parser


def _region(id, name, key, start, region_type="dynamic", sort=0, skip=0):
    return {
        "id": id,
        "name": name,
        "region_key": key,
        "region_type": region_type,
        "start_keywords": start,
        "end_keywords": "",
        "end_mode": "eof",
        "sort_order": sort,
        "enabled": True,
        "skip_header_rows": skip,
        "start_mode": "keyword",
        "start_config": None,
        "end_config": None,
    }


def _df(values):
    return pd.DataFrame({0: values})


def test_locate_regions_no_end_keyword_uses_next_region_start():
    parser = _parser([
        _region(1, "Header", "header", "Header", "static", 0),
        _region(2, "L6", "l6", "L6", "dynamic", 1, 1),
        _region(3, "Keyparts", "kp", "Keyparts", "dynamic", 2, 1),
    ])
    bounds = parser._locate_regions(_df(["Header", "quote_date", "L6", "item", "Keyparts", "cpu"]))

    assert list(bounds) == ["header", "l6", "kp"]
    assert bounds["header"]["start_row"] == 0
    assert bounds["header"]["end_row"] == 2
    assert bounds["l6"]["start_row"] == 2
    assert bounds["l6"]["end_row"] == 4
    assert bounds["kp"]["start_row"] == 4
    assert bounds["kp"]["end_row"] == 6


def test_locate_regions_same_name_uses_region_key_not_overwrite():
    parser = _parser([
        _region(1, "Header", "header_main", "Header", "static", 0),
        _region(2, "Header", "header_extra", "Extra", "dynamic", 1),
    ])
    bounds = parser._locate_regions(_df(["Header", "quote_date", "Extra", "value"]))

    assert list(bounds) == ["header_main", "header_extra"]
    assert bounds["header_main"]["region_name"] == "Header"
    assert bounds["header_extra"]["region_name"] == "Header"
    assert bounds["header_main"]["start_row"] == 0
    assert bounds["header_extra"]["start_row"] == 2


def test_parse_binds_field_rule_by_region_id():
    parser = _parser(
        [
            _region(1, "Header", "header", "Header", "static", 0),
            _region(2, "L6", "l6", "L6", "dynamic", 1, 1),
            _region(3, "Keyparts", "kp", "Keyparts", "dynamic", 2, 1),
        ],
        [
            {
                "id": 1,
                "field_key": "model",
                "region_id": 2,
                "region": "",
                "source_type": "column",
                "source_config": {"col": "A"},
                "fallback_config": None,
                "enabled": True,
                "sort_order": 0,
            }
        ],
    )
    result = parser.parse(_df(["Header", "quote_date", "L6", "server-01", "Keyparts", "cpu"]))

    assert "l6" in result["dynamic_regions"]
    assert result["dynamic_regions"]["l6"][0]["model"] == "server-01"
    assert "kp" not in result["dynamic_regions"]


def test_preview_includes_region_bounds_even_without_field_rules():
    parser = _parser([
        _region(1, "Server", "server", "Server", "dynamic", 0),
    ])
    preview = parser.preview_parse(_df(["Server", "value", "end"]), max_row=10, max_col=5)

    assert "server" in preview["region_bounds"]
    assert preview["region_bounds"]["server"]["region_name"] == "Server"


def test_api_create_region_uses_single_create(monkeypatch):
    from app.api import rules as rules_mod

    fake = MagicMock()
    fake.add_parse_region.return_value = 42
    monkeypatch.setattr(rules_mod, "rules_repo", fake)

    payload = {"name": "Server", "region_type": "dynamic", "start_keywords": "Server"}
    assert rules_mod.save_parse_regions(payload) == {"status": "success", "id": 42}
    fake.add_parse_region.assert_called_once_with(payload)


def test_api_create_field_rule_uses_single_create(monkeypatch):
    from app.api import rules as rules_mod

    fake = MagicMock()
    fake.add_parse_field_rule.return_value = 9
    monkeypatch.setattr(rules_mod, "rules_repo", fake)

    payload = {"field_key": "model", "region_id": 2, "source_type": "column", "source_config": {"col": "A"}}
    assert rules_mod.save_parse_field_rules(payload) == {"status": "success", "id": 9}
    fake.add_parse_field_rule.assert_called_once_with(payload)