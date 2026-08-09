"""Auth foundation tests — password hashing, JWT, login/me/change-password.

No DB dependency: FeedUserRepository is monkeypatched with an in-memory fake.
"""
import pytest

from app.core.security import hash_password, verify_password, create_access_token, decode_token


# ── security: bcrypt ──

def test_hash_password_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert h.startswith("$2")
    assert verify_password("secret123", h)


def test_verify_password_wrong_and_empty():
    h = hash_password("secret123")
    assert not verify_password("wrong", h)
    assert not verify_password("", h)
    assert not verify_password("secret123", "")


# ── security: JWT ──

def test_token_roundtrip():
    t = create_access_token("u_1", "admin")
    payload = decode_token(t)
    assert payload["sub"] == "u_1"
    assert payload["role"] == "admin"


def test_token_invalid_raises():
    with pytest.raises(Exception):
        decode_token("not.a.jwt")


# ── auth API ──

class _FakeRepo:
    """In-memory FeedUserRepository stand-in."""

    def __init__(self, users=None):
        self.users = users or []
        self.calls = []

    def close(self):
        pass

    def get_by_name(self, name):
        self.calls.append(("get_by_name", name))
        for u in self.users:
            if u["name"] == name:
                d = dict(u)
                d.pop("password_hash", None)
                return d
        return None

    def get_by_name_auth(self, name):
        self.calls.append(("get_by_name_auth", name))
        for u in self.users:
            if u["name"] == name:
                return dict(u)
        return None

    def get_auth(self, user_id):
        self.calls.append(("get_auth", user_id))
        for u in self.users:
            if u["user_id"] == user_id:
                return dict(u)
        return None
    def get(self, user_id):
        self.calls.append(("get", user_id))
        for u in self.users:
            if u["user_id"] == user_id:
                return dict(u)
        return None

    def set_password(self, user_id, password_hash):
        self.calls.append(("set_password", user_id))
        for u in self.users:
            if u["user_id"] == user_id:
                u["password_hash"] = password_hash
                return True
        return False


def _patch_repo(monkeypatch, users):
    from app.api import auth as auth_mod
    fake = _FakeRepo(users)
    monkeypatch.setattr(auth_mod, "FeedUserRepository", lambda: fake)
    return fake


def _user(name="业务", role="member", password="pw123456", is_active=True, user_id=None):
    return {
        "user_id": user_id or f"u_{name}",
        "name": name,
        "email": "",
        "role": role,
        "is_active": is_active,
        "created_at": "2026-08-09T00:00:00",
        "password_hash": hash_password(password),
    }


def test_login_success(monkeypatch):
    from app.api.auth import login, LoginBody
    u = _user()
    _patch_repo(monkeypatch, [u])
    resp = login(LoginBody(username="业务", password="pw123456"))
    assert resp["token"]
    assert resp["user"]["name"] == "业务"
    assert resp["user"]["role"] == "member"
    assert "password_hash" not in resp["user"]  # 哈希永不外泄
    # token 应能解出对应用户
    assert decode_token(resp["token"])["sub"] == u["user_id"]


def test_login_wrong_password(monkeypatch):
    from fastapi import HTTPException
    from app.api.auth import login, LoginBody
    _patch_repo(monkeypatch, [_user()])
    with pytest.raises(HTTPException) as ei:
        login(LoginBody(username="业务", password="bad"))
    assert ei.value.status_code == 401


def test_login_unknown_user(monkeypatch):
    from fastapi import HTTPException
    from app.api.auth import login, LoginBody
    _patch_repo(monkeypatch, [_user()])
    with pytest.raises(HTTPException) as ei:
        login(LoginBody(username="不存在", password="pw123456"))
    assert ei.value.status_code == 401


def test_login_legacy_user_without_password(monkeypatch):
    """旧身份（feed picker 创建、无密码）不能登录，直到管理员设密码。"""
    from fastapi import HTTPException
    from app.api.auth import login, LoginBody
    legacy = _user(password="")
    legacy["password_hash"] = None
    _patch_repo(monkeypatch, [legacy])
    with pytest.raises(HTTPException) as ei:
        login(LoginBody(username="业务", password="whatever"))
    assert ei.value.status_code == 401


def test_login_disabled_user(monkeypatch):
    from fastapi import HTTPException
    from app.api.auth import login, LoginBody
    _patch_repo(monkeypatch, [_user(is_active=False)])
    with pytest.raises(HTTPException) as ei:
        login(LoginBody(username="业务", password="pw123456"))
    assert ei.value.status_code == 403


def test_me_returns_user():
    from app.api.auth import me
    u = _user()
    resp = me(user=u)
    assert resp["user"]["name"] == "业务"


def test_change_password_success(monkeypatch):
    from app.api.auth import change_password, ChangePasswordBody
    u = _user()
    old_hash = u["password_hash"]
    fake = _patch_repo(monkeypatch, [u])
    resp = change_password(
        ChangePasswordBody(old_password="pw123456", new_password="newpass1"),
        user=u,
    )
    assert resp["success"] is True
    assert fake.users[0]["password_hash"] != old_hash
    assert verify_password("newpass1", fake.users[0]["password_hash"])


def test_change_password_wrong_old(monkeypatch):
    from fastapi import HTTPException
    from app.api.auth import change_password, ChangePasswordBody
    u = _user()
    _patch_repo(monkeypatch, [u])
    with pytest.raises(HTTPException) as ei:
        change_password(
            ChangePasswordBody(old_password="wrong", new_password="newpass1"),
            user=u,
        )
    assert ei.value.status_code == 400
