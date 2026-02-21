import asyncio
import json
from typing import Dict, List, Optional, Tuple

import httpx
from loguru import logger

from lnbits.core.services import create_invoice, get_pr_from_lnurl, pay_invoice
from lnbits.settings import settings
from lnbits.utils.exchange_rates import (
    fiat_amount_as_satoshis,
    satoshis_amount_as_fiat,
)

from .crud import (
    create_message,
    create_order,
    create_return,
    delete_cart,
    get_cart,
    get_order,
    get_orders_by_chat,
    get_active_return_for_order,
    get_total_available_credit,
    update_order_status,
    upsert_cart,
    upsert_customer,
    use_credits,
)
from .helpers import escape_html, format_address, format_sats, validate_email
from .models import (
    BuyerAddress,
    CartItem,
    Order,
    Shop,
    ShopProduct,
    UserSession,
    UserState,
)
from .product_sources import (
    _is_telegram_reachable_url,
    fetch_inventory_products,
)

SEP = "━━━━━━━━━━━━━━━━━━"


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

    async def _send_or_edit(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
        edit_message_id: Optional[int] = None,
    ) -> dict:
        """Send a new message or edit an existing one in place."""
        if edit_message_id:
            return await self.edit_message_text(
                chat_id, edit_message_id, text, reply_markup=reply_markup
            )
        return await self.send_message(
            chat_id, text, reply_markup=reply_markup
        )

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
            logger.error(f"Telegram API call failed ({method}): {e}")
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

    async def send_media_group(
        self,
        chat_id: int,
        media: list,
    ) -> dict:
        return await self.api_call(
            "sendMediaGroup", chat_id=chat_id, media=media
        )

    async def answer_callback(
        self, callback_query_id: str, text: Optional[str] = None
    ) -> dict:
        kwargs = {"callback_query_id": callback_query_id}
        if text:
            kwargs["text"] = text
            kwargs["show_alert"] = False
        return await self.api_call("answerCallbackQuery", **kwargs)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
    ) -> dict:
        kwargs = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            kwargs["reply_markup"] = reply_markup
        return await self.api_call("editMessageText", **kwargs)

    async def edit_message_reply_markup(
        self, chat_id: int, message_id: int, reply_markup: dict
    ) -> dict:
        return await self.api_call(
            "editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )

    async def delete_message(self, chat_id: int, message_id: int) -> dict:
        return await self.api_call(
            "deleteMessage", chat_id=chat_id, message_id=message_id
        )

    async def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "🛍 Welcome & open shop"},
            {"command": "orders", "description": "📦 View your orders"},
            {"command": "credits", "description": "✨ Store credit balance"},
            {"command": "message", "description": "💬 Contact us"},
            {"command": "help", "description": "📖 How to shop"},
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
            logger.error(f"Failed to load products: {e}")

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

    async def ensure_session(self, chat_id: int) -> UserSession:
        """Get or create session, loading cart from DB if empty."""
        session = self.get_session(chat_id)
        if not session.cart:
            await self._load_cart_from_db(chat_id)
        return session

    async def _sync_cart_to_db(self, chat_id: int) -> None:
        """Persist in-memory cart to DB."""
        session = self.get_session(chat_id)
        if session.cart:
            cart_json = json.dumps([item.dict() for item in session.cart])
            await upsert_cart(self.shop.id, chat_id, cart_json)
        else:
            await delete_cart(self.shop.id, chat_id)

    async def _load_cart_from_db(self, chat_id: int) -> None:
        """Load cart from DB into empty in-memory session."""
        session = self.get_session(chat_id)
        if session.cart:
            return
        cart = await get_cart(self.shop.id, chat_id)
        if cart and cart.cart_json:
            try:
                items_raw = json.loads(cart.cart_json)
                session.cart = [CartItem(**item) for item in items_raw]
            except (json.JSONDecodeError, TypeError):
                pass

    # --- Product helpers ---

    def get_active_products(self) -> List[ShopProduct]:
        return [p for p in self.products if not p.disabled]

    def get_categories(self) -> List[str]:
        cats = set()
        for p in self.get_active_products():
            if p.category:
                cats.add(p.category)
        return sorted(cats)

    def get_products_for_category(self, category: str) -> List[ShopProduct]:
        active = self.get_active_products()
        if category == "all":
            return active
        return [p for p in active if p.category == category]

    def get_product_by_id(self, product_id: str) -> Optional[ShopProduct]:
        for p in self.products:
            if p.id == product_id:
                return p
        return None

    # --- Price helpers ---

    async def sats_amount(self, amount: float) -> int:
        if self.shop.currency == "sat":
            return int(amount)
        return await fiat_amount_as_satoshis(amount, self.shop.currency)

    async def fiat_display(self, sats: int) -> Optional[str]:
        if self.shop.currency == "sat":
            return None
        fiat = await satoshis_amount_as_fiat(sats, self.shop.currency)
        return f"~{fiat:.2f} {self.shop.currency.upper()}"

    def format_price(self, amount: float) -> str:
        if self.shop.currency == "sat":
            return f"{format_sats(int(amount))} sats"
        return f"{amount:.2f} {self.shop.currency.upper()}"

    def cart_has_physical_items(self, session: UserSession) -> bool:
        for item in session.cart:
            product = self.get_product_by_id(item.product_id)
            if product and product.requires_shipping:
                return True
        return False

    def _cart_tax_inclusive(self, session: UserSession) -> bool:
        """Check if any product in cart uses inclusive tax."""
        for item in session.cart:
            product = self.get_product_by_id(item.product_id)
            if product and product.tax_rate:
                return product.is_tax_inclusive
        return True

    # --- Cart calculations ---

    def calculate_cart(
        self, session: UserSession
    ) -> Tuple[float, float, float, float]:
        """
        Calculate cart totals.
        Returns (subtotal, tax_total, shipping, total).
        """
        subtotal = 0.0
        tax_total = 0.0
        total_weight_grams = 0
        has_physical = False
        tax_inclusive = True

        for item in session.cart:
            item_total = item.price * item.quantity
            product = self.get_product_by_id(item.product_id)
            tax_rate = 0.0
            if product and product.tax_rate is not None:
                tax_rate = product.tax_rate
                tax_inclusive = product.is_tax_inclusive
            if product and product.requires_shipping:
                has_physical = True
                total_weight_grams += (
                    (product.weight_grams or 0) * item.quantity
                )

            if tax_rate > 0:
                if tax_inclusive:
                    tax_amount = item_total * (
                        tax_rate / (100 + tax_rate)
                    )
                else:
                    tax_amount = item_total * (tax_rate / 100)
                tax_total += tax_amount

            subtotal += item_total

        shipping = 0.0
        if has_physical:
            flat = self.shop.shipping_flat_rate or 0
            per_kg = self.shop.shipping_per_kg or 0
            threshold = self.shop.shipping_free_threshold or 0

            shipping = flat + (total_weight_grams / 1000.0) * per_kg

            if threshold > 0 and subtotal >= threshold:
                shipping = 0.0

        if tax_inclusive:
            total = subtotal + shipping
        else:
            total = subtotal + tax_total + shipping
        return subtotal, tax_total, shipping, total

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
                else:
                    await self.handle_text(message)
            elif "callback_query" in update:
                cb = update["callback_query"]
                chat_id = cb["message"]["chat"]["id"]
                self._capture_user_identity(
                    chat_id, cb.get("from", {})
                )
                await self.handle_callback(cb)
            elif "inline_query" in update:
                await self.handle_inline_query(update["inline_query"])
        except Exception as e:
            logger.error(f"Error handling update: {e}")

    # --- Command handlers ---

    async def handle_command(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        parts = text.split()
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else None

        if command == "/start":
            await self.cmd_start(chat_id, args)
        elif command == "/orders":
            await self.cmd_orders(chat_id)
        elif command == "/credits":
            await self.cmd_credits(chat_id)
        elif command == "/message":
            await self.cmd_message(chat_id)
        elif command == "/help":
            await self.cmd_help(chat_id)
        elif command == "/skip":
            await self.handle_skip(chat_id)

    async def cmd_start(
        self, chat_id: int, args: Optional[str] = None
    ) -> None:
        session = await self.ensure_session(chat_id)
        session.state = UserState.BROWSING

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
            "⚡ <b>Lightning-powered shop</b>\n"
            "Browse products, pay instantly, track orders\n"
            "— all right here in Telegram.\n"
        )

        tma_url = self.tma_url
        buttons = [
            [{"text": "🛍  Open Shop", "web_app": {"url": tma_url}}],
            [
                {"text": "📦 Orders", "web_app": {"url": tma_url}},
                {"text": "📖 Help", "web_app": {"url": tma_url}},
            ],
        ]
        keyboard = self._inline_keyboard(buttons)
        await self.send_message(chat_id, text, reply_markup=keyboard)

    async def cmd_orders(self, chat_id: int) -> None:
        await self.show_orders(chat_id)

    async def cmd_credits(self, chat_id: int) -> None:
        balance = await get_total_available_credit(self.shop.id, chat_id)
        tma_url = self.tma_url
        if balance > 0:
            text = (
                f"✨ <b>Store Credit</b>\n\n"
                f"Your balance: <b>{format_sats(balance)} sats</b>\n\n"
                f"Credit is applied automatically at checkout."
            )
        else:
            text = (
                "✨ <b>Store Credit</b>\n\n"
                "You have no store credit at the moment."
            )
        await self.send_message(
            chat_id,
            text,
            reply_markup=self._inline_keyboard(
                [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
            ),
        )

    async def cmd_message(self, chat_id: int) -> None:
        session = self.get_session(chat_id)
        session.state = UserState.WAITING_MESSAGE
        session.pending_order_id = None
        keyboard = self._inline_keyboard(
            [[{"text": "❌ Cancel", "callback_data": "cancel"}]]
        )
        await self.send_message(
            chat_id,
            "💬 <b>Contact Us</b>\n\nType your message below and we'll get back to you:",
            reply_markup=keyboard,
        )

    async def cmd_help(self, chat_id: int) -> None:
        tma_url = self.tma_url
        text = (
            "📖 <b>How to Shop</b>\n\n"
            f"{SEP}\n"
            "🛍 Tap <b>Open Shop</b> to browse and buy\n"
            "📦 /orders — View your orders\n"
            "✨ /credits — Store credit balance\n"
            "💬 /message — Contact us\n"
            "📖 /help — This guide\n"
            f"{SEP}\n\n"
            "Pay instantly with ⚡ Lightning!"
        )
        await self.send_message(
            chat_id,
            text,
            reply_markup=self._inline_keyboard(
                [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
            ),
        )

    # --- Callback handlers ---

    async def handle_callback(self, callback_query: dict) -> None:
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        data = callback_query.get("data", "")
        cb_id = callback_query["id"]

        session = self.get_session(chat_id)

        if data == "cancel":
            session.state = UserState.BROWSING
            session.pending_product_id = None
            await self.answer_callback(cb_id)
            tma_url = self.tma_url
            await self._send_or_edit(
                chat_id,
                "❌ Cancelled.",
                reply_markup=self._inline_keyboard(
                    [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
                ),
                edit_message_id=message_id,
            )
        elif data == "back":
            await self.answer_callback(cb_id)
            await self.handle_back(chat_id)
        elif data == "skip":
            await self.answer_callback(cb_id)
            await self.handle_skip(chat_id)
        elif data == "confirm_address":
            await self.answer_callback(cb_id)
            await self.create_order_and_invoice(chat_id, edit_message_id=message_id)
        elif data == "edit_address":
            session.state = UserState.WAITING_NAME
            await self.answer_callback(cb_id)
            await self.prompt_checkout_field(chat_id)
        elif data == "orders":
            await self.answer_callback(cb_id)
            await self.show_orders(chat_id, edit_message_id=message_id)
        elif data == "help_cb":
            await self.answer_callback(cb_id)
            await self.cmd_help(chat_id)
        elif data.startswith("msg_"):
            order_id = data[4:] if data[4:] != "general" else None
            session.state = UserState.WAITING_MESSAGE
            session.pending_order_id = order_id
            await self.answer_callback(cb_id)
            await self._send_or_edit(
                chat_id,
                "💬 <b>Contact Us</b>\n\nType your message below and we'll get back to you:",
                reply_markup=self._inline_keyboard(
                    [[{"text": "❌ Cancel", "callback_data": "cancel"}]]
                ),
                edit_message_id=message_id,
            )
        elif data.startswith("return_"):
            order_id = data[7:]
            await self.answer_callback(cb_id)
            await self.start_return(chat_id, order_id, edit_message_id=message_id)
        elif data.startswith("retitem_"):
            product_id = data[8:]
            await self.answer_callback(cb_id)
            await self.toggle_return_item(chat_id, product_id, edit_message_id=message_id)
        elif data == "retconfirm":
            await self.answer_callback(cb_id)
            session.state = UserState.WAITING_RETURN_REASON
            await self.send_message(
                chat_id,
                "↩️ <b>Reason for Return</b>\n\n"
                "Please tell us why you'd like to return these items. "
                "For example:\n"
                "• What's wrong with the item (defect, damage, etc.)\n"
                "• How it differs from what you expected\n"
                "• Any other details that help us process your return\n\n"
                "<i>Your message is required to submit the return.</i>",
                reply_markup=self._inline_keyboard(
                    [[{"text": "❌ Cancel", "callback_data": "retcancel"}]]
                ),
            )
        elif data == "retcancel":
            session.state = UserState.BROWSING
            session.pending_return_items = None
            session.pending_order_id = None
            await self.answer_callback(cb_id)
            tma_url = self.tma_url
            await self._send_or_edit(
                chat_id,
                "❌ Return cancelled.",
                reply_markup=self._inline_keyboard(
                    [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
                ),
                edit_message_id=message_id,
            )
        else:
            await self.answer_callback(cb_id)

    # --- Text input handlers ---

    async def handle_text(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        session = self.get_session(chat_id)
        username = message.get("from", {}).get("username")

        if session.state == UserState.WAITING_EMAIL:
            if not validate_email(text):
                await self.send_message(
                    chat_id,
                    "❌ Invalid email address. Please try again.",
                    reply_markup=self._inline_keyboard(
                        [[{"text": "↩️ Back", "callback_data": "back"},
                          {"text": "❌ Cancel", "callback_data": "cancel"}]]
                    ),
                )
                return
            session.buyer_email = text
            if self.cart_has_physical_items(session):
                session.state = UserState.WAITING_NAME
                await self.prompt_checkout_field(chat_id)
            else:
                await self.create_order_and_invoice(chat_id)

        elif session.state == UserState.WAITING_NAME:
            session.buyer_name = text
            session.state = UserState.WAITING_STREET
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_STREET:
            session.buyer_street = text
            session.state = UserState.WAITING_STREET2
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_STREET2:
            session.buyer_street2 = text
            session.state = UserState.WAITING_POBOX
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_POBOX:
            session.buyer_po_box = text
            session.state = UserState.WAITING_CITY
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_CITY:
            session.buyer_city = text
            session.state = UserState.WAITING_STATE
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_STATE:
            session.buyer_state = text
            session.state = UserState.WAITING_ZIP
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_ZIP:
            session.buyer_zip = text
            session.state = UserState.WAITING_COUNTRY
            await self.prompt_checkout_field(chat_id)

        elif session.state == UserState.WAITING_COUNTRY:
            session.buyer_country = text
            await self.show_address_summary(chat_id)

        elif session.state == UserState.WAITING_MESSAGE:
            await create_message(
                shop_id=self.shop.id,
                chat_id=chat_id,
                direction="in",
                content=text,
                username=username,
                order_id=session.pending_order_id,
            )
            session.state = UserState.BROWSING
            await self.send_message(chat_id, "✅ Message sent! We'll get back to you soon.")
            await self.notify_admin_message(chat_id, username, text, session.pending_order_id)

        elif session.state == UserState.WAITING_RETURN_REASON:
            if not text or len(text.strip()) < 5:
                await self.send_message(
                    chat_id,
                    "⚠️ Please provide a more detailed reason "
                    "(at least a few words) so we can process your return.",
                )
                return
            await self.submit_return(chat_id, text.strip())

        elif session.state == UserState.WAITING_REFUND_INVOICE:
            await self.process_refund_invoice(chat_id, text)

    async def handle_skip(self, chat_id: int) -> None:
        session = self.get_session(chat_id)
        if session.state == UserState.WAITING_STREET2:
            session.buyer_street2 = None
            session.state = UserState.WAITING_POBOX
            await self.prompt_checkout_field(chat_id)
        elif session.state == UserState.WAITING_POBOX:
            session.buyer_po_box = None
            session.state = UserState.WAITING_CITY
            await self.prompt_checkout_field(chat_id)
        elif session.state == UserState.WAITING_STATE:
            session.buyer_state = None
            session.state = UserState.WAITING_ZIP
            await self.prompt_checkout_field(chat_id)

    async def handle_back(self, chat_id: int) -> None:
        session = self.get_session(chat_id)
        back_map = {
            UserState.WAITING_EMAIL: None,
            UserState.WAITING_NAME: UserState.WAITING_EMAIL,
            UserState.WAITING_STREET: UserState.WAITING_NAME,
            UserState.WAITING_STREET2: UserState.WAITING_STREET,
            UserState.WAITING_POBOX: UserState.WAITING_STREET2,
            UserState.WAITING_CITY: UserState.WAITING_POBOX,
            UserState.WAITING_STATE: UserState.WAITING_CITY,
            UserState.WAITING_ZIP: UserState.WAITING_STATE,
            UserState.WAITING_COUNTRY: UserState.WAITING_ZIP,
        }
        prev = back_map.get(session.state)
        if prev is None:
            session.state = UserState.BROWSING
            await self.cmd_start(chat_id)
        else:
            session.state = prev
            await self.prompt_checkout_field(chat_id)

    # --- Checkout prompts ---

    async def prompt_checkout_field(self, chat_id: int) -> None:
        session = self.get_session(chat_id)
        prompts = {
            UserState.WAITING_EMAIL: ("What's your email address?", False),
            UserState.WAITING_NAME: ("What's your full name?", False),
            UserState.WAITING_STREET: ("What's your street address?", False),
            UserState.WAITING_STREET2: ("Apartment, suite, or unit (optional):", True),
            UserState.WAITING_POBOX: ("PO Box number (optional):", True),
            UserState.WAITING_CITY: ("What city?", False),
            UserState.WAITING_STATE: ("State or province (optional):", True),
            UserState.WAITING_ZIP: ("What's your postal / ZIP code?", False),
            UserState.WAITING_COUNTRY: ("What country?", False),
        }

        prompt_text, is_optional = prompts.get(
            session.state, ("Enter information:", False)
        )

        step_labels = [
            UserState.WAITING_NAME,
            UserState.WAITING_STREET,
            UserState.WAITING_STREET2,
            UserState.WAITING_POBOX,
            UserState.WAITING_CITY,
            UserState.WAITING_STATE,
            UserState.WAITING_ZIP,
            UserState.WAITING_COUNTRY,
        ]
        step_num = (
            step_labels.index(session.state) + 1
            if session.state in step_labels
            else None
        )
        step_text = f"Step {step_num} of {len(step_labels)}\n\n" if step_num else ""

        text = f"📦 <b>Shipping Details</b>\n{step_text}{prompt_text}"

        buttons = []
        if is_optional:
            buttons.append([{"text": "⏭ Skip", "callback_data": "skip"}])
        buttons.append(
            [
                {"text": "↩️ Back", "callback_data": "back"},
                {"text": "❌ Cancel", "callback_data": "cancel"},
            ]
        )
        await self.send_message(
            chat_id, text, reply_markup=self._inline_keyboard(buttons)
        )

    async def show_address_summary(self, chat_id: int) -> None:
        session = self.get_session(chat_id)
        addr = format_address(
            session.buyer_name or "",
            session.buyer_street or "",
            session.buyer_street2,
            session.buyer_po_box,
            session.buyer_city or "",
            session.buyer_state,
            session.buyer_zip or "",
            session.buyer_country or "",
        )
        text = (
            f"📦 <b>Shipping Address</b>\n\n"
            f"<pre>{escape_html(addr)}</pre>\n\n"
            f"Is this correct?"
        )
        keyboard = self._inline_keyboard(
            [
                [
                    {"text": "✅ Confirm", "callback_data": "confirm_address"},
                    {"text": "✏️ Edit", "callback_data": "edit_address"},
                ],
                [{"text": "❌ Cancel", "callback_data": "cancel"}],
            ]
        )
        await self.send_message(chat_id, text, reply_markup=keyboard)

    # --- Checkout flow ---

    async def begin_checkout(
        self, chat_id: int, edit_message_id: Optional[int] = None
    ) -> None:
        session = self.get_session(chat_id)
        if not session.cart:
            await self._send_or_edit(
                chat_id, "🛒 Your cart is empty.",
                edit_message_id=edit_message_id,
            )
            return

        if not await self.validate_stock(chat_id):
            return

        checkout_mode = self.shop.checkout_mode
        has_physical = self.cart_has_physical_items(session)

        if checkout_mode == "none" and not has_physical:
            await self.create_order_and_invoice(chat_id, edit_message_id=edit_message_id)
        elif checkout_mode in ("email", "address"):
            session.state = UserState.WAITING_EMAIL
            await self._send_or_edit(
                chat_id,
                "💳 <b>Checkout</b>\n\nPlease enter your email address:",
                reply_markup=self._inline_keyboard(
                    [[{"text": "↩️ Back", "callback_data": "back"},
                      {"text": "❌ Cancel", "callback_data": "cancel"}]]
                ),
                edit_message_id=edit_message_id,
            )
        elif checkout_mode == "none" and has_physical:
            session.state = UserState.WAITING_NAME
            await self.prompt_checkout_field(chat_id)

    async def create_order_and_invoice(
        self, chat_id: int, edit_message_id: Optional[int] = None
    ) -> None:
        session = self.get_session(chat_id)
        if not session.cart:
            return

        _, _, _, total = self.calculate_cart(session)
        total_sats = await self.sats_amount(total)
        has_physical = self.cart_has_physical_items(session)

        # Apply store credit
        credit_used = 0
        available_credit = await get_total_available_credit(
            self.shop.id, chat_id
        )
        if available_credit > 0:
            credit_used = min(available_credit, total_sats)
            total_sats -= credit_used
            await use_credits(self.shop.id, chat_id, credit_used)

        # Build address JSON
        buyer_address_json = None
        if has_physical and session.buyer_name:
            addr = BuyerAddress(
                name=session.buyer_name or "",
                street=session.buyer_street or "",
                street2=session.buyer_street2,
                po_box=session.buyer_po_box,
                city=session.buyer_city or "",
                state=session.buyer_state,
                zip_code=session.buyer_zip or "",
                country=session.buyer_country or "",
            )
            buyer_address_json = json.dumps(addr.dict())

        cart_json = json.dumps([item.dict() for item in session.cart])
        username = session.username

        if total_sats <= 0:
            # Fully covered by credit
            order = await create_order(
                shop_id=self.shop.id,
                payment_hash="credit_" + str(chat_id),
                telegram_chat_id=chat_id,
                telegram_username=username,
                amount_sats=0,
                currency=self.shop.currency,
                currency_amount=total,
                cart_json=cart_json,
                buyer_email=session.buyer_email,
                buyer_name=session.buyer_name,
                buyer_address=buyer_address_json,
                has_physical_items=has_physical,
            )
            await update_order_status(order.id, "paid")
            await self.send_payment_confirmation(chat_id, order, credit_used)
            await self._reset_session(session, chat_id)
            return

        # Create Lightning invoice (15 minute expiry)
        memo = f"Order from {self.shop.title}"
        try:
            payment = await create_invoice(
                wallet_id=self.shop.wallet,
                amount=total_sats,
                memo=memo,
                expiry=900,
                extra={"tag": "telegramshop", "shop_id": self.shop.id, "chat_id": chat_id},
            )
        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            await self.send_message(chat_id, "❌ Something went wrong creating your invoice. Please try again.")
            return

        order = await create_order(
            shop_id=self.shop.id,
            payment_hash=payment.payment_hash,
            telegram_chat_id=chat_id,
            telegram_username=username,
            amount_sats=total_sats,
            currency=self.shop.currency,
            currency_amount=total,
            cart_json=cart_json,
            buyer_email=session.buyer_email,
            buyer_name=session.buyer_name,
            buyer_address=buyer_address_json,
            has_physical_items=has_physical,
        )

        # Build invoice message
        fiat_text = await self.fiat_display(total_sats)
        text = (
            f"⚡ <b>Invoice Created</b>\n"
            f"{SEP}\n\n"
            f"<b>Order #{order.id[:8]}</b>\n"
            f"💰 Total: <b>{format_sats(total_sats)} sats</b>\n"
        )
        if credit_used > 0:
            text += f"✨ Store credit: -{format_sats(credit_used)} sats\n"
        if fiat_text:
            text += f"({fiat_text})\n"
        text += (
            f"\n⏰ Expires in 15 minutes\n\n"
            f"<code>{payment.bolt11}</code>\n\n"
            f"Copy and pay with any ⚡ Lightning wallet."
        )

        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [
                [{"text": "⚡ Pay Now", "url": f"{settings.lnbits_baseurl}/wallet?pay={payment.bolt11}"}],
                [{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}],
            ]
        )
        await self._send_or_edit(
            chat_id, text, reply_markup=keyboard,
            edit_message_id=edit_message_id,
        )

        # Schedule expiry notification (15 minutes)
        asyncio.create_task(
            self._notify_invoice_expiry(chat_id, order.id, payment.payment_hash)
        )

        await self._reset_session(session, chat_id)

    async def _reset_session(
        self, session: UserSession, chat_id: Optional[int] = None
    ) -> None:
        session.cart = []
        session.state = UserState.BROWSING
        session.buyer_email = None
        session.buyer_name = None
        session.buyer_street = None
        session.buyer_street2 = None
        session.buyer_po_box = None
        session.buyer_city = None
        session.buyer_state = None
        session.buyer_zip = None
        session.buyer_country = None
        session.pending_product_id = None
        session.pending_order_id = None
        session.pending_return_items = None
        if chat_id is not None:
            await self._sync_cart_to_db(chat_id)

    async def _notify_invoice_expiry(
        self, chat_id: int, order_id: str, payment_hash: str
    ) -> None:
        """Wait 15 minutes, then check if order is still unpaid and notify."""
        try:
            await asyncio.sleep(900)
            order = await get_order(order_id)
            if not order or order.status != "pending":
                return
            await update_order_status(order_id, "expired")
            tma_url = self.tma_url
            keyboard = self._inline_keyboard(
                [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
            )
            await self.send_message(
                chat_id,
                (
                    f"⏰ <b>Invoice Expired</b>\n\n"
                    f"Order #{order_id[:8]} — no payment received\n"
                    f"within 15 minutes.\n\n"
                    f"You can place a new order anytime."
                ),
                reply_markup=keyboard,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Expiry notification error: {e}")

    # --- Stock validation ---

    async def validate_stock(self, chat_id: int) -> bool:
        session = self.get_session(chat_id)
        issues = []
        for item in session.cart:
            product = self.get_product_by_id(item.product_id)
            if not product:
                issues.append(f"❌ {item.title} is no longer available.")
                continue
            if product.disabled:
                issues.append(f"❌ {item.title} is no longer available.")
                continue
            if product.inventory is not None and item.quantity > product.inventory:
                if product.inventory <= 0:
                    issues.append(f"❌ {item.title} is out of stock.")
                else:
                    issues.append(
                        f"⚠️ {item.title}: only {product.inventory} available (you have {item.quantity})."
                    )
        if issues:
            text = "⚠️ <b>Stock Issues</b>\n\n" + "\n".join(issues)
            text += "\n\nPlease update your cart."
            await self.send_message(chat_id, text)
            return False
        return True

    # --- Payment confirmation (called from tasks.py) ---

    async def send_payment_confirmation(
        self, chat_id: int, order: Order, credit_used: int = 0
    ) -> None:
        cart_items = json.loads(order.cart_json)
        items_text = "\n".join(
            f"  {item['quantity']}× {escape_html(item['title'])}"
            for item in cart_items
        )
        text = (
            f"✅ <b>Payment Confirmed!</b>\n"
            f"{SEP}\n\n"
            f"Thank you for your order!\n\n"
            f"<b>Order #{order.id[:8]}</b>\n"
            f"{items_text}\n"
            f"💰 Total: {format_sats(order.amount_sats)} sats"
        )
        if credit_used > 0:
            text += f"\n✨ Store credit: {format_sats(credit_used)} sats"

        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [
                [{"text": "📦 My Orders", "callback_data": "orders"}],
                [{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}],
            ]
        )
        await self.send_message(chat_id, text, reply_markup=keyboard)

        # Notify admin
        await self.notify_admin_new_order(order)

    # --- Orders display ---

    async def show_orders(
        self, chat_id: int, edit_message_id: Optional[int] = None
    ) -> None:
        orders = await get_orders_by_chat(self.shop.id, chat_id)
        tma_url = self.tma_url
        if not orders:
            await self._send_or_edit(
                chat_id,
                "📦 You have no orders yet.",
                reply_markup=self._inline_keyboard(
                    [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
                ),
                edit_message_id=edit_message_id,
            )
            return

        text = f"📦 <b>Your Orders</b>\n{SEP}\n\n"
        buttons: list[list[dict]] = []
        for order in orders[:10]:
            cart_items = json.loads(order.cart_json)
            items_summary = ", ".join(
                f"{i['quantity']}× {i['title']}" for i in cart_items
            )
            status_emoji = {
                "paid": "✅",
                "pending": "⏳",
                "expired": "⏰",
                "refunded": "↩️",
            }
            s_emoji = status_emoji.get(order.status, "📋")
            fulfillment_text = ""
            if order.fulfillment_status:
                fulfillment_emoji = {
                    "preparing": "📋 Preparing",
                    "shipping": "🚚 Shipping",
                    "delivered": "✅ Delivered",
                }
                fulfillment_text = f" · {fulfillment_emoji.get(order.fulfillment_status, order.fulfillment_status)}"
                if order.fulfillment_note:
                    fulfillment_text += f"\n   📝 {escape_html(order.fulfillment_note)}"

            text += (
                f"{s_emoji} <b>#{order.id[:8]}</b>{fulfillment_text}\n"
                f"  {escape_html(items_summary)}\n"
                f"  💰 {format_sats(order.amount_sats)} sats\n\n"
            )
            order_buttons: list[dict] = []
            order_buttons.append(
                {"text": f"💬 #{order.id[:8]}", "callback_data": f"msg_{order.id}"}
            )
            if self.shop.allow_returns and order.status == "paid":
                order_buttons.append(
                    {"text": "↩️ Return", "callback_data": f"return_{order.id}"}
                )
            buttons.append(order_buttons)

        buttons.append([{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}])
        await self._send_or_edit(
            chat_id, text,
            reply_markup=self._inline_keyboard(buttons),
            edit_message_id=edit_message_id,
        )

    # --- Returns ---

    async def start_return(
        self, chat_id: int, order_id: str, edit_message_id: Optional[int] = None
    ) -> None:
        session = self.get_session(chat_id)
        order = await get_order(order_id)
        if not order or order.telegram_chat_id != chat_id:
            await self._send_or_edit(
                chat_id, "❌ Order not found.",
                edit_message_id=edit_message_id,
            )
            return
        if order.status != "paid":
            await self._send_or_edit(
                chat_id, "❌ Returns are only available for completed orders.",
                edit_message_id=edit_message_id,
            )
            return

        # Block duplicate returns
        existing = await get_active_return_for_order(order_id)
        if existing:
            status_msg = {
                "requested": "pending review",
                "approved": "already approved",
                "refunded": "already refunded",
            }.get(existing.status, "in progress")
            tma_url = self.tma_url
            await self._send_or_edit(
                chat_id,
                f"↩️ A return for this order is {status_msg}.\n"
                "You cannot request another return.",
                reply_markup=self._inline_keyboard(
                    [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
                ),
                edit_message_id=edit_message_id,
            )
            return

        # Check return window
        if self.shop.return_window_hours > 0:
            from datetime import datetime, timezone
            try:
                ts = order.timestamp
                if isinstance(ts, str):
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            order_time = datetime.strptime(ts, fmt).replace(
                                tzinfo=timezone.utc
                            )
                            break
                        except ValueError:
                            continue
                    else:
                        order_time = datetime.now(timezone.utc)
                else:
                    order_time = datetime.now(timezone.utc)
                elapsed_hours = (
                    datetime.now(timezone.utc) - order_time
                ).total_seconds() / 3600
                if elapsed_hours > self.shop.return_window_hours:
                    tma_url = self.tma_url
                    await self._send_or_edit(
                        chat_id,
                        "❌ The return window for this order has expired.",
                        reply_markup=self._inline_keyboard(
                            [[{"text": "🛍 Open Shop",
                               "web_app": {"url": tma_url}}]]
                        ),
                        edit_message_id=edit_message_id,
                    )
                    return
            except Exception:
                pass

        session.pending_order_id = order_id
        session.pending_return_items = []
        session.state = UserState.WAITING_RETURN_ITEMS

        cart_items = json.loads(order.cart_json)
        text = f"↩️ <b>Return Request</b>\nOrder #{order_id[:8]}\n\nSelect items to return:"
        buttons = []
        for item in cart_items:
            pid = item["product_id"]
            check = "☐"
            buttons.append(
                [{"text": f"{check} {item['title']} ({item['quantity']}×)", "callback_data": f"retitem_{pid}"}]
            )
        buttons.append(
            [
                {"text": "✅ Confirm", "callback_data": "retconfirm"},
                {"text": "❌ Cancel", "callback_data": "retcancel"},
            ]
        )
        await self._send_or_edit(
            chat_id, text,
            reply_markup=self._inline_keyboard(buttons),
            edit_message_id=edit_message_id,
        )

    async def toggle_return_item(
        self, chat_id: int, product_id: str, edit_message_id: Optional[int] = None
    ) -> None:
        session = self.get_session(chat_id)
        if session.pending_return_items is None:
            session.pending_return_items = []
        if product_id in session.pending_return_items:
            session.pending_return_items.remove(product_id)
        else:
            session.pending_return_items.append(product_id)

        order = await get_order(session.pending_order_id or "")
        if not order:
            return
        cart_items = json.loads(order.cart_json)
        text = f"↩️ <b>Return Request</b>\nOrder #{order.id[:8]}\n\nSelect items to return:"
        buttons = []
        for item in cart_items:
            pid = item["product_id"]
            check = "☑" if pid in session.pending_return_items else "☐"
            buttons.append(
                [{"text": f"{check} {item['title']} ({item['quantity']}×)", "callback_data": f"retitem_{pid}"}]
            )
        buttons.append(
            [
                {"text": "✅ Confirm", "callback_data": "retconfirm"},
                {"text": "❌ Cancel", "callback_data": "retcancel"},
            ]
        )
        await self._send_or_edit(
            chat_id, text,
            reply_markup=self._inline_keyboard(buttons),
            edit_message_id=edit_message_id,
        )

    async def submit_return(self, chat_id: int, reason: str) -> None:
        session = self.get_session(chat_id)
        order = await get_order(session.pending_order_id or "")
        if not order:
            await self.send_message(chat_id, "❌ Order not found.")
            session.state = UserState.BROWSING
            return

        existing = await get_active_return_for_order(order.id)
        if existing:
            await self.send_message(
                chat_id,
                "↩️ A return for this order already exists. "
                "You cannot submit another one.",
            )
            session.state = UserState.BROWSING
            session.pending_return_items = None
            session.pending_order_id = None
            return

        cart_items = json.loads(order.cart_json)
        selected = session.pending_return_items or []
        return_items = [i for i in cart_items if i["product_id"] in selected]

        if not return_items:
            await self.send_message(chat_id, "⚠️ No items selected for return.")
            session.state = UserState.BROWSING
            return

        refund_amount = sum(
            i["price"] * i["quantity"] for i in return_items
        )
        refund_sats = await self.sats_amount(refund_amount)

        ret = await create_return(
            shop_id=self.shop.id,
            order_id=order.id,
            chat_id=chat_id,
            items_json=json.dumps(return_items),
            refund_amount_sats=refund_sats,
            reason=reason,
        )

        items_text = ", ".join(
            f"{i['quantity']}× {i['title']}" for i in return_items
        )
        await create_message(
            shop_id=self.shop.id,
            chat_id=chat_id,
            direction="in",
            content=(
                f"↩️ Return requested for order #{order.id[:8]}\n"
                f"Items: {items_text}\n"
                f"Reason: {reason}"
            ),
            username=session.username,
            order_id=order.id,
        )

        session.state = UserState.BROWSING
        session.pending_return_items = None
        session.pending_order_id = None

        tma_url = self.tma_url
        await self.send_message(
            chat_id,
            f"↩️ <b>Return Requested</b>\n"
            f"{SEP}\n\n"
            f"Your return request has been submitted.\n\n"
            f"Items: {escape_html(items_text)}\n"
            f"💰 Refund amount: {format_sats(refund_sats)} sats\n\n"
            f"We'll review your request shortly.",
            reply_markup=self._inline_keyboard(
                [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
            ),
        )

        await self.notify_admin_return(ret, order)

    async def process_refund_invoice(self, chat_id: int, text: str) -> None:
        session = self.get_session(chat_id)
        session.state = UserState.BROWSING
        amount_sats = session.pending_refund_sats
        session.pending_refund_sats = 0

        text = text.strip()
        try:
            bolt11 = None
            is_lnaddress = "@" in text and "." in text.split("@")[-1]
            is_lnurl = text.lower().startswith("lnurl")

            if is_lnaddress or is_lnurl:
                if amount_sats <= 0:
                    await self.send_message(
                        chat_id,
                        "❌ Could not determine the refund amount. "
                        "Please contact us via /message.",
                    )
                    return
                await self.send_message(
                    chat_id,
                    f"⚡ Resolving your Lightning address and sending "
                    f"{format_sats(amount_sats)} sats…",
                )
                bolt11 = await get_pr_from_lnurl(
                    text, amount_msat=amount_sats * 1000
                )
            else:
                bolt11 = text

            if not bolt11:
                await self.send_message(
                    chat_id,
                    "❌ Could not resolve that address. Please try again "
                    "with a ⚡ Lightning invoice or Lightning address.",
                )
                session.state = UserState.WAITING_REFUND_INVOICE
                session.pending_refund_sats = amount_sats
                return

            await pay_invoice(
                wallet_id=self.shop.wallet,
                payment_request=bolt11,
                description="Refund",
                tag="telegramshop_refund",
            )
            await self.send_message(
                chat_id,
                "✅ <b>Refund Sent!</b>\n\n"
                "Your refund has been processed successfully.",
            )
        except Exception as e:
            logger.error(f"Refund payment failed: {e}")
            await self.send_message(
                chat_id,
                "❌ We couldn't process the refund. "
                "Please check your input and try again, "
                "or contact us via /message.",
            )
            session.state = UserState.WAITING_REFUND_INVOICE
            session.pending_refund_sats = amount_sats

    # --- Admin notifications ---

    async def notify_admin_new_order(self, order: Order) -> None:
        if not self.shop.admin_chat_id:
            return
        admin_chat_id = int(self.shop.admin_chat_id)
        cart_items = json.loads(order.cart_json)
        lines = []
        for i in cart_items:
            line = f"  {i['quantity']}× {i['title']}"
            if i.get("sku"):
                line += f" [{i['sku']}]"
            lines.append(line)
        items_text = "\n".join(lines)
        text = (
            f"🔔 <b>New Order!</b>\n"
            f"{SEP}\n\n"
            f"Order #{order.id[:8]}\n"
            f"Customer: @{order.telegram_username or 'unknown'}\n"
            f"{items_text}\n"
            f"💰 Total: {format_sats(order.amount_sats)} sats"
        )
        if order.buyer_email:
            text += f"\n📧 {order.buyer_email}"
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
        text = f"💬 <b>New message from {escape_html(user_display)}</b>\n"
        if order_id:
            text += f"📦 Order: #{order_id[:8]}\n"
        text += f"\n\"{escape_html(content)}\""
        await self.send_message(admin_chat_id, text)

    async def notify_admin_return(self, ret, order: Order) -> None:
        if not self.shop.admin_chat_id:
            return
        admin_chat_id = int(self.shop.admin_chat_id)
        items = json.loads(ret.items_json)
        items_text = ", ".join(f"{i['quantity']}× {i['title']}" for i in items)
        text = (
            f"↩️ <b>Return Request</b>\n"
            f"{SEP}\n\n"
            f"📦 Order: #{order.id[:8]}\n"
            f"Customer: @{order.telegram_username or 'unknown'}\n"
            f"Items: {escape_html(items_text)}\n"
            f"💰 Amount: {format_sats(ret.refund_amount_sats)} sats\n"
            f"Reason: \"{escape_html(ret.reason or 'No reason given')}\""
        )
        await self.send_message(admin_chat_id, text)

    # --- Notifications from admin actions ---

    async def send_admin_reply(
        self, chat_id: int, content: str, order_id: Optional[str]
    ) -> None:
        text = "💬 <b>Message from Shop</b>\n\n"
        if order_id:
            text += f"📦 Regarding Order #{order_id[:8]}\n\n"
        text += f"\"{escape_html(content)}\""
        tma_url = self.tma_url
        keyboard = self._inline_keyboard(
            [
                [
                    {"text": "💬 Reply", "callback_data": f"msg_{order_id or 'general'}"},
                    {"text": "🛍 Shop", "web_app": {"url": tma_url}},
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
            f"✅ <b>Return Approved</b>\n\n"
            f"You've received <b>{format_sats(amount_sats)} sats</b> "
            f"in store credit ✨\n\n"
            f"It will be applied automatically at checkout.\n"
            f"Use /credits to check your balance anytime.",
            reply_markup=self._inline_keyboard(
                [[{"text": "🛍 Open Shop", "web_app": {"url": tma_url}}]]
            ),
        )

    async def notify_return_approved_lightning(
        self, chat_id: int, amount_sats: int
    ) -> None:
        session = self.get_session(chat_id)
        session.state = UserState.WAITING_REFUND_INVOICE
        session.pending_refund_sats = amount_sats
        session.pending_return_items = None
        session.pending_order_id = None
        await self.send_message(
            chat_id,
            f"✅ <b>Return Approved!</b>\n"
            f"{SEP}\n\n"
            f"Your refund of <b>{format_sats(amount_sats)} sats</b> "
            f"is ready to be sent.\n\n"
            f"Please send one of the following:\n"
            f"- A ⚡ <b>Lightning invoice</b> for {format_sats(amount_sats)} sats\n"
            f"- Your ⚡ <b>Lightning address</b> (e.g. you@wallet.com)\n\n"
            f"Paste it below:",
            reply_markup=self._inline_keyboard(
                [[{"text": "❌ Cancel", "callback_data": "cancel"}]]
            ),
        )

    async def notify_return_denied(
        self, chat_id: int, admin_note: str
    ) -> None:
        tma_url = self.tma_url
        await self.send_message(
            chat_id,
            f"❌ <b>Return Not Approved</b>\n\n"
            f"Reason: \"{escape_html(admin_note)}\"\n\n"
            f"If you have questions, tap /message to reach us.",
            reply_markup=self._inline_keyboard(
                [[{"text": "💬 Reply", "callback_data": "msg_general"},
                  {"text": "🛍 Shop", "web_app": {"url": tma_url}}]]
            ),
        )

    async def notify_fulfillment_update(
        self, chat_id: int, order: Order, status: str, note: Optional[str]
    ) -> None:
        status_labels = {
            "preparing": "📋 Preparing",
            "shipping": "🚚 Shipping",
            "delivered": "✅ Delivered",
        }
        label = status_labels.get(status, status)
        text = (
            f"📦 <b>Order Update</b>\n\n"
            f"Order #{order.id[:8]} → <b>{label}</b>"
        )
        if note:
            text += f"\n\n📝 {escape_html(note)}"
        keyboard = self._inline_keyboard(
            [[{"text": "📦 View Orders", "callback_data": "orders"}]]
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
        tma_url = self.tma_url
        for p in products[:20]:
            buy_btn = {
                "text": "🛍 Open Shop",
                "url": f"https://t.me/{self._bot_username}?start=open",
            }
            caption = (
                f"<b>{escape_html(p.title)}</b>\n"
                f"💰 {self.format_price(p.price)}"
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
