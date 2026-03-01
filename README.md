# Telegram Shopping

A [LNbits](https://lnbits.com) extension that turns a Telegram bot into a Lightning-powered shop.

Customers open a **Telegram Mini App** — a native-feeling storefront embedded right inside the chat — to browse products, fill a cart, and pay with Lightning. You manage orders, messages, returns, and marketing from the LNbits dashboard.

Products live in the [Inventory](https://github.com/lnbits/inventory) extension. One catalog, multiple sales channels.


## Features

**Storefront (Telegram Mini App)**
- Full web storefront embedded inside Telegram — no browser, no app install
- Product browsing by category with images, descriptions, and stock levels
- Persistent shopping cart with quantity controls (synced server-side)
- Checkout with buyer info collection, Lightning invoice, and store credit
- Order history, returns, credits, and messaging — all in-app
- Inline product sharing across any Telegram chat

**Payments**
- Lightning invoices generated at checkout
- Fiat pricing (`USD`, `EUR`, ...) with automatic sat conversion
- Store credit applied before invoicing
- Automatic stock deduction on payment

**Order management**
- Fulfillment tracking: preparing → shipping → delivered
- Customer notifications at each status change (via Telegram with deep links back to the Mini App)
- Buyer info collection: none, email-only, or full shipping address

**Customer communication**
- Bidirectional messaging through the Mini App
- Conversations threaded by customer and order
- Unread message filtering in the admin panel

**Returns & refunds**
- Customer-initiated returns from order history in the Mini App
- Approve with Lightning refund or store credit (full or partial)
- Deny with a written reason
- Configurable return window (default: 30 days)

**Marketing campaigns**
- Abandoned cart reminders
- Back-in-stock notifications
- Post-purchase follow-ups
- Manual promotion broadcasts with image support and live preview

**AI-ready API**
- Full REST API for headless store management
- Create, configure, and run a shop entirely through API calls
- Agent guide and ready-made system prompt included — see [docs/ai](docs/ai/)


## Quick start

1. Install the **Inventory** extension in LNbits and add your products
2. Install **Telegram Shopping**
3. Create a bot via [@BotFather](https://t.me/BotFather) - copy the token
4. Create a shop in the extension: paste the token, follow the setup
5. Toggle the shop on! Then your bot goes live

> Use **polling** mode for development (no public URL needed). Consider switch to **webhook** for production.


## Bot commands

The bot registers a single command. All customer interaction happens in the Mini App.

| Command | Description |
|---------|-------------|
| `/start` | Welcome message with an "Open Shop" button that launches the Mini App |


## Deep links

Link directly to a product — the "Open Shop" button opens the Mini App on that product's page:

```
https://t.me/yourbotname?start=product_PRODUCT_ID
```

Use these for QR codes at events, social media posts, pinned group messages, or anywhere you want one-tap access to a specific product.


## Inline mode

Customers can share products in any Telegram chat. Type `@yourbotname` followed by a search term — the bot suggests matching products as rich inline results with images and prices. Tapping a result posts it into the chat with an "Open Shop" button.

```
@yourbotname pizza
```

Great for word-of-mouth: customers share products with friends without leaving their current conversation.


## Configuration

| Setting | Options |
|---------|---------|
| **Checkout mode** | `none` · `email` · `address` |
| **Currency** | `sat` or any fiat code (`USD`, `EUR`, `GBP`, ...) |
| **Shipping** | Flat rate, per-kg rate, free-shipping threshold |
| **Returns** | On/off, return window, credit refund toggle |
| **Order tracking** | Fulfillment statuses with customer notifications |
| **Delivery** | Webhook (production) or polling (development) |
| **Admin chat ID** | Personal notifications for orders, messages, returns |


## Requirements

- LNbits **1.4.0+**
- [Inventory extension](https://github.com/lnbits/inventory)


## Documentation

**[docs-telegramshop.netlify.app](https://docs-telegramshop.netlify.app)** — full documentation with setup guides, configuration reference, and AI integration.


## License

This project is dual-licensed:

- **AGPLv3** — free for open-source and community use. If you modify and deploy it as a network service, you must publish your source code.
- **Commercial License** — for closed-source, commercial, or production use without AGPL obligations.

See [LICENSE](LICENSE) for full details. For commercial licensing inquiries: [DoktorShift](https://github.com/DoktorShift)
