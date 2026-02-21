# Telegram Shopping

A [LNbits](https://lnbits.com) extension that turns a Telegram bot into a Lightning-powered shop.

Customers browse your catalog, fill a cart, and pay — all without leaving Telegram. They can use classic bot commands or a full **Telegram Mini App** with a native-feeling storefront UI. You manage orders, messages, returns, and marketing from the LNbits dashboard.

Products live in the [Inventory](https://github.com/lnbits/inventory) extension. One catalog, multiple sales channels.

---

## Features

**Storefront**
- Product browsing by category with images, descriptions, and stock levels
- Persistent shopping cart with quantity controls
- Two interfaces: bot commands (inline keyboards) and Telegram Mini App (embedded web UI)
- Deep links to individual products — great for QR codes and social sharing

**Payments**
- Lightning invoices generated at checkout
- Fiat pricing (`USD`, `EUR`, ...) with automatic sat conversion
- Store credit applied before invoicing
- Automatic stock deduction on payment

**Order management**
- Fulfillment tracking: preparing → shipping → delivered
- Customer notifications at each status change
- Buyer info collection: none, email-only, or full shipping address

**Customer communication**
- Bidirectional messaging through the bot
- Conversations threaded by customer and order
- Unread message filtering in the admin panel

**Returns & refunds**
- Customer-initiated returns from order history
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

---

## Quick start

1. Install the **Inventory** extension in LNbits and add your products
2. Install **Telegram Shopping**
3. Create a bot via [@BotFather](https://t.me/BotFather) — copy the token
4. Create a shop in the extension: paste the token, pick a wallet, select your inventory
5. Toggle the shop on — your bot goes live

> Use **polling** mode for development (no public URL needed). Switch to **webhook** for production.

---

## Bot commands

Registered in Telegram's command menu:

| Command | Description |
|---------|-------------|
| `/start` | Welcome screen — opens the Mini App |
| `/orders` | Order history with return option |
| `/credits` | Store credit balance |
| `/message` | Send a message to the shop |
| `/help` | How to shop |

---

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

---

## Requirements

- LNbits **1.4.0+**
- [Inventory extension](https://github.com/lnbits/inventory)
- No external Python dependencies — ships with everything LNbits provides
- SQLite or PostgreSQL

---

## Documentation

Full docs with setup guides, configuration reference, and AI integration:

- [Getting started](docs/guide/getting-started.md)
- [Shop configuration](docs/guide/shop-configuration.md)
- [Telegram Mini App](docs/guide/telegram-mini-app.md)
- [Marketing campaigns](docs/guide/commercials.md)
- [AI agent guide](docs/ai/agent-readme.md)

---

## License

MIT
