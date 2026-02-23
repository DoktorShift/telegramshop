window.app = Vue.createApp({
  el: '#vue',
  mixins: [window.windowMixin],

  data() {
    return {
      loading: true,
      selectedWallet: null,
      activeTab: 'shops',
      drawerRight: false,

      // Data
      shops: [],
      orders: [],
      messages: [],
      returns: [],
      commercials: [],
      customers: [],

      // Stats
      stats: {
        shops: 0,
        shops_live: 0,
        orders_total: 0,
        orders_paid: 0,
        orders_today: 0,
        revenue_sats: 0,
        unread_messages: 0,
        total_messages: 0,
        open_returns: 0,
        total_returns: 0,
        customers: 0
      },
      statsLoading: false,

      // Filters
      shopFilter: '',
      ordersFilter: {shop_id: null, status: null},
      messagesFilter: {shop_id: null, unread_only: false},
      returnsFilter: {shop_id: null, status: null},
      commercialsFilter: {shop_id: null},

      // Dialogs
      shopDialog: {
        show: false,
        data: this._defaultShopData(),
        isEdit: false,
        botUsername: null,
        testing: false,
        step: 1,
        showAdvanced: false
      },
      deleteDialog: {show: false, data: null},
      denyDialog: {show: false, data: null, adminNote: ''},
      approveDialog: {show: false, data: null, method: 'lightning', refundAmount: 0},
      threadDialog: {
        show: false,
        messages: [],
        username: '',
        shopId: '',
        chatId: 0,
        orderId: null
      },
      _threadPollTimer: null,
      fulfillmentDialog: {
        show: false,
        order: null,
        status: '',
        statusLabel: '',
        note: ''
      },
      broadcastDialog: {show: false, sending: false},
      // Reply
      replyText: '',

      // Inventory
      inventoryName: '',
      inventoryLoading: false,
      inventoryError: false,
      activeOmitTags: [],
      availableTags: [],
      tagsLoading: false,

      // Currencies
      currencies: [],

      // Running bots
      runningBots: new Set(),

      // Table columns
      shopColumns: [
        {
          name: 'title',
          label: 'Title',
          field: 'title',
          align: 'left',
          sortable: true
        },
        {
          name: 'bot',
          label: 'Bot',
          field: 'bot_username',
          align: 'left'
        },
        {
          name: 'admin_chat',
          label: 'Admin Chat',
          field: 'admin_chat_id',
          align: 'left'
        },
        {
          name: 'currency',
          label: 'Currency',
          field: 'currency',
          align: 'left',
          format: v => v.toUpperCase()
        },
        {
          name: 'status',
          label: 'Status',
          field: 'is_enabled',
          align: 'center'
        },
        {
          name: 'actions',
          label: 'Actions',
          field: '',
          align: 'right'
        }
      ],
      orderColumns: [
        {
          name: 'expand',
          label: '',
          field: '',
          align: 'left',
          style: 'width: 36px'
        },
        {
          name: 'date',
          label: 'Date',
          field: 'timestamp',
          align: 'left',
          sortable: true
        },
        {
          name: 'customer',
          label: 'Customer',
          field: 'telegram_username',
          align: 'left'
        },
        {
          name: 'items',
          label: 'Items',
          field: 'cart_json',
          align: 'left'
        },
        {
          name: 'amount',
          label: 'Amount',
          field: 'amount_sats',
          align: 'right',
          sortable: true
        },
        {
          name: 'status',
          label: 'Status',
          field: 'status',
          align: 'center'
        }
      ],
      conversationColumns: [
        {
          name: 'unread',
          label: '',
          field: 'unreadCount',
          align: 'center',
          style: 'width: 20px'
        },
        {
          name: 'customer',
          label: 'Customer',
          field: 'username',
          align: 'left'
        },
        {
          name: 'context',
          label: 'Context',
          field: 'orderId',
          align: 'left'
        },
        {
          name: 'preview',
          label: 'Last Message',
          field: 'lastContent',
          align: 'left'
        },
        {
          name: 'date',
          label: 'Date',
          field: 'lastTimestamp',
          align: 'right',
          sortable: true
        },
        {
          name: 'count',
          label: '',
          field: 'totalCount',
          align: 'right'
        }
      ],
      returnColumns: [
        {
          name: 'date',
          label: 'Date',
          field: 'timestamp',
          align: 'left',
          sortable: true
        },
        {
          name: 'order',
          label: 'Order',
          field: 'order_id',
          align: 'left'
        },
        {
          name: 'items',
          label: 'Items',
          field: 'items_json',
          align: 'left'
        },
        {
          name: 'amount',
          label: 'Amount',
          field: 'refund_amount_sats',
          align: 'right'
        },
        {
          name: 'status',
          label: 'Status',
          field: 'status',
          align: 'center'
        },
        {
          name: 'actions',
          label: '',
          field: '',
          align: 'right'
        }
      ],

      commercialColumns: [
        {
          name: 'type',
          label: 'Type',
          field: 'type',
          align: 'left'
        },
        {
          name: 'title',
          label: 'Title',
          field: 'title',
          align: 'left',
          sortable: true
        },
        {
          name: 'status',
          label: 'Enabled',
          field: 'is_enabled',
          align: 'center'
        },
        {
          name: 'actions',
          label: '',
          field: '',
          align: 'right'
        }
      ],
      campaignTypes: [
        {
          value: 'abandoned_cart',
          label: 'Abandoned Cart Reminder',
          icon: 'shopping_cart',
          color: 'orange',
          cta: 'Complete your order',
          description: 'When a customer adds items to their cart but doesn\'t check out, they get a personalised reminder showing exactly what they left behind — item names, quantities, and total.',
          trigger: 'Automatic — sends after cart is inactive for the set time',
          example: '<b>🛒 You left something behind!</b>\n\nHey Sarah, your cart is still waiting for you.\n\n<b>Your cart:</b>\n  • 2× Bitcoin Hoodie\n  • 1× Lightning Sticker Pack\n\n💰 <b>Total: 12,500 sats</b>'
        },
        {
          value: 'post_purchase',
          label: 'Post-Purchase Thank You',
          icon: 'card_giftcard',
          color: 'blue',
          cta: 'Shop again',
          description: 'After you mark an order as delivered, the customer gets a thank-you message. A simple way to build loyalty and encourage repeat purchases.',
          trigger: 'Automatic — sends once an order is marked as delivered',
          example: '<b>🎉 Thanks for shopping with us!</b>\n\nThanks for your order, Sarah! We hope you love it. ✨'
        },
        {
          value: 'back_in_stock',
          label: 'Back in Stock Alert',
          icon: 'inventory',
          color: 'positive',
          cta: 'See what\'s new',
          description: 'When products that were out of stock become available again, all your customers get notified with the names of restocked items.',
          trigger: 'Automatic — sends when sold-out products have stock again',
          example: '<b>📦 Fresh stock just landed!</b>\n\nGood news, Sarah! Items are back in stock.\n\n<b>Now available:</b>\n  • Bitcoin Hoodie\n  • Lightning Node Kit\n  • Satoshi Poster'
        },
        {
          value: 'promotion',
          label: 'Broadcast Promotion',
          icon: 'celebration',
          color: 'purple',
          cta: 'Check it out',
          description: 'Send a message to all your customers inviting them to browse your shop. Use this for new product launches, seasonal pushes, or just to stay top of mind.',
          trigger: 'Manual — you decide when to send',
          example: '<b>🎁 Check out what\'s new!</b>\n\nHey Sarah, see what\'s new at your favourite shop — browse our latest products.'
        }
      ],

      // Status options
      orderStatusOptions: [
        {label: 'All Statuses', value: null},
        {label: 'Pending', value: 'pending'},
        {label: 'Paid', value: 'paid'},
        {label: 'Expired', value: 'expired'},
        {label: 'Refunded', value: 'refunded'}
      ],
      returnStatusOptions: [
        {label: 'All Statuses', value: null},
        {label: 'Requested', value: 'requested'},
        {label: 'Approved', value: 'approved'},
        {label: 'Refunded', value: 'refunded'},
        {label: 'Denied', value: 'denied'}
      ],
      fulfillmentOptions: [
        {label: 'Preparing', value: 'preparing'},
        {label: 'Shipping', value: 'shipping'},
        {label: 'Delivered', value: 'delivered'}
      ]
    }
  },

  computed: {
    promotionPreview() {
      const promo = this.commercials.find(cm => cm.type === 'promotion') || null
      const content = promo && promo.content ? promo.content : null
      const title = promo && promo.title ? promo.title : 'Check out what\'s new!'
      if (content) {
        return `<b>🎁 ${title}</b>\n\n${content}`
      }
      return '<b>🎁 Check out what\'s new!</b>\n\nHey Sarah, see what\'s new at your favourite shop — browse our latest products.'
    },
    currentWallet() {
      if (!this.selectedWallet || !this.g.user.wallets) return null
      return this.g.user.wallets.find(w => w.id === this.selectedWallet)
    },
    filteredShops() {
      let shops = this.shops
      if (this.selectedWallet) {
        shops = shops.filter(s => s.wallet === this.selectedWallet)
      }
      if (this.shopFilter) {
        const q = this.shopFilter.toLowerCase()
        shops = shops.filter(s => s.title.toLowerCase().includes(q))
      }
      return shops
    },
    walletsWithCount() {
      const counts = {}
      this.shops.forEach(s => {
        counts[s.wallet] = (counts[s.wallet] || 0) + 1
      })
      const options = this.g.user.wallets.map(w => ({
        label: w.name,
        value: w.id,
        count: counts[w.id] || 0
      }))
      options.unshift({
        label: 'All Wallets',
        value: null,
        count: this.shops.length
      })
      return options
    },
    shopOptions() {
      const options = this.shops.map(s => ({
        label: s.title,
        value: s.id
      }))
      options.unshift({label: 'All Shops', value: null})
      return options
    },
    conversations() {
      const groups = {}
      for (const msg of this.messages) {
        // Group by chat_id + order_id so separate order threads stay separate
        const key = `${msg.chat_id}_${msg.order_id || 'general'}`
        if (!groups[key]) {
          groups[key] = {
            key,
            chatId: msg.chat_id,
            shopId: msg.shop_id,
            orderId: msg.order_id,
            username: msg.username,
            lastContent: msg.content,
            lastTimestamp: msg.timestamp,
            unreadCount: 0,
            totalCount: 0,
            lastMessage: msg
          }
        }
        const g = groups[key]
        g.totalCount++
        if (!msg.is_read && msg.direction === 'in') g.unreadCount++
        // Keep the username if we find one
        if (msg.username && !g.username) g.username = msg.username
        // Keep the most recent message (messages come sorted DESC from API)
        if (g.totalCount === 1 || msg.timestamp > g.lastTimestamp) {
          g.lastContent = msg.content
          g.lastTimestamp = msg.timestamp
          g.lastMessage = msg
        }
      }
      let convs = Object.values(groups)
      if (this.messagesFilter.unread_only) {
        convs = convs.filter(c => c.unreadCount > 0)
      }
      return convs.sort((a, b) => {
        // Unread first, then by timestamp descending
        if (a.unreadCount > 0 && b.unreadCount === 0) return -1
        if (b.unreadCount > 0 && a.unreadCount === 0) return 1
        return (b.lastTimestamp || '').localeCompare(a.lastTimestamp || '')
      })
    }
  },

  methods: {
    copyText(text) {
      navigator.clipboard.writeText(String(text)).then(() => {
        this.$q.notify({type: 'positive', message: 'Copied!'})
      })
    },
    walletFor(shop) {
      if (!shop) return this.currentWallet || this.g.user.wallets[0]
      return this.g.user.wallets.find(w => w.id === shop.wallet)
        || this.currentWallet || this.g.user.wallets[0]
    },
    // --- Data loading ---
    async loadShops() {
      try {
        const wallets = this.g.user.wallets || []
        if (!wallets.length) return
        const all = []
        const seen = new Set()
        for (const w of wallets) {
          try {
            const {data} = await LNbits.api.request(
              'GET',
              '/telegramshop/api/v1/shop',
              w.inkey
            )
            for (const shop of data) {
              if (!seen.has(shop.id)) {
                seen.add(shop.id)
                all.push(shop)
              }
            }
          } catch {}
        }
        this.shops = all
        this.runningBots = new Set()
        all.forEach(s => {
          if (s.is_enabled) this.runningBots.add(s.id)
        })
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    _walletForShopId(shopId) {
      const shop = this.shops.find(s => s.id === shopId)
      return this.walletFor(shop)
    },

    async loadOrders() {
      const shopId =
        this.ordersFilter.shop_id ||
        (this.shops[0] && this.shops[0].id)
      if (!shopId) return
      // Collect orders from all shops when no filter is set
      const shopIds = this.ordersFilter.shop_id
        ? [this.ordersFilter.shop_id]
        : this.shops.map(s => s.id)
      const all = []
      for (const sid of shopIds) {
        try {
          const wallet = this._walletForShopId(sid)
          let url = `/telegramshop/api/v1/order?shop_id=${sid}`
          if (this.ordersFilter.status) {
            url += `&status=${this.ordersFilter.status}`
          }
          const {data} = await LNbits.api.request(
            'GET',
            url,
            wallet.inkey
          )
          all.push(...data)
        } catch (e) {
          console.error(`Failed to load orders for shop ${sid}:`, e)
        }
      }
      all.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
      this.orders = all
    },

    async loadMessages() {
      const shopIds = this.messagesFilter.shop_id
        ? [this.messagesFilter.shop_id]
        : this.shops.map(s => s.id)
      if (!shopIds.length) return
      const all = []
      let totalUnread = 0
      for (const sid of shopIds) {
        const wallet = this._walletForShopId(sid)
        try {
          let url = `/telegramshop/api/v1/message?shop_id=${sid}`
          const {data} = await LNbits.api.request('GET', url, wallet.inkey)
          all.push(...data)
        } catch (e) {
          console.error(`Failed to load messages for shop ${sid}:`, e)
        }
        try {
          const {data} = await LNbits.api.request(
            'GET',
            `/telegramshop/api/v1/message/unread-count?shop_id=${sid}`,
            wallet.inkey
          )
          totalUnread += data.count || 0
        } catch (e) {
          console.error(`Failed to load unread count for shop ${sid}:`, e)
        }
      }
      all.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
      this.messages = all
    },

    async loadReturns() {
      const shopIds = this.returnsFilter.shop_id
        ? [this.returnsFilter.shop_id]
        : this.shops.map(s => s.id)
      if (!shopIds.length) return
      const all = []
      for (const sid of shopIds) {
        try {
          const wallet = this._walletForShopId(sid)
          let url = `/telegramshop/api/v1/return?shop_id=${sid}`
          if (this.returnsFilter.status) {
            url += `&status=${this.returnsFilter.status}`
          }
          const {data} = await LNbits.api.request('GET', url, wallet.inkey)
          all.push(...data)
        } catch (e) {
          console.error(`Failed to load returns for shop ${sid}:`, e)
        }
      }
      all.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
      this.returns = all
    },

    async loadStats() {
      const wallets = this.g.user.wallets || []
      if (!wallets.length) return
      this.statsLoading = true
      // Aggregate stats across all wallets (each wallet may own different shops)
      const merged = {
        shops: 0, shops_live: 0,
        orders_total: 0, orders_paid: 0, orders_today: 0, revenue_sats: 0,
        unread_messages: 0, total_messages: 0,
        open_returns: 0, total_returns: 0,
        customers: 0
      }
      for (const w of wallets) {
        try {
          const {data} = await LNbits.api.request(
            'GET', '/telegramshop/api/v1/stats', w.inkey
          )
          for (const key of Object.keys(merged)) {
            merged[key] += data[key] || 0
          }
        } catch {}
      }
      this.stats = merged
      this.statsLoading = false
    },

    async loadAll() {
      this.loading = true
      await this.loadShops()
      await this.loadStats()
      this.loading = false
    },

    // --- Shop CRUD ---
    async openShopDialog(shop) {
      if (shop) {
        const d = {...shop}
        // Convert CSV tag strings to arrays for q-select
        d.include_tags = d.include_tags
          ? d.include_tags.split(',').map(t => t.trim()).filter(Boolean)
          : []
        d.omit_tags = d.omit_tags
          ? d.omit_tags.split(',').map(t => t.trim()).filter(Boolean)
          : []
        this.shopDialog.data = d
        this.shopDialog.isEdit = true
        this.shopDialog.botUsername = null
        this.shopDialog.step = 1
        this.shopDialog.showAdvanced = false
      } else {
        this.shopDialog.data = this._defaultShopData()
        this.shopDialog.isEdit = false
        this.shopDialog.botUsername = null
        this.shopDialog.step = 1
        this.shopDialog.showAdvanced = false
      }
      this.shopDialog.show = true
      await this.loadInventoryOptions()
    },

    onShopDialogHide() {
      this.shopDialog.botUsername = null
      this.shopDialog.step = 1
      this.shopDialog.showAdvanced = false
    },

    async saveShop() {
      try {
        const d = {...this.shopDialog.data}
        // Convert tag arrays to CSV strings for the API
        d.include_tags = Array.isArray(d.include_tags)
          ? d.include_tags.join(',') : (d.include_tags || '')
        d.omit_tags = Array.isArray(d.omit_tags)
          ? d.omit_tags.join(',') : (d.omit_tags || '')
        // Send empty string as null
        if (!d.include_tags) d.include_tags = null
        if (!d.omit_tags) d.omit_tags = null
        if (this.shopDialog.isEdit) {
          const wallet = this.walletFor(d)
          await LNbits.api.request(
            'PUT',
            `/telegramshop/api/v1/shop/${d.id}`,
            wallet.adminkey,
            d
          )
          this.$q.notify({type: 'positive', message: 'Shop updated'})
        } else {
          const wallet = this.currentWallet || this.g.user.wallets[0]
          await LNbits.api.request(
            'POST',
            '/telegramshop/api/v1/shop',
            wallet.adminkey,
            d
          )
          this.$q.notify({type: 'positive', message: 'Shop created'})
        }
        this.shopDialog.show = false
        await this.loadShops()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    openDeleteDialog(shop) {
      this.deleteDialog.data = shop
      this.deleteDialog.show = true
    },

    async confirmDelete() {
      try {
        const wallet = this.walletFor(this.deleteDialog.data)
        await LNbits.api.request(
          'DELETE',
          `/telegramshop/api/v1/shop/${this.deleteDialog.data.id}`,
          wallet.adminkey
        )
        this.$q.notify({type: 'positive', message: 'Shop deleted'})
        this.deleteDialog.show = false
        this.runningBots.delete(this.deleteDialog.data.id)
        await this.loadShops()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    async testBotToken() {
      this.shopDialog.testing = true
      try {
        const wallet = this.currentWallet || this.g.user.wallets[0]
        const {data} = await LNbits.api.request(
          'POST',
          '/telegramshop/api/v1/shop/test-token',
          wallet.adminkey,
          {bot_token: this.shopDialog.data.bot_token}
        )
        this.shopDialog.botUsername = data.username
        this.$q.notify({
          type: 'positive',
          message: `Connected to @${data.username}`
        })
      } catch (e) {
        LNbits.utils.notifyApiError(e)
        this.shopDialog.botUsername = null
      }
      this.shopDialog.testing = false
    },

    async loadInventoryOptions() {
      this.inventoryLoading = true
      this.inventoryError = false
      this.activeOmitTags = []
      try {
        const wallet = this.currentWallet || this.g.user.wallets[0]
        if (!wallet) {
          console.error('[TelegramShop] No wallet available')
          this.inventoryName = ''
          this.inventoryError = true
          this.inventoryLoading = false
          return
        }
        console.log('[TelegramShop] Fetching inventory with key:',
          wallet.inkey?.substring(0, 8) + '...')
        const resp = await LNbits.api.request(
          'GET',
          '/telegramshop/api/v1/sources/inventory',
          wallet.inkey
        )
        console.log('[TelegramShop] Inventory response:', resp)
        const data = resp.data
        if (data && data.length > 0) {
          this.inventoryName = data[0].name || data[0].id
          // Auto-set inventory_id (only one inventory per user)
          if (!this.shopDialog.data.inventory_id) {
            this.shopDialog.data.inventory_id = data[0].id
          }
          if (data[0].omit_tags) {
            this.activeOmitTags = data[0].omit_tags
          }
        } else {
          this.inventoryName = ''
          this.inventoryError = true
        }
      } catch (e) {
        console.error('[TelegramShop] Failed to load inventory:', e)
        console.error('[TelegramShop] Error response:',
          e.response?.status, e.response?.data)
        this.inventoryName = ''
        this.inventoryError = true
      }
      this.inventoryLoading = false
      // Fetch available tags from inventory items
      this.tagsLoading = true
      try {
        const wallet = this.currentWallet || this.g.user.wallets[0]
        if (wallet) {
          const resp = await LNbits.api.request(
            'GET',
            '/telegramshop/api/v1/sources/inventory/tags',
            wallet.inkey
          )
          this.availableTags = resp.data.tags || []
        }
      } catch (e) {
        console.error('[TelegramShop] Failed to load tags:', e)
        this.availableTags = []
      }
      this.tagsLoading = false
    },

    // --- Shop actions ---
    async toggleShop(shop) {
      const action = shop.is_enabled ? 'stop' : 'start'
      try {
        const wallet = this.walletFor(shop)
        await LNbits.api.request(
          'POST',
          `/telegramshop/api/v1/shop/${shop.id}/${action}`,
          wallet.adminkey
        )
        if (action === 'start') {
          this.runningBots.add(shop.id)
        } else {
          this.runningBots.delete(shop.id)
        }
        this.$q.notify({
          type: 'positive',
          message: `Bot ${action}ed`
        })
        await this.loadShops()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    async refreshShop(shop) {
      try {
        const wallet = this.walletFor(shop)
        await LNbits.api.request(
          'POST',
          `/telegramshop/api/v1/shop/${shop.id}/refresh`,
          wallet.adminkey
        )
        this.$q.notify({
          type: 'positive',
          message: 'Products refreshed'
        })
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    // --- Orders ---
    canTrackFulfillment(order) {
      if (order.status !== 'paid') {
        return false
      }
      const shop = this.shops.find(s => s.id === order.shop_id)
      return shop && shop.enable_order_tracking
    },

    updateFulfillment(order, status) {
      const labels = {
        preparing: 'Preparing',
        shipping: 'Shipping',
        delivered: 'Delivered'
      }
      this.fulfillmentDialog.order = order
      this.fulfillmentDialog.status = status
      this.fulfillmentDialog.statusLabel = labels[status]
      this.fulfillmentDialog.note = ''
      this.fulfillmentDialog.show = true
    },

    async confirmFulfillment() {
      try {
        const order = this.fulfillmentDialog.order
        const wallet = this._walletForShopId(order.shop_id)
        await LNbits.api.request(
          'PUT',
          `/telegramshop/api/v1/order/${this.fulfillmentDialog.order.id}/fulfillment`,
          wallet.adminkey,
          {
            status: this.fulfillmentDialog.status,
            note: this.fulfillmentDialog.note || null
          }
        )
        this.$q.notify({
          type: 'positive',
          message: 'Fulfillment updated'
        })
        this.fulfillmentDialog.show = false
        await this.loadOrders()
        this.loadStats()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    // --- Messages ---
    async openConversation(conv) {
      const shopId = conv.shopId || conv.shop_id
      const chatId = conv.chatId || conv.chat_id
      const orderId = conv.orderId || conv.order_id || null
      const username = conv.username || ''
      const wallet = this._walletForShopId(shopId)

      // Mark unread messages as read
      if (conv.unreadCount > 0 || (!conv.is_read && conv.direction === 'in')) {
        for (const msg of this.messages) {
          if (msg.chat_id === chatId && msg.shop_id === shopId
              && !msg.is_read && msg.direction === 'in'
              && ((!orderId && !msg.order_id) || msg.order_id === orderId)) {
            try {
              await LNbits.api.request(
                'PUT',
                `/telegramshop/api/v1/message/${msg.id}/read`,
                wallet.adminkey
              )
            } catch (e) {
              /* silent */
            }
          }
        }
      }
      try {
        let url =
          `/telegramshop/api/v1/message/thread?shop_id=${shopId}&chat_id=${chatId}`
        if (orderId) url += `&order_id=${orderId}`
        const {data} = await LNbits.api.request(
          'GET',
          url,
          wallet.inkey
        )
        this.threadDialog.messages = data
        this.threadDialog.username = username
        this.threadDialog.shopId = shopId
        this.threadDialog.chatId = chatId
        this.threadDialog.orderId = orderId
        this.threadDialog.show = true
        this._startThreadPoll()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    _startThreadPoll() {
      this._stopThreadPoll()
      this._threadPollTimer = setInterval(async () => {
        if (!this.threadDialog.show) {
          this._stopThreadPoll()
          return
        }
        try {
          const wallet = this._walletForShopId(this.threadDialog.shopId)
          let url =
            `/telegramshop/api/v1/message/thread?shop_id=${this.threadDialog.shopId}&chat_id=${this.threadDialog.chatId}`
          if (this.threadDialog.orderId) url += `&order_id=${this.threadDialog.orderId}`
          const {data} = await LNbits.api.request('GET', url, wallet.inkey)
          if (data.length !== this.threadDialog.messages.length
              || (data.length && data[data.length - 1].id
                  !== this.threadDialog.messages[this.threadDialog.messages.length - 1].id)) {
            this.threadDialog.messages = data
          }
        } catch { /* silent */ }
      }, 5000)
    },

    _stopThreadPoll() {
      if (this._threadPollTimer) {
        clearInterval(this._threadPollTimer)
        this._threadPollTimer = null
      }
    },

    async sendReply() {
      if (!this.replyText.trim()) return
      try {
        const wallet = this._walletForShopId(this.threadDialog.shopId)
        await LNbits.api.request(
          'POST',
          `/telegramshop/api/v1/message/${this.threadDialog.shopId}`,
          wallet.adminkey,
          {
            chat_id: this.threadDialog.chatId,
            content: this.replyText,
            order_id: this.threadDialog.orderId
          }
        )
        this.replyText = ''
        await this.openConversation({
          shopId: this.threadDialog.shopId,
          chatId: this.threadDialog.chatId,
          orderId: this.threadDialog.orderId,
          username: this.threadDialog.username
        })
        await this.loadMessages()
        this.loadStats()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    // --- Returns ---
    openApproveDialog(ret) {
      this.approveDialog.data = ret
      this.approveDialog.refundAmount = ret.refund_amount_sats
      this.approveDialog.method = 'lightning'
      this.approveDialog.show = true
    },

    async confirmApprove() {
      const ret = this.approveDialog.data
      if (!ret) return
      try {
        const wallet = this._walletForShopId(ret.shop_id)
        const payload = {
          refund_method: this.approveDialog.method
        }
        if (this.approveDialog.refundAmount !== ret.refund_amount_sats) {
          payload.refund_amount_sats = this.approveDialog.refundAmount
        }
        await LNbits.api.request(
          'PUT',
          `/telegramshop/api/v1/return/${ret.id}/approve`,
          wallet.adminkey,
          payload
        )
        this.$q.notify({
          type: 'positive',
          message:
            this.approveDialog.method === 'credit'
              ? 'Approved: Store credit issued'
              : 'Approved: Awaiting customer invoice/address'
        })
        this.approveDialog.show = false
        await this.loadReturns()
        this.loadStats()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    openDenyDialog(ret) {
      this.denyDialog.data = ret
      this.denyDialog.adminNote = ''
      this.denyDialog.show = true
    },

    async confirmDeny() {
      try {
        const wallet = this._walletForShopId(this.denyDialog.data.shop_id)
        await LNbits.api.request(
          'PUT',
          `/telegramshop/api/v1/return/${this.denyDialog.data.id}/deny`,
          wallet.adminkey,
          {admin_note: this.denyDialog.adminNote}
        )
        this.$q.notify({type: 'positive', message: 'Return denied'})
        this.denyDialog.show = false
        await this.loadReturns()
        this.loadStats()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    // --- Commercials ---
    async loadCommercials() {
      const shopIds = this.commercialsFilter.shop_id
        ? [this.commercialsFilter.shop_id]
        : this.shops.map(s => s.id)
      if (!shopIds.length) return
      const all = []
      for (const sid of shopIds) {
        try {
          const wallet = this._walletForShopId(sid)
          const {data} = await LNbits.api.request(
            'GET',
            `/telegramshop/api/v1/commercial?shop_id=${sid}`,
            wallet.inkey
          )
          all.push(...data)
        } catch (e) {
          console.error(`Failed to load commercials for shop ${sid}:`, e)
        }
      }
      this.commercials = all
    },

    async loadCustomers() {
      const shopIds = this.commercialsFilter.shop_id
        ? [this.commercialsFilter.shop_id]
        : this.shops.map(s => s.id)
      if (!shopIds.length) return
      const all = []
      for (const sid of shopIds) {
        try {
          const wallet = this._walletForShopId(sid)
          const {data} = await LNbits.api.request(
            'GET',
            `/telegramshop/api/v1/customer?shop_id=${sid}`,
            wallet.inkey
          )
          all.push(...data)
        } catch (e) {
          console.error(`Failed to load customers for shop ${sid}:`, e)
        }
      }
      this.customers = all
    },

    _commercialByType(type) {
      return this.commercials.find(c => c.type === type) || null
    },

    getCommercialEnabled(type) {
      const c = this._commercialByType(type)
      return c ? c.is_enabled : false
    },

    getCommercialDelay(type) {
      const c = this._commercialByType(type)
      return c ? c.delay_minutes : 60
    },

    async toggleCommercialType(type) {
      const c = this._commercialByType(type)
      if (!c) return
      try {
        const wallet = this._walletForShopId(c.shop_id)
        await LNbits.api.request(
          'PUT',
          `/telegramshop/api/v1/commercial/${c.id}`,
          wallet.adminkey,
          {is_enabled: !c.is_enabled}
        )
        await this.loadCommercials()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    async updateCommercialDelay(type, minutes) {
      const c = this._commercialByType(type)
      if (!c) return
      const val = parseInt(minutes)
      if (isNaN(val) || val < 1) return
      try {
        const wallet = this._walletForShopId(c.shop_id)
        await LNbits.api.request(
          'PUT',
          `/telegramshop/api/v1/commercial/${c.id}`,
          wallet.adminkey,
          {delay_minutes: val}
        )
        await this.loadCommercials()
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      }
    },

    getCommercialContent(type) {
      const c = this._commercialByType(type)
      return c ? c.content || '' : ''
    },

    getCommercialImageUrl(type) {
      const c = this._commercialByType(type)
      return c ? c.image_url || '' : ''
    },

    async updateCommercialContent(type, val) {
      const c = this._commercialByType(type)
      if (!c) return
      // Update locally for instant preview
      c.content = val
      // Debounce save
      clearTimeout(this._contentSaveTimer)
      this._contentSaveTimer = setTimeout(async () => {
        try {
          const wallet = this._walletForShopId(c.shop_id)
          await LNbits.api.request(
            'PUT',
            `/telegramshop/api/v1/commercial/${c.id}`,
            wallet.adminkey,
            {content: val}
          )
        } catch (e) {
          LNbits.utils.notifyApiError(e)
        }
      }, 800)
    },

    async updateCommercialImageUrl(type, val) {
      const c = this._commercialByType(type)
      if (!c) return
      c.image_url = val
      clearTimeout(this._imageSaveTimer)
      this._imageSaveTimer = setTimeout(async () => {
        try {
          const wallet = this._walletForShopId(c.shop_id)
          await LNbits.api.request(
            'PUT',
            `/telegramshop/api/v1/commercial/${c.id}`,
            wallet.adminkey,
            {image_url: val || null}
          )
        } catch (e) {
          LNbits.utils.notifyApiError(e)
        }
      }, 800)
    },

    broadcastType(type) {
      const c = this._commercialByType(type)
      if (!c) return
      this.broadcastDialog.show = true
    },

    async confirmBroadcast() {
      const c = this._commercialByType('promotion')
      if (!c) return
      this.broadcastDialog.sending = true
      try {
        const wallet = this._walletForShopId(c.shop_id)
        const {data} = await LNbits.api.request(
          'POST',
          `/telegramshop/api/v1/commercial/${c.id}/broadcast`,
          wallet.adminkey
        )
        this.broadcastDialog.show = false
        this.$q.notify({
          type: 'positive',
          message: `Broadcast sent to ${data.sent} of ${data.total} customers`
        })
      } catch (e) {
        LNbits.utils.notifyApiError(e)
      } finally {
        this.broadcastDialog.sending = false
      }
    },

    // --- Formatters ---
    formatSat(val) {
      return LNbits.utils.formatSat(val)
    },
    _parseTimestamp(val) {
      if (!val) return null
      // If numeric (epoch seconds), convert directly
      if (typeof val === 'number') return new Date(val * 1000)
      // If string that looks like epoch
      if (/^\d+(\.\d+)?$/.test(val)) return new Date(parseFloat(val) * 1000)
      // ISO / SQL timestamp string — append Z if no timezone to treat as UTC
      const d = new Date(val.includes('T') || val.includes('Z') ? val : val + 'Z')
      return isNaN(d.getTime()) ? null : d
    },
    formatDate(val) {
      const d = this._parseTimestamp(val)
      if (!d) return ''
      return d.toLocaleDateString(undefined, {year: 'numeric', month: 'short', day: 'numeric'})
    },
    formatDateFrom(val) {
      const d = this._parseTimestamp(val)
      if (!d) return ''
      const now = new Date()
      const diff = now - d
      const mins = Math.floor(diff / 60000)
      if (mins < 1) return 'just now'
      if (mins < 60) return `${mins}m ago`
      const hours = Math.floor(mins / 60)
      if (hours < 24) return `${hours}h ago`
      const days = Math.floor(hours / 24)
      if (days < 7) return `${days}d ago`
      return d.toLocaleDateString(undefined, {month: 'short', day: 'numeric'})
    },
    truncate(text, max) {
      if (!text) return ''
      return text.length > max
        ? text.substring(0, max - 3) + '...'
        : text
    },
    cartItemCount(cartJson) {
      try {
        const items = JSON.parse(cartJson)
        return items.reduce((sum, i) => sum + i.quantity, 0)
      } catch {
        return 0
      }
    },
    parseCart(cartJson) {
      try {
        return JSON.parse(cartJson)
      } catch {
        return []
      }
    },
    formatAddress(addrJson) {
      try {
        const a = JSON.parse(addrJson)
        const lines = [a.name, a.street]
        if (a.street2) lines.push(a.street2)
        if (a.po_box) lines.push(`PO Box ${a.po_box}`)
        let city = a.city
        if (a.state) city += `, ${a.state}`
        city += ` ${a.zip_code}`
        lines.push(city)
        lines.push(a.country)
        return lines.join('\n')
      } catch {
        return addrJson
      }
    },
    returnItemsSummary(itemsJson) {
      try {
        const items = JSON.parse(itemsJson)
        return items.map(i => `${i.quantity}x ${i.title}`).join(', ')
      } catch {
        return ''
      }
    },
    orderStatusColor(status) {
      const colors = {
        pending: 'orange',
        paid: 'positive',
        expired: 'negative',
        refunded: 'blue'
      }
      return colors[status] || 'grey'
    },
    returnStatusColor(status) {
      const colors = {
        requested: 'orange',
        approved: 'blue',
        refunded: 'positive',
        denied: 'negative'
      }
      return colors[status] || 'grey'
    },
    fulfillmentColor(status) {
      const colors = {
        preparing: 'orange',
        shipping: 'blue',
        delivered: 'positive'
      }
      return colors[status] || 'grey'
    },

    // --- Helpers ---
    _defaultShopData() {
      return {
        title: '',
        description: '',
        bot_token: '',
        currency: 'sat',
        inventory_id: '',
        checkout_mode: 'none',
        enable_order_tracking: false,
        use_webhook: false,
        admin_chat_id: '',
        allow_returns: true,
        allow_credit_refund: true,
        return_window_hours: 720,
        shipping_flat_rate: 0,
        shipping_free_threshold: 0,
        shipping_per_kg: 0,
        include_tags: [],
        omit_tags: []
      }
    }
  },

  watch: {
    activeTab(tab) {
      if (tab === 'orders') this.loadOrders()
      else if (tab === 'messages') this.loadMessages()
      else if (tab === 'returns') this.loadReturns()
      else if (tab === 'commercials') {
        this.loadCommercials()
        this.loadCustomers()
      }
    },
    'threadDialog.show'(open) {
      if (!open) this._stopThreadPoll()
    },
    'ordersFilter.shop_id'() {
      this.loadOrders()
    },
    'ordersFilter.status'() {
      this.loadOrders()
    },
    'messagesFilter.shop_id'() {
      this.loadMessages()
    },
    'returnsFilter.shop_id'() {
      this.loadReturns()
    },
    'returnsFilter.status'() {
      this.loadReturns()
    },
    'commercialsFilter.shop_id'() {
      this.loadCommercials()
      this.loadCustomers()
    }
  },

  async created() {
    // Default to all wallets so every shop is visible
    this.selectedWallet = null
    try {
      const {data} = await LNbits.api.getCurrencies()
      this.currencies = ['sat', ...data]
    } catch {
      this.currencies = ['sat', 'USD', 'EUR', 'GBP', 'CHF']
    }
    await this.loadAll()
    // Auto-refresh stats every 60s
    this._statsInterval = setInterval(() => this.loadStats(), 60000)
  },
  beforeUnmount() {
    if (this._statsInterval) clearInterval(this._statsInterval)
  }
})
