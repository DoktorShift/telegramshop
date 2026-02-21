import secrets
from typing import Optional

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import (
    Cart,
    Commercial,
    CommercialLog,
    CreateCommercial,
    CreateShop,
    Customer,
    Shop,
    Order,
    Message,
    Return,
    Credit,
    UpdateCommercial,
)

db = Database("ext_telegramshop")


# --- Shops ---


async def create_shop(wallet_id: str, data: CreateShop) -> Shop:
    shop_id = urlsafe_short_hash()
    webhook_secret = secrets.token_hex(32)
    await db.execute(
        """
        INSERT INTO telegramshop.shops (
            id, wallet, title, description, bot_token, currency,
            inventory_id, checkout_mode,
            enable_order_tracking, use_webhook, admin_chat_id,
            allow_returns, allow_credit_refund, return_window_hours,
            shipping_flat_rate, shipping_free_threshold, shipping_per_kg,
            webhook_secret
        ) VALUES (
            :id, :wallet, :title, :description, :bot_token, :currency,
            :inventory_id, :checkout_mode,
            :enable_order_tracking, :use_webhook, :admin_chat_id,
            :allow_returns, :allow_credit_refund, :return_window_hours,
            :shipping_flat_rate, :shipping_free_threshold, :shipping_per_kg,
            :webhook_secret
        )
        """,
        {
            "id": shop_id,
            "wallet": wallet_id,
            "title": data.title,
            "description": data.description,
            "bot_token": data.bot_token,
            "currency": data.currency,
            "inventory_id": data.inventory_id,
            "checkout_mode": data.checkout_mode.value,
            "enable_order_tracking": int(data.enable_order_tracking),
            "use_webhook": int(data.use_webhook),
            "admin_chat_id": data.admin_chat_id,
            "allow_returns": int(data.allow_returns),
            "allow_credit_refund": int(data.allow_credit_refund),
            "return_window_hours": data.return_window_hours,
            "shipping_flat_rate": data.shipping_flat_rate,
            "shipping_free_threshold": data.shipping_free_threshold,
            "shipping_per_kg": data.shipping_per_kg,
            "webhook_secret": webhook_secret,
        },
    )
    shop = await get_shop(shop_id)
    assert shop, "Shop was created but could not be retrieved"
    return shop


async def update_shop(shop_id: str, data: CreateShop) -> Shop:
    await db.execute(
        """
        UPDATE telegramshop.shops SET
            title = :title,
            description = :description,
            bot_token = :bot_token,
            currency = :currency,
            inventory_id = :inventory_id,
            checkout_mode = :checkout_mode,
            enable_order_tracking = :enable_order_tracking,
            use_webhook = :use_webhook,
            admin_chat_id = :admin_chat_id,
            allow_returns = :allow_returns,
            allow_credit_refund = :allow_credit_refund,
            return_window_hours = :return_window_hours,
            shipping_flat_rate = :shipping_flat_rate,
            shipping_free_threshold = :shipping_free_threshold,
            shipping_per_kg = :shipping_per_kg
        WHERE id = :id
        """,
        {
            "id": shop_id,
            "title": data.title,
            "description": data.description,
            "bot_token": data.bot_token,
            "currency": data.currency,
            "inventory_id": data.inventory_id,
            "checkout_mode": data.checkout_mode.value,
            "enable_order_tracking": int(data.enable_order_tracking),
            "use_webhook": int(data.use_webhook),
            "admin_chat_id": data.admin_chat_id,
            "allow_returns": int(data.allow_returns),
            "allow_credit_refund": int(data.allow_credit_refund),
            "return_window_hours": data.return_window_hours,
            "shipping_flat_rate": data.shipping_flat_rate,
            "shipping_free_threshold": data.shipping_free_threshold,
            "shipping_per_kg": data.shipping_per_kg,
        },
    )
    shop = await get_shop(shop_id)
    assert shop, "Shop was updated but could not be retrieved"
    return shop


async def get_shop(shop_id: str) -> Optional[Shop]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.shops WHERE id = :id",
        {"id": shop_id},
        Shop,
    )


