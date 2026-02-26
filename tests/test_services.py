"""Tests for services.py — business logic functions."""

from unittest.mock import AsyncMock, patch

import pytest

from telegramshop.services import (
    calculate_cart,
    format_price,
    sats_amount,
    validate_stock,
)
from telegramshop.tests.conftest import make_cart_item, make_product, make_shop


class TestFormatPrice:
    def test_sats(self):
        assert format_price(1000, "sat") == "1,000 sats"

    def test_fiat(self):
        assert format_price(12.5, "usd") == "12.50 USD"


class TestValidateStock:
    def test_ok(self):
        product = make_product(id="p1", inventory=10)
        item = make_cart_item(product_id="p1", quantity=2)
        assert validate_stock([item], [product]) == []

    def test_unavailable(self):
        item = make_cart_item(product_id="missing", title="Ghost")
        issues = validate_stock([item], [])
        assert len(issues) == 1
        assert "no longer available" in issues[0]

    def test_disabled(self):
        product = make_product(id="p1", disabled=True)
        item = make_cart_item(product_id="p1", title="Disabled Item")
        issues = validate_stock([item], [product])
        assert len(issues) == 1
        assert "no longer available" in issues[0]

    def test_out_of_stock(self):
        product = make_product(id="p1", inventory=0)
        item = make_cart_item(product_id="p1", title="Sold Out")
        issues = validate_stock([item], [product])
        assert len(issues) == 1
        assert "out of stock" in issues[0]

    def test_insufficient(self):
        product = make_product(id="p1", inventory=3)
        item = make_cart_item(product_id="p1", title="Widget", quantity=5)
        issues = validate_stock([item], [product])
        assert len(issues) == 1
        assert "3 available" in issues[0]
        assert "5" in issues[0]


class TestCalculateCart:
    def test_simple_no_tax_no_shipping(self):
        shop = make_shop()
        product = make_product(id="p1", price=100.0)
        item = make_cart_item(product_id="p1", price=100.0, quantity=3)
        subtotal, tax, shipping, total = calculate_cart([item], [product], shop)
        assert subtotal == 300.0
        assert tax == 0.0
        assert shipping == 0.0
        assert total == 300.0

    def test_tax_inclusive(self):
        shop = make_shop()
        product = make_product(
            id="p1", price=110.0, tax_rate=10.0, is_tax_inclusive=True
        )
        item = make_cart_item(product_id="p1", price=110.0, quantity=1)
        subtotal, tax, shipping, total = calculate_cart([item], [product], shop)
        assert subtotal == 110.0
        # tax = 110 * (10 / 110) = 10
        assert abs(tax - 10.0) < 0.01
        # total = subtotal (inclusive tax doesn't add)
        assert abs(total - 110.0) < 0.01

    def test_tax_exclusive(self):
        shop = make_shop()
        product = make_product(
            id="p1", price=100.0, tax_rate=10.0, is_tax_inclusive=False
        )
        item = make_cart_item(product_id="p1", price=100.0, quantity=1)
        subtotal, tax, shipping, total = calculate_cart([item], [product], shop)
        assert subtotal == 100.0
        # tax = 100 * (10 / 100) = 10
        assert abs(tax - 10.0) < 0.01
        # total = subtotal + tax
        assert abs(total - 110.0) < 0.01


class TestSatsAmount:
    @pytest.mark.asyncio
    async def test_sat_currency(self):
        result = await sats_amount(100, "sat")
        assert result == 100

    @pytest.mark.asyncio
    @patch(
        "telegramshop.services.fiat_amount_as_satoshis",
        new_callable=AsyncMock,
        return_value=50000,
    )
    async def test_fiat_currency(self, mock_fiat):
        result = await sats_amount(10.0, "usd")
        assert result == 50000
        mock_fiat.assert_awaited_once_with(10.0, "usd")
