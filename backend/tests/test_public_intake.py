"""公开 intake 端点测试：无鉴权可达、DTO 无价格键（递归断言）、蜜罐静默、限流 429、
手机号并入、附件保存与格式校验。走本地开发库，测试线索用 199 前缀手机号自清理。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re

from fastapi.testclient import TestClient

from app.main import app
from app.models.lead import OpportunityLead
from app.repository.lead_repo import LeadRepository
from app.utils.rate_limit import SlidingWindowLimiter
from app.api import public_intake

client = TestClient(app)

_FORBIDDEN_KEY_RE = re.compile(r"(price|cost|margin|profit|drawing_config|base_config_id|is_published)", re.I)


def _assert_no_sensitive_keys(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not _FORBIDDEN_KEY_RE.search(str(k)), f"sensitive key leaked at {path}.{k}"
            _assert_no_sensitive_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_sensitive_keys(v, f"{path}[{i}]")


def _fresh_limiters():
    public_intake._catalog_limiter = SlidingWindowLimiter()
    public_intake._submit_ip_limiter = SlidingWindowLimiter()
    public_intake._submit_global_limiter = SlidingWindowLimiter()


def _cleanup():
    repo = LeadRepository()
    try:
        repo.session.query(OpportunityLead).filter(OpportunityLead.contact_phone.like("199%")).delete()
        repo.session.commit()
    finally:
        repo.close()


def setup_function():
    _fresh_limiters()
    _cleanup()


def teardown_function():
    _cleanup()


def test_public_catalog_gets_200_without_auth_and_no_sensitive_keys():
    r = client.get("/api/public/catalog/types")
    assert r.status_code == 200
    _assert_no_sensitive_keys(r.json())

    r = client.get("/api/public/catalog/models")
    assert r.status_code == 200
    _assert_no_sensitive_keys(r.json())
    models = r.json()["models"]
    for m in models:
        assert "base_config_id" not in m

    r = client.get("/api/public/catalog/banner")
    assert r.status_code == 200
    _assert_no_sensitive_keys(r.json())

    if models:
        r = client.get(f"/api/public/catalog/models/{models[0]['id']}")
        assert r.status_code == 200
        _assert_no_sensitive_keys(r.json())


def test_public_model_404_when_not_published_or_missing():
    assert client.get("/api/public/catalog/models/99999999").status_code == 404


def test_submit_requires_phone_and_text():
    r = client.post("/api/public/leads", data={
        "requirement_text": "短", "company": "测试", "contact_phone": "19912345678",
    })
    assert r.status_code == 400
    r = client.post("/api/public/leads", data={
        "requirement_text": "想要两台训练机，Q1 交货", "company": "测试", "contact_phone": "12345",
    })
    assert r.status_code == 400


def test_submit_ok_and_dedup_merge():
    payload = {
        "requirement_text": "想要两台 8 卡训练机，Q1 交货，机房已就绪",
        "company": "先锋科技", "contact_name": "张工", "contact_phone": "19912345678",
        "source": "catalog_model",
        "config_slots": '{"config_relation":"compose","configs":[{"name":"CFG1","server_model":"擎天 T-4U","qty":2,"warranty_years":"3"}]}',
    }
    r = client.post("/api/public/leads", data=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["merged"] is False and body["lead_id"]

    repo = LeadRepository()
    try:
        got = repo.get(body["lead_id"])
        assert got["company"] == "先锋科技"
        assert got["config_slots"]["configs"][0]["server_model"] == "擎天 T-4U"
        assert got["config_slots"]["purchase_qty"] == 2

        r2 = client.post("/api/public/leads", data={**payload, "requirement_text": "补充：最好 5 年质保"})
        assert r2.json()["merged"] is True
        merged = repo.get(body["lead_id"])
        assert merged["dedup_count"] == 2
        assert "补充" in merged["requirement_text"]
    finally:
        repo.close()


def test_honeypot_silent_drop():
    r = client.post("/api/public/leads", data={
        "requirement_text": "机器人灌水内容超过五个字", "company": "机器人公司",
        "contact_phone": "19912345678", "website": "http://spam.example",
    })
    assert r.status_code == 200 and r.json() == {"ok": True, "lead_id": None, "merged": False}
    repo = LeadRepository()
    try:
        assert repo.find_open_by_phone("19912345678") is None
    finally:
        repo.close()


def test_rate_limit_429_on_sixth_submit(monkeypatch):
    _fresh_limiters()
    base = {"requirement_text": "限流测试需求描述足够长", "company": "限流公司"}
    statuses = []
    for i in range(6):
        r = client.post("/api/public/leads", data={**base, "contact_phone": f"1991234000{i}"})
        statuses.append(r.status_code)
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_attachment_upload_and_reject_bad_ext():
    files = [("files", ("配置清单.pdf", b"%PDF-1.4 fake", "application/pdf"))]
    r = client.post("/api/public/leads", data={
        "requirement_text": "带附件的测试需求描述", "company": "附件公司", "contact_phone": "19912345679",
    }, files=files)
    assert r.status_code == 200
    lead_id = r.json()["lead_id"]
    repo = LeadRepository()
    try:
        got = repo.get(lead_id)
        assert len(got["attachments"]) == 1
        assert got["attachments"][0]["name"] == "配置清单.pdf"
        assert got["attachments"][0]["storage_key"].startswith("lead-attachments/")
    finally:
        repo.close()
    # 顺带清掉落盘文件
    import shutil
    from app.utils.file_storage import FileStorage
    d = FileStorage().base_path / "lead-attachments" / lead_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)

    r = client.post("/api/public/leads", data={
        "requirement_text": "坏附件格式测试需求描述", "company": "附件公司", "contact_phone": "19912345680",
    }, files=[("files", ("evil.exe", b"MZ fake", "application/x-msdownload"))])
    assert r.status_code == 400
