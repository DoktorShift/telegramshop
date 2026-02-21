"""
Customer-facing TMA (Telegram Mini App) API.

Router prefix: /api/v1/tma

Auth pattern: `Authorization: tma <initData>` header, validated per-request
using the shop's bot_token. Same unauthenticated-at-FastAPI-level pattern
as the existing webhook endpoint.
"""

import json
from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from loguru import logger

from lnbits.core.services import create_invoice
from lnbits.settings import settings

from .helpers import tma_auth_limiter

from .crud import (
    delete_cart,
    get_cart,
    get_order,
    get_orders_by_chat,
    get_returns,
    get_shop,
    get_total_available_credit,
    create_message,
    create_order,
    create_return,
    get_active_return_for_order,
    get_message_thread,
    update_order_status,
    upsert_cart,
    upsert_customer,
    use_credits,
)
from .models import (
    CartItem,
    Shop,
    TmaAuthRequest,
    TmaAuthResponse,
    TmaCartUpdate,
    TmaCheckoutRequest,
    TmaMessageRequest,
    TmaReturnRequest,
    TmaUser,
)
from .product_sources import fetch_inventory_products
from .tasks import bot_manager
from .tma_auth import validate_init_data

tma_api_router = APIRouter(prefix="/api/v1/tma")


# --- Auth helpers ---


async def _get_shop_or_404(shop_id: str) -> Shop:
    shop = await get_shop(shop_id)
    if not shop:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return shop


def _extract_tma_user(
    authorization: Optional[str], bot_token: str
) -> TmaUser:
    """Extract and validate TMA user from Authorization header."""
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Missing TMA authorization")
    init_data = authorization[4:]
    user = validate_init_data(init_data, bot_token)
    if not user:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Invalid or expired initData")
    return user


# --- Auth endpoint ---


@tma_api_router.post("/auth")
async def tma_auth(data: TmaAuthRequest, request: Request):
    """Validate initData, return session info + shop config."""
    client_ip = request.client.host if request.client else "unknown"
    tma_auth_limiter.check(client_ip)
    shop = await _get_shop_or_404(data.shop_id)
    user = validate_init_data(data.init_data, shop.bot_token)
    if not user:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Invalid or expired initData")

    # Track customer
    await upsert_customer(
        shop.id, user.chat_id, user.username, user.first_name
    )

    return TmaAuthResponse(
        chat_id=user.chat_id,
        username=user.username,
        shop_title=shop.title,
        shop_currency=shop.currency,
        checkout_mode=shop.checkout_mode,
        allow_returns=shop.allow_returns,
        welcome_text=shop.description,
    )


# --- Products (public, no auth) ---


@tma_api_router.get("/{shop_id}/products")
async def tma_get_products(shop_id: str):
    """Public product catalog."""
    shop = await _get_shop_or_404(shop_id)

    # Try to get products from running bot first (cached)
    bot = bot_manager.get_bot(shop_id)
    if bot:
        products = bot.get_active_products()
    else:
        # Fallback: fetch directly (needs user_id from wallet)
        from lnbits.core.crud import get_wallet

        wallet = await get_wallet(shop.wallet)
        if not wallet:
            raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, "Wallet not found")
        products = await fetch_inventory_products(shop.inventory_id, wallet.user)
        products = [p for p in products if not p.disabled]

    result = []
    for p in products:
        result.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "price": p.price,
            "image_url": p.image_url,
            "image_urls": p.image_urls,
            "category": p.category,
            "inventory": p.inventory,
            "discount_percentage": p.discount_percentage,
            "requires_shipping": p.requires_shipping,
            "tax_rate": p.tax_rate,
            "is_tax_inclusive": p.is_tax_inclusive,
            "sku": p.sku,
        })
    return result


