import hashlib
import re
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException


class RateLimiter:
    """Simple in-memory sliding-window rate limiter. No external deps."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        """Raise 429 if rate limit exceeded for the given key."""
        now = time.monotonic()
        cutoff = now - self.window
        hits = self._hits[key]
        # Prune old entries
        self._hits[key] = [t for t in hits if t > cutoff]
        if len(self._hits[key]) >= self.max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")
        self._hits[key].append(now)


# Shared limiters
webhook_limiter = RateLimiter(max_requests=60, window_seconds=60)
tma_auth_limiter = RateLimiter(max_requests=10, window_seconds=60)


def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def image_hash(image_ref: str) -> str:
    return hashlib.sha256(image_ref.encode()).hexdigest()[:16]


def truncate(text: str, max_length: int = 60) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_sats(amount: int) -> str:
    return f"{amount:,}"


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_address(
    name: str,
    street: str,
    street2: Optional[str],
    po_box: Optional[str],
    city: str,
    state: Optional[str],
    zip_code: str,
    country: str,
) -> str:
    lines = [name, street]
    if street2:
        lines.append(street2)
    if po_box:
        lines.append(f"PO Box {po_box}")
    city_line = city
    if state:
        city_line += f", {state}"
    city_line += f" {zip_code}"
    lines.append(city_line)
    lines.append(country)
    return "\n".join(lines)
