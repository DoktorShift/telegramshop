import json
from typing import Dict, List, Optional

import httpx
from loguru import logger

from lnbits.settings import settings

from .crud import upsert_customer
from .helpers import escape_html, format_sats
from .services import format_price
from .models import Order, Shop, ShopProduct, UserSession
from .product_sources import (
    _is_telegram_reachable_url,
    fetch_inventory_products,
)

SEP = "━━━━━━━━━━━━━━━━━━"


def _safe_err(e: Exception, bot_token: str) -> str:
    """Sanitise exception text so the bot token is never logged."""
    msg = str(e)
    if bot_token:
        msg = msg.replace(bot_token, "bot<REDACTED>")
    return msg


class TelegramBot:
    def __init__(self, shop: Shop, wallet_key: str, user_id: str):
        self.shop = shop
        self.wallet_key = wallet_key
        self.user_id = user_id
        self.base_url = f"https://api.telegram.org/bot{shop.bot_token}"
        self.client = httpx.AsyncClient(timeout=40.0)
        self.sessions: Dict[int, UserSession] = {}
        self.products: List[ShopProduct] = []
        self._running = False
        self._offset = 0
        self._bot_username: Optional[str] = None

    # --- Helpers ---

    @property
    def tma_url(self) -> str:
        """TMA web app URL for this shop (HTTPS required by Telegram)."""
        base = settings.lnbits_baseurl.rstrip("/")
        return (
            f"{base}/telegramshop/static/tma/"
            f"index.html?shop={self.shop.id}"
        )

    @staticmethod
    def _is_valid_photo_url(url: Optional[str]) -> bool:
        """Return True if *url* can be sent to Telegram as a photo."""
        if not url:
            return False
        return _is_telegram_reachable_url(url)

    def _capture_user_identity(self, chat_id: int, from_obj: dict) -> None:
        """Store Telegram user identity on the session from any update."""
        if not from_obj:
            return
        session = self.get_session(chat_id)
        if from_obj.get("username"):
            session.username = from_obj["username"]
        elif from_obj.get("first_name") and not session.username:
            session.username = from_obj["first_name"]

    # --- Telegram API ---

    async def api_call(self, method: str, **kwargs) -> dict:
        try:
            resp = await self.client.post(
                f"{self.base_url}/{method}", json=kwargs
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(
                    f"Telegram API error ({method}): {data.get('description')}"
                )
                return {}
            return data.get("result", {})
        except Exception as e:
            logger.error(
                f"Telegram API call failed ({method}): "
                f"{_safe_err(e, self.shop.bot_token)}"
            )
            return {}

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "HTML",
    ) -> dict:
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        return await self.api_call("sendMessage", **kwargs)

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str,
        reply_markup: Optional[dict] = None,
    ) -> dict:
        if not self._is_valid_photo_url(photo):
            return await self.send_message(
                chat_id, caption, reply_markup=reply_markup
            )
        kwargs = {
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "parse_mode": "HTML",
        }
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        result = await self.api_call("sendPhoto", **kwargs)
        if not result:
            return await self.send_message(
                chat_id, caption, reply_markup=reply_markup
            )
        return result

    async def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Welcome & open shop"},
        ]
        await self.api_call("setMyCommands", commands=commands)

    # --- Lifecycle ---

    async def start(self) -> None:
        self._running = True
        me = await self.api_call("getMe")
        self._bot_username = me.get("username")
        await self.set_commands()
        await self.refresh_products()
        logger.info(
            f"Bot started for shop '{self.shop.title}' (@{self._bot_username})"
        )

    async def stop(self) -> None:
        self._running = False
        if self.shop.use_webhook:
            await self.api_call("deleteWebhook")
        try:
            await self.client.aclose()
        except Exception:
            pass
        logger.info(f"Bot stopped for shop '{self.shop.title}'")

    async def refresh_products(self) -> None:
        try:
            self.products = await fetch_inventory_products(
                self.shop.inventory_id, self.user_id
            )
            active = [p for p in self.products if not p.disabled]
            logger.info(
                f"Loaded {len(active)} products for shop '{self.shop.title}'"
            )
        except Exception as e:
            logger.error(
                f"Failed to load products: {_safe_err(e, self.shop.bot_token)}"
            )

    async def register_webhook(self) -> None:
        webhook_url = (
            f"{settings.lnbits_baseurl}/telegramshop/api/v1/webhook/{self.shop.id}"
        )
        kwargs: dict = {"url": webhook_url}
        if self.shop.webhook_secret:
            kwargs["secret_token"] = self.shop.webhook_secret
        await self.api_call("setWebhook", **kwargs)

    # --- Session ---

    def get_session(self, chat_id: int) -> UserSession:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = UserSession()
        return self.sessions[chat_id]

    # --- Product helpers ---

    def get_active_products(self) -> List[ShopProduct]:
        return [p for p in self.products if not p.disabled]

    def get_product_by_id(self, product_id: str) -> Optional[ShopProduct]:
        for p in self.products:
            if p.id == product_id:
                return p
        return None

    # --- Price helper ---

    def format_price(self, amount: float) -> str:
        return format_price(amount, self.shop.currency)

    # --- Update dispatch ---

    async def handle_update(self, update: dict) -> None:
        try:
            if "message" in update:
                message = update["message"]
                chat_id = message["chat"]["id"]
                self._capture_user_identity(
                    chat_id, message.get("from", {})
                )
                text = message.get("text", "")
                if text.startswith("/"):
                    await self.handle_command(message)
            elif "inline_query" in update:
                await self.handle_inline_query(update["inline_query"])
        except Exception as e:
            logger.error(
                f"Error handling update: {_safe_err(e, self.shop.bot_token)}"
            )

    # --- Command handler ---

    async def handle_command(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        parts = text.split()
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else None

        if command == "/start":
            await self.cmd_start(chat_id, args)

    async def cmd_start(
        self, chat_id: int, args: Optional[str] = None
    ) -> None:
        session = self.get_session(chat_id)

        # Track customer
        username = session.username
        await upsert_customer(
            self.shop.id, chat_id, username=username
        )

        title = escape_html(self.shop.title)
        desc = escape_html(self.shop.description or "")

        text = f"<b>{title}</b>\n"
        text += f"{SEP}\n\n"
        if desc:
            text += f"{desc}\n\n"
        text += (
            "Browse products, pay instantly, track orders\n"
            "— all right here in Telegram.\n"
        )

        # Deep link: /start product_<id> → open TMA on that product
        tma_url = self.tma_url
        if args and args.startswith("product_"):
            product_id = args[8:]
            if self.get_product_by_id(product_id):
                tma_url = self.tma_url + f"#/product/{product_id}"

        buttons = [
            [{"text": "Open Shop", "web_app": {"url": tma_url}}],
        ]
        keyboard = self._inline_keyboard(buttons)
        await self.send_message(chat_id, text, reply_markup=keyboard)

    # --- Payment confirmation (called from tasks.py) ---

    async def send_payment_confirmation(
        self, chat_id: int, order: Order, credit_used: int = 0
    ) -> None:
        cart_items = json.loads(order.cart_json)
        items_text = "\n".join(
            f"  {item['quantity']}x {escape_html(item['title'])}"
            for item in cart_items
        )
        text = (
            f"<b>Payment Confirmed!</b>\n"
            f"{SEP}\n\n"
            f"Thank you for your order!\n\n"
            f"<b>Order #{order.id[:8]}</b>\n"
            f"{items_text}\n"
            f"Total: {format_sats(order.amount_sats)} sats"
        )
        if credit_used > 0:
            text += f"\nStore credit: {format_sats(credit_used)} sats"

        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [
                [{"text": "My Orders", "web_app": {"url": tma_url + "#/orders"}}],
                [{"text": "Open Shop", "web_app": {"url": tma_url}}],
            ]
        )
        await self.send_message(chat_id, text, reply_markup=keyboard)

        # Notify admin
        await self.notify_admin_new_order(order)

    # --- Admin notifications ---

    async def notify_admin_new_order(self, order: Order) -> None:
        if not self.shop.admin_chat_id:
            return
        admin_chat_id = int(self.shop.admin_chat_id)
        cart_items = json.loads(order.cart_json)
        lines = []
        for i in cart_items:
            line = f"  {i['quantity']}x {i['title']}"
            if i.get("sku"):
                line += f" [{i['sku']}]"
            lines.append(line)
        items_text = "\n".join(lines)
        text = (
            f"<b>New Order!</b>\n"
            f"{SEP}\n\n"
            f"Order #{order.id[:8]}\n"
            f"Customer: @{order.telegram_username or 'unknown'}\n"
            f"{items_text}\n"
            f"Total: {format_sats(order.amount_sats)} sats"
        )
        if order.buyer_email:
            text += f"\n{order.buyer_email}"
        await self.send_message(admin_chat_id, text)

    async def notify_admin_message(
        self,
        chat_id: int,
        username: Optional[str],
        content: str,
        order_id: Optional[str],
    ) -> None:
        if not self.shop.admin_chat_id:
            return
        admin_chat_id = int(self.shop.admin_chat_id)
        user_display = f"@{username}" if username else f"Chat #{chat_id}"
        text = f"<b>New message from {escape_html(user_display)}</b>\n"
        if order_id:
            text += f"Order: #{order_id[:8]}\n"
        text += f"\n\"{escape_html(content)}\""
        await self.send_message(admin_chat_id, text)

    async def notify_admin_return(self, ret, order: Order) -> None:
        if not self.shop.admin_chat_id:
            return
        admin_chat_id = int(self.shop.admin_chat_id)
        items = json.loads(ret.items_json)
        items_text = ", ".join(f"{i['quantity']}x {i['title']}" for i in items)
        text = (
            f"<b>Return Request</b>\n"
            f"{SEP}\n\n"
            f"Order: #{order.id[:8]}\n"
            f"Customer: @{order.telegram_username or 'unknown'}\n"
            f"Items: {escape_html(items_text)}\n"
            f"Amount: {format_sats(ret.refund_amount_sats)} sats\n"
            f"Reason: \"{escape_html(ret.reason or 'No reason given')}\""
        )
        await self.send_message(admin_chat_id, text)

    # --- Notifications from admin actions ---

    async def send_admin_reply(
        self, chat_id: int, content: str, order_id: Optional[str]
    ) -> None:
        text = "<b>Message from Shop</b>\n\n"
        if order_id:
            text += f"Regarding Order #{order_id[:8]}\n\n"
        text += f"\"{escape_html(content)}\""
        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [
                [
                    {"text": "Messages", "web_app": {"url": tma_url + "#/messages"}},
                    {"text": "Shop", "web_app": {"url": tma_url}},
                ]
            ]
        )
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def notify_return_approved_credit(
        self, chat_id: int, amount_sats: int
    ) -> None:
        tma_url = self.tma_url
        await self.send_message(
            chat_id,
            f"<b>Return Approved</b>\n\n"
            f"You've received <b>{format_sats(amount_sats)} sats</b> "
            f"in store credit.\n\n"
            f"It will be applied automatically at checkout.",
            reply_markup=self._inline_keyboard(
                [[{"text": "Open Shop", "web_app": {"url": tma_url}}]]
            ),
        )

    async def notify_return_approved_lightning(
        self, chat_id: int, amount_sats: int
    ) -> None:
        tma_url = self.tma_url
        await self.send_message(
            chat_id,
            f"<b>Return Approved</b>\n"
            f"{SEP}\n\n"
            f"Your refund of <b>{format_sats(amount_sats)} sats</b> "
            f"has been approved.\n\n"
            f"Please open Messages in the shop and send us your "
            f"Lightning address or invoice so we can process your refund.",
            reply_markup=self._inline_keyboard(
                [[{"text": "Messages", "web_app": {"url": tma_url + "#/messages"}}]]
            ),
        )

    async def notify_return_denied(
        self, chat_id: int, admin_note: str
    ) -> None:
        tma_url = self.tma_url
        await self.send_message(
            chat_id,
            f"<b>Return Not Approved</b>\n\n"
            f"Reason: \"{escape_html(admin_note)}\"\n\n"
            f"If you have questions, reach us via Messages.",
            reply_markup=self._inline_keyboard(
                [
                    [
                        {"text": "Messages", "web_app": {"url": tma_url + "#/messages"}},
                        {"text": "Shop", "web_app": {"url": tma_url}},
                    ]
                ]
            ),
        )

    async def notify_fulfillment_update(
        self, chat_id: int, order: Order, status: str, note: Optional[str]
    ) -> None:
        status_labels = {
            "preparing": "Preparing",
            "shipping": "Shipping",
            "delivered": "Delivered",
        }
        label = status_labels.get(status, status)
        text = (
            f"<b>Order Update</b>\n\n"
            f"Order #{order.id[:8]} — <b>{label}</b>"
        )
        if note:
            text += f"\n\n{escape_html(note)}"
        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [[{"text": "View Orders", "web_app": {"url": tma_url + "#/orders"}}]]
        )
        await self.send_message(chat_id, text, reply_markup=keyboard)

    # --- Inline mode ---

    async def handle_inline_query(self, inline_query: dict) -> None:
        query = inline_query.get("query", "").lower()
        query_id = inline_query["id"]
        products = self.get_active_products()

        if query:
            products = [
                p for p in products if query in p.title.lower()
            ]

        results = []
        for p in products[:20]:
            buy_btn = {
                "text": "Open Shop",
                "url": f"https://t.me/{self._bot_username}?start=open",
            }
            caption = (
                f"<b>{escape_html(p.title)}</b>\n"
                f"{self.format_price(p.price)}"
            )
            if p.image_url and self._is_valid_photo_url(p.image_url):
                results.append(
                    {
                        "type": "photo",
                        "id": p.id,
                        "photo_url": p.image_url,
                        "thumbnail_url": p.image_url,
                        "title": p.title,
                        "description": self.format_price(p.price),
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": [[buy_btn]]},
                    }
                )
            else:
                results.append(
                    {
                        "type": "article",
                        "id": p.id,
                        "title": p.title,
                        "description": self.format_price(p.price),
                        "input_message_content": {
                            "message_text": caption,
                            "parse_mode": "HTML",
                        },
                        "reply_markup": {"inline_keyboard": [[buy_btn]]},
                    }
                )

        await self.api_call(
            "answerInlineQuery",
            inline_query_id=query_id,
            results=results,
            cache_time=30,
        )

    # --- Keyboard helper ---

    @staticmethod
    def _inline_keyboard(
        buttons: list[list[dict]],
    ) -> dict:
        return {"inline_keyboard": buttons}