async def get_shops(wallet_ids: list[str]) -> list[Shop]:
    if not wallet_ids:
        return []
    placeholders = ",".join([f":w{i}" for i in range(len(wallet_ids))])
    params = {f"w{i}": wid for i, wid in enumerate(wallet_ids)}
    rows = await db.fetchall(
        f"SELECT * FROM telegramshop.shops WHERE wallet IN ({placeholders}) ORDER BY timestamp DESC",
        params,
    )
    return [Shop(**dict(row)) for row in rows]


async def get_shop_by_token(bot_token: str) -> Optional[Shop]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.shops WHERE bot_token = :bot_token",
        {"bot_token": bot_token},
        Shop,
    )


async def get_enabled_shops() -> list[Shop]:
    rows = await db.fetchall(
        "SELECT * FROM telegramshop.shops WHERE is_enabled = 1",
    )
    return [Shop(**dict(row)) for row in rows]


async def set_shop_enabled(shop_id: str, enabled: bool) -> None:
    await db.execute(
        "UPDATE telegramshop.shops SET is_enabled = :enabled WHERE id = :id",
        {"id": shop_id, "enabled": int(enabled)},
    )


async def ensure_webhook_secret(shop_id: str) -> str:
    """Generate and store a webhook_secret if one doesn't exist."""
    secret = secrets.token_hex(32)
    await db.execute(
        "UPDATE telegramshop.shops SET webhook_secret = :secret WHERE id = :id",
        {"id": shop_id, "secret": secret},
    )
    return secret


async def delete_shop(shop_id: str) -> None:
    await db.execute(
        "DELETE FROM telegramshop.shops WHERE id = :id",
        {"id": shop_id},
    )


async def get_stats(shop_ids: list[str]) -> dict:
    """Efficient aggregate stats across one or more shops."""
    if not shop_ids:
        return {
            "orders_total": 0,
            "orders_paid": 0,
            "orders_today": 0,
            "revenue_sats": 0,
            "unread_messages": 0,
            "total_messages": 0,
            "open_returns": 0,
            "total_returns": 0,
            "customers": 0,
        }

    placeholders = ", ".join(f":sid{i}" for i in range(len(shop_ids)))
    params = {f"sid{i}": sid for i, sid in enumerate(shop_ids)}

    # Orders: total, paid, today, revenue
    order_row = await db.fetchone(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid,
            SUM(CASE WHEN status = 'paid' THEN amount_sats ELSE 0 END) as revenue
        FROM telegramshop.orders
        WHERE shop_id IN ({placeholders})""",
        params,
    )

    # Orders today (paid only) - cross-DB: compare date string prefix
    from datetime import date

    today_params = {**params, "today": date.today().isoformat()}
    today_row = await db.fetchone(
        f"""SELECT COUNT(*) as cnt
        FROM telegramshop.orders
        WHERE shop_id IN ({placeholders})
          AND status = 'paid'
          AND timestamp >= :today""",
        today_params,
    )

    # Unread messages + total messages
    msg_row = await db.fetchone(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN direction = 'in' AND is_read = 0 THEN 1 ELSE 0 END) as unread
        FROM telegramshop.messages
        WHERE shop_id IN ({placeholders})""",
        params,
    )

    # Returns: open + total
    ret_row = await db.fetchone(
        f"""SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'requested' THEN 1 ELSE 0 END) as open_count
        FROM telegramshop.returns
        WHERE shop_id IN ({placeholders})""",
        params,
    )

    # Customers
    cust_row = await db.fetchone(
        f"""SELECT COUNT(*) as cnt
        FROM telegramshop.customers
        WHERE shop_id IN ({placeholders})""",
        params,
    )

    def _int(row, attr, fallback=0):
        if not row:
            return fallback
        val = getattr(row, attr, None) if hasattr(row, attr) else None
        if val is None:
            return fallback
        return int(val)

    return {
        "orders_total": _int(order_row, "total"),
        "orders_paid": _int(order_row, "paid"),
        "orders_today": _int(today_row, "cnt"),
        "revenue_sats": _int(order_row, "revenue"),
        "unread_messages": _int(msg_row, "unread"),
        "total_messages": _int(msg_row, "total"),
        "open_returns": _int(ret_row, "open_count"),
        "total_returns": _int(ret_row, "total"),
        "customers": _int(cust_row, "cnt"),
    }


