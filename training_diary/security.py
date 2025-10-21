"""Utilities for verifying Telegram Web App authentication."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict
from urllib.parse import unquote_plus

from .config import get_settings


def verify_telegram_webapp(init_data: str) -> Dict[str, Any]:
    """Validate Telegram initData payload and return parsed user payload.

    Raises ValueError when the signature cannot be verified.
    """

    if not init_data:
        raise ValueError("Missing init data")

    parsed = dict(item.split("=", 1) for item in init_data.split("&") if "=" in item)
    parsed = {key: unquote_plus(value) for key, value in parsed.items()}
    data_check_string = "\n".join(
        f"{key}={parsed[key]}"
        for key in sorted(parsed.keys())
        if key != "hash"
    )

    secret_key = hashlib.sha256(get_settings().telegram_bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if parsed.get("hash") != expected_hash:
        raise ValueError("Invalid Telegram signature")

    user_json = parsed.get("user")
    if not user_json:
        raise ValueError("User payload missing")

    return json.loads(user_json)
