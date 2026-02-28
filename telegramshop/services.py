"""
Pure business-logic functions extracted from TelegramBot.

These have no dependency on bot instances, Telegram sessions, or httpx clients.
Both telegram.py and views_api_tma.py import from here.
"""

from typing import List, Optional, Tuple

from lnbits.utils.exchange_rates import (
    fiat_amount_as_satoshis,
    satoshis_amount_as_fiat,
)

from .helpers import format_sats
from .models import CartItem, Shop, ShopProduct


async def sats_amount(amount: float, currency: str) -> int:
    """Convert a price amount to satoshis."""
    if currency == "sat":
        return int(amount)
    return await fiat_amount_as_satoshis(amount, currency)


async def fiat_display(sats: int, currency: str) -> Optional[str]:
    """Return a fiat display string like '~12.34 USD', or None for sat shops."""
    if currency == "sat":
        return None
    fiat = await satoshis_amount_as_fiat(sats, currency)
    return f"~{fiat:.2f} {currency.upper()}"


def format_price(amount: float, currency: str) -> str:
    """Format a price for display."""
    if currency == "sat":
        return f"{format_sats(int(amount))} sats"
    return f"{amount:.2f} {currency.upper()}"


def cart_has_physical_items(
    cart_items: List[CartItem], products: List[ShopProduct]
) -> bool:
    """Check if any cart item requires shipping."""
    product_map = {p.id: p for p in products}
    for item in cart_items:
        product = product_map.get(item.product_id)
        if product and product.requires_shipping:
            return True
    return False


def validate_stock(
    cart_items: List[CartItem],
    products: List[ShopProduct],
    reserved: Optional[dict] = None,
) -> List[str]:
    """Validate cart items against current stock minus existing reservations.

    Args:
        reserved: dict mapping product_id -> already-reserved quantity.
                  If None, reservations are not considered (cart updates).

    Returns a list of human-readable issue strings (empty = all OK).
    """
    product_map = {p.id: p for p in products}
    reserved = reserved or {}
    issues: List[str] = []
    for item in cart_items:
        product = product_map.get(item.product_id)
        if not product:
            issues.append(f"{item.title} is no longer available.")
            continue
        if product.disabled:
            issues.append(f"{item.title} is no longer available.")
            continue
        if product.inventory is not None:
            effective = product.inventory - reserved.get(item.product_id, 0)
            if item.quantity > effective:
                if effective <= 0:
                    issues.append(f"{item.title} is out of stock.")
                else:
                    issues.append(
                        f"{item.title}: only {effective} available"
                        f" (you have {item.quantity})."
                    )
    return issues


def calculate_cart(
    cart_items: List[CartItem],
    products: List[ShopProduct],
    shop: Shop,
) -> Tuple[float, float, float, float]:
    """Calculate cart totals.

    Returns (subtotal, tax_total, shipping, total).
    """
    product_map = {p.id: p for p in products}
    subtotal = 0.0
    tax_total = 0.0
    total_weight_grams = 0
    has_physical = False
    tax_inclusive = True

    for item in cart_items:
        product = product_map.get(item.product_id)
        # Use canonical catalog price, never the client-supplied price
        price = product.price if product else item.price
        item_total = price * item.quantity
        tax_rate = 0.0
        if product and product.tax_rate is not None:
            tax_rate = product.tax_rate
            tax_inclusive = product.is_tax_inclusive
        if product and product.requires_shipping:
            has_physical = True
            total_weight_grams += (product.weight_grams or 0) * item.quantity

        if tax_rate > 0:
            if tax_inclusive:
                tax_amount = item_total * (tax_rate / (100 + tax_rate))
            else:
                tax_amount = item_total * (tax_rate / 100)
            tax_total += tax_amount

        subtotal += item_total

    shipping = 0.0
    if has_physical:
        flat = shop.shipping_flat_rate or 0
        per_kg = shop.shipping_per_kg or 0
        threshold = shop.shipping_free_threshold or 0

        shipping = flat + (total_weight_grams / 1000.0) * per_kg

        if threshold > 0 and subtotal >= threshold:
            shipping = 0.0

    if tax_inclusive:
        total = subtotal + shipping
    else:
        total = subtotal + tax_total + shipping
    return subtotal, tax_total, shipping, total