# --- Orders ---


async def create_order(
    shop_id: str,
    payment_hash: str,
    telegram_chat_id: int,
    telegram_username: Optional[str],
    amount_sats: int,
    currency: str,
    currency_amount: float,
    cart_json: str,
    buyer_email: Optional[str] = None,
    buyer_name: Optional[str] = None,
    buyer_address: Optional[str] = None,
    has_physical_items: bool = False,
) -> Order:
    order_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO telegramshop.orders (
            id, shop_id, payment_hash, telegram_chat_id,
            telegram_username, amount_sats, currency, currency_amount,
            cart_json, buyer_email, buyer_name, buyer_address,
            has_physical_items
        ) VALUES (
            :id, :shop_id, :payment_hash, :telegram_chat_id,
            :telegram_username, :amount_sats, :currency, :currency_amount,
            :cart_json, :buyer_email, :buyer_name, :buyer_address,
            :has_physical_items
        )
        """,
        {
            "id": order_id,
            "shop_id": shop_id,
            "payment_hash": payment_hash,
            "telegram_chat_id": telegram_chat_id,
            "telegram_username": telegram_username,
            "amount_sats": amount_sats,
            "currency": currency,
            "currency_amount": currency_amount,
            "cart_json": cart_json,
            "buyer_email": buyer_email,
            "buyer_name": buyer_name,
            "buyer_address": buyer_address,
            "has_physical_items": int(has_physical_items),
        },
    )
    order = await get_order(order_id)
    assert order, "Order was created but could not be retrieved"
    return order


async def get_order(order_id: str) -> Optional[Order]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.orders WHERE id = :id",
        {"id": order_id},
        Order,
    )


async def get_order_by_payment_hash(payment_hash: str) -> Optional[Order]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.orders WHERE payment_hash = :payment_hash",
        {"payment_hash": payment_hash},
        Order,
    )


async def get_orders(
    shop_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    where = "WHERE shop_id = :shop_id"
    params: dict = {"shop_id": shop_id, "limit": limit, "offset": offset}
    if status:
        where += " AND status = :status"
        params["status"] = status
    rows = await db.fetchall(
        f"SELECT * FROM telegramshop.orders {where} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset",
        params,
    )
    return [Order(**dict(row)) for row in rows]


async def get_orders_by_chat(
    shop_id: str, chat_id: int
) -> list[Order]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.orders
           WHERE shop_id = :shop_id AND telegram_chat_id = :chat_id AND status = 'paid'
           ORDER BY timestamp DESC""",
        {"shop_id": shop_id, "chat_id": chat_id},
    )
    return [Order(**dict(row)) for row in rows]


async def update_order_status(order_id: str, status: str) -> None:
    await db.execute(
        "UPDATE telegramshop.orders SET status = :status WHERE id = :id",
        {"id": order_id, "status": status},
    )


async def update_order_fulfillment(
    order_id: str,
    fulfillment_status: str,
    fulfillment_note: Optional[str] = None,
) -> None:
    await db.execute(
        """UPDATE telegramshop.orders
           SET fulfillment_status = :fulfillment_status,
               fulfillment_note = :fulfillment_note
           WHERE id = :id""",
        {
            "id": order_id,
            "fulfillment_status": fulfillment_status,
            "fulfillment_note": fulfillment_note,
        },
    )


# --- Messages ---


