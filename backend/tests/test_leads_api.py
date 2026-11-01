"""线索池 API 测试：401 未登录 / 403 无权限 / 确认幂等 / 转化并发抢占 / 驳回字典校验。

转化流程的商业对象（建商机/需求草稿/附件转钉/企微）在测试中打桩——本文件验证的是
线索状态机与权限门，商业对象联动由各自模块的测试与联调覆盖。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import deps
from app.api import leads as leads_api
from app.models.lead import OpportunityLead
from app.repository.lead_repo import LeadRepository
from app.repository.system_config_repo import SystemConfigRepository

ADMIN = {"user_id": "test-admin", "role": "admin", "name": "测试管理员", "username": "test-admin"}
NO_PERM = {"user_id": "test-nobody", "role": "quote", "name": "无权人", "username": "test-nobody"}


def _override_user(user):
    app.dependency_overrides[deps.get_current_user] = lambda: user


def _cleanup():
    repo = LeadRepository()
    try:
        repo.session.query(OpportunityLead).filter(OpportunityLead.lead_id.like("LEADAPI-%")).delete()
        repo.session.commit()
    finally:
        repo.close()


@pytest.fixture()
def client_admin():
    _override_user(ADMIN)
    _cleanup()
    yield TestClient(app)
    app.dependency_overrides.pop(deps.get_current_user, None)
    _cleanup()


def _seed_reject_dict():
    repo = SystemConfigRepository()
    try:
        repo.set("lead.reject_reasons", [
            {"key": "no_need", "label": "无真实需求", "enabled": True},
            {"key": "spam", "label": "垃圾广告", "enabled": True},
        ], type="json")
    finally:
        repo.close()


def _mk_lead(repo: LeadRepository, lead_id: str, status: str = "new"):
    repo.insert({"lead_id": lead_id, "company": "接口测试公司", "contact_name": "李四",
                 "contact_phone": "19800001111", "requirement_text": "接口测试需求内容足够长"})
    if status == "confirmed":
        repo.mark_confirmed(lead_id)
    elif status == "assigned":
        repo.try_mark_converting(lead_id)
        repo.finalize_converted(lead_id, "OPP-X", "u-biz")


def test_list_requires_login(client_admin):
    app.dependency_overrides.pop(deps.get_current_user, None)
    c = TestClient(app)
    assert c.get("/api/leads").status_code == 401
    assert c.post("/api/leads/LEADAPI-x/confirm").status_code == 401


def test_list_requires_perm(client_admin):
    _override_user(NO_PERM)
    c = TestClient(app)
    assert c.get("/api/leads").status_code == 403
    assert c.post("/api/leads/LEADAPI-x/confirm").status_code == 403


def test_confirm_idempotent_and_conflict(client_admin):
    repo = LeadRepository()
    _mk_lead(repo, "LEADAPI-C1", status="new")
    _mk_lead(repo, "LEADAPI-C2", status="assigned")
    r1 = client_admin.post("/api/leads/LEADAPI-C1/confirm")
    assert r1.status_code == 200 and r1.json()["status"] == "confirmed"
    r2 = client_admin.post("/api/leads/LEADAPI-C1/confirm")
    assert r2.status_code == 200  # 幂等
    assert client_admin.post("/api/leads/LEADAPI-C2/confirm").status_code == 409
    assert client_admin.post("/api/leads/LEADAPI-404/confirm").status_code == 404


def test_reject_requires_dict_reason(client_admin):
    _seed_reject_dict()
    repo = LeadRepository()
    _mk_lead(repo, "LEADAPI-R1")
    r = client_admin.post("/api/leads/LEADAPI-R1/reject", json={"reason": "made_up_key"})
    assert r.status_code == 422
    r = client_admin.post("/api/leads/LEADAPI-R1/reject", json={"reason": "spam", "note": "广告"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert repo.get("LEADAPI-R1")["status"] == "rejected"


def test_delete_and_restore(client_admin):
    _seed_reject_dict()
    repo = LeadRepository()
    _mk_lead(repo, "LEADAPI-D1", status="new")
    _mk_lead(repo, "LEADAPI-D2", status="assigned")
    # 未转化可删（软删除）
    assert client_admin.post("/api/leads/LEADAPI-D1/delete").status_code == 200
    assert repo.get("LEADAPI-D1")["status"] == "deleted"
    # 回收站恢复 → 回到待处理
    assert client_admin.post("/api/leads/LEADAPI-D1/restore").status_code == 200
    assert repo.get("LEADAPI-D1")["status"] == "new"
    # 已转化不可删（商机溯源依赖）
    assert client_admin.post("/api/leads/LEADAPI-D2/delete").status_code == 409
    # 回收站视图
    repo.mark_deleted("LEADAPI-D1")
    page = client_admin.get("/api/leads", params={"status": "deleted"}).json()
    assert any(i["lead_id"] == "LEADAPI-D1" for i in page["items"])
    page_all = client_admin.get("/api/leads").json()
    assert all(i["status"] != "deleted" for i in page_all["items"])  # 默认视图不含回收站


def test_convert_race_and_validation(client_admin, monkeypatch):
    _seed_reject_dict()
    repo = LeadRepository()

    # 打桩：商业对象联动（建商机/溯源/草稿/附件/企微）
    monkeypatch.setattr(leads_api.OpportunityRepository, "create_or_update_opportunity",
                        lambda self, oid, payload: None)
    monkeypatch.setattr(leads_api.OpportunityRepository, "update_meta", lambda self, oid, meta: None)
    monkeypatch.setattr(leads_api.FlowRepository, "create_or_update_requirement_draft",
                        lambda self, oid, slots, requirement_text="", created_by="": {"version": 1})
    monkeypatch.setattr(leads_api, "_pin_lead_attachments", lambda *a, **k: None)

    _mk_lead(repo, "LEADAPI-V1", status="confirmed")
    _mk_lead(repo, "LEADAPI-V2", status="confirmed")
    _mk_lead(repo, "LEADAPI-V3", status="assigned")

    # 归属业务必须真实存在
    r = client_admin.post("/api/leads/LEADAPI-V1/convert", json={"assignee_user_id": "ghost-user"})
    assert r.status_code == 409

    options = repo.business_options()
    assert options, "开发库需至少一个启用中的业务账号"
    r = client_admin.post("/api/leads/LEADAPI-V1/convert", json={"assignee_user_id": options[0]["user_id"]})
    assert r.status_code == 200
    opp_id = r.json()["opportunity_id"]
    got = repo.get("LEADAPI-V1")
    assert got["status"] == "assigned" and got["converted_opportunity_id"] == opp_id

    # 并发/重复转化：已 assigned → 409
    r = client_admin.post("/api/leads/LEADAPI-V1/convert", json={"assignee_user_id": options[0]["user_id"]})
    assert r.status_code == 409
    assert client_admin.post("/api/leads/LEADAPI-V3/convert", json={"assignee_user_id": options[0]["user_id"]}).status_code == 409
