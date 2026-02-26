"""
Admin-facing TMA (Telegram Mini App) API.

Router prefix: /api/v1/tma-admin

Auth pattern: `Authorization: tma <initData>` header, validated per-request
using the shop's bot_token. Extra gate: chat_id == int(shop.admin_chat_id).
Calls CRUD functions directly — no internal HTTP calls needed.
"""

from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from loguru import logger

from .helpers import tma_admin_auth_limiter, tma_admin_api_limiter
from .crud import (
    create_credit,
    create_message,
    expire_stale_pending_orders,
    get_customer_by_chat,
    get_customers_with_stats,
    get_daily_revenue,
    get_message_conversations,
    get_message_count_by_chat,
    get_message_thread,
    get_order,
    get_orders,
    get_orders_by_chat,
    get_return,
    get_returns,
    get_returns_by_chat,
    get_shop,
    get_stats,
    get_total_available_credit,
    mark_thread_read,
    search_orders,
    update_order_fulfillment,
    update_return_status,
)
from .models import (
    FulfillmentStatus,
    Shop,
    TmaAdminApproveReturn,
    TmaAdminAuthResponse,
    TmaAdminDenyReturn,
    TmaAdminFulfillment,
    TmaAdminReply,
    TmaUser,
)
from .product_sources import sync_orders_shipped
from .tasks import bot_manager
from .tma_auth import validate_init_data

tma_admin_api_router = APIRouter(prefix="/api/v1/tma-admin")


# --- Helpers ---


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _get_shop_or_404(shop_id: str) -> Shop:
    """Get shop, check existence only (admin accesses stopped shops too)."""
    shop = await get_shop(shop_id)
    if not shop:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return shop


def _extract_admin(
    authorization: Optional[str], shop: Shop
) -> TmaUser:
    """Validate initData + admin gate: chat_id must match shop.admin_chat_id."""
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Missing TMA authorization")
    init_data = authorization[4:]
    user = validate_init_data(init_data, shop.bot_token)
    if not user:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Invalid or expired initData")
    if not shop.admin_chat_id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "No admin configured for this shop")
    if user.chat_id != int(shop.admin_chat_id):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not authorized as admin")
    return user


# --- Auth endpoint ---


@tma_admin_api_router.post("/auth")
async def tma_admin_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Validate initData + admin gate, return shop config."""
    tma_admin_auth_limiter.check(_client_ip(request))

    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Missing TMA authorization")
    init_data = authorization[4:]

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Invalid request body")

    shop_id = body.get("shop_id")
    if not shop_id:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Missing shop_id")

    shop = await _get_shop_or_404(shop_id)
    user = validate_init_data(init_data, shop.bot_token)
    if not user:
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Invalid or expired initData")
    if not shop.admin_chat_id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "No admin configured for this shop")
    if user.chat_id != int(shop.admin_chat_id):
        raise HTTPException(HTTPStatus.FORBIDDEN, "Not authorized as admin")

    return TmaAdminAuthResponse(
        chat_id=user.chat_id,
        username=user.username,
        shop_id=shop.id,
        shop_title=shop.title,
        shop_currency=shop.currency,
        enable_order_tracking=shop.enable_order_tracking,
        allow_returns=shop.allow_returns,
    )


# --- Dashboard stats ---


@tma_admin_api_router.get("/{shop_id}/stats")
async def tma_admin_stats(
    shop_id: str,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Dashboard statistics."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    await expire_stale_pending_orders(shop_id)
    return await get_stats([shop_id])


@tma_admin_api_router.get("/{shop_id}/stats/revenue-daily")
async def tma_admin_revenue_daily(
    shop_id: str,
    days: int = 7,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Daily revenue for the last N days."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    if days < 1 or days > 90:
        days = 7
    return await get_daily_revenue([shop_id], days)


# --- Orders ---


def _order_dict(o) -> dict:
    return {
        "id": o.id,
        "telegram_chat_id": o.telegram_chat_id,
        "telegram_username": o.telegram_username,
        "amount_sats": o.amount_sats,
        "currency": o.currency,
        "currency_amount": o.currency_amount,
        "cart_json": o.cart_json,
        "buyer_email": o.buyer_email,
        "buyer_name": o.buyer_name,
        "buyer_address": o.buyer_address,
        "has_physical_items": o.has_physical_items,
        "credit_used": o.credit_used,
        "status": o.status,
        "fulfillment_status": o.fulfillment_status,
        "fulfillment_note": o.fulfillment_note,
        "timestamp": o.timestamp,
    }


@tma_admin_api_router.get("/{shop_id}/orders")
async def tma_admin_orders(
    shop_id: str,
    status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """List orders with optional status filter and search."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    # Expire stale pending orders so the response reflects truth
    await expire_stale_pending_orders(shop_id)

    if q and q.strip():
        orders = await search_orders(shop_id, q, limit=limit, offset=offset)
    else:
        orders = await get_orders(shop_id, status=status, limit=limit, offset=offset)
    return [_order_dict(o) for o in orders]