async def create_message(
    shop_id: str,
    chat_id: int,
    direction: str,
    content: str,
    username: Optional[str] = None,
    order_id: Optional[str] = None,
    telegram_message_id: Optional[int] = None,
) -> Message:
    msg_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO telegramshop.messages (
            id, shop_id, order_id, chat_id, username,
            direction, content, telegram_message_id
        ) VALUES (
            :id, :shop_id, :order_id, :chat_id, :username,
            :direction, :content, :telegram_message_id
        )
        """,
        {
            "id": msg_id,
            "shop_id": shop_id,
            "order_id": order_id,
            "chat_id": chat_id,
            "username": username,
            "direction": direction,
            "content": content,
            "telegram_message_id": telegram_message_id,
        },
    )
    msg = await get_message(msg_id)
    assert msg, "Message was created but could not be retrieved"
    return msg


async def get_message(message_id: str) -> Optional[Message]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.messages WHERE id = :id",
        {"id": message_id},
        Message,
    )


async def get_messages(
    shop_id: str,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    where = "WHERE shop_id = :shop_id"
    params: dict = {"shop_id": shop_id, "limit": limit, "offset": offset}
    if unread_only:
        where += " AND is_read = 0"
    rows = await db.fetchall(
        f"SELECT * FROM telegramshop.messages {where} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset",
        params,
    )
    return [Message(**dict(row)) for row in rows]


async def get_message_thread(
    shop_id: str, chat_id: int, order_id: Optional[str] = None
) -> list[Message]:
    where = "WHERE shop_id = :shop_id AND chat_id = :chat_id"
    params: dict = {"shop_id": shop_id, "chat_id": chat_id}
    if order_id:
        where += " AND order_id = :order_id"
        params["order_id"] = order_id
    rows = await db.fetchall(
        f"SELECT * FROM telegramshop.messages {where} ORDER BY timestamp ASC",
        params,
    )
    return [Message(**dict(row)) for row in rows]


async def mark_message_read(message_id: str) -> None:
    await db.execute(
        "UPDATE telegramshop.messages SET is_read = 1 WHERE id = :id",
        {"id": message_id},
    )


async def get_unread_count(shop_id: str) -> int:
    row = await db.fetchone(
        """SELECT COUNT(*) as count FROM telegramshop.messages
           WHERE shop_id = :shop_id AND direction = 'in' AND is_read = 0""",
        {"shop_id": shop_id},
    )
    if row:
        return int(row.count) if hasattr(row, "count") else int(row[0])
    return 0


# --- Returns ---


async def create_return(
    shop_id: str,
    order_id: str,
    chat_id: int,
    items_json: str,
    refund_amount_sats: int,
    reason: Optional[str] = None,
) -> Return:
    return_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO telegramshop.returns (
            id, shop_id, order_id, chat_id, items_json,
            reason, refund_amount_sats
        ) VALUES (
            :id, :shop_id, :order_id, :chat_id, :items_json,
            :reason, :refund_amount_sats
        )
        """,
        {
            "id": return_id,
            "shop_id": shop_id,
            "order_id": order_id,
            "chat_id": chat_id,
            "items_json": items_json,
            "reason": reason,
            "refund_amount_sats": refund_amount_sats,
        },
    )
    ret = await get_return(return_id)
    assert ret, "Return was created but could not be retrieved"
    return ret


async def get_return(return_id: str) -> Optional[Return]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.returns WHERE id = :id",
        {"id": return_id},
        Return,
    )


async def get_returns(
    shop_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Return]:
    where = "WHERE shop_id = :shop_id"
    params: dict = {"shop_id": shop_id, "limit": limit, "offset": offset}
    if status:
        where += " AND status = :status"
        params["status"] = status
    rows = await db.fetchall(
        f"SELECT * FROM telegramshop.returns {where} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset",
        params,
    )
    return [Return(**dict(row)) for row in rows]


async def get_returns_by_order(order_id: str) -> list[Return]:
    rows = await db.fetchall(
        "SELECT * FROM telegramshop.returns WHERE order_id = :order_id ORDER BY timestamp DESC",
        {"order_id": order_id},
    )
    return [Return(**dict(row)) for row in rows]


