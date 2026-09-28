# -*- coding: utf-8 -*-
"""使用位置绑定（scope→模板）裁决矩阵。

显式 template_id > scope 绑定 > 通用兜底；死 id / 已停用 / 未绑定一律落兜底。
"""


class _StubRepo:
    def __init__(self, templates, bindings):
        self._templates = templates
        self._bindings = bindings

    def get_parse_templates(self):
        return self._templates

    def get_parse_template(self, template_id):
        return next((t for t in self._templates if t["id"] == template_id), None)

    def get_parse_scope_binding(self, scope_key):
        return self._bindings.get(scope_key)

    def get_parse_scope_bindings(self):
        return [{"scope_key": k, "template_id": v} for k, v in self._bindings.items()]

    def set_parse_scope_binding(self, scope_key, template_id):
        self._bindings[scope_key] = template_id


def _service(templates=None, bindings=None):
    from app.services.parse_template_service import ParseTemplateService
    templates = templates if templates is not None else [
        {"id": 1, "name": "通用", "is_fallback": True, "enabled": True},
        {"id": 2, "name": "方案部配置表", "is_fallback": False, "enabled": True},
    ]
    return ParseTemplateService(rules_repo=_StubRepo(templates, bindings or {}))


def test_scope_binding_resolves_bound_template():
    svc = _service(bindings={"cost_sheet_upload": 2})
    assert svc.resolve_scope_template("cost_sheet_upload") == {
        "template_id": 2, "mode": "scope", "scope": "cost_sheet_upload"}


def test_unbound_scope_falls_back_to_default():
    svc = _service()
    assert svc.resolve_scope_template("cost_sheet_upload") == {
        "template_id": 1, "mode": "default"}


def test_unknown_scope_falls_back():
    svc = _service(bindings={"cost_sheet_upload": 2})
    assert svc.resolve_scope_template("not_a_scope")["mode"] == "default"


def test_binding_to_deleted_template_falls_back():
    svc = _service(bindings={"cost_sheet_upload": 99})
    assert svc.resolve_scope_template("cost_sheet_upload") == {
        "template_id": 1, "mode": "default"}


def test_binding_to_disabled_template_falls_back():
    templates = [
        {"id": 1, "name": "通用", "is_fallback": True, "enabled": True},
        {"id": 2, "name": "停用模板", "is_fallback": False, "enabled": False},
    ]
    svc = _service(templates=templates, bindings={"cost_sheet_upload": 2})
    assert svc.resolve_scope_template("cost_sheet_upload")["mode"] == "default"


def test_explicit_template_id_wins_over_scope():
    svc = _service(bindings={"cost_sheet_upload": 2})
    assert svc.resolve_scope_template("cost_sheet_upload", 1) == {
        "template_id": 1, "mode": "manual"}


def test_dead_explicit_id_falls_back():
    svc = _service(bindings={"cost_sheet_upload": 2})
    assert svc.resolve_scope_template("cost_sheet_upload", 99)["mode"] == "default"


def test_set_scope_binding_validates_scope_and_template():
    svc = _service()
    out = svc.set_scope_binding("cost_sheet_upload", 2)
    assert out == {"scope_key": "cost_sheet_upload", "template_id": 2}
    assert svc.repo.get_parse_scope_binding("cost_sheet_upload") == 2
    import pytest
    with pytest.raises(ValueError):
        svc.set_scope_binding("nope", 1)
    with pytest.raises(ValueError):
        svc.set_scope_binding("cost_sheet_upload", 99)


def test_list_scope_bindings_reports_registry_shape():
    svc = _service(bindings={"cost_sheet_upload": 2})
    rows = svc.list_scope_bindings()
    assert rows == [{
        "scope_key": "cost_sheet_upload", "label": "成本核算 · 上传解析",
        "template_id": 2, "template_name": "方案部配置表"}]
