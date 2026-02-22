import asyncio
import json
from typing import Dict, List, Optional, Tuple

from loguru import logger

from lnbits.core.crud import get_wallet
from lnbits.tasks import register_invoice_listener

from .crud import (
    create_message,
    get_cart,
    get_commercials,
    get_customers,
    get_enabled_shops,
    get_order_by_payment_hash,
    get_orders,
    get_stale_carts,
    has_commercial_been_sent,
    log_commercial_send,
    update_commercial_stock_snapshot,
    update_order_status,
)
from .models import Commercial, Customer, Shop
from .product_sources import deduct_inventory_stock
from .telegram import TelegramBot, _safe_err


class BotManager:
    def __init__(self):
        self.bots: Dict[str, TelegramBot] = {}
        self._poll_tasks: Dict[str, asyncio.Task] = {}

    async def start_bot(self, shop: Shop) -> None:
        if shop.id in self.bots:
            await self.stop_bot(shop.id)

        wallet = await get_wallet(shop.wallet)
        if not wallet:
            logger.error(f"Wallet not found for shop '{shop.title}'")
            return

        bot = TelegramBot(shop, wallet.inkey, wallet.user)
        self.bots[shop.id] = bot

        try:
            await bot.start()
            if shop.use_webhook:
                await bot.register_webhook()
            else:
                task = asyncio.create_task(self._poll_loop(bot))
                self._poll_tasks[shop.id] = task
        except Exception as e:
            logger.error(
                f"Failed to start bot for shop '{shop.title}': "
                f"{_safe_err(e, shop.bot_token)}"
            )
            try:
                await bot.stop()
            except Exception:
                pass
            del self.bots[shop.id]

    async def stop_bot(self, shop_id: str) -> None:
        if shop_id in self._poll_tasks:
            self._poll_tasks[shop_id].cancel()
            del self._poll_tasks[shop_id]

        if shop_id in self.bots:
            bot = self.bots[shop_id]
            try:
                await bot.stop()
            except Exception as e:
                logger.warning(
                    f"Error stopping bot: {_safe_err(e, bot.shop.bot_token)}"
                )
            del self.bots[shop_id]

    def get_bot(self, shop_id: str) -> Optional[TelegramBot]:
        return self.bots.get(shop_id)

    async def stop_all(self) -> None:
        shop_ids = list(self.bots.keys())
        for shop_id in shop_ids:
            await self.stop_bot(shop_id)

    async def start_all_enabled(self) -> None:
        shops = await get_enabled_shops()
        for shop in shops:
            try:
                await self.start_bot(shop)
            except Exception as e:
                logger.error(
                    f"Failed to start bot for shop '{shop.title}': "
                    f"{_safe_err(e, shop.bot_token)}"
                )

    async def _poll_loop(self, bot: TelegramBot) -> None:
        while bot._running:
            try:
                result = await bot.api_call(
                    "getUpdates", offset=bot._offset, timeout=30
                )
                if isinstance(result, list):
                    for update in result:
                        bot._offset = update["update_id"] + 1
                        await bot.handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Polling error for '{bot.shop.title}': "
                    f"{_safe_err(e, bot.shop.bot_token)}"
                )
                await asyncio.sleep(5)


bot_manager = BotManager()


async def start_all_bots() -> None:
    await asyncio.sleep(3)
    await bot_manager.start_all_enabled()


async def stop_all_bots() -> None:
    await bot_manager.stop_all()


async def wait_for_paid_invoices() -> None:
    invoice_queue: asyncio.Queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_telegramshop")

    while True:
        payment = await invoice_queue.get()
        try:
            extra = payment.extra or {}
            if extra.get("tag") != "telegramshop":
                continue

            shop_id = extra.get("shop_id")
            chat_id = extra.get("chat_id")
            if not shop_id or not chat_id:
                continue

            order = await get_order_by_payment_hash(payment.payment_hash)
            if not order or order.status == "paid":
                continue

            await update_order_status(order.id, "paid")

            # Deduct inventory stock
            bot = bot_manager.get_bot(shop_id)
            if bot:
                cart_items = json.loads(order.cart_json)
                stock_items = [
                    (item["product_id"], item["quantity"])
                    for item in cart_items
                ]
                try:
                    await deduct_inventory_stock(
                        bot.shop.inventory_id,
                        stock_items,
                        bot.user_id,
                    )
                except Exception as e:
                    logger.error(f"Stock deduction failed: {e}")

            # Refresh products to update stock counts
            if bot:
                await bot.refresh_products()

            # Send confirmation to customer
            if bot:
                updated_order = await get_order_by_payment_hash(
                    payment.payment_hash
                )
                if updated_order:
                    await bot.send_payment_confirmation(
                        int(chat_id), updated_order
                    )

        except Exception as e:
            logger.error(f"Error processing paid invoice: {e}")