async def update_return_status(
    return_id: str,
    status: str,
    refund_method: Optional[str] = None,
    admin_note: Optional[str] = None,
    refund_amount_sats: Optional[int] = None,
    expected_status: Optional[str] = None,
) -> bool:
    """Update return status. If expected_status is given, only updates if current
    status matches (atomic check-and-set). Returns True if a row was updated."""
    where = "WHERE id = :id"
    params: dict = {
        "id": return_id,
        "status": status,
        "refund_method": refund_method,
        "admin_note": admin_note,
        "refund_amount_sats": refund_amount_sats,
    }
    if expected_status:
        where += " AND status = :expected_status"
        params["expected_status"] = expected_status

    result = await db.execute(
        f"""UPDATE telegramshop.returns
           SET status = :status,
               refund_method = COALESCE(:refund_method, refund_method),
               admin_note = COALESCE(:admin_note, admin_note),
               refund_amount_sats = COALESCE(:refund_amount_sats, refund_amount_sats)
           {where}""",
        params,
    )
    return result.rowcount > 0 if result else False


async def get_active_return_for_order(order_id: str) -> Optional[Return]:
    """Get any non-denied return for an order (requested/approved/refunded)."""
    return await db.fetchone(
        """SELECT * FROM telegramshop.returns
           WHERE order_id = :order_id AND status != 'denied'
           ORDER BY timestamp DESC LIMIT 1""",
        {"order_id": order_id},
        Return,
    )


# --- Credits ---


async def create_credit(
    shop_id: str,
    chat_id: int,
    amount_sats: int,
    source_return_id: Optional[str] = None,
) -> Credit:
    credit_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO telegramshop.credits (
            id, shop_id, chat_id, amount_sats, source_return_id
        ) VALUES (
            :id, :shop_id, :chat_id, :amount_sats, :source_return_id
        )
        """,
        {
            "id": credit_id,
            "shop_id": shop_id,
            "chat_id": chat_id,
            "amount_sats": amount_sats,
            "source_return_id": source_return_id,
        },
    )
    credit = await get_credit(credit_id)
    assert credit, "Credit was created but could not be retrieved"
    return credit


async def get_credit(credit_id: str) -> Optional[Credit]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.credits WHERE id = :id",
        {"id": credit_id},
        Credit,
    )


async def get_available_credits(shop_id: str, chat_id: int) -> list[Credit]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.credits
           WHERE shop_id = :shop_id AND chat_id = :chat_id
           AND used_sats < amount_sats
           ORDER BY timestamp ASC""",
        {"shop_id": shop_id, "chat_id": chat_id},
    )
    return [Credit(**dict(row)) for row in rows]


async def get_total_available_credit(shop_id: str, chat_id: int) -> int:
    row = await db.fetchone(
        """SELECT COALESCE(SUM(amount_sats - used_sats), 0) as total
           FROM telegramshop.credits
           WHERE shop_id = :shop_id AND chat_id = :chat_id
           AND used_sats < amount_sats""",
        {"shop_id": shop_id, "chat_id": chat_id},
    )
    if row:
        return int(row.total) if hasattr(row, "total") else int(row[0])
    return 0


async def use_credits(shop_id: str, chat_id: int, amount_sats: int) -> int:
    """
    Apply credits to a purchase. Returns the amount actually deducted.
    Credits are consumed in FIFO order (oldest first).
    """
    credits = await get_available_credits(shop_id, chat_id)
    remaining = amount_sats
    total_used = 0

    for credit in credits:
        if remaining <= 0:
            break
        available = credit.amount_sats - credit.used_sats
        use = min(available, remaining)
        await db.execute(
            "UPDATE telegramshop.credits SET used_sats = used_sats + :use WHERE id = :id",
            {"id": credit.id, "use": use},
        )
        remaining -= use
        total_used += use

    return total_used


# --- Carts ---


async def get_cart(shop_id: str, chat_id: int) -> Optional[Cart]:
    return await db.fetchone(
        """SELECT * FROM telegramshop.carts
           WHERE shop_id = :shop_id AND chat_id = :chat_id""",
        {"shop_id": shop_id, "chat_id": chat_id},
        Cart,
    )


