"""Tests for views_api.py — admin API endpoints via mocked CRUD + auth."""

from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from telegramshop.models import (
    ApproveReturn,
    CreateShop,
    DenyReturn,
    FulfillmentStatus,
    Message,
    Order,
    RefundMethod,
    Return,
    SendMessage,
    Shop,
    UpdateFulfillment,
)
from telegramshop.tests.conftest import (
    SAMPLE_BOT_TOKEN,
    SAMPLE_CHAT_ID,
    SAMPLE_SHOP_ID,
    make_order,
    make_shop,
)


# ---------------------------------------------------------------------------
# Helper: fake WalletTypeInfo
# ---------------------------------------------------------------------------

def _key_info(wallet_id: str = "wallet_001", user_id: str = "user_001"):
    info = MagicMock()
    info.wallet.id = wallet_id
    info.wallet.user = user_id
    return info


# ---------------------------------------------------------------------------
# Shop endpoints
# ---------------------------------------------------------------------------


class TestCreateShopEndpoint:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.create_shop", new_callable=AsyncMock)
    async def test_201(self, mock_create):
        from telegramshop.views_api import api_create_shop

        shop = make_shop()
        mock_create.return_value = shop
        data = CreateShop(
            title="New", bot_token=SAMPLE_BOT_TOKEN, inventory_id="inv_001"
        )
        result = await api_create_shop(data, _key_info())
        assert result.id == SAMPLE_SHOP_ID
        mock_create.assert_awaited_once()


class TestListShops:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.get_shops", new_callable=AsyncMock)
    async def test_list(self, mock_get, mock_bm):
        from telegramshop.views_api import api_list_shops

        mock_get.return_value = [make_shop()]
        mock_bm.get_bot.return_value = None
        result = await api_list_shops(_key_info())
        assert len(result) == 1


class TestGetShopEndpoint:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_found(self, mock_get, mock_bm):
        from telegramshop.views_api import api_get_shop

        mock_get.return_value = make_shop()
        mock_bm.get_bot.return_value = None
        result = await api_get_shop(SAMPLE_SHOP_ID, _key_info())
        assert result.id == SAMPLE_SHOP_ID

    @pytest.mark.asyncio
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_not_found(self, mock_get):
        from telegramshop.views_api import api_get_shop

        mock_get.return_value = None
        with pytest.raises(HTTPException) as exc:
            await api_get_shop("nonexistent", _key_info())
        assert exc.value.status_code == HTTPStatus.NOT_FOUND


class TestDeleteShopEndpoint:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.delete_shop", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_delete(self, mock_get, mock_del, mock_bm):
        from telegramshop.views_api import api_delete_shop

        mock_get.return_value = make_shop()
        mock_bm.stop_bot = AsyncMock()
        result = await api_delete_shop(SAMPLE_SHOP_ID, _key_info())
        assert result["success"] is True
        mock_del.assert_awaited_once()


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


class TestListOrders:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.get_orders", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_list(self, mock_shop, mock_orders):
        from telegramshop.views_api import api_list_orders

        mock_shop.return_value = make_shop()
        mock_orders.return_value = [make_order()]
        result = await api_list_orders(
            shop_id=SAMPLE_SHOP_ID, key_info=_key_info()
        )
        assert len(result) == 1


class TestGetOrderEndpoint:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_order", new_callable=AsyncMock)
    async def test_found(self, mock_order, mock_shop):
        from telegramshop.views_api import api_get_order

        mock_order.return_value = make_order()
        mock_shop.return_value = make_shop()
        result = await api_get_order("order_001", _key_info())
        assert result.id == "order_001"


class TestUpdateFulfillment:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.update_order_fulfillment", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_order", new_callable=AsyncMock)
    async def test_success(self, mock_order, mock_shop, mock_update, mock_bm):
        from telegramshop.views_api import api_update_fulfillment

        mock_order.return_value = make_order(status="paid")
        mock_shop.return_value = make_shop(enable_order_tracking=True)
        mock_bm.get_bot.return_value = None
        data = UpdateFulfillment(status=FulfillmentStatus.SHIPPING, note="Shipped")
        result = await api_update_fulfillment("order_001", data, _key_info())
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Message endpoints
# ---------------------------------------------------------------------------


