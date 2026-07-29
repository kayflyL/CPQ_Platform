"""Regression tests for preview_data_loader field semantics.

锁定 quotation_items 字段去重载后的展示契约：
  - L6 模板路径：catalogue=label（零件名），description=desc（规格）
  - L6 excel 快照路径：catalogue/description 直通
  - KP 行：catalogue=型号，part_category=类别

防止历史 bug 复发：曾把 desc 写进 part_name、spec 留空，导致预览 Catalogue 列显示规格、
Description 列空白。
"""
import json
from unittest.mock import MagicMock
from app.services.preview_data_loader import _load_l6_from_template


def _make_quotation(extra: dict) -> MagicMock:
    q = MagicMock()
    q.extra_fields = json.dumps(extra, ensure_ascii=False)
    return q


def test_l6_template_path_catalogue_is_label_description_is_desc():
    """live + bom_template 路径：catalogue 必须是行 label（零件名），description 是 ctx.desc（规格）。"""
    extra = {
        "config_l6_picks": {
            "CFG1": {
                "bom_source": "live",
                "bom_template": {
                    "name": "2U12标准",
                    "rows": [
                        {"type": "front_backplane", "label": "Front backplane"},
                        {"type": "io_slot", "label": "IO1", "slot": "IO1"},
                        {"type": "psu_requirement", "label": "Power Supply Requirement"},
                    ],
                },
                "bom_context": {
                    "front_backplane": {"desc": "12*3.5 SATA/SAS", "qty": 1},
                    "IO1": {"desc": "", "qty": 1},
                    "psu_requirement": {"desc": "PSU 1300W", "qty": 2},
                },
            }
        }
    }
    rows, covered, excel_cfgs, *_ = _load_l6_from_template(_make_quotation(extra))

    assert "CFG1" in covered
    by_label = {r["catalogue"]: r for r in rows}
    # catalogue 是 label（零件名），不是规格
    assert "Front backplane" in by_label
    assert by_label["Front backplane"]["description"] == "12*3.5 SATA/SAS"
    assert by_label["Front backplane"]["part_category"] == ""
    # desc 为空时 description 也为空，catalogue 仍是 label
    assert by_label["IO1"]["description"] == ""
    assert by_label["IO1"]["catalogue"] == "IO1"
    # 绝不能出现把规格塞进 catalogue 的历史 bug 形态
    assert "12*3.5 SATA/SAS" not in by_label  # 规格不应成为 catalogue


def test_l6_excel_snapshot_passthrough():
    """excel 快照路径：catalogue/description 按行 category 直通。"""
    extra = {
        "config_l6_picks": {
            "CFG1": {
                "bom_source": "excel",
                "bom_excel_rows": [
                    {"category": "L6", "catalogue": "Front backplane", "description": "12*3.5 SATA/SAS", "qty": 1},
                    {"category": "Key Parts", "catalogue": "AMD EPYC 9334", "part_category": "CPU", "description": "", "qty": 1},
                    {"category": "整机", "catalogue": "Chassis", "description": "2U", "qty": 1},
                ],
            }
        }
    }
    rows, covered, excel_cfgs, *_ = _load_l6_from_template(_make_quotation(extra))

    assert "CFG1" in covered
    assert "CFG1" in excel_cfgs
    l6 = [r for r in rows if r["category"] in ("L6", "整机")]
    assert len(l6) == 2  # 只取 L6/整机，不含 KP
    bp = next(r for r in l6 if r["catalogue"] == "Front backplane")
    assert bp["description"] == "12*3.5 SATA/SAS"
    assert bp["part_category"] == ""


def test_empty_or_invalid_extra_yields_no_rows():
    """extra_fields 缺失/非法 JSON 时返回空，不抛。"""
    rows, covered, excel_cfgs, *_ = _load_l6_from_template(None)
    assert rows == [] and covered == set() and excel_cfgs == set()

    q = MagicMock()
    q.extra_fields = "{not valid json"
    rows2, *_ = _load_l6_from_template(q)
    assert rows2 == []
