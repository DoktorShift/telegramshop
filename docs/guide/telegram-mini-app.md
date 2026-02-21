# Telegram Mini App

> A full web storefront embedded inside Telegram. No browser, no app install — customers tap a button and they're shopping.

---

## How it works

When a customer taps **Open Shop** after `/start`, Telegram opens an embedded web page served by your LNbits instance. It looks and feels like a native app but runs inside the chat.

```
Customer taps "Open Shop"
        ↓
Telegram opens Mini App (embedded web view)
        ↓
Auth via Telegram's HMAC-SHA256 signature
        ↓
Full storefront: browse → cart → checkout → pay
```

---

## What customers see

| Screen | What's there |
|--------|-------------|
| **Product grid** | All products with images, prices, stock. Filter by category. |
| **Product detail** | Full description, all images, add-to-cart |
| **Cart** | Quantity controls, running totals with tax + shipping |
| **Checkout** | Buyer info form (based on checkout mode), Lightning invoice |
| **Orders** | Order history with status and fulfillment details |
| **Returns** | Submit return requests, view return status |
| **Credits** | Store credit balance and breakdown |
| **Messages** | Chat with the shop owner |

---

## Shared backend

The Mini App and bot commands share everything:

- Same product catalog
- Same cart (persisted server-side by chat ID)
- Same orders, credits, messages
- Same payment flow

A customer can add items in the Mini App, close it, and check out via `/orders` in the bot — or the other way around.

---

## Cart persistence

Carts are stored in the database, not just in memory. Close the Mini App, reopen it later — the cart is still there. Stale carts (configurable delay) feed into the [abandoned cart campaign](./commercials.md).

---

## Authentication

Handled automatically by Telegram — no passwords, no login screens.

1. Telegram passes signed `initData` to the Mini App
2. The extension validates the HMAC-SHA256 signature using the bot token
3. Checks `auth_date` freshness (max 1 hour)
4. Extracts chat ID, username, first name

> [!NOTE]
> Product listings are public (no auth needed). Cart, checkout, orders, and messages require valid authentication.

---

## Requirements

The Mini App needs your LNbits instance to be reachable over **HTTPS**. Telegram enforces this for all Mini Apps.

For local development without HTTPS, use bot commands instead — they work fine with polling mode.