# --- Commercial message builder ---

# Type-specific config: emoji, default CTA text, TMA deep-link fragment
_COMMERCIAL_META = {
    "abandoned_cart": {
        "emoji": "🛒",
        "cta": "Complete your order",
        "fragment": "#/cart",
    },
    "post_purchase": {
        "emoji": "🎉",
        "cta": "Shop again",
        "fragment": "#/",
    },
    "back_in_stock": {
        "emoji": "📦",
        "cta": "See what's new",
        "fragment": "#/",
    },
    "promotion": {
        "emoji": "🎁",
        "cta": "Check it out",
        "fragment": "#/",
    },
}


async def build_commercial_message(
    commercial: Commercial,
    customer: Customer,
    shop: Shop,
    bot: Optional[TelegramBot] = None,
    restocked_products: Optional[List] = None,
) -> Tuple[str, str]:
    """Build a rich, type-specific message for a commercial.

    Returns (telegram_html, plain_text_for_tma_messages).
    The telegram_html includes HTML tags; the plain text is for the TMA
    messages table.
    """
    meta = _COMMERCIAL_META.get(
        commercial.type, _COMMERCIAL_META["promotion"]
    )
    emoji = meta["emoji"]
    name = customer.first_name or customer.username or "there"

    # --- Type-specific body ---

    if commercial.type == "abandoned_cart":
        # Try to show actual cart items
        cart_detail = ""
        cart = await get_cart(shop.id, customer.chat_id)
        if cart:
            try:
                items = json.loads(cart.cart_json)
                if items:
                    lines = []
                    total = 0
                    for item in items:
                        qty = item.get("quantity", 1)
                        title = item.get("title", "Item")
                        price = item.get("price", 0)
                        line_total = price * qty
                        total += line_total
                        lines.append(f"  • {qty}× {title}")
                    cart_detail = (
                        "\n\n<b>Your cart:</b>\n"
                        + "\n".join(lines)
                        + f"\n\n💰 <b>Total: {total:,} sats</b>"
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        body = (
            f"Hey {name}, you left something behind! "
            f"Your cart is still waiting for you."
            f"{cart_detail}"
        )
        if commercial.content:
            body += f"\n\n{commercial.content}"

    elif commercial.type == "post_purchase":
        body = (
            f"Thanks for your order, {name}! "
            f"We hope you love it. ✨"
        )
        if commercial.content:
            body += f"\n\n{commercial.content}"

    elif commercial.type == "back_in_stock":
        # Show which products are back
        product_names = ""
        show_products = restocked_products or []
        if show_products:
            top = show_products[:5]
            product_names = (
                "\n\n<b>Now available:</b>\n"
                + "\n".join(f"  • {p.title}" for p in top)
            )
            if len(show_products) > 5:
                product_names += (
                    f"\n  … and {len(show_products) - 5} more"
                )

        body = f"Good news, {name}! Items are back in stock."
        if commercial.content:
            body += f"\n\n{commercial.content}"
        body += product_names

    else:
        # promotion / generic
        if commercial.content:
            body = commercial.content
        else:
            body = (
                f"Hey {name}, see what's new at {shop.title}"
                f" — browse our latest products."
            )

    telegram_html = (
        f"{emoji} <b>{commercial.title}</b>\n\n"
        f"{body}"
    )

    # Plain text version for TMA messages table (no HTML tags)
    import re
    plain = re.sub(r"<[^>]+>", "", telegram_html)

    return telegram_html, plain


def build_commercial_keyboard(
    commercial: Commercial, tma_base_url: str
) -> dict:
    """Build an inline keyboard with a type-specific CTA."""
    meta = _COMMERCIAL_META.get(
        commercial.type, _COMMERCIAL_META["promotion"]
    )
    fragment = meta["fragment"]
    cta_text = meta["cta"]

    tma_url = tma_base_url + fragment

    return {"inline_keyboard": [
        [{"text": f"{meta['emoji']} {cta_text}", "web_app": {"url": tma_url}}]
    ]}


async def send_commercial_to_customer(
    bot: TelegramBot,
    shop: Shop,
    commercial: Commercial,
    customer: Customer,
    tma_base_url: str,
    order_id: Optional[str] = None,
    restocked_products: Optional[List] = None,
) -> None:
    """Send a commercial message and log it (Telegram + TMA messages)."""
    telegram_html, plain_text = await build_commercial_message(
        commercial, customer, shop, bot,
        restocked_products=restocked_products,
    )
    keyboard = build_commercial_keyboard(commercial, tma_base_url)

    if commercial.image_url:
        await bot.send_photo(
            customer.chat_id,
            commercial.image_url,
            telegram_html,
            reply_markup=keyboard,
        )
    else:
        await bot.send_message(
            customer.chat_id,
            telegram_html,
            reply_markup=keyboard,
        )

    # Also save in TMA messages so customer sees it in the Messages tab
    await create_message(
        shop_id=shop.id,
        chat_id=customer.chat_id,
        direction="out",
        content=plain_text,
        username=None,
    )

    await log_commercial_send(
        commercial.id, shop.id, customer.chat_id, order_id=order_id
    )


async def run_commercial_engine() -> None:
    """Background task: process automated commercials every 5 minutes."""
    from lnbits.settings import settings

    await asyncio.sleep(10)  # Initial delay
    while True:
        try:
            shops = await get_enabled_shops()
            for shop in shops:
                bot = bot_manager.get_bot(shop.id)
                if not bot:
                    continue

                commercials = await get_commercials(shop.id)
                enabled = [c for c in commercials if c.is_enabled]
                if not enabled:
                    continue

                customers = await get_customers(shop.id)
                if not customers:
                    continue

                base = settings.lnbits_baseurl.rstrip("/")
                tma_base_url = (
                    f"{base}/telegramshop/static/tma/"
                    f"index.html?shop={shop.id}"
                )

                for commercial in enabled:
                    try:
                        targets: List[Customer] = []
                        restocked_products: Optional[List] = None

                        if commercial.type == "abandoned_cart":
                            stale = await get_stale_carts(
                                shop.id, commercial.delay_minutes
                            )
                            stale_chat_ids = {c.chat_id for c in stale}
                            targets = [
                                c for c in customers
                                if c.chat_id in stale_chat_ids
                            ]

                        elif commercial.type == "post_purchase":
                            # Dedup per delivered order, not per customer
                            orders = await get_orders(
                                shop.id, status="paid", limit=200
                            )
                            delivered = [
                                o for o in orders
                                if o.fulfillment_status == "delivered"
                            ]
                            # Build customer lookup
                            cust_by_chat = {
                                c.chat_id: c for c in customers
                            }
                            for order in delivered:
                                cust = cust_by_chat.get(
                                    order.telegram_chat_id
                                )
                                if not cust:
                                    continue
                                already = await has_commercial_been_sent(
                                    commercial.id, cust.chat_id,
                                    order_id=order.id,
                                )
                                if already:
                                    continue
                                try:
                                    await send_commercial_to_customer(
                                        bot, shop, commercial,
                                        cust, tma_base_url,
                                        order_id=order.id,
                                    )
                                    await asyncio.sleep(1 / 30)
                                except Exception as e:
                                    logger.warning(
                                        f"Commercial send failed for "
                                        f"{cust.chat_id}: {e}"
                                    )
                            continue  # skip generic loop below

                        elif commercial.type == "promotion":
                            # Promotions are sent via manual broadcast only
                            continue

                        elif commercial.type == "back_in_stock":
                            # Track 0 → >0 transitions
                            active = bot.get_active_products()
                            current_stock = {
                                p.id: (p.inventory or 0)
                                for p in active
                            }
                            prev_stock: dict = {}
                            if commercial.last_known_stock:
                                try:
                                    prev_stock = json.loads(
                                        commercial.last_known_stock
                                    )
                                except (json.JSONDecodeError, TypeError):
                                    pass

                            # Find products that went from 0 → >0
                            restocked_ids = [
                                pid for pid, qty in current_stock.items()
                                if qty > 0
                                and prev_stock.get(pid, 0) == 0
                            ]
                            restocked_products = [
                                p for p in active
                                if p.id in restocked_ids
                            ]

                            # Always save current snapshot
                            await update_commercial_stock_snapshot(
                                commercial.id,
                                json.dumps(current_stock),
                            )

                            if restocked_products:
                                targets = customers
                            else:
                                continue  # no transitions

                        for customer in targets:
                            already = await has_commercial_been_sent(
                                commercial.id, customer.chat_id
                            )
                            if already:
                                continue
                            try:
                                await send_commercial_to_customer(
                                    bot, shop, commercial,
                                    customer, tma_base_url,
                                    restocked_products=(
                                        restocked_products
                                        if commercial.type == "back_in_stock"
                                        else None
                                    ),
                                )
                                await asyncio.sleep(1 / 30)
                            except Exception as e:
                                logger.warning(
                                    f"Commercial send failed for "
                                    f"{customer.chat_id}: {e}"
                                )
                    except Exception as e:
                        logger.error(
                            f"Commercial engine error for "
                            f"{commercial.id}: {e}"
                        )

        except Exception as e:
            logger.error(f"Commercial engine error: {e}")

        await asyncio.sleep(300)  # Every 5 minutes
