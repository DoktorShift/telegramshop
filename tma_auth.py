"""
Telegram Mini App (TMA) initData validation.

Validates the `initData` string sent by the Telegram WebApp SDK using
HMAC-SHA256, as specified in the Telegram Bot API documentation.

No external dependencies — uses only stdlib modules.
"""

import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qs, unquote

from .models import TmaUser

# Maximum age of auth_date before we reject (1 hour)
MAX_AUTH_AGE_SECONDS = 3600


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age: int = MAX_AUTH_AGE_SECONDS,
) -> Optional[TmaUser]:
    """
    Validate Telegram Mini App initData.

    Returns TmaUser on success, None on failure.

    Steps:
    1. Parse initData as URL-encoded params
    2. Extract `hash`, sort remaining params alphabetically
    3. secret_key = HMAC-SHA256("WebAppData", bot_token)
    4. computed = HMAC-SHA256(secret_key, data_check_string)
    5. Compare hashes, check auth_date freshness
    """
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
    except Exception:
        return None

    # Extract hash
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        return None

    # Build data_check_string: sort all params except hash alphabetically
    check_pairs = []
    for key in sorted(parsed.keys()):
        if key == "hash":
            continue
        # parse_qs returns lists; take first value
        value = parsed[key][0]
        check_pairs.append(f"{key}={value}")
    data_check_string = "\n".join(check_pairs)

    # Compute HMAC
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    # Check auth_date freshness
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        return None
    try:
        auth_date = int(auth_date_str)
    except (ValueError, TypeError):
        return None
    if max_age > 0 and (time.time() - auth_date) > max_age:
        return None

    # Extract user info
    user_json = parsed.get("user", [None])[0]
    if not user_json:
        return None
    try:
        user_data = json.loads(unquote(user_json))
    except (json.JSONDecodeError, TypeError):
        return None

    chat_id = user_data.get("id")
    if not chat_id:
        return None

    return TmaUser(
        chat_id=int(chat_id),
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        photo_url=user_data.get("photo_url"),
    )
