"""Tests for portal cost-sheet upload mapping and source-file archiving."""
import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.datastructures import UploadFile

from app.api.portal import _parse_result_to_cost_configs, upload_cost_sheet


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


def test_upload_cost_sheet_archives_source_and_attachment():
    service = MagicMock()
    service.process_upload.return_value = {
        "status": "success",
        "configs": {
            "Sheet1": {
                "meta": {"server_model": "ZSA24V2-P", "description": "spec", "model_qty": 1},
                "items": [],
                "bom_excel_rows": [],
            }
        },
    }
    flow_repo = MagicMock()
    flow_repo.save_cost_sheet_draft.return_value = {"id": 42, "name": "成本-test"}
    flow_repo.list_cost_sheets.return_value = [{"id": 42}]
    feed_repo = MagicMock()
    feed_repo.add_attachment.return_value = {"attachment_id": "a1", "opportunity_id": "OPP-1"}
    storage = MagicMock()
    storage.save_bytes.return_value = "opportunities/客户A_OPP-1/成本核算/test_obj.xlsx"

    with patch("app.api.portal.QuoteService", return_value=service), \
         patch("app.api.portal.FlowRepository", return_value=flow_repo), \
         patch("app.api.portal.FeedRepository", return_value=feed_repo), \
         patch("app.api.portal.get_storage", return_value=storage), \
         patch("app.api.portal._svc", return_value=({"opportunity_id": "OPP-1", "customer_name": "客户A"}, {})), \
         patch("app.api.portal.field_visible", return_value=True), \
         patch("app.api.portal._attach_entity_card", return_value={"id": 7}), \
         patch("app.api.portal._unlink_entity_card"), \
         patch("app.api.portal.build_object_id", return_value="test_obj"), \
         patch("app.api.portal.hub.broadcast", new=AsyncMock()):
        file = UploadFile(filename="test.xlsx", file=io.BytesIO(b"abc"))
        result = asyncio.run(upload_cost_sheet("OPP-1", file, {"user_id": "u1", "name": "张三"}))

    assert result["sheet"]["id"] == 42
    assert result["attachment"]["attachment_id"] == "a1"

    storage.save_bytes.assert_called_once()
    args, kwargs = storage.save_bytes.call_args
    assert args[3] == ".xlsx"
    assert kwargs["subfolder"] == "成本核算"

    feed_repo.add_attachment.assert_called_once()
    _, att_kwargs = feed_repo.add_attachment.call_args
    assert att_kwargs["category"] == "requirement"
    assert att_kwargs["flow_card_id"] == 7
    assert att_kwargs["kind"] == "upload"
