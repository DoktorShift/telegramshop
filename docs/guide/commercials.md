# Marketing Campaigns

> Four campaign types built into the extension. Automated triggers or manual broadcasts — no external tools needed.

---

## Campaign types

| Type | Trigger | What it sends |
|------|---------|---------------|
| **Abandoned cart** | Cart sitting idle for X minutes | Reminder with actual cart contents |
| **Back in stock** | Items return to inventory | List of restocked products |
| **Post-purchase** | Order marked as delivered | Follow-up / thank you message |
| **Promotion** | You click Send | Custom message + optional image |

---

## How it works

> [!NOTE]
> Each customer only receives a campaign **once** per qualifying event. The engine deduplicates automatically.

| Step | What happens |
|:----:|-------------|
| **1** | Shop is created — 4 default campaigns are added, all **disabled** |
| **2** | You enable and customize the campaigns you want |
| **3** | A background engine wakes up every **5 minutes** |
| **4** | It finds customers who match the campaign criteria |
| **5** | It checks the send log — skips anyone who already got this campaign |
| **6** | It delivers the message via Telegram and logs the send |

---

## Managing campaigns

Every campaign has:

| Setting | What it does |
|---------|-------------|
| **Title** | Internal name (for your reference) |
| **Content** | Message text the customer receives |
| **Image URL** | Optional image attached to the message |
| **Delay** | Minutes before auto-trigger fires (automated types only) |
| **Enabled** | Master toggle |

---

## Promotion broadcasts

The promotion type is the only manual campaign. The admin panel gives you:

- **Compose area** — write your message, add an image URL
- **Live preview** — see exactly what customers will receive
- **Send button** — confirmation dialog shows audience size before committing

Broadcasts are rate-limited (30 messages/second) and run in the background.

> [!TIP]
> The audience counter shows how many customers will receive the message. Build your audience by having customers interact with the bot first.

---

## Send log

Every campaign tracks who received what and when. View the log from the admin panel to see delivery history per campaign.

---

## Where messages appear

Campaign messages are sent via Telegram **and** saved as messages in the customer's conversation thread. You can see them in the admin panel's Messages tab alongside regular customer conversations.
