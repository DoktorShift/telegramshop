# Shop Configuration

> Every setting explained. Only title, token, wallet, and inventory are required — the rest has defaults.

---

## Checkout modes

Controls what you collect from customers before payment.

| Mode | Collects | Best for |
|------|----------|----------|
| `none` | Nothing | Digital goods, anonymous purchases |
| `email` | Email address | Download links, receipts |
| `address` | Full shipping address | Physical products |

<details>
<summary>Address fields collected in <code>address</code> mode</summary>

| Field | Required |
|-------|----------|
| Name | Yes |
| Street | Yes |
| Apartment / Unit | No |
| PO Box | No |
| City | Yes |
| State / Province | No |
| ZIP / Postal code | Yes |
| Country | Yes |

</details>

---

## Currency

`sat` for sats-only pricing. Any fiat code (`USD`, `EUR`, `GBP`, ...) for fiat display with automatic sat conversion at checkout.

> [!IMPORTANT]
> Match this to your Inventory extension currency. Mismatched currencies = wrong prices.

---

## Shipping

Three settings that stack:

| Setting | What it does |
|---------|-------------|
| **Flat rate** | Fixed cost per order with physical items |
| **Per-kg rate** | Added per kilogram of total weight |
| **Free threshold** | Orders above this subtotal ship free |

All three at zero = free shipping everywhere.

> [!NOTE]
> Only products with `weight_grams > 0` or tagged `physical` / `shipping` trigger shipping charges.

---

## Tax

Configured in your **Inventory extension**, not here. Telegram Shopping reads:

- Per-product tax rate (or inventory default as fallback)
- Tax-inclusive pricing toggle (default: on — listed prices include tax)

Tax shows as a separate line in the cart.

---

## Returns

| Setting | Default | Effect |
|---------|---------|--------|
| **Allow returns** | On | Shows return option in order history |
| **Return window** | 720 hours (30 days) | Time limit for return requests |
| **Allow credit refund** | On | Enables store credit as a refund option |

---

## Order tracking

When enabled, orders move through:

```
Preparing  →  Shipping  →  Delivered
```

Each transition notifies the customer in Telegram. You can attach a note (tracking number, delivery instructions) that the customer sees.

---

## Webhook security

When using webhook mode, the extension generates a random `secret_token` per shop. Telegram sends it in every update via the `X-Telegram-Bot-Api-Secret-Token` header. The extension verifies it — unsigned updates are rejected silently.

---

## Admin chat ID

Your personal Telegram chat ID. When set, you receive notifications for:

- New paid orders
- Customer messages
- Return requests

Find yours: message [@userinfobot](https://t.me/userinfobot) in Telegram.
