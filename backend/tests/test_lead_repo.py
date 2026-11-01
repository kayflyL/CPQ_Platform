"""LeadRepository 单测：走本地开发库，测试数据用 LEADTEST- 前缀 + finally 自清理。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.models.lead import OpportunityLead
from app.repository.lead_repo import LeadRepository

PHONE = "19900001234"


def _cleanup(repo: LeadRepository):
    repo.session.query(OpportunityLead).filter(OpportunityLead.lead_id.like("LEADTEST-%")).delete()
    repo.session.commit()


@pytest.fixture()
def repo():
    r = LeadRepository()
    _cleanup(r)
    yield r
    _cleanup(r)
    r.close()


def _mk(repo: LeadRepository, lead_id: str, phone: str = PHONE, status: str = "new") -> str:
    return repo.insert({
        "lead_id": lead_id,
        "source": "catalog_model",
        "company": "测试公司",
        "contact_name": "测试人",
        "contact_phone": phone,
        "contact_email": "t@t.com",
        "requirement_text": "要 2 台训练机",
        "config_slots": {"configs": [{"name": "CFG1", "server_model": "擎天 T-4U", "qty": 2}], "config_relation": "compose"},
        "expected_delivery": "2026-12-31",
        "attachments": [{"storage_key": "k", "name": "a.pdf", "size": 1}],
    })


def test_insert_and_get_roundtrip(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-1")
    got = repo.get(lead_id)
    assert got["company"] == "测试公司"
    assert got["status"] == "new"
    assert got["config_slots"]["configs"][0]["server_model"] == "擎天 T-4U"
    assert got["attachments"][0]["name"] == "a.pdf"
    assert got["dedup_count"] == 1


def test_find_open_by_phone_and_merge(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-2")
    hit = repo.find_open_by_phone(PHONE)
    assert hit and hit["lead_id"] == lead_id

    repo.merge_submission(lead_id, "补充：要 3 年维保", attachments_append=[{"storage_key": "k2", "name": "b.xlsx", "size": 2}])
    got = repo.get(lead_id)
    assert got["dedup_count"] == 2
    assert "---\n补充：要 3 年维保" in got["requirement_text"]
    assert len(got["attachments"]) == 2

    # rejected 后不再是 open，找不到
    repo.mark_rejected(lead_id, "no_need", "")
    assert repo.find_open_by_phone(PHONE) is None


def test_merge_text_capped_at_4000(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-3")
    repo.merge_submission(lead_id, "x" * 6000)
    assert len(repo.get(lead_id)["requirement_text"]) <= 4000


def test_confirm_idempotent_and_illegal_transition(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-4")
    assert repo.mark_confirmed(lead_id) == "confirmed"
    assert repo.mark_confirmed(lead_id) == "confirmed"  # 幂等
    assert repo.mark_rejected(lead_id, "no_need", "")    # confirmed 可驳回
    assert repo.mark_confirmed(lead_id) is None          # rejected 不可确认


def test_reject_only_before_assign(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-5")
    assert repo.mark_rejected(lead_id, "spam", "广告")
    got = repo.get(lead_id)
    assert got["status"] == "rejected" and got["reject_reason"] == "spam"


def test_convert_race_only_one_wins(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-6")
    assert repo.try_mark_converting(lead_id) is True
    assert repo.try_mark_converting(lead_id) is False    # 并发第二次抢不到
    assert repo.get(lead_id)["status"] == "converting"
    repo.finalize_converted(lead_id, "OPP-TEST", "u-business")
    got = repo.get(lead_id)
    assert got["status"] == "assigned"
    assert got["converted_opportunity_id"] == "OPP-TEST"
    assert repo.mark_rejected(lead_id, "no_need", "") is False


def test_restore_from_converting(repo: LeadRepository):
    lead_id = _mk(repo, "LEADTEST-7")
    repo.try_mark_converting(lead_id)
    repo.restore_from_converting(lead_id)
    assert repo.get(lead_id)["status"] == "new"


def test_list_leads_filters(repo: LeadRepository):
    _mk(repo, "LEADTEST-8")
    page = repo.list_leads(search="训练机")
    assert any(i["lead_id"] == "LEADTEST-8" for i in page["items"])
    page = repo.list_leads(status="assigned")
    assert all(i["status"] == "assigned" for i in page["items"])


def test_business_options_shape(repo: LeadRepository):
    options = repo.business_options()
    assert isinstance(options, list)
    for o in options:
        assert "user_id" in o and "name" in o
