import hmac
from http import HTTPStatus
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from loguru import logger

from lnbits.settings import settings

from lnbits.core.models import WalletTypeInfo
from lnbits.decorators import require_admin_key, require_invoice_key

from .helpers import webhook_limiter
from .crud import (
    create_shop,
    update_shop,
    get_shop,
    get_shops,
    delete_shop,
    set_shop_enabled,
    ensure_webhook_secret,
    get_order,
    get_orders,
    update_order_fulfillment,
    get_messages,
    get_message_thread,
    create_message,
    mark_message_read,
    get_unread_count,
    get_returns,
    get_return,
    update_return_status,
    create_credit,
    get_total_available_credit,
    create_commercial,
    get_commercial,
    get_commercials,
    update_commercial,
    delete_commercial,
    get_commercial_logs,
    log_commercial_send,
    get_customers,
    get_stats,
    ensure_shop_commercials,
)
from .models import (
    Commercial,
    CreateCommercial,
    CreateShop,
    Customer,
    Shop,
    ShopResponse,
    Order,
    Message,
    Return,
    UpdateCommercial,
    UpdateFulfillment,
    SendMessage,
    ApproveReturn,
    DenyReturn,
    TestToken,
    FulfillmentStatus,
)
from .product_sources import get_cached_image, sync_orders_shipped
from .tasks import bot_manager

telegramshop_api_router = APIRouter(prefix="/api/v1")


# --- Shops ---


