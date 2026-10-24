"""评论 @提及 — 解析器边界 + feed 接线（mock，不依赖 DB）。"""
import pytest

from app.services.mention import parse_mentions


ROSTER = {
    "张三": ["u-zhang"],
    "张三丰": ["u-zhangsanfeng"],
    "李四": ["u-li-1", "u-li-2"],  # 同名多人
    "王五": ["u-wang"],
}


def ids(body: str) -> list:
    return parse_mentions(body, ROSTER)


# ── parse_mentions ──

def test_basic_mention():
    assert ids("@张三 看下这个方案") == ["u-zhang"]


def test_longest_name_wins():
    # 名册同时有 张三/张三丰，@张三丰 只命中张三丰
    assert ids("@张三丰 来看下") == ["u-zhangsanfeng"]


def test_prefix_name_matches_when_no_longer_in_roster_body():
    # 名册有张三丰，正文 @张三 仍命中张三
    assert ids("@张三 收到请回复") == ["u-zhang"]


def test_name_without_mention_sign_is_plain_text():
    assert ids("张三 看下这个") == []


def test_multiple_mentions_deduped():
    assert ids("@张三 @李四 @张三") == ["u-zhang", "u-li-1", "u-li-2"]


def test_same_name_multi_ids():
    assert ids("问下@李四") == ["u-li-1", "u-li-2"]


def test_no_match_is_plain_text():
    assert ids("@赵六 不在名册") == []


def test_email_not_mention():
    assert ids("联系 a@b.com 收") == []


def test_no_at_sign():
    assert ids("普通文本") == []


def test_empty_body():
    assert ids("") == []


def test_empty_roster():
    assert parse_mentions("@张三", {}) == []


def test_mention_at_end():
    assert ids("这个型号问@王五") == ["u-wang"]


def test_consecutive_mentions_no_space():
    assert ids("@张三@李四") == ["u-zhang", "u-li-1", "u-li-2"]


def test_mention_with_punctuation_suffix():
    assert ids("@张三：请看，谢谢") == ["u-zhang"]


def test_unknown_at_then_known_later():
    assert ids("@未知 @王五") == ["u-wang"]


# ── feed._notify_mentions 接线 ──

OPP = {"opportunity_id": "opp-1", "customer_name": "测试客户", "owner_user_id": "u-author"}


class _FakeUserRepo:
    def list_all(self):
        return [
            {"user_id": "u-author", "name": "作者", "role": "business", "is_active": True},
            {"user_id": "u-zhang", "name": "张三", "role": "te", "is_active": True},
            {"user_id": "u-wang", "name": "王五", "role": "director", "is_active": True},
            {"user_id": "u-dead", "name": "停用", "role": "te", "is_active": False},
        ]

    def close(self):
        pass


@pytest.fixture()
def wire(monkeypatch):
    """接管名册 / 权限 / notify_users，返回捕获器。"""
    from app.api import feed as feed_mod

    captured = {"calls": []}

    def fake_notify(user_ids, type, title, body="", opportunity_id="", payload=None, exclude_user_id=""):
        captured["calls"].append({
            "user_ids": list(user_ids), "type": type, "title": title, "body": body,
            "opportunity_id": opportunity_id, "exclude": exclude_user_id,
        })

    monkeypatch.setattr(feed_mod, "FeedUserRepository", lambda: _FakeUserRepo())
    monkeypatch.setattr(feed_mod, "user_can_access_opportunity",
                        lambda user, opp: (user or {}).get("user_id") != "u-wang")
    monkeypatch.setattr("app.services.notification_hub.notify_users", fake_notify)
    return captured


def test_notify_mention_happy_path(wire):
    from app.api.feed import _notify_mentions
    _notify_mentions("@张三 请看", OPP, {"user_id": "u-author", "name": "作者"}, "m1", "boming")
    assert len(wire["calls"]) == 1
    call = wire["calls"][0]
    assert call["user_ids"] == ["u-zhang"]
    assert call["type"] == "comment_mention"
    assert "测试客户" in call["title"]
    assert call["opportunity_id"] == "opp-1"
    assert call["exclude"] == "u-author"


def test_notify_excludes_author_and_inactive(wire):
    from app.api.feed import _notify_mentions
    # @作者(自己) 不通知；停用用户不在名册解析范围
    _notify_mentions("@作者 @停用 @张三", OPP, {"user_id": "u-author"}, "m1", None)
    assert len(wire["calls"]) == 1
    assert wire["calls"][0]["user_ids"] == ["u-zhang"]


def test_notify_restricted_user_redacted(wire):
    from app.api.feed import _notify_mentions
    # 王五被 mock 为无权限：单独一条脱敏通知（无客户名/无正文/不跳转）
    _notify_mentions("@张三 @王五 机密内容", OPP, {"user_id": "u-author"}, "m1", None)
    assert len(wire["calls"]) == 2
    normal = next(c for c in wire["calls"] if c["user_ids"] == ["u-zhang"])
    redacted = next(c for c in wire["calls"] if c["user_ids"] == ["u-wang"])
    assert "测试客户" in normal["title"] and normal["body"].endswith("机密内容")
    assert "测试客户" not in redacted["title"] and redacted["body"] == ""
    assert redacted["opportunity_id"] == ""


def test_notify_no_mention_no_call(wire):
    from app.api.feed import _notify_mentions
    _notify_mentions("普通评论", OPP, {"user_id": "u-author"}, "m1", None)
    assert wire["calls"] == []


def test_notify_body_truncated(wire):
    from app.api.feed import _notify_mentions
    long_body = "长" * 200
    _notify_mentions(f"@张三 {long_body}", OPP, {"user_id": "u-author"}, "m1", None)
    assert len(wire["calls"][0]["body"]) <= 121 and wire["calls"][0]["body"].endswith("…")


def test_notify_failure_never_raises(wire, monkeypatch):
    from app.api import feed as feed_mod
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("app.services.notification_hub.notify_users", boom)
    # 不抛异常即通过
    feed_mod._notify_mentions("@张三", OPP, {"user_id": "u-author"}, "m1", None)
