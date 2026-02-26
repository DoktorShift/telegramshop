"""Tests for Telegram Mini App initData HMAC validation."""

import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlencode

import pytest

from telegramshop.tma_auth import validate_init_data

BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


def _build_init_data(
    bot_token: str,
    user_data: dict | None = None,
    auth_date: int | None = None,
    *,
    tamper_hash: bool = False,
    omit_hash: bool = False,
    omit_user: bool = False,
) -> str:
    """Construct a properly-signed initData string."""
    if auth_date is None:
        auth_date = int(time.time())
    if user_data is None:
        user_data = {"id": 12345, "username": "tester", "first_name": "Test"}

    params: dict[str, str] = {"auth_date": str(auth_date)}
    if not omit_user:
        params["user"] = json.dumps(user_data)

    # Build data_check_string (sorted, newline-separated)
    check_string = "\n".join(
        f"{k}={params[k]}" for k in sorted(params.keys())
    )

    # Compute HMAC
    secret = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret, check_string.encode(), hashlib.sha256
    ).hexdigest()

    if tamper_hash:
        computed_hash = "0" * 64

    if not omit_hash:
        params["hash"] = computed_hash

    return urlencode(params)


# --- Tests ---


class TestValidInitData:
    def test_valid_init_data(self):
        user = {"id": 42, "username": "alice", "first_name": "Alice"}
        init_data = _build_init_data(BOT_TOKEN, user)
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result is not None
        assert result.chat_id == 42
        assert result.username == "alice"
        assert result.first_name == "Alice"

    def test_invalid_hash(self):
        init_data = _build_init_data(BOT_TOKEN, tamper_hash=True)
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_missing_hash(self):
        init_data = _build_init_data(BOT_TOKEN, omit_hash=True)
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_expired_auth_date(self):
        old = int(time.time()) - 7200  # 2 hours ago
        init_data = _build_init_data(BOT_TOKEN, auth_date=old)
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_max_age_zero_accepts_old(self):
        old = int(time.time()) - 86400  # 24 hours ago
        user = {"id": 1, "username": "u", "first_name": "U"}
        init_data = _build_init_data(BOT_TOKEN, user, auth_date=old)
        result = validate_init_data(init_data, BOT_TOKEN, max_age=0)
        assert result is not None
        assert result.chat_id == 1

    def test_missing_user(self):
        init_data = _build_init_data(BOT_TOKEN, omit_user=True)
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_invalid_user_json(self):
        auth_date = int(time.time())
        params = {"auth_date": str(auth_date), "user": "not-json{{{"}
        check_string = "\n".join(
            f"{k}={params[k]}" for k in sorted(params.keys())
        )
        secret = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        h = hmac.new(
            secret, check_string.encode(), hashlib.sha256
        ).hexdigest()
        params["hash"] = h
        init_data = urlencode(params)
        assert validate_init_data(init_data, BOT_TOKEN) is None

    def test_wrong_bot_token(self):
        init_data = _build_init_data(BOT_TOKEN)
        assert validate_init_data(init_data, "999999:WRONG-TOKEN") is None
