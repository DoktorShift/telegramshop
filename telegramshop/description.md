A Lightning-powered Telegram shop for LNbits, built around a Telegram Mini App that gives customers a full native-feeling storefront inside the chat.

Its functions include:

- **Telegram Mini App Storefront**  
  Embedded web shop inside Telegram with persistent cart and seamless checkout flow.

- **Smart Inventory & Catalog**  
  Products sync automatically with inventory management, including categories, multi-image galleries, and real-time stock control.

- **Flexible Payments & Refunds**  
  Lightning payments, multi-currency support with live fiat conversion, plus full and partial refunds (including store credit options).

- **Shipping & Order Tracking**  
  Configurable shipping rules (flat rate, weight-based, free threshold) and real-time order status updates from preparation to delivery.

- **Growth & Automation Tools**  
  Automated campaigns (abandoned cart, back-in-stock, follow-ups), customer analytics, inline product sharing, secure webhooks, and full REST API access.

The bot itself is a thin launcher — `/start` opens the Mini App, and inline queries let customers search and share products. All shopping, checkout, orders, returns, credits, and messaging happen in the Mini App. Admin notifications (new orders, messages, returns, fulfillment updates) are sent via Telegram with deep links back into the Mini App.