@telegramshop_api_router.post("/shop", status_code=HTTPStatus.CREATED)
async def api_create_shop(
    data: CreateShop,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> ShopResponse:
    shop = await create_shop(key_info.wallet.id, data)
    return ShopResponse.from_shop(shop)


@telegramshop_api_router.put("/shop/{shop_id}")
async def api_update_shop(
    shop_id: str,
    data: CreateShop,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> ShopResponse:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    # Keep existing bot_token if not provided in update
    if not data.bot_token:
        data.bot_token = shop.bot_token
    updated = await update_shop(shop_id, data)
    bot = bot_manager.get_bot(shop_id)
    return ShopResponse.from_shop(
        updated, bot._bot_username if bot else None
    )


@telegramshop_api_router.get("/shop")
async def api_list_shops(
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[ShopResponse]:
    shops = await get_shops([key_info.wallet.id])
    result = []
    for shop in shops:
        bot = bot_manager.get_bot(shop.id)
        result.append(ShopResponse.from_shop(
            shop, bot._bot_username if bot else None
        ))
    return result


@telegramshop_api_router.get("/shop/{shop_id}")
async def api_get_shop(
    shop_id: str,
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> ShopResponse:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    bot = bot_manager.get_bot(shop_id)
    return ShopResponse.from_shop(
        shop, bot._bot_username if bot else None
    )


@telegramshop_api_router.delete("/shop/{shop_id}")
async def api_delete_shop(
    shop_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    await bot_manager.stop_bot(shop_id)
    await delete_shop(shop_id)
    return {"success": True}


@telegramshop_api_router.post("/shop/{shop_id}/start")
async def api_start_shop(
    shop_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    # Backfill webhook_secret for shops created before m004
    if not shop.webhook_secret:
        await ensure_webhook_secret(shop_id)
    await set_shop_enabled(shop_id, True)
    shop = await get_shop(shop_id)
    assert shop
    await bot_manager.start_bot(shop)
    return {"success": True}


@telegramshop_api_router.post("/shop/{shop_id}/stop")
async def api_stop_shop(
    shop_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    await bot_manager.stop_bot(shop_id)
    await set_shop_enabled(shop_id, False)
    return {"success": True}


@telegramshop_api_router.post("/shop/{shop_id}/refresh")
async def api_refresh_shop(
    shop_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    bot = bot_manager.get_bot(shop_id)
    if bot:
        await bot.refresh_products()
    return {"success": True}


@telegramshop_api_router.post("/shop/test-token")
async def api_test_token(
    data: TestToken,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    url = f"https://api.telegram.org/bot{data.bot_token}/getMe"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(HTTPStatus.BAD_REQUEST, "Invalid bot token")
        result = resp.json()
        if not result.get("ok"):
            raise HTTPException(HTTPStatus.BAD_REQUEST, "Invalid bot token")
        bot_info = result["result"]
        return {
            "username": bot_info.get("username"),
            "first_name": bot_info.get("first_name"),
        }


# --- Stats ---


@telegramshop_api_router.get("/stats")
async def api_stats(
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> dict:
    shops = await get_shops([key_info.wallet.id])
    shop_ids = [s.id for s in shops]
    stats = await get_stats(shop_ids)
    stats["shops"] = len(shops)
    stats["shops_live"] = sum(1 for s in shops if s.is_enabled)
    return stats


# --- Orders ---


@telegramshop_api_router.get("/order")
async def api_list_orders(
    shop_id: str = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Order]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await get_orders(shop_id, status=status, limit=limit, offset=offset)


@telegramshop_api_router.get("/order/{order_id}")
async def api_get_order(
    order_id: str,
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> Order:
    order = await get_order(order_id)
    if not order:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    shop = await get_shop(order.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    return order


@telegramshop_api_router.put("/order/{order_id}/fulfillment")
async def api_update_fulfillment(
    order_id: str,
    data: UpdateFulfillment,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    order = await get_order(order_id)
    if not order:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    shop = await get_shop(order.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Order not found")
    if not shop.enable_order_tracking:
        raise HTTPException(
            HTTPStatus.BAD_REQUEST, "Order tracking not enabled for this shop"
        )
    if order.status != "paid":
        raise HTTPException(
            HTTPStatus.BAD_REQUEST, "Can only track fulfillment for paid orders"
        )

    await update_order_fulfillment(order_id, data.status.value, data.note)

    # Notify customer via Telegram bot
    bot = bot_manager.get_bot(shop.id)
    if bot:
        await bot.notify_fulfillment_update(
            order.telegram_chat_id, order, data.status.value, data.note
        )

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

    return {"success": True}


# --- Messages ---


@telegramshop_api_router.get("/message")
async def api_list_messages(
    shop_id: str = Query(...),
    unread_only: bool = Query(False),
    limit: int = Query(50),
    offset: int = Query(0),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Message]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await get_messages(
        shop_id, unread_only=unread_only, limit=limit, offset=offset
    )


@telegramshop_api_router.get("/message/thread")
async def api_get_thread(
    shop_id: str = Query(...),
    chat_id: int = Query(...),
    order_id: Optional[str] = Query(None),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Message]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await get_message_thread(shop_id, chat_id, order_id)


@telegramshop_api_router.get("/message/unread-count")
async def api_unread_count(
    shop_id: str = Query(...),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> dict:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    count = await get_unread_count(shop_id)
    return {"count": count}


@telegramshop_api_router.post("/message/{shop_id}")
async def api_send_message(
    shop_id: str,
    data: SendMessage,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Message:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")

    msg = await create_message(
        shop_id=shop_id,
        chat_id=data.chat_id,
        direction="out",
        content=data.content,
        order_id=data.order_id,
    )

    # Send via Telegram bot
    bot = bot_manager.get_bot(shop_id)
    if bot:
        await bot.send_admin_reply(data.chat_id, data.content, data.order_id)

    return msg


@telegramshop_api_router.put("/message/{message_id}/read")
async def api_mark_read(
    message_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    await mark_message_read(message_id)
    return {"success": True}


# --- Returns ---


@telegramshop_api_router.get("/return")
async def api_list_returns(
    shop_id: str = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Return]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await get_returns(shop_id, status=status, limit=limit, offset=offset)


@telegramshop_api_router.get("/return/{return_id}")
async def api_get_return(
    return_id: str,
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> Return:
    ret = await get_return(return_id)
    if not ret:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    shop = await get_shop(ret.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    return ret


@telegramshop_api_router.put("/return/{return_id}/approve")
async def api_approve_return(
    return_id: str,
    data: ApproveReturn,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    ret = await get_return(return_id)
    if not ret:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    shop = await get_shop(ret.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    if ret.status != "requested":
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Return already processed")

    # Use custom amount if provided, otherwise full refund
    refund_sats = data.refund_amount_sats or ret.refund_amount_sats
    if refund_sats <= 0:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Refund amount must be positive")
    if refund_sats > ret.refund_amount_sats:
        raise HTTPException(
            HTTPStatus.BAD_REQUEST,
            "Refund amount cannot exceed original amount",
        )

    # Atomic: only update if still "requested" (prevents race conditions)
    updated = await update_return_status(
        return_id,
        "approved",
        refund_method=data.refund_method.value,
        refund_amount_sats=refund_sats,
        expected_status="requested",
    )
    if not updated:
        raise HTTPException(HTTPStatus.CONFLICT, "Return was already processed")

    bot = bot_manager.get_bot(shop.id)

    if data.refund_method.value == "credit":
        await create_credit(
            shop_id=shop.id,
            chat_id=ret.chat_id,
            amount_sats=refund_sats,
            source_return_id=return_id,
        )
        await update_return_status(return_id, "refunded", expected_status="approved")
        if bot:
            await bot.notify_return_approved_credit(
                ret.chat_id, refund_sats
            )
    elif data.refund_method.value == "lightning":
        if bot:
            await bot.notify_return_approved_lightning(
                ret.chat_id, refund_sats
            )

    return {"success": True}


@telegramshop_api_router.put("/return/{return_id}/deny")
async def api_deny_return(
    return_id: str,
    data: DenyReturn,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    ret = await get_return(return_id)
    if not ret:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    shop = await get_shop(ret.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Return not found")
    if ret.status != "requested":
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Return already processed")

    # Atomic: only update if still "requested"
    updated = await update_return_status(
        return_id, "denied", admin_note=data.admin_note,
        expected_status="requested",
    )
    if not updated:
        raise HTTPException(HTTPStatus.CONFLICT, "Return was already processed")

    bot = bot_manager.get_bot(shop.id)
    if bot:
        await bot.notify_return_denied(ret.chat_id, data.admin_note)

    return {"success": True}


# --- Commercials ---


@telegramshop_api_router.get("/commercial")
async def api_list_commercials(
    shop_id: str = Query(...),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Commercial]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await ensure_shop_commercials(shop_id)


@telegramshop_api_router.post("/commercial", status_code=HTTPStatus.CREATED)
async def api_create_commercial(
    data: CreateCommercial,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Commercial:
    shop = await get_shop(data.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await create_commercial(data)


@telegramshop_api_router.put("/commercial/{commercial_id}")
async def api_update_commercial(
    commercial_id: str,
    data: UpdateCommercial,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Commercial:
    commercial = await get_commercial(commercial_id)
    if not commercial:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    shop = await get_shop(commercial.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    return await update_commercial(commercial_id, data)


@telegramshop_api_router.delete("/commercial/{commercial_id}")
async def api_delete_commercial(
    commercial_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    commercial = await get_commercial(commercial_id)
    if not commercial:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    shop = await get_shop(commercial.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    await delete_commercial(commercial_id)
    return {"success": True}


@telegramshop_api_router.post("/commercial/{commercial_id}/broadcast")
async def api_broadcast_commercial(
    commercial_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    from .tasks import send_commercial_to_customer

    commercial = await get_commercial(commercial_id)
    if not commercial:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    shop = await get_shop(commercial.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")

    customers = await get_customers(commercial.shop_id)
    bot = bot_manager.get_bot(commercial.shop_id)
    if not bot:
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Bot not running")

    import asyncio
    sent = 0
    base = settings.lnbits_baseurl.rstrip("/")
    tma_base_url = (
        f"{base}/telegramshop/static/tma/"
        f"index.html?shop={commercial.shop_id}"
    )
    for customer in customers:
        try:
            await send_commercial_to_customer(
                bot, shop, commercial, customer, tma_base_url,
            )
            sent += 1
            await asyncio.sleep(1 / 30)  # Rate limit: 30 msg/sec
        except Exception as e:
            logger.warning(
                f"Failed to send commercial to {customer.chat_id}: {e}"
            )

    return {"success": True, "sent": sent, "total": len(customers)}


@telegramshop_api_router.get("/commercial/{commercial_id}/log")
async def api_commercial_logs(
    commercial_id: str,
    limit: int = Query(50),
    offset: int = Query(0),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
):
    commercial = await get_commercial(commercial_id)
    if not commercial:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    shop = await get_shop(commercial.shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Commercial not found")
    return await get_commercial_logs(commercial_id, limit=limit, offset=offset)


# --- Customers ---


@telegramshop_api_router.get("/customer")
async def api_list_customers(
    shop_id: str = Query(...),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Customer]:
    shop = await get_shop(shop_id)
    if not shop or shop.wallet != key_info.wallet.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Shop not found")
    return await get_customers(shop_id)


# --- Telegram Webhook ---


@telegramshop_api_router.post("/webhook/{shop_id}")
async def api_webhook(shop_id: str, request: Request) -> dict:
    webhook_limiter.check(shop_id)

    bot = bot_manager.get_bot(shop_id)
    if not bot:
        return {"ok": False}

    # Verify Telegram's secret_token header (always required)
    if not bot.shop.webhook_secret:
        logger.warning(f"Webhook rejected: shop {shop_id} has no secret")
        return {"ok": False}
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(token, bot.shop.webhook_secret):
        return {"ok": False}

    update = await request.json()
    try:
        await bot.handle_update(update)
    except Exception as e:
        from .telegram import _safe_err
        logger.error(
            f"Webhook error for shop {shop_id}: "
            f"{_safe_err(e, bot.shop.bot_token)}"
        )
    return {"ok": True}


# --- Utility ---


@telegramshop_api_router.get("/sources/inventory")
async def api_list_inventory_sources(
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[dict]:
    """
    Fetch the user's inventory from the Inventory extension.
    Uses a short-lived internal access token since check_user_exists
    does not accept API keys.
    """
    from .product_sources import _internal_token, _internal_url

    url = _internal_url("/inventory/api/v1")
    token = _internal_token(key_info.wallet.user)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                inventory = resp.json()
                if inventory:
                    omit_tags_str = inventory.get("omit_tags") or ""
                    omit_tags = [
                        t.strip()
                        for t in omit_tags_str.split(",")
                        if t.strip()
                    ]
                    return [
                        {
                            "id": inventory["id"],
                            "name": inventory.get(
                                "name", inventory["id"]
                            ),
                            "omit_tags": omit_tags,
                        }
                    ]
            logger.warning(
                f"Inventory API: {resp.status_code} "
                f"{resp.text[:200]}"
            )
    except Exception as e:
        logger.warning(f"Failed to fetch Inventory: {e}")
    return []


@telegramshop_api_router.get("/sources/inventory/tags")
async def api_list_inventory_tags(
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> dict:
    """
    Fetch all unique tags from the user's inventory items.
    Returns sorted list of tag strings.
    """
    from .product_sources import _internal_token, _internal_url, _parse_csv_tags

    user_id = key_info.wallet.user

    # First get inventory to find inventory_id and omit_tags
    inv_url = _internal_url("/inventory/api/v1")
    token = _internal_token(user_id)
    inventory_id = None
    inv_omit_tags: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                inv_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                inventory = resp.json()
                if inventory:
                    inventory_id = inventory["id"]
                    inv_omit_tags = _parse_csv_tags(
                        inventory.get("omit_tags")
                    )
    except Exception as e:
        logger.warning(f"Failed to fetch inventory for tags: {e}")

    if not inventory_id:
        return {"tags": [], "omit_tags": []}

    # Fetch all active+approved items and collect tags
    items_url = _internal_url(
        f"/inventory/api/v1/items/{inventory_id}/paginated"
    )
    all_tags: set[str] = set()
    offset = 0
    limit = 50
    token = _internal_token(user_id)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            while True:
                resp = await client.get(
                    items_url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "limit": limit,
                        "offset": offset,
                        "is_active": True,
                        "is_approved": True,
                    },
                )
                resp.raise_for_status()
                page = resp.json()
                items = page.get("data", [])
                for item in items:
                    tags_str = item.get("tags") or ""
                    for t in tags_str.split(","):
                        t = t.strip()
                        if t:
                            all_tags.add(t)
                total = page.get("total", 0)
                offset += limit
                if offset >= total or not items:
                    break
    except Exception as e:
        logger.warning(f"Failed to fetch inventory items for tags: {e}")

    return {
        "tags": sorted(all_tags, key=str.lower),
        "omit_tags": inv_omit_tags,
    }


@telegramshop_api_router.get("/image/{image_id}")
async def api_proxy_image(image_id: str) -> Response:
    data = get_cached_image(image_id)
    if not data:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Image not found")
    return Response(content=data, media_type="image/png")
