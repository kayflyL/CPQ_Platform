# -*- coding: utf-8 -*-
"""报价单解冻（action.quote.unfreeze）测试：权限目录种子 + 状态回退分支（mock repo，不依赖 DB）。"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _quote(exported_at=None, submitted_at=None, payload=None):
    q = MagicMock()
    q.exported_at = exported_at
    q.submitted_at = submitted_at
    q.to_dict.return_value = payload or {"quotation_id": "QUO-1", "exported_at": None}
    return q


def _call(quotation_id="QUO-1"):
    from app.api import quotations as qmod
    return qmod.unfreeze_quotation(quotation_id, {"role": "admin"}, {"user_id": "u1"})


def test_permission_catalog_seeds_unfreeze_key():
    """权限目录必须有解冻 key，否则「用户与权限」页无法分配。"""
    from app.core.startup import _DEFAULT_PERMISSIONS
    item = next((p for p in _DEFAULT_PERMISSIONS if p["key"] == "action.quote.unfreeze"), None)
    assert item, "解冻权限未进权限目录"
    assert item["group"] == "action"
    assert item["module"] == "商机线索 · 报价工作台"


def test_unfreeze_clears_exported_at():
    repo = MagicMock()
    repo.get_by_id.return_value = _quote(exported_at="2026-09-01T10:00:00")
    repo.unfreeze.return_value = _quote()
    with patch("app.api.quotations.QuotationRepository", return_value=repo):
        res = _call()
    repo.unfreeze.assert_called_once_with("QUO-1")
    assert res["quotation"]["exported_at"] is None


def test_unfreeze_rejects_draft():
    repo = MagicMock()
    repo.get_by_id.return_value = _quote()
    with patch("app.api.quotations.QuotationRepository", return_value=repo):
        with pytest.raises(HTTPException) as ei:
            _call()
    assert ei.value.status_code == 400
    repo.unfreeze.assert_not_called()


def test_unfreeze_rejects_submitted_quote():
    """已发送（报价单已出）的单不许解冻：先退回审批节点再改。"""
    repo = MagicMock()
    repo.get_by_id.return_value = _quote(exported_at="2026-09-01T10:00:00",
                                       submitted_at="2026-09-02T09:00:00")
    with patch("app.api.quotations.QuotationRepository", return_value=repo):
        with pytest.raises(HTTPException) as ei:
            _call()
    assert ei.value.status_code == 409
    repo.unfreeze.assert_not_called()


def test_unfreeze_missing_quotation():
    repo = MagicMock()
    repo.get_by_id.return_value = None
    with patch("app.api.quotations.QuotationRepository", return_value=repo):
        with pytest.raises(HTTPException) as ei:
            _call("QUO-NONE")
    assert ei.value.status_code == 404
