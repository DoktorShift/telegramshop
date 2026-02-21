# AI Agent Guide

> Everything an AI agent needs to set up, run, and manage a Telegram shop through the REST API.

**Base URL:** `{LNBITS_URL}/telegramshop/api/v1`
**Auth:** `X-API-KEY: {wallet_key}` header on every request

---

## Two ways to use this

**Option A** — Bot sells, AI manages
The Telegram bot handles customers. Your AI uses the API for admin tasks: checking orders, replying to messages, handling returns, running campaigns.

**Option B** — AI runs the whole store
Set up the shop, start the bot, monitor everything, and manage the full lifecycle through API calls alone.

---

## End-to-end store setup

```bash
# 1. Validate bot token
POST /shop/test-token
{"bot_token": "123456:ABC-DEF"}

# 2. Create shop
POST /shop
{"title": "My Shop", "bot_token": "123456:ABC-DEF", "inventory_id": "inv_abc",
 "currency": "USD", "checkout_mode": "email"}

# 3. Start the bot
POST /shop/{id}/start

# 4. Check it's running
GET /stats?shop_id={id}

# 5. Configure campaigns
GET /commercial?shop_id={id}          # list defaults
PUT /commercial/{id}                   # customize + enable
```

---

## Daily operations loop

```bash
GET /message/unread-count?shop_id={id}     # new messages?
GET /order?shop_id={id}&status=paid        # new orders?
PUT /order/{id}/fulfillment                # update shipping
GET /return?shop_id={id}&status=requested  # pending returns?
PUT /return/{id}/approve                   # handle returns
POST /message/{shop_id}                    # reply to customers
```

---

## API reference

### Shops

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `POST` | `/shop` | Admin | Create shop |
| `GET` | `/shop` | Invoice | List shops |
| `GET` | `/shop/{id}` | Invoice | Get shop (token excluded) |
| `PUT` | `/shop/{id}` | Admin | Update settings |
| `DELETE` | `/shop/{id}` | Admin | Delete shop |
| `POST` | `/shop/{id}/start` | Admin | Enable bot |
| `POST` | `/shop/{id}/stop` | Admin | Disable bot |
| `POST` | `/shop/{id}/refresh` | Admin | Force product sync |
| `POST` | `/shop/test-token` | Admin | Validate bot token |

<details>
<summary>Create shop — full body</summary>

```json
{
  "title": "string (required)",
  "bot_token": "string (required)",
  "inventory_id": "string (required)",
  "description": "string",
  "currency": "sat | USD | EUR | ...",
  "checkout_mode": "none | email | address",
  "enable_order_tracking": false,
  "use_webhook": false,
  "admin_chat_id": "string",
  "allow_returns": true,
  "allow_credit_refund": true,
  "return_window_hours": 720,
  "shipping_flat_rate": 0,
  "shipping_free_threshold": 0,
  "shipping_per_kg": 0
}
```

</details>

### Orders

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/order?shop_id={id}&status=paid` | Invoice | List (filter by status, limit, offset) |
| `GET` | `/order/{id}` | Invoice | Get order |
| `PUT` | `/order/{id}/fulfillment` | Admin | Body: `{"status": "shipping", "note": "..."}` |

Fulfillment values: `preparing` · `shipping` · `delivered`

### Messages

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/message?shop_id={id}` | Invoice | List messages |
| `GET` | `/message/thread?shop_id={id}&chat_id={id}` | Invoice | Conversation thread |
| `GET` | `/message/unread-count?shop_id={id}` | Invoice | Returns `{"count": N}` |
| `POST` | `/message/{shop_id}` | Admin | Body: `{"chat_id": 123, "content": "text"}` |
| `PUT` | `/message/{id}/read` | Admin | Mark as read |

### Returns

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/return?shop_id={id}&status=requested` | Invoice | List returns |
| `GET` | `/return/{id}` | Invoice | Get return |
| `PUT` | `/return/{id}/approve` | Admin | Body: `{"refund_method": "credit", "refund_amount_sats": 5000}` |
| `PUT` | `/return/{id}/deny` | Admin | Body: `{"admin_note": "reason"}` |

> [!WARNING]
> Approve returns `409 Conflict` if already processed. Always check status first.

### Campaigns

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/commercial?shop_id={id}` | Invoice | List campaigns |
| `POST` | `/commercial` | Admin | Create campaign |
| `PUT` | `/commercial/{id}` | Admin | Update (content, enabled, delay) |
| `DELETE` | `/commercial/{id}` | Admin | Delete campaign |
| `POST` | `/commercial/{id}/broadcast` | Admin | Send to all customers |
| `GET` | `/commercial/{id}/log` | Invoice | View send history |

Types: `abandoned_cart` · `back_in_stock` · `post_purchase` · `promotion`

### Analytics

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| `GET` | `/stats?shop_id={id}` | Invoice | Orders, revenue, customers, unread |
| `GET` | `/customer?shop_id={id}` | Invoice | Customer list with activity timestamps |

---

## Error codes

| Code | Meaning |
|------|---------|
| `400` | Validation error |
| `401` | Missing or invalid API key |
| `404` | Not found or wrong wallet |
| `409` | Already processed (duplicate approval) |
| `429` | Rate limit exceeded |

---

## Tips for agents

- **Admin key** for writes, **invoice key** for reads
- Shop ID is required on most list endpoints — fetch shops first
- Order `cart_json` is a JSON string — parse it to read items
- `currency_amount` has the fiat value, `amount_sats` has what was paid
- Message `direction`: `in` = customer, `out` = admin
- Bot tokens are never in API responses — store them on your side
- Broadcasts are deduplicated — safe to trigger multiple times
