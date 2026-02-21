# Getting Started

> From zero to a running Telegram shop in 5 minutes.

---

## Prerequisites

| What | Why |
|------|-----|
| LNbits **1.4.0+** | Runtime for the extension |
| [Inventory extension](https://github.com/lnbits/inventory) | Your product catalog |
| Telegram bot token | From [@BotFather](https://t.me/BotFather) |

---

## Step by step

### 1. Create your bot

Open [@BotFather](https://t.me/BotFather) in Telegram → `/newbot` → pick a name and username → copy the token.

### 2. Set up products

Install the **Inventory** extension in LNbits. Create an inventory and add products with:
- Name, price, description
- At least one image
- Stock quantity
- Tags (these become your shop categories)

> [!TIP]
> Set your inventory currency to match the shop currency. Prices in USD? Both should be USD.

### 3. Create the shop

In the Telegram Shopping extension, click **Create Shop**:

| Field | Value |
|-------|-------|
| **Title** | Your shop name (shown to customers) |
| **Bot token** | The token from BotFather |
| **Wallet** | Which LNbits wallet receives payments |
| **Inventory** | Select your inventory |
| **Currency** | `sat` or a fiat code like `USD`, `EUR` |

Everything else has sensible defaults.

### 4. Go live

Toggle the shop **on**. That's it. The bot:

- Fetches your product catalog
- Registers commands with Telegram
- Sets up a secure webhook (or starts polling)
- Creates default marketing campaigns (disabled)

### 5. Test it

Open your bot in Telegram → send `/start` → tap **Open Shop**.

---

## Development vs production

| Mode | Use when |
|------|----------|
| **Polling** | Local development — no public URL needed |
| **Webhook** | Production — lower latency, Telegram pushes updates to you |

> [!TIP]
> Use polling + [FakeWallet](https://docs.lnbits.org) for testing without real Lightning.

---

## What's next

- [Shop Configuration](./shop-configuration.md) — checkout modes, shipping, tax, returns
- [Telegram Mini App](./telegram-mini-app.md) — the embedded web storefront
- [Marketing Campaigns](./commercials.md) — automated and manual customer engagement
