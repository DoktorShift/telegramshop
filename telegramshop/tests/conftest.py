"""Shared fixtures and factory functions for telegramshop tests."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out heavy / unavailable imports so the telegramshop package can be
# imported in a plain pytest run (no running LNbits instance).
# ---------------------------------------------------------------------------

# lnbits.db.Database
_lnbits_db = ModuleType("lnbits.db")
_lnbits_db.Database = lambda name: MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits", ModuleType("lnbits"))
sys.modules.setdefault("lnbits.db", _lnbits_db)

# lnbits.helpers
_lnbits_helpers = ModuleType("lnbits.helpers")
_lnbits_helpers.urlsafe_short_hash = lambda: "test_hash_id"  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits.helpers", _lnbits_helpers)

# lnbits.settings
_lnbits_settings_mod = ModuleType("lnbits.settings")
_settings = MagicMock()
_settings.host = "127.0.0.1"
_settings.port = 5000
_settings.lnbits_baseurl = "http://127.0.0.1:5000"
_lnbits_settings_mod.settings = _settings  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits.settings", _lnbits_settings_mod)

# lnbits.core.models
_lnbits_core = ModuleType("lnbits.core")
_lnbits_core_models = ModuleType("lnbits.core.models")
_lnbits_core_models.WalletTypeInfo = type("WalletTypeInfo", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits.core", _lnbits_core)
sys.modules.setdefault("lnbits.core.models", _lnbits_core_models)

# lnbits.decorators
_lnbits_decorators = ModuleType("lnbits.decorators")
_lnbits_decorators.require_admin_key = MagicMock()  # type: ignore[attr-defined]
_lnbits_decorators.require_invoice_key = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits.decorators", _lnbits_decorators)

# lnbits.utils.exchange_rates
_lnbits_utils = ModuleType("lnbits.utils")
_lnbits_utils_er = ModuleType("lnbits.utils.exchange_rates")
_lnbits_utils_er.fiat_amount_as_satoshis = MagicMock()  # type: ignore[attr-defined]
_lnbits_utils_er.satoshis_amount_as_fiat = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("lnbits.utils", _lnbits_utils)
sys.modules.setdefault("lnbits.utils.exchange_rates", _lnbits_utils_er)

# loguru
_loguru = ModuleType("loguru")
_loguru.logger = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("loguru", _loguru)

# ---------------------------------------------------------------------------
# Now safe to import telegramshop models
# ---------------------------------------------------------------------------
from telegramshop.models import (  # noqa: E402
    CartItem,
    Credit,
    CreateShop,
    CheckoutMode,
    Message,
    Order,
    Return,
    Shop,
    ShopProduct,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
SAMPLE_SHOP_ID = "shop_abc123"
SAMPLE_CHAT_ID = 99887766


# ---------------------------------------------------------------------------
# Factory helpers — every field has a sensible default; override via kwargs.
# ---------------------------------------------------------------------------

def make_shop(**overrides) -> Shop:
    defaults = dict(
        id=SAMPLE_SHOP_ID,
        wallet="wallet_001",
        title="Test Shop",
        description="A test shop",
        bot_token=SAMPLE_BOT_TOKEN,
        currency="sat",
        inventory_id="inv_001",
        checkout_mode=CheckoutMode.NONE,
        enable_order_tracking=False,
        use_webhook=False,
        admin_chat_id=None,
        allow_returns=True,
        allow_credit_refund=True,
        return_window_hours=720,
        shipping_flat_rate=0,
        shipping_free_threshold=0,
        shipping_per_kg=0,
        include_tags=None,
        omit_tags=None,
        is_enabled=False,
        webhook_secret=None,
        timestamp="2024-01-01 00:00:00",
    )
    defaults.update(overrides)
    return Shop(**defaults)


def make_order(**overrides) -> Order:
    defaults = dict(
        id="order_001",
        shop_id=SAMPLE_SHOP_ID,
        payment_hash="ph_abc123",
        telegram_chat_id=SAMPLE_CHAT_ID,
        telegram_username="testuser",
        amount_sats=10000,
        currency="sat",
        currency_amount=10000.0,
        cart_json='[{"product_id":"p1","title":"Widget","quantity":2,"price":5000}]',
        buyer_email=None,
        buyer_name=None,
        buyer_address=None,
        has_physical_items=False,
        credit_used=0,
        status="pending",
        fulfillment_status=None,
        fulfillment_note=None,
        timestamp="2024-01-01 00:00:00",
    )
    defaults.update(overrides)
    return Order(**defaults)


def make_product(**overrides) -> ShopProduct:
    defaults = dict(
        id="prod_001",
        title="Widget",
        description="A widget",
        price=5000.0,
        image_url=None,
        image_urls=[],
        category=None,
        tags=[],
        sku=None,
        tax_rate=None,
        is_tax_inclusive=True,
        inventory=100,
        discount_percentage=None,
        disabled=False,
        requires_shipping=False,
        weight_grams=0,
    )
    defaults.update(overrides)
    return ShopProduct(**defaults)


def make_cart_item(**overrides) -> CartItem:
    defaults = dict(
        product_id="prod_001",
        title="Widget",
        quantity=2,
        price=5000.0,
        sku=None,
    )
    defaults.update(overrides)
    return CartItem(**defaults)


def make_credit(**overrides) -> Credit:
    defaults = dict(
        id="credit_001",
        shop_id=SAMPLE_SHOP_ID,
        chat_id=SAMPLE_CHAT_ID,
        amount_sats=500,
        used_sats=0,
        source_return_id=None,
        timestamp="2024-01-01 00:00:00",
    )
    defaults.update(overrides)
    return Credit(**defaults)
