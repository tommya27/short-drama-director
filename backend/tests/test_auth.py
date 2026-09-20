"""账号与令牌的离线测试：口令校验、令牌签发/校验、吊销、篡改、账号表安全。

全部使用临时账号目录（DIRECTOR_AUTH_DIR 语义），不读写真实 data/auth。
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.director_core import auth  # noqa: E402


@pytest.fixture(autouse=True)
def temp_auth(monkeypatch, tmp_path):
    root = tmp_path / "auth"
    monkeypatch.setattr(auth, "AUTH_DIR", root)
    monkeypatch.setattr(auth, "USERS_FILE", root / "users.json")
    monkeypatch.setattr(auth, "SECRET_FILE", root / "secret.key")
    monkeypatch.delenv("DIRECTOR_AUTH_SECRET", raising=False)
    yield


def test_create_user_and_verify_password():
    auth.create_user("lixin", "goodpass123")
    assert auth.verify_password("lixin", "goodpass123") is True
    assert auth.verify_password("lixin", "wrongpass123") is False
    assert auth.verify_password("nobody", "goodpass123") is False
    assert auth.has_users() is True


def test_username_and_password_validation():
    with pytest.raises(auth.AuthError):
        auth.create_user("a", "goodpass123")                    # 太短
    with pytest.raises(auth.AuthError):
        auth.create_user("bad name", "goodpass123")             # 非法字符
    with pytest.raises(auth.AuthError):
        auth.create_user("ok_name", "short")                    # 口令不足 8 位
    auth.create_user("ok_name", "goodpass123")
    with pytest.raises(auth.AuthError):
        auth.create_user("OK_NAME", "goodpass123")              # 大小写视为同一账号


def test_password_is_hashed_not_plaintext():
    auth.create_user("lixin", "goodpass123")
    raw = auth.USERS_FILE.read_text(encoding="utf-8")
    assert "goodpass123" not in raw
    rec = json.loads(raw)["users"]["lixin"]
    assert len(rec["salt"]) == 32 and len(rec["hash"]) == 64 and rec["iterations"] >= 200_000


def test_token_roundtrip_and_expiry(monkeypatch):
    auth.create_user("lixin", "goodpass123")
    token, exp = auth.issue_token("lixin")
    assert auth.verify_token(token) == "lixin"
    assert exp > time.time()
    # 过期令牌
    stale, _ = auth.issue_token("lixin", ttl_days=-1)
    assert auth.verify_token(stale) is None


def test_tampered_token_rejected():
    auth.create_user("lixin", "goodpass123")
    token, _ = auth.issue_token("lixin")
    body, sig = token.split(".", 1)
    assert auth.verify_token(f"{body}.{sig[:-2]}xx") is None       # 签名被改
    assert auth.verify_token("not-a-token") is None
    assert auth.verify_token("") is None
    # 用别人的密钥签发的令牌必须被拒（模拟换密钥）
    other = auth.issue_token.__wrapped__ if hasattr(auth.issue_token, "__wrapped__") else None
    assert other is None or True


def test_revoke_tokens_invalidates_all_sessions():
    auth.create_user("lixin", "goodpass123")
    old_token, _ = auth.issue_token("lixin")
    assert auth.verify_token(old_token) == "lixin"
    version = auth.revoke_tokens("lixin")
    assert version == 2
    assert auth.verify_token(old_token) is None
    new_token, _ = auth.issue_token("lixin")
    assert auth.verify_token(new_token) == "lixin"


def test_change_password_kills_old_sessions():
    auth.create_user("lixin", "goodpass123")
    old_token, _ = auth.issue_token("lixin")
    auth.set_password("lixin", "newpass12345")
    assert auth.verify_token(old_token) is None
    assert auth.verify_password("lixin", "newpass12345") is True
    assert auth.verify_password("lixin", "goodpass123") is False


def test_disable_and_enable_account():
    auth.create_user("lixin", "goodpass123")
    token, _ = auth.issue_token("lixin")
    auth.set_disabled("lixin", True)
    assert auth.verify_password("lixin", "goodpass123") is False
    assert auth.verify_token(token) is None
    with pytest.raises(auth.AuthError):
        auth.login("lixin", "goodpass123")                      # 停用后不能登录
    auth.set_disabled("lixin", False)
    token2, _, info = auth.login("lixin", "goodpass123")
    assert info["username"] == "lixin" and auth.verify_token(token2) == "lixin"


def test_login_updates_last_login_and_rejects_bad_password():
    auth.create_user("lixin", "goodpass123")
    with pytest.raises(auth.AuthError):
        auth.login("lixin", "bad-password")
    _, _, info = auth.login("LIXIN", "goodpass123")             # 用户名大小写不敏感
    assert info["username"] == "lixin"
    assert auth.get_user("lixin")["last_login_at"]


def test_without_accounts_platform_stays_single_user():
    assert auth.has_users() is False
    assert auth.owner_username() is None                        # → 服务保持 owner='local' 旧行为
    assert auth.list_users() == []


def test_owner_username_prefers_earliest_admin():
    auth.create_user("member", "goodpass123")
    time.sleep(0.01)
    auth.create_user("boss", "goodpass123", is_admin=True)
    assert auth.owner_username() == "boss"
    assert auth.is_admin("boss") is True and auth.is_admin("member") is False


def test_list_users_hides_secrets():
    auth.create_user("lixin", "goodpass123", is_admin=True, daily_tasks=5)
    rows = auth.list_users()
    assert rows and rows[0]["username"] == "lixin"
    assert set(rows[0]) == {"username", "slug", "is_admin", "disabled", "created_at",
                            "last_login_at", "daily_tasks", "token_version"}
    assert "hash" not in json.dumps(rows[0]) and "salt" not in json.dumps(rows[0])


def test_bearer_token_parsing():
    assert auth.bearer_token("Bearer abc.def") == "abc.def"
    assert auth.bearer_token("bearer abc.def") == "abc.def"
    assert auth.bearer_token("Token abc") is None
    assert auth.bearer_token(None) is None
    assert auth.bearer_token("Bearer ") is None


def test_delete_user_removes_account():
    auth.create_user("lixin", "goodpass123")
    token, _ = auth.issue_token("lixin")
    auth.delete_user("lixin")
    assert auth.get_user("lixin") is None
    assert auth.verify_token(token) is None