@tma_api_router.get("/{shop_id}/products/{product_id}")
async def tma_get_product(shop_id: str, product_id: str):
    """Single product detail."""
    shop = await _get_shop_or_404(shop_id)

    bot = bot_manager.get_bot(shop_id)
    if bot:
        product = bot.get_product_by_id(product_id)
    else:
        from lnbits.core.crud import get_wallet

        wallet = await get_wallet(shop.wallet)
        if not wallet:
            raise HTTPException(HTTPStatus.INTERNAL_SERVER_ERROR, "Wallet not found")
        products = await fetch_inventory_products(shop.inventory_id, wallet.user)
        product = next((p for p in products if p.id == product_id), None)

    if not product:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Product not found")

    return {
        "id": product.id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "image_url": product.image_url,
        "image_urls": product.image_urls,
        "category": product.category,
        "inventory": product.inventory,
        "discount_percentage": product.discount_percentage,
        "requires_shipping": product.requires_shipping,
        "weight_grams": product.weight_grams,
        "tax_rate": product.tax_rate,
        "is_tax_inclusive": product.is_tax_inclusive,
        "sku": product.sku,
        "tags": product.tags,
    }


# --- Cart ---


@tma_api_router.get("/{shop_id}/cart")
async def tma_get_cart(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Get persisted cart for authenticated user."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)
    cart = await get_cart(shop_id, user.chat_id)
    if not cart:
        return {"items": []}
    try:
        items = json.loads(cart.cart_json)
    except (json.JSONDecodeError, TypeError):
        items = []
    return {"items": items}


@tma_api_router.put("/{shop_id}/cart")
async def tma_update_cart(
    shop_id: str,
    data: TmaCartUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update cart (validated against stock)."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)

    # Validate items against current stock
    bot = bot_manager.get_bot(shop_id)
    for item in data.items:
        product = bot.get_product_by_id(item.product_id) if bot else None
        if product:
            if product.disabled:
                raise HTTPException(
                    HTTPStatus.BAD_REQUEST,
                    f"{product.title} is no longer available",
                )
            if product.inventory is not None and item.quantity > product.inventory:
                raise HTTPException(
                    HTTPStatus.BAD_REQUEST,
                    f"Only {product.inventory} of {product.title} available",
                )

    cart_json = json.dumps([item.dict() for item in data.items])
    await upsert_cart(shop_id, user.chat_id, cart_json)

    # Track customer
    await upsert_customer(
        shop_id, user.chat_id, user.username, user.first_name
    )

    return {"success": True}


@tma_api_router.delete("/{shop_id}/cart")
async def tma_clear_cart(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Clear cart."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)
    await delete_cart(shop_id, user.chat_id)
    return {"success": True}


# --- Checkout ---


@tma_api_router.post("/{shop_id}/checkout")
async def tma_checkout(
    shop_id: str,
    data: TmaCheckoutRequest,
    authorization: Optional[str] = Header(None),
):
    """Create order + invoice, return bolt11."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)

    # Load cart from DB
    cart_record = await get_cart(shop_id, user.chat_id)
    if not cart_record:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Cart is empty")

    try:
        cart_items_raw = json.loads(cart_record.cart_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Cart is empty")

    if not cart_items_raw:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Cart is empty")

    cart_items = [CartItem(**item) for item in cart_items_raw]

    # Calculate totals using bot's calculate_cart if available
    bot = bot_manager.get_bot(shop_id)
    if bot:
        # Build a temporary session-like object for calculation
        from .models import UserSession

        temp_session = UserSession()
        temp_session.cart = cart_items
        _, _, _, total = bot.calculate_cart(temp_session)
        total_sats = await bot.sats_amount(total)
        has_physical = bot.cart_has_physical_items(temp_session)
    else:
        # Fallback: simple calculation without shipping/tax
        from lnbits.utils.exchange_rates import fiat_amount_as_satoshis

        total = sum(item.price * item.quantity for item in cart_items)
        if shop.currency == "sat":
            total_sats = int(total)
        else:
            total_sats = await fiat_amount_as_satoshis(total, shop.currency)
        has_physical = False

    # Apply store credit
    credit_used = 0
    available_credit = await get_total_available_credit(shop_id, user.chat_id)
    if available_credit > 0:
        credit_used = min(available_credit, total_sats)
        total_sats -= credit_used
        await use_credits(shop_id, user.chat_id, credit_used)

    cart_json = json.dumps([item.dict() for item in cart_items])

    if total_sats <= 0:
        # Fully covered by credit
        order = await create_order(
            shop_id=shop_id,
            payment_hash="credit_" + str(user.chat_id),
            telegram_chat_id=user.chat_id,
            telegram_username=user.username,
            amount_sats=0,
            currency=shop.currency,
            currency_amount=total,
            cart_json=cart_json,
            buyer_email=data.buyer_email,
            buyer_name=data.buyer_name,
            buyer_address=data.buyer_address,
            has_physical_items=has_physical,
        )
        await update_order_status(order.id, "paid")
        await delete_cart(shop_id, user.chat_id)

        # Send confirmation via bot
        if bot:
            await bot.send_payment_confirmation(
                user.chat_id, order, credit_used
            )

        return {
            "order_id": order.id,
            "status": "paid",
            "amount_sats": 0,
            "credit_used": credit_used,
        }

    # Create Lightning invoice
    original_sats = total_sats + credit_used
    if credit_used > 0:
        memo = (
            f"Order from {shop.title} "
            f"({original_sats:,} sats - {credit_used:,} credit "
            f"= {total_sats:,} sats)"
        )
    else:
        memo = f"Order from {shop.title}"
    try:
        payment = await create_invoice(
            wallet_id=shop.wallet,
            amount=total_sats,
            memo=memo,
            expiry=900,
            extra={
                "tag": "telegramshop",
                "shop_id": shop_id,
                "chat_id": user.chat_id,
            },
        )
    except Exception as e:
        logger.error(f"TMA: Failed to create invoice: {e}")
        raise HTTPException(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Failed to create invoice",
        )

    order = await create_order(
        shop_id=shop_id,
        payment_hash=payment.payment_hash,
        telegram_chat_id=user.chat_id,
        telegram_username=user.username,
        amount_sats=total_sats,
        currency=shop.currency,
        currency_amount=total,
        cart_json=cart_json,
        buyer_email=data.buyer_email,
        buyer_name=data.buyer_name,
        buyer_address=data.buyer_address,
        has_physical_items=has_physical,
    )

    # Clear cart after order creation
    await delete_cart(shop_id, user.chat_id)

    return {
        "order_id": order.id,
        "status": "pending",
        "amount_sats": total_sats,
        "original_total_sats": original_sats,
        "credit_used": credit_used,
        "bolt11": payment.bolt11,
        "payment_hash": payment.payment_hash,
    }


# --- Orders ---


@tma_api_router.get("/{shop_id}/orders")
async def tma_get_orders(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Customer's order history."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)
    orders = await get_orders_by_chat(shop_id, user.chat_id)
    return [
        {
            "id": o.id,
            "amount_sats": o.amount_sats,
            "currency": o.currency,
            "currency_amount": o.currency_amount,
            "cart_json": o.cart_json,
            "status": o.status,
            "fulfillment_status": o.fulfillment_status,
            "fulfillment_note": o.fulfillment_note,
            "timestamp": o.timestamp,
        }
        for o in orders
    ]


# --- Credits ---


@tma_api_router.get("/{shop_id}/credits")
async def tma_get_credits(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Store credit balance + individual credit entries."""
    from .crud import get_available_credits

    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)
    balance = await get_total_available_credit(shop_id, user.chat_id)
    credits = await get_available_credits(shop_id, user.chat_id)
    return {
        "balance_sats": balance,
        "credits": [
            {
                "id": c.id,
                "amount_sats": c.amount_sats,
                "used_sats": c.used_sats,
                "remaining_sats": c.amount_sats - c.used_sats,
                "source": "return" if c.source_return_id else "gift",
                "timestamp": c.timestamp,
            }
            for c in credits
        ],
    }


# --- Messages ---


@tma_api_router.post("/{shop_id}/messages")
async def tma_send_message(
    shop_id: str,
    data: TmaMessageRequest,
    authorization: Optional[str] = Header(None),
):
    """Send message to admin."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)

    msg = await create_message(
        shop_id=shop_id,
        chat_id=user.chat_id,
        direction="in",
        content=data.content,
        username=user.username,
        order_id=data.order_id,
    )

    # Notify admin via bot
    bot = bot_manager.get_bot(shop_id)
    if bot:
        await bot.notify_admin_message(
            user.chat_id, user.username, data.content, data.order_id
        )

    return {"id": msg.id, "timestamp": msg.timestamp}


@tma_api_router.get("/{shop_id}/messages")
async def tma_get_messages(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Get message history for customer."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)
    messages = await get_message_thread(shop_id, user.chat_id)
    return [
        {
            "id": m.id,
            "direction": m.direction,
            "content": m.content,
            "order_id": m.order_id,
            "timestamp": m.timestamp,
        }
        for m in messages
    ]


# --- Returns ---


@tma_api_router.post("/{shop_id}/returns")
async def tma_submit_return(
    shop_id: str,
    data: TmaReturnRequest,
    authorization: Optional[str] = Header(None),
):
    """Submit return request."""
    shop = await _get_shop_or_404(shop_id)
    if not shop.allow_returns:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Returns not allowed")

    user = _extract_tma_user(authorization, shop.bot_token)

    order = await get_order(data.order_id)
    if not order or order.telegram_chat_id != user.chat_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    if order.status != "paid":
        raise HTTPException(
            HTTPStatus.BAD_REQUEST, "Returns only for paid orders"
        )

    # Block duplicate returns
    existing = await get_active_return_for_order(data.order_id)
    if existing:
        raise HTTPException(
            HTTPStatus.CONFLICT, "Return already exists for this order"
        )

    # Parse return items and calculate refund
    try:
        return_items = json.loads(data.items_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Invalid items_json")

    refund_amount = sum(
        i["price"] * i["quantity"] for i in return_items
    )

    bot = bot_manager.get_bot(shop_id)
    if bot:
        refund_sats = await bot.sats_amount(refund_amount)
    else:
        from lnbits.utils.exchange_rates import fiat_amount_as_satoshis

        if shop.currency == "sat":
            refund_sats = int(refund_amount)
        else:
            refund_sats = await fiat_amount_as_satoshis(
                refund_amount, shop.currency
            )

    ret = await create_return(
        shop_id=shop_id,
        order_id=data.order_id,
        chat_id=user.chat_id,
        items_json=data.items_json,
        refund_amount_sats=refund_sats,
        reason=data.reason,
    )

    # Notify admin
    if bot:
        await bot.notify_admin_return(ret, order)

    return {
        "id": ret.id,
        "status": ret.status,
        "refund_amount_sats": refund_sats,
    }


@tma_api_router.get("/{shop_id}/returns")
async def tma_get_returns(
    shop_id: str, authorization: Optional[str] = Header(None)
):
    """Customer's return history."""
    shop = await _get_shop_or_404(shop_id)
    user = _extract_tma_user(authorization, shop.bot_token)

    # Get all returns for this customer across all orders
    all_returns = await get_returns(shop_id)
    customer_returns = [
        r for r in all_returns if r.chat_id == user.chat_id
    ]

    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "items_json": r.items_json,
            "reason": r.reason,
            "refund_amount_sats": r.refund_amount_sats,
            "refund_method": r.refund_method,
            "status": r.status,
            "admin_note": r.admin_note,
            "timestamp": r.timestamp,
        }
        for r in customer_returns
    ]
