# Telegram Mini App

> The entire customer experience lives here — a full web storefront embedded inside Telegram. No browser, no app install — customers tap a button and they're shopping.

---

## How it works

When a customer sends `/start`, the bot replies with an **Open Shop** button. Tapping it opens the Mini App — an embedded web page served by your LNbits instance that looks and feels like a native app.

```
Customer sends /start
        ↓
Bot replies with "Open Shop" button
        ↓
Telegram opens Mini App (embedded web view)
        ↓
Auth via Telegram's HMAC-SHA256 signature
        ↓
Full storefront: browse → cart → checkout → pay → orders → returns → messages
```

The bot itself is a thin launcher. All customer interaction — browsing, cart management, checkout, order history, returns, credits, and messaging — happens in the Mini App.

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

## Notifications

When something happens — a payment is confirmed, an order ships, a return is approved, a message arrives — the bot sends a Telegram notification with a button that deep-links back to the relevant Mini App screen (orders, messages, etc.).

---

## Cart persistence

Carts are stored in the database by chat ID, not just in memory. Close the Mini App, reopen it later — the cart is still there. Switch devices — same Telegram account, same cart. Stale carts (configurable delay) feed into the [abandoned cart campaign](./commercials.md).

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

## Deep links

Link directly to a product — the "Open Shop" button opens the Mini App on that product's page:

```
https://t.me/yourbotname?start=product_PRODUCT_ID
```

When a customer opens this link, the bot sends the welcome message with an **Open Shop** button pre-configured to land on that product. Use these for:

- **QR codes** at markets, events, or physical stores
- **Social media posts** linking to a specific product
- **Pinned group messages** featuring a product drop
- **Email campaigns** or website embeds

---

## Inline mode

Customers can share products in any Telegram chat. Type `@yourbotname` followed by a search term — the bot suggests matching products as rich inline cards with images and prices:

```
@yourbotname pizza
```

Each card posts into the conversation with an **Open Shop** button. Great for word-of-mouth — customers share products with friends without leaving their current chat.

---

## Requirements

The Mini App needs your LNbits instance to be reachable over **HTTPS**. Telegram enforces this for all Mini Apps.

For local development without HTTPS, use polling mode — the bot's `/start` command works, but the Mini App won't open without HTTPS.