async def upsert_cart(shop_id: str, chat_id: int, cart_json: str) -> None:
    existing = await get_cart(shop_id, chat_id)
    if existing:
        await db.execute(
            """UPDATE telegramshop.carts
               SET cart_json = :cart_json, updated_at = CURRENT_TIMESTAMP
               WHERE shop_id = :shop_id AND chat_id = :chat_id""",
            {"shop_id": shop_id, "chat_id": chat_id, "cart_json": cart_json},
        )
    else:
        cart_id = urlsafe_short_hash()
        await db.execute(
            """INSERT INTO telegramshop.carts (id, shop_id, chat_id, cart_json)
               VALUES (:id, :shop_id, :chat_id, :cart_json)""",
            {
                "id": cart_id,
                "shop_id": shop_id,
                "chat_id": chat_id,
                "cart_json": cart_json,
            },
        )


async def delete_cart(shop_id: str, chat_id: int) -> None:
    await db.execute(
        """DELETE FROM telegramshop.carts
           WHERE shop_id = :shop_id AND chat_id = :chat_id""",
        {"shop_id": shop_id, "chat_id": chat_id},
    )


# --- Customers ---


async def upsert_customer(
    shop_id: str,
    chat_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> None:
    existing = await db.fetchone(
        """SELECT id FROM telegramshop.customers
           WHERE shop_id = :shop_id AND chat_id = :chat_id""",
        {"shop_id": shop_id, "chat_id": chat_id},
    )
    if existing:
        await db.execute(
            """UPDATE telegramshop.customers
               SET username = COALESCE(:username, username),
                   first_name = COALESCE(:first_name, first_name),
                   last_active = CURRENT_TIMESTAMP
               WHERE shop_id = :shop_id AND chat_id = :chat_id""",
            {
                "shop_id": shop_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
            },
        )
    else:
        cust_id = urlsafe_short_hash()
        await db.execute(
            """INSERT INTO telegramshop.customers
               (id, shop_id, chat_id, username, first_name)
               VALUES (:id, :shop_id, :chat_id, :username, :first_name)""",
            {
                "id": cust_id,
                "shop_id": shop_id,
                "chat_id": chat_id,
                "username": username,
                "first_name": first_name,
            },
        )


async def get_customers(shop_id: str) -> list[Customer]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.customers
           WHERE shop_id = :shop_id ORDER BY last_active DESC""",
        {"shop_id": shop_id},
    )
    return [Customer(**dict(row)) for row in rows]


async def get_stale_carts(shop_id: str, older_than_minutes: int = 60) -> list[Cart]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.carts
           WHERE shop_id = :shop_id
           AND updated_at < datetime('now', :interval)""",
        {
            "shop_id": shop_id,
            "interval": f"-{older_than_minutes} minutes",
        },
    )
    return [Cart(**dict(row)) for row in rows]


# --- Commercials ---


