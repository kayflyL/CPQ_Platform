"""feed 评论 @提及 全链路集成测 — 真路由 + 真库，企微 stub，scratch 商机物理清理。

覆盖：HTTP(multipart) → JWT 依赖 → feed 落库 → 名册解析 → notify_users 落库。
不走真实企微（_relay_wecom stub 捕获）；scratch 商机/评论/通知行 finally 全删。
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_current_user, user_can_access_opportunity
from app.main import app
from app.models.base import Opportunity_SessionLocal
from app.models.feed_message import FeedMessage
from app.models.notification import Notification
from app.models.opportunity import Opportunity

AUTHOR = {"user_id": "u-test-mention-author", "name": "集成作者", "role": "business"}
PEER = {"user_id": "u-test-mention-peer", "name": "集合同事", "role": "director"}
OPP_ID = f"zzztest-mention-{uuid.uuid4().hex[:8]}"


class _FakeUserRepo:
    def list_all(self):
        return [
            {**AUTHOR, "is_active": True},
            {**PEER, "is_active": True},
        ]

    def close(self):
        pass


@pytest.fixture()
def env(monkeypatch):
    from app.api import feed as feed_mod
    from app.services import notification_hub

    captured = {"wecom": []}
    monkeypatch.setattr(feed_mod, "FeedUserRepository", lambda: _FakeUserRepo())
    monkeypatch.setattr(notification_hub, "_relay_wecom",
                        lambda user_ids, type_, title, body="": captured["wecom"].append(
                            {"to": list(user_ids), "type": type_, "title": title, "body": body}))
    app.dependency_overrides[get_current_user] = lambda: AUTHOR
    yield captured
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def scratch_opp():
    session = Opportunity_SessionLocal()
    try:
        session.add(Opportunity(opportunity_id=OPP_ID, customer_name="ZZZTEST提及集成测",
                                owner_user_id=AUTHOR["user_id"]))
        session.commit()
    finally:
        session.close()
    yield OPP_ID
    # 物理清理：通知(payload 含本次 message_id 或测试用户) / feed 消息 / 商机行
    session = Opportunity_SessionLocal()
    try:
        session.query(Notification).filter(
            (Notification.payload.like(f"%{OPP_ID}%"))
            | (Notification.user_id.in_([AUTHOR["user_id"], PEER["user_id"]]))
        ).delete(synchronize_session=False)
        session.query(FeedMessage).filter(FeedMessage.opportunity_id == OPP_ID).delete(
            synchronize_session=False)
        session.query(Opportunity).filter(Opportunity.opportunity_id == OPP_ID).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _client() -> TestClient:
    return TestClient(app)


def test_post_mention_creates_notification_end_to_end(env, scratch_opp):
    client = _client()
    resp = client.post(f"/api/feed/{scratch_opp}/messages",
                       data={"body": f"@{PEER['name']} 请看这个方案", "node_key": "boming"})
    assert resp.status_code == 200, resp.text
    message_id = resp.json()["message"]["message_id"]

    # feed 行落库
    session = Opportunity_SessionLocal()
    try:
        rows = session.query(FeedMessage).filter(
            FeedMessage.message_id == message_id).all()
        assert len(rows) == 1 and rows[0].kind == "comment"
    finally:
        session.close()

    # 通知：peer 一条 comment_mention；作者零条
    session = Opportunity_SessionLocal()
    try:
        notifs = session.query(Notification).filter(
            Notification.type == "comment_mention",
            Notification.payload.like(f"%{message_id}%"),
        ).all()
    finally:
        session.close()
    by_user = {n.user_id: n for n in notifs}
    assert set(by_user) == {PEER["user_id"]}, f"应只有 peer 收到: {set(by_user)}"

    n = by_user[PEER["user_id"]]
    peer_view = user_can_access_opportunity({**PEER}, {"opportunity_id": scratch_opp,
                                                       "owner_user_id": AUTHOR["user_id"],
                                                       "customer_name": ""})
    if peer_view:
        assert n.opportunity_id == scratch_opp
        assert "请看这个方案" in (n.body or "")
        assert AUTHOR["name"] in n.title and "ZZZTEST提及集成测" in n.title
    else:
        # 本地 roles 被改过导致 director 无全量权限时走脱敏分支
        assert n.opportunity_id == "" and not n.body

    # 企微 stub：恰好一次，目标是 peer
    assert len(env["wecom"]) == 1
    assert env["wecom"][0]["to"] == [PEER["user_id"]]
    assert env["wecom"][0]["type"] == "comment_mention"


def test_post_plain_comment_no_notification(env, scratch_opp):
    client = _client()
    resp = client.post(f"/api/feed/{scratch_opp}/messages", data={"body": "普通评论"})
    assert resp.status_code == 200
    session = Opportunity_SessionLocal()
    try:
        notifs = session.query(Notification).filter(
            Notification.type == "comment_mention",
            Notification.opportunity_id == scratch_opp,
        ).all()
        assert notifs == []
    finally:
        session.close()


def test_unauthed_post_rejected(env, scratch_opp):
    """依赖覆盖移除后（真 JWT 校验），无 token 401。"""
    app.dependency_overrides.pop(get_current_user, None)
    client = _client()
    resp = client.post(f"/api/feed/{scratch_opp}/messages", data={"body": "x"})
    assert resp.status_code == 401
