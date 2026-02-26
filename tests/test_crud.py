"""Tests for crud.py — database operations via mocked db."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegramshop.models import (
    CheckoutMode,
    CreateShop,
    Credit,
    Message,
    Order,
    Return,
    Shop,
)
from telegramshop.tests.conftest import (
    SAMPLE_BOT_TOKEN,
    SAMPLE_CHAT_ID,
    SAMPLE_SHOP_ID,
    make_credit,
    make_order,
    make_shop,
)


# ---------------------------------------------------------------------------
# Helper: build a mock Row that behaves like both attr-access and dict(row)
# ---------------------------------------------------------------------------

def _row(model_cls, obj):
    """Return a mock that works with both dict(row) and model_cls(**dict(row))."""
    d = obj.dict() if hasattr(obj, "dict") else dict(obj)
    row = MagicMock()
    row.__iter__ = MagicMock(return_value=iter(d.items()))
    row.__getitem__ = lambda self, k: d[k]
    row.keys = lambda: d.keys()
    for k, v in d.items():
        setattr(row, k, v)
    return row


# ---------------------------------------------------------------------------
# Shop CRUD
# ---------------------------------------------------------------------------

class TestCreateShop:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="new_shop_id")
    @patch("telegramshop.crud.secrets.token_hex", return_value="secret_hex")
    async def test_create_shop(self, _tok, _hash, mock_db):
        mock_db.execute = AsyncMock()
        expected_shop = make_shop(id="new_shop_id")
        mock_db.fetchone = AsyncMock(return_value=expected_shop)

        from telegramshop.crud import create_shop

        data = CreateShop(
            title="New Shop",
            bot_token=SAMPLE_BOT_TOKEN,
            inventory_id="inv_001",
        )
        shop = await create_shop("wallet_001", data)
        assert shop.id == "new_shop_id"
        mock_db.execute.assert_awaited_once()


class TestGetShop:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_found(self, mock_db):
        expected = make_shop()
        mock_db.fetchone = AsyncMock(return_value=expected)
        from telegramshop.crud import get_shop

        result = await get_shop(SAMPLE_SHOP_ID)
        assert result is not None
        assert result.id == SAMPLE_SHOP_ID

    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_not_found(self, mock_db):
        mock_db.fetchone = AsyncMock(return_value=None)
        from telegramshop.crud import get_shop

        result = await get_shop("nonexistent")
        assert result is None


class TestGetShops:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_returns_list(self, mock_db):
        shop = make_shop()
        mock_db.fetchall = AsyncMock(return_value=[_row(Shop, shop)])
        from telegramshop.crud import get_shops

        result = await get_shops(["wallet_001"])
        assert len(result) == 1
        assert result[0].id == SAMPLE_SHOP_ID


class TestUpdateShop:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_update(self, mock_db):
        mock_db.execute = AsyncMock()
        updated = make_shop(title="Updated")
        mock_db.fetchone = AsyncMock(return_value=updated)

        from telegramshop.crud import update_shop

        data = CreateShop(
            title="Updated",
            bot_token=SAMPLE_BOT_TOKEN,
            inventory_id="inv_001",
        )
        result = await update_shop(SAMPLE_SHOP_ID, data)
        assert result.title == "Updated"
        mock_db.execute.assert_awaited_once()


class TestDeleteShop:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_delete(self, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.crud import delete_shop

        await delete_shop(SAMPLE_SHOP_ID)
        mock_db.execute.assert_awaited_once()
        call_args = mock_db.execute.call_args
        assert "DELETE" in call_args[0][0]


class TestSetShopEnabled:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_enable(self, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.crud import set_shop_enabled

        await set_shop_enabled(SAMPLE_SHOP_ID, True)
        mock_db.execute.assert_awaited_once()
        params = mock_db.execute.call_args[0][1]
        assert params["enabled"] == 1


class TestUpdateShopCurrency:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_update_currency(self, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.crud import update_shop_currency

        await update_shop_currency(SAMPLE_SHOP_ID, "usd")
        params = mock_db.execute.call_args[0][1]
        assert params["currency"] == "usd"


# ---------------------------------------------------------------------------
# Order CRUD
# ---------------------------------------------------------------------------


class TestCreateOrder:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="ord_001")
    async def test_create(self, _hash, mock_db):
        mock_db.execute = AsyncMock()
        expected = make_order(id="ord_001")
        mock_db.fetchone = AsyncMock(return_value=expected)

        from telegramshop.crud import create_order

        order = await create_order(
            shop_id=SAMPLE_SHOP_ID,
            payment_hash="ph_123",
            telegram_chat_id=SAMPLE_CHAT_ID,
            telegram_username="tester",
            amount_sats=10000,
            currency="sat",
            currency_amount=10000.0,
            cart_json="[]",
            credit_used=500,
        )
        assert order.id == "ord_001"
        call_sql = mock_db.execute.call_args[0][0]
        assert "credit_used" in call_sql


class TestGetOrder:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_found(self, mock_db):
        expected = make_order()
        mock_db.fetchone = AsyncMock(return_value=expected)
        from telegramshop.crud import get_order

        result = await get_order("order_001")
        assert result is not None


class TestUpdateOrderStatus:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_update_status(self, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.crud import update_order_status

        await update_order_status("order_001", "paid")
        params = mock_db.execute.call_args[0][1]
        assert params["status"] == "paid"


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------


class TestCreateMessage:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="msg_001")
    async def test_create(self, _hash, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.models import Message

        expected = Message(
            id="msg_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id=None,
            chat_id=SAMPLE_CHAT_ID,
            username="tester",
            direction="in",
            content="Hello",
            is_read=False,
            telegram_message_id=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_db.fetchone = AsyncMock(return_value=expected)

        from telegramshop.crud import create_message

        msg = await create_message(
            shop_id=SAMPLE_SHOP_ID,
            chat_id=SAMPLE_CHAT_ID,
            direction="in",
            content="Hello",
            username="tester",
        )
        assert msg.id == "msg_001"
        assert msg.direction == "in"


class TestGetMessageThread:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_thread(self, mock_db):
        from telegramshop.models import Message

        msg = Message(
            id="msg_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id=None,
            chat_id=SAMPLE_CHAT_ID,
            username=None,
            direction="in",
            content="Hi",
            is_read=False,
            telegram_message_id=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_db.fetchall = AsyncMock(return_value=[_row(Message, msg)])

        from telegramshop.crud import get_message_thread

        result = await get_message_thread(SAMPLE_SHOP_ID, SAMPLE_CHAT_ID)
        assert len(result) == 1
        call_sql = mock_db.fetchall.call_args[0][0]
        assert "shop_id" in call_sql
        assert "chat_id" in call_sql


class TestMarkMessageRead:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_mark_read(self, mock_db):
        mock_db.execute = AsyncMock()
        from telegramshop.crud import mark_message_read

        await mark_message_read("msg_001")
        call_sql = mock_db.execute.call_args[0][0]
        assert "is_read" in call_sql


# ---------------------------------------------------------------------------
# Credit CRUD
# ---------------------------------------------------------------------------


class TestCreateCredit:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="cred_001")
    async def test_create(self, _hash, mock_db):
        mock_db.execute = AsyncMock()
        expected = make_credit(id="cred_001")
        mock_db.fetchone = AsyncMock(return_value=expected)

        from telegramshop.crud import create_credit

        credit = await create_credit(
            shop_id=SAMPLE_SHOP_ID,
            chat_id=SAMPLE_CHAT_ID,
            amount_sats=500,
            source_return_id="ret_001",
        )
        assert credit.id == "cred_001"


class TestUseCredits:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_fifo_deduction(self, mock_db):
        c1 = make_credit(id="c1", amount_sats=300, used_sats=0)
        c2 = make_credit(id="c2", amount_sats=400, used_sats=0)
        mock_db.fetchall = AsyncMock(
            return_value=[_row(Credit, c1), _row(Credit, c2)]
        )
        mock_db.execute = AsyncMock()

        from telegramshop.crud import use_credits

        used = await use_credits(SAMPLE_SHOP_ID, SAMPLE_CHAT_ID, 500)
        assert used == 500
        # Should have made two UPDATE calls (300 from c1, 200 from c2)
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_partial_deduction(self, mock_db):
        c1 = make_credit(id="c1", amount_sats=200, used_sats=0)
        mock_db.fetchall = AsyncMock(return_value=[_row(Credit, c1)])
        mock_db.execute = AsyncMock()

        from telegramshop.crud import use_credits

        used = await use_credits(SAMPLE_SHOP_ID, SAMPLE_CHAT_ID, 500)
        assert used == 200  # Only 200 available


class TestGetTotalAvailableCredit:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    async def test_sum(self, mock_db):
        row = MagicMock()
        row.total = 750
        mock_db.fetchone = AsyncMock(return_value=row)

        from telegramshop.crud import get_total_available_credit

        total = await get_total_available_credit(SAMPLE_SHOP_ID, SAMPLE_CHAT_ID)
        assert total == 750


# ---------------------------------------------------------------------------
# Return CRUD
# ---------------------------------------------------------------------------


class TestCreateReturn:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="ret_001")
    async def test_create(self, _hash, mock_db):
        mock_db.execute = AsyncMock()
        expected = Return(
            id="ret_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id="order_001",
            chat_id=SAMPLE_CHAT_ID,
            items_json="[]",
            reason="Defective",
            refund_method=None,
            refund_amount_sats=5000,
            status="requested",
            admin_note=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_db.fetchone = AsyncMock(return_value=expected)

        from telegramshop.crud import create_return

        ret = await create_return(
            shop_id=SAMPLE_SHOP_ID,
            order_id="order_001",
            chat_id=SAMPLE_CHAT_ID,
            items_json="[]",
            refund_amount_sats=5000,
            reason="Defective",
        )
        assert ret.id == "ret_001"
        assert ret.status == "requested"


# ---------------------------------------------------------------------------
# Cart CRUD
# ---------------------------------------------------------------------------


class TestUpsertCart:
    @pytest.mark.asyncio
    @patch("telegramshop.crud.db")
    @patch("telegramshop.crud.urlsafe_short_hash", return_value="cart_001")
    async def test_insert_new(self, _hash, mock_db):
        # No existing cart
        mock_db.fetchone = AsyncMock(return_value=None)
        mock_db.execute = AsyncMock()

        from telegramshop.crud import upsert_cart

        await upsert_cart(SAMPLE_SHOP_ID, SAMPLE_CHAT_ID, '["item"]')
        # Should INSERT (get_cart returns None → fetchone None → execute INSERT)
        assert mock_db.execute.await_count >= 1
        insert_sql = mock_db.execute.call_args[0][0]
        assert "INSERT" in insert_sql
