from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.passwords import hash_password, verify_password
from app.core.settings import Settings
from app.services import rate_limits


def test_password_hash_is_salted_and_verifies():
    password = "A long movie passphrase 2026!"
    first = hash_password(password)
    assert first.startswith("$argon2id$")
    assert first != hash_password(password)
    assert password not in first
    assert verify_password(password, first)
    assert not verify_password("A wrong movie passphrase", first)


def test_registration_limit_fails_closed(monkeypatch):
    client = Mock()
    client.eval.side_effect = RedisConnectionError("sensitive address")
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    request = Request({"type": "http", "client": ("127.0.0.1", 1)})
    with pytest.raises(HTTPException) as caught:
        rate_limits.limit_registration(request, Settings(_env_file=None))
    assert caught.value.status_code == 503
    assert "sensitive" not in caught.value.detail


def test_registration_rate_limit(monkeypatch):
    client = Mock()
    client.eval.return_value = 11
    monkeypatch.setattr(rate_limits, "get_registration_redis", lambda: client)
    request = Request({"type": "http", "client": ("127.0.0.1", 1)})
    with pytest.raises(HTTPException) as caught:
        rate_limits.limit_registration(request, Settings(_env_file=None))
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "60"
    assert "127.0.0.1" not in client.eval.call_args.args[2]