@tma_admin_api_router.get("/{shop_id}/orders/{order_id}")
async def tma_admin_order_detail(
    shop_id: str,
    order_id: str,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Single order detail."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    order = await get_order(order_id)
    if not order or order.shop_id != shop_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    return _order_dict(order)


# --- Fulfillment ---


@tma_admin_api_router.put("/{shop_id}/orders/{order_id}/fulfillment")
async def tma_admin_update_fulfillment(
    shop_id: str,
    order_id: str,
    data: TmaAdminFulfillment,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Update order fulfillment status and notify customer."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    order = await get_order(order_id)
    if not order or order.shop_id != shop_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    if order.status != "paid":
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Can only update paid orders")

    await update_order_fulfillment(
        order_id, data.status.value, data.note
    )

    bot = bot_manager.get_bot(shop_id)
    if bot:
        try:
            await bot.notify_fulfillment_update(
                order.telegram_chat_id, order, data.status.value, data.note
            )
        except Exception as e:
            logger.warning(f"Admin TMA: Failed to notify customer: {e}")

    # Sync shipped status to Orders extension
    if order.orders_ext_id and shop.forward_to_orders:
        shipped = data.status in (
            FulfillmentStatus.SHIPPING, FulfillmentStatus.DELIVERED
        )
        try:
            from lnbits.core.crud import get_wallet
            wallet = await get_wallet(shop.wallet)
            if wallet:
                await sync_orders_shipped(
                    wallet.user, order.orders_ext_id, shipped
                )
        except Exception as e:
            logger.warning(f"Orders shipped sync failed: {e}")

    return {"success": True, "fulfillment_status": data.status.value}


# --- Returns ---


def _return_dict(r) -> dict:
    return {
        "id": r.id,
        "shop_id": r.shop_id,
        "order_id": r.order_id,
        "chat_id": r.chat_id,
        "items_json": r.items_json,
        "reason": r.reason,
        "refund_method": r.refund_method,
        "refund_amount_sats": r.refund_amount_sats,
        "status": r.status,
        "admin_note": r.admin_note,
        "timestamp": r.timestamp,
    }


@tma_admin_api_router.get("/{shop_id}/returns")
async def tma_admin_returns(
    shop_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """List returns with optional status filter."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    returns = await get_returns(shop_id, status=status, limit=limit, offset=offset)

    # Enrich with order username for display
    result = []
    for r in returns:
        d = _return_dict(r)
        order = await get_order(r.order_id)
        d["telegram_username"] = order.telegram_username if order else None
        result.append(d)
    return result


@tma_admin_api_router.get("/{shop_id}/returns/{return_id}")
async def tma_admin_return_detail(
    shop_id: str,
    return_id: str,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Single return detail with linked order info."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    ret = await get_return(return_id)
    if not ret or ret.shop_id != shop_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")

    d = _return_dict(ret)
    order = await get_order(ret.order_id)
    if order:
        d["telegram_username"] = order.telegram_username
        d["order_amount_sats"] = order.amount_sats
        d["order_cart_json"] = order.cart_json
    return d


@tma_admin_api_router.put("/{shop_id}/returns/{return_id}/approve")
async def tma_admin_approve_return(
    shop_id: str,
    return_id: str,
    data: TmaAdminApproveReturn,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Approve a return request (credit or lightning)."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    ret = await get_return(return_id)
    if not ret or ret.shop_id != shop_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    if ret.status != "requested":
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Return already processed")

    refund_sats = data.refund_amount_sats or ret.refund_amount_sats
    if refund_sats <= 0:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Refund amount must be positive")
    if refund_sats > ret.refund_amount_sats:
        raise HTTPException(
            HTTPStatus.BAD_REQUEST,
            "Refund amount cannot exceed original amount",
        )

    updated = await update_return_status(
        return_id,
        "approved",
        refund_method=data.refund_method.value,
        refund_amount_sats=refund_sats,
        expected_status="requested",
    )
    if not updated:
        raise HTTPException(HTTPStatus.CONFLICT, "Return was already processed")

    bot = bot_manager.get_bot(shop_id)

    if data.refund_method.value == "credit":
        await create_credit(
            shop_id=shop_id,
            chat_id=ret.chat_id,
            amount_sats=refund_sats,
            source_return_id=return_id,
        )
        await update_return_status(return_id, "refunded", expected_status="approved")
        if bot:
            try:
                await bot.notify_return_approved_credit(ret.chat_id, refund_sats)
            except Exception as e:
                logger.warning(f"Admin TMA: Failed to notify return credit: {e}")
    elif data.refund_method.value == "lightning":
        if bot:
            try:
                await bot.notify_return_approved_lightning(ret.chat_id, refund_sats)
            except Exception as e:
                logger.warning(f"Admin TMA: Failed to notify return lightning: {e}")

    return {"success": True}


@tma_admin_api_router.put("/{shop_id}/returns/{return_id}/deny")
async def tma_admin_deny_return(
    shop_id: str,
    return_id: str,
    data: TmaAdminDenyReturn,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Deny a return request with admin note."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    ret = await get_return(return_id)
    if not ret or ret.shop_id != shop_id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    if ret.status != "requested":
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Return already processed")

    updated = await update_return_status(
        return_id, "denied", admin_note=data.admin_note,
        expected_status="requested",
    )
    if not updated:
        raise HTTPException(HTTPStatus.CONFLICT, "Return was already processed")

    bot = bot_manager.get_bot(shop_id)
    if bot:
        try:
            await bot.notify_return_denied(ret.chat_id, data.admin_note)
        except Exception as e:
            logger.warning(f"Admin TMA: Failed to notify return denial: {e}")

    return {"success": True}


# --- Conversations ---


@tma_admin_api_router.get("/{shop_id}/conversations")
async def tma_admin_conversations(
    shop_id: str,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Grouped conversation list."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    return await get_message_conversations(shop_id)


# --- Messages (thread) ---


@tma_admin_api_router.get("/{shop_id}/messages/thread")
async def tma_admin_thread(
    shop_id: str,
    chat_id: int = 0,
    order_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Get thread messages and mark as read."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    if not chat_id:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Missing chat_id")

    messages = await get_message_thread(shop_id, chat_id, order_id)
    await mark_thread_read(shop_id, chat_id, order_id)

    return [
        {
            "id": m.id,
            "direction": m.direction,
            "content": m.content,
            "order_id": m.order_id,
            "username": m.username,
            "timestamp": m.timestamp,
        }
        for m in messages
    ]


# --- Send reply ---


@tma_admin_api_router.post("/{shop_id}/messages")
async def tma_admin_send_reply(
    shop_id: str,
    data: TmaAdminReply,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Send reply to customer."""
    shop = await _get_shop_or_404(shop_id)
    admin = _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    if not data.content.strip():
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Message content required")

    msg = await create_message(
        shop_id=shop_id,
        chat_id=data.chat_id,
        direction="out",
        content=data.content.strip(),
        username=admin.username,
        order_id=data.order_id,
    )

    bot = bot_manager.get_bot(shop_id)
    if bot:
        try:
            await bot.send_admin_reply(
                data.chat_id, data.content.strip(), data.order_id
            )
        except Exception as e:
            logger.warning(f"Admin TMA: Failed to send reply: {e}")

    return {"id": msg.id, "timestamp": msg.timestamp}


# --- Customers list ---


@tma_admin_api_router.get("/{shop_id}/customers")
async def tma_admin_customers(
    shop_id: str,
    q: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """List all customers with order stats."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))
    return await get_customers_with_stats(shop_id, q)


# --- Customer profile ---


@tma_admin_api_router.get("/{shop_id}/customers/{chat_id}/profile")
async def tma_admin_customer_profile(
    shop_id: str,
    chat_id: int,
    authorization: Optional[str] = Header(None),
    request: Request = None,
):
    """Aggregated customer profile: orders, revenue, credits, messages, returns."""
    shop = await _get_shop_or_404(shop_id)
    _extract_admin(authorization, shop)
    tma_admin_api_limiter.check(_client_ip(request))

    customer = await get_customer_by_chat(shop_id, chat_id)
    orders = await get_orders_by_chat(shop_id, chat_id)
    returns = await get_returns_by_chat(shop_id, chat_id)
    credit_balance = await get_total_available_credit(shop_id, chat_id)
    message_count = await get_message_count_by_chat(shop_id, chat_id)

    total_spent = sum(o.amount_sats for o in orders)

    return {
        "chat_id": chat_id,
        "username": customer.username if customer else None,
        "first_name": customer.first_name if customer else None,
        "first_seen": customer.first_seen if customer else None,
        "last_active": customer.last_active if customer else None,
        "order_count": len(orders),
        "total_spent_sats": total_spent,
        "credit_balance_sats": credit_balance,
        "message_count": message_count,
        "return_count": len(returns),
        "recent_orders": [
            {
                "id": o.id,
                "amount_sats": o.amount_sats,
                "status": o.status,
                "fulfillment_status": o.fulfillment_status,
                "cart_json": o.cart_json,
                "timestamp": o.timestamp,
            }
            for o in orders[:10]
        ],
    }