class TestSendMessage:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.create_message", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_send(self, mock_shop, mock_create, mock_bm):
        from telegramshop.views_api import api_send_message

        mock_shop.return_value = make_shop()
        msg = Message(
            id="msg_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id=None,
            chat_id=SAMPLE_CHAT_ID,
            username=None,
            direction="out",
            content="Hello customer",
            is_read=False,
            telegram_message_id=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_create.return_value = msg
        mock_bm.get_bot.return_value = None
        data = SendMessage(chat_id=SAMPLE_CHAT_ID, content="Hello customer")
        result = await api_send_message(SAMPLE_SHOP_ID, data, _key_info())
        assert result.content == "Hello customer"


# ---------------------------------------------------------------------------
# Return endpoints
# ---------------------------------------------------------------------------


class TestListReturns:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.get_returns", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    async def test_list(self, mock_shop, mock_returns):
        from telegramshop.views_api import api_list_returns

        mock_shop.return_value = make_shop()
        mock_returns.return_value = []
        result = await api_list_returns(
            shop_id=SAMPLE_SHOP_ID, key_info=_key_info()
        )
        assert result == []


class TestApproveReturn:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.create_credit", new_callable=AsyncMock)
    @patch("telegramshop.views_api.update_return_status", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_return", new_callable=AsyncMock)
    async def test_approve(self, mock_ret, mock_shop, mock_update, mock_credit, mock_bm):
        from telegramshop.views_api import api_approve_return

        ret = Return(
            id="ret_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id="order_001",
            chat_id=SAMPLE_CHAT_ID,
            items_json="[]",
            reason="Broken",
            refund_method=None,
            refund_amount_sats=5000,
            status="requested",
            admin_note=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_ret.return_value = ret
        mock_shop.return_value = make_shop()
        mock_update.return_value = True
        mock_credit.return_value = MagicMock()
        mock_bm.get_bot.return_value = None
        data = ApproveReturn(refund_method=RefundMethod.CREDIT)
        result = await api_approve_return("ret_001", data, _key_info())
        assert result["success"] is True


class TestDenyReturn:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.bot_manager")
    @patch("telegramshop.views_api.update_return_status", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shop", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_return", new_callable=AsyncMock)
    async def test_deny(self, mock_ret, mock_shop, mock_update, mock_bm):
        from telegramshop.views_api import api_deny_return

        ret = Return(
            id="ret_001",
            shop_id=SAMPLE_SHOP_ID,
            order_id="order_001",
            chat_id=SAMPLE_CHAT_ID,
            items_json="[]",
            reason="Changed mind",
            refund_method=None,
            refund_amount_sats=3000,
            status="requested",
            admin_note=None,
            timestamp="2024-01-01 00:00:00",
        )
        mock_ret.return_value = ret
        mock_shop.return_value = make_shop()
        mock_update.return_value = True
        mock_bm.get_bot.return_value = None
        data = DenyReturn(admin_note="Policy violation")
        result = await api_deny_return("ret_001", data, _key_info())
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------


class TestStats:
    @pytest.mark.asyncio
    @patch("telegramshop.views_api.get_stats", new_callable=AsyncMock)
    @patch("telegramshop.views_api.get_shops", new_callable=AsyncMock)
    async def test_stats(self, mock_shops, mock_stats):
        from telegramshop.views_api import api_stats

        mock_shops.return_value = [make_shop(is_enabled=True)]
        mock_stats.return_value = {
            "orders_total": 10,
            "orders_paid": 8,
            "orders_today": 2,
            "revenue_sats": 50000,
            "unread_messages": 3,
            "total_messages": 20,
            "open_returns": 1,
            "total_returns": 5,
            "customers": 15,
        }
        result = await api_stats(_key_info())
        assert result["orders_total"] == 10
        assert result["shops"] == 1
        assert result["shops_live"] == 1
