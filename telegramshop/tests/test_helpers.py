"""Tests for helpers.py — utility functions and RateLimiter."""

from unittest.mock import patch

import pytest

from telegramshop.helpers import (
    RateLimiter,
    escape_html,
    format_sats,
    image_hash,
    truncate,
    validate_email,
)


class TestValidateEmail:
    def test_valid(self):
        assert validate_email("user@example.com") is True

    def test_invalid(self):
        assert validate_email("not-an-email") is False


class TestImageHash:
    def test_deterministic(self):
        h1 = image_hash("https://example.com/img.png")
        h2 = image_hash("https://example.com/img.png")
        assert h1 == h2
        assert len(h1) == 16

    def test_different_inputs(self):
        h1 = image_hash("image_a")
        h2 = image_hash("image_b")
        assert h1 != h2


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 60) == "hello"

    def test_long_text_truncated(self):
        text = "a" * 100
        result = truncate(text, 20)
        assert len(result) == 20
        assert result.endswith("...")


class TestFormatSats:
    def test_format(self):
        assert format_sats(1234567) == "1,234,567"


class TestEscapeHtml:
    def test_escapes(self):
        assert escape_html("<b>Hi & bye</b>") == "&lt;b&gt;Hi &amp; bye&lt;/b&gt;"


class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        # Should not raise
        limiter.check("key1")
        limiter.check("key1")

    def test_blocks_over_limit(self):
        from fastapi import HTTPException

        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.check("key2")
        limiter.check("key2")
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("key2")
        assert exc_info.value.status_code == 429

    @patch("telegramshop.helpers.time.monotonic")
    def test_window_expires(self, mock_monotonic):
        from fastapi import HTTPException

        limiter = RateLimiter(max_requests=2, window_seconds=10)

        # Time 0: two requests fill the window
        mock_monotonic.return_value = 100.0
        limiter.check("key3")
        limiter.check("key3")

        # Still at time 0: should block
        with pytest.raises(HTTPException):
            limiter.check("key3")

        # Time moves past window: should allow again
        mock_monotonic.return_value = 111.0
        limiter.check("key3")  # Should not raise
