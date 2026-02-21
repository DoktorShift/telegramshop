from lnbits.db import Database


async def m001_initial(db: Database):
    """
    Initial tables for Telegram Shopping extension.
    """
    await db.execute(
        f"""
        CREATE TABLE telegramshop.shops (
            id TEXT NOT NULL PRIMARY KEY,
            wallet TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            bot_token TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'sat',
            inventory_id TEXT NOT NULL,
            checkout_mode TEXT NOT NULL DEFAULT 'none',
            enable_order_tracking INTEGER NOT NULL DEFAULT 0,
            use_webhook INTEGER NOT NULL DEFAULT 0,
            admin_chat_id TEXT,
            allow_returns INTEGER NOT NULL DEFAULT 1,
            allow_credit_refund INTEGER NOT NULL DEFAULT 1,
            return_window_hours INTEGER NOT NULL DEFAULT 720,
            is_enabled INTEGER NOT NULL DEFAULT 0,
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE telegramshop.orders (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            payment_hash TEXT,
            telegram_chat_id {db.big_int} NOT NULL,
            telegram_username TEXT,
            amount_sats INTEGER NOT NULL,
            currency TEXT NOT NULL,
            currency_amount REAL NOT NULL,
            cart_json TEXT NOT NULL,
            buyer_email TEXT,
            buyer_name TEXT,
            buyer_address TEXT,
            has_physical_items INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            fulfillment_status TEXT,
            fulfillment_note TEXT,
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE telegramshop.messages (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            order_id TEXT,
            chat_id {db.big_int} NOT NULL,
            username TEXT,
            direction TEXT NOT NULL,
            content TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            telegram_message_id {db.big_int},
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE telegramshop.returns (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            chat_id {db.big_int} NOT NULL,
            items_json TEXT NOT NULL,
            reason TEXT,
            refund_method TEXT,
            refund_amount_sats INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            admin_note TEXT,
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE telegramshop.credits (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            chat_id {db.big_int} NOT NULL,
            amount_sats INTEGER NOT NULL,
            used_sats INTEGER NOT NULL DEFAULT 0,
            source_return_id TEXT,
            timestamp TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )


async def m002_add_shipping(db: Database):
    """Add shipping cost fields to shops."""
    for col, default in [
        ("shipping_flat_rate", "0"),
        ("shipping_free_threshold", "0"),
        ("shipping_per_kg", "0"),
    ]:
        await db.execute(
            f"ALTER TABLE telegramshop.shops "
            f"ADD COLUMN {col} REAL NOT NULL DEFAULT {default}"
        )


async def m003_tma_tables(db: Database):
    """Add TMA (Telegram Mini App) tables and shop columns."""

    # New columns on shops
    await db.execute(
        "ALTER TABLE telegramshop.shops "
        "ADD COLUMN tma_enabled INTEGER NOT NULL DEFAULT 0"
    )
    await db.execute(
        "ALTER TABLE telegramshop.shops "
        "ADD COLUMN tma_welcome_text TEXT"
    )

    # Persistent cart (shared by TMA + chat bot)
    await db.execute(
        f"""
        CREATE TABLE telegramshop.carts (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            chat_id {db.big_int} NOT NULL,
            cart_json TEXT NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            UNIQUE(shop_id, chat_id)
        );
        """
    )

    # Customer tracking per shop
    await db.execute(
        f"""
        CREATE TABLE telegramshop.customers (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            chat_id {db.big_int} NOT NULL,
            username TEXT,
            first_name TEXT,
            first_seen TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            last_active TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            UNIQUE(shop_id, chat_id)
        );
        """
    )

    # Commercial campaign templates
    await db.execute(
        f"""
        CREATE TABLE telegramshop.commercials (
            id TEXT NOT NULL PRIMARY KEY,
            shop_id TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_url TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            delay_minutes INTEGER NOT NULL DEFAULT 60,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    # Sent message log (prevents duplicates)
    await db.execute(
        f"""
        CREATE TABLE telegramshop.commercial_logs (
            id TEXT NOT NULL PRIMARY KEY,
            commercial_id TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            chat_id {db.big_int} NOT NULL,
            sent_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )


async def m004_webhook_secret(db: Database):
    """Add webhook_secret column to shops for Telegram signature verification."""
    await db.execute(
        "ALTER TABLE telegramshop.shops ADD COLUMN webhook_secret TEXT"
    )
