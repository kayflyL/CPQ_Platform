"""Tests for portal cost-sheet upload mapping."""
from app.api.portal import _parse_result_to_cost_configs


def test_cost_configs_use_meta_for_model_description_and_qty():
    result = _parse_result_to_cost_configs({
        "Sheet1": {
            "meta": {
                "server_model": "ZSA24V2-P",
                "description": "1*4U KH50000 switch机型",
                "model_qty": 2,
            },
            "items": [],
            "bom_excel_rows": [],
        }
    })

    assert result[0]["name"] == "Sheet1"
    assert result[0]["server_model"] == "ZSA24V2-P"
    assert result[0]["description"] == "1*4U KH50000 switch机型"
    assert result[0]["qty"] == 2


def test_cost_configs_fall_back_when_meta_missing():
    result = _parse_result_to_cost_configs({
        "Sheet1": {"items": [], "bom_excel_rows": []}
    })

    assert result[0]["server_model"] == ""
    assert result[0]["description"] == ""
    assert result[0]["qty"] == 1