async def create_commercial(data: CreateCommercial) -> Commercial:
    commercial_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO telegramshop.commercials (
            id, shop_id, type, title, content,
            image_url, delay_minutes
        ) VALUES (
            :id, :shop_id, :type, :title, :content,
            :image_url, :delay_minutes
        )
        """,
        {
            "id": commercial_id,
            "shop_id": data.shop_id,
            "type": data.type.value,
            "title": data.title,
            "content": data.content,
            "image_url": data.image_url,
            "delay_minutes": data.delay_minutes,
        },
    )
    commercial = await get_commercial(commercial_id)
    assert commercial, "Commercial was created but could not be retrieved"
    return commercial


async def get_commercial(commercial_id: str) -> Optional[Commercial]:
    return await db.fetchone(
        "SELECT * FROM telegramshop.commercials WHERE id = :id",
        {"id": commercial_id},
        Commercial,
    )


_DEFAULT_COMMERCIALS = [
    {
        "type": "abandoned_cart",
        "title": "You left something behind!",
        "content": "",
        "delay_minutes": 60,
    },
    {
        "type": "post_purchase",
        "title": "Thanks for shopping with us!",
        "content": "",
        "delay_minutes": 0,
    },
    {
        "type": "back_in_stock",
        "title": "Fresh stock just landed!",
        "content": "",
        "delay_minutes": 0,
    },
    {
        "type": "promotion",
        "title": "Check out what's new!",
        "content": "",
        "delay_minutes": 0,
    },
]


async def ensure_shop_commercials(shop_id: str) -> list[Commercial]:
    """Ensure all 4 commercial types exist for a shop. Returns the full list."""
    existing = await db.fetchall(
        "SELECT type FROM telegramshop.commercials WHERE shop_id = :shop_id",
        {"shop_id": shop_id},
    )
    existing_types = {row[0] if not hasattr(row, "type") else row.type for row in existing}

    for defaults in _DEFAULT_COMMERCIALS:
        if defaults["type"] not in existing_types:
            cid = urlsafe_short_hash()
            await db.execute(
                """INSERT INTO telegramshop.commercials
                   (id, shop_id, type, title, content, delay_minutes, is_enabled)
                   VALUES (:id, :shop_id, :type, :title, :content, :delay_minutes, 0)""",
                {
                    "id": cid,
                    "shop_id": shop_id,
                    "type": defaults["type"],
                    "title": defaults["title"],
                    "content": defaults["content"],
                    "delay_minutes": defaults["delay_minutes"],
                },
            )

    return await get_commercials(shop_id)


async def get_commercials(shop_id: str) -> list[Commercial]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.commercials
           WHERE shop_id = :shop_id ORDER BY created_at DESC""",
        {"shop_id": shop_id},
    )
    return [Commercial(**dict(row)) for row in rows]


async def update_commercial(
    commercial_id: str, data: UpdateCommercial
) -> Commercial:
    sets = []
    params: dict = {"id": commercial_id}
    if data.title is not None:
        sets.append("title = :title")
        params["title"] = data.title
    if data.content is not None:
        sets.append("content = :content")
        params["content"] = data.content
    if data.image_url is not None:
        sets.append("image_url = :image_url")
        params["image_url"] = data.image_url
    if data.is_enabled is not None:
        sets.append("is_enabled = :is_enabled")
        params["is_enabled"] = int(data.is_enabled)
    if data.delay_minutes is not None:
        sets.append("delay_minutes = :delay_minutes")
        params["delay_minutes"] = data.delay_minutes
    if sets:
        await db.execute(
            f"UPDATE telegramshop.commercials SET {', '.join(sets)} WHERE id = :id",
            params,
        )
    commercial = await get_commercial(commercial_id)
    assert commercial, "Commercial was updated but could not be retrieved"
    return commercial


async def delete_commercial(commercial_id: str) -> None:
    await db.execute(
        "DELETE FROM telegramshop.commercials WHERE id = :id",
        {"id": commercial_id},
    )


async def log_commercial_send(
    commercial_id: str, shop_id: str, chat_id: int
) -> None:
    log_id = urlsafe_short_hash()
    await db.execute(
        """INSERT INTO telegramshop.commercial_logs
           (id, commercial_id, shop_id, chat_id)
           VALUES (:id, :commercial_id, :shop_id, :chat_id)""",
        {
            "id": log_id,
            "commercial_id": commercial_id,
            "shop_id": shop_id,
            "chat_id": chat_id,
        },
    )


async def has_commercial_been_sent(
    commercial_id: str, chat_id: int
) -> bool:
    row = await db.fetchone(
        """SELECT id FROM telegramshop.commercial_logs
           WHERE commercial_id = :commercial_id AND chat_id = :chat_id
           LIMIT 1""",
        {"commercial_id": commercial_id, "chat_id": chat_id},
    )
    return row is not None


async def get_commercial_logs(
    commercial_id: str, limit: int = 50, offset: int = 0
) -> list[CommercialLog]:
    rows = await db.fetchall(
        """SELECT * FROM telegramshop.commercial_logs
           WHERE commercial_id = :commercial_id
           ORDER BY sent_at DESC LIMIT :limit OFFSET :offset""",
        {"commercial_id": commercial_id, "limit": limit, "offset": offset},
    )
    return [CommercialLog(**dict(row)) for row in rows]
