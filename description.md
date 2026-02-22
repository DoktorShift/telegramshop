A Lightning-powered Telegram shop for LNbits, built around a Telegram Mini App that gives customers a full native-feeling storefront inside the chat.

Its functions include:

* Telegram Mini App with embedded web storefront, persistent cart, and full checkout flow
* Connecting a Telegram Bot to your LNbits wallet for seamless Lightning checkout
* Pulling products from the Inventory extension with automatic stock management
* Category browsing, product galleries with multi-image support, and cart management
* Flexible shipping costs with flat rate, per-kg weight surcharge, and free shipping threshold
* Order tracking with status updates (preparing, shipping, delivered)
* Returns and refunds via Lightning or store credit
* Partial refunds with adjustable amounts for restocking fees
* Admin-customer messaging through the Mini App, threaded by customer and order
* Marketing campaigns: abandoned cart reminders, back-in-stock alerts, post-purchase follow-ups, and custom promotion broadcasts
* Customer tracking with activity timestamps and audience analytics
* Inline product sharing across any Telegram chat
* Multi-currency support with real-time fiat conversion
* Full REST API for AI-driven store setup and autonomous management
* Webhook security with Telegram secret token verification
* Rate limiting on public endpoints

The bot itself is a thin launcher — `/start` opens the Mini App, and inline queries let customers search and share products. All shopping, checkout, orders, returns, credits, and messaging happen in the Mini App. Admin notifications (new orders, messages, returns, fulfillment updates) are sent via Telegram with deep links back into the Mini App.
