# Use Cases — Telegram Shopping

Real scenarios where this extension fits. For setup and feature details, see [README.md](README.md).

---

## Small online shop

You sell stickers, prints, or handmade goods. You don't want to maintain a website or pay platform fees.

Set up your catalog in the Inventory extension, create a Telegram bot, and share the link. Customers browse in the Mini App or through bot commands, pay with Lightning, and you get notified in your admin chat. Ship the order, update the status, and the customer gets a delivery notification in Telegram.

Use checkout mode `address` to collect shipping info. Set a flat shipping rate or a free-shipping threshold to encourage larger orders.

## Digital goods

You sell e-books, templates, presets, or access codes. No shipping, no address needed.

Set checkout mode to `none` or `email`. Shipping stays at zero. Customers pay and you fulfill by sending a message through the bot or by email with their download.

## Pop-up or event sales

You're at a market, conference, or meetup. You want people to order and pay without standing in line.

Share a QR code or deep link (`t.me/yourbot?start=product_<id>`) to a specific product. Customers scan, open the Mini App, tap, pay. You see orders roll in. Works well for pre-orders too — set up products before the event and take orders in advance.

## Community merch store

Your Telegram group wants to sell branded merchandise. Drop the bot into the group or share it in the channel description.

Members browse the Mini App catalog, pick sizes/variants (use categories or tags in Inventory), and pay. You handle fulfillment when enough orders come in. Store credit refunds work well here — if something is out of stock, credit the customer and they spend it on the next drop.

## Restaurant or cafe takeaway

List your menu items in Inventory with categories (Drinks, Mains, Sides). Customers open the Mini App, tap their order, and pay immediately. You see the order, prepare it, and mark it as ready. No checkout address needed — they pick it up.

Set checkout mode to `email` if you want to send receipts, or `none` to keep it minimal.

## Automated store with AI

You want a fully autonomous shop. Set up the store through the REST API — an AI agent creates the shop, configures settings, and starts the bot. From there it monitors orders, replies to customer messages, updates fulfillment, handles returns, and runs marketing campaigns.

See the [AI Setup section](docs/ai/index.md) for the integration guide, system prompt, and Python client.

## Marketing-driven shop

Use the campaign engine to drive repeat purchases. Abandoned cart reminders bring customers back. Back-in-stock alerts notify them when items return. Post-purchase follow-ups encourage reviews. Promotion broadcasts announce sales to all customers.

Each campaign runs independently with its own toggle, content, and send log. The engine runs every 5 minutes and deduplicates automatically.

## Testing and development

Running a workshop or demo? Use polling mode (no public URL needed) and the LNbits FakeWallet backend. The full flow works without real Lightning payments — useful for testing your catalog and checkout before going live.

---

Each of these works with the same extension. The difference is in how you configure the shop: checkout mode, shipping, return policy, campaigns, and what products you put in Inventory.
