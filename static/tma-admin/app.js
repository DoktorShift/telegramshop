/* ===== Admin TMA (Telegram Mini App) SPA ===== */

const INVOICE_EXPIRY_SECONDS = 900

const Admin = {
  // --- State ---
  shopId: null,
  initData: null,
  chatId: null,
  username: null,
  shopTitle: '',
  shopCurrency: 'sat',
  enableOrderTracking: false,
  allowReturns: true,
  authenticated: false,
  stats: null,
  orders: [],
  conversations: [],
  currentScreen: 'auth',
  orderFilter: 'all',
  returnFilter: 'all',
  _searchQuery: '',
  _searchTimer: null,

  // --- Base URL ---
  get baseUrl() {
    return window.location.origin + '/telegramshop/api/v1/tma-admin'
  },

  // --- Init ---
  async init() {
    const params = new URLSearchParams(window.location.search)
    this.shopId = params.get('shop')
    if (!this.shopId) {
      document.getElementById('app').innerHTML =
        '<div style="padding:40px;text-align:center">Missing shop parameter</div>'
      return
    }

    const tg = window.Telegram && window.Telegram.WebApp
    if (tg && tg.initData) {
      tg.ready()
      tg.expand()
      tg.setHeaderColor(tg.themeParams.bg_color || '#ffffff')
      tg.setBackgroundColor(tg.themeParams.bg_color || '#ffffff')
      if (tg.setBottomBarColor) {
        tg.setBottomBarColor(tg.themeParams.bottom_bar_bg_color || tg.themeParams.bg_color || '#ffffff')
      }
      this.initData = tg.initData
    }

    // Listen for runtime theme changes
    if (tg) {
      tg.onEvent('themeChanged', () => {
        tg.setHeaderColor(tg.themeParams.bg_color || '#ffffff')
        tg.setBackgroundColor(tg.themeParams.bg_color || '#ffffff')
        if (tg.setBottomBarColor) {
          tg.setBottomBarColor(tg.themeParams.bottom_bar_bg_color || tg.themeParams.bg_color || '#ffffff')
        }
      })
    }

    if (!this.initData) {
      this._showDevBanner()
    }

    // BackButton handler
    this._backHandler = () => window.history.back()
    if (tg && tg.BackButton) {
      tg.BackButton.onClick(this._backHandler)
    }

    window.addEventListener('hashchange', () => this.route())

    await this.authenticate()

    // Check for deep-link route
    const initialRoute = params.get('route')
    if (initialRoute) {
      window.location.hash = '#/' + initialRoute
    } else if (window.location.hash && window.location.hash !== '#/') {
      this.route()
    } else {
      this.navigate('#/')
    }

    // Start stats refresh
    this._startStatsRefresh()
  },

  _showDevBanner() {
    const banner = document.createElement('div')
    banner.style.cssText =
      'background:#e8eaf6;color:#283593;padding:8px 16px;font-size:13px;'
      + 'text-align:center;border-bottom:1px solid #7986cb;position:sticky;top:0;z-index:999'
    banner.textContent = 'Browser preview \u2014 admin features require Telegram'
    document.body.prepend(banner)
  },

  // --- API Client ---
  async api(path, options = {}) {
    const url = this.baseUrl + path
    const headers = options.headers || {}
    if (options.body) {
      headers['Content-Type'] = 'application/json'
    }
    if (this.initData) {
      headers['Authorization'] = 'tma ' + this.initData
    }
    try {
      const resp = await fetch(url, {
        ...options,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || 'HTTP ' + resp.status)
      }
      return resp.json()
    } catch (e) {
      console.error('API error:', path, e)
      throw e
    }
  },

  // --- Auth ---
  async authenticate() {
    if (!this.initData) {
      this.authenticated = false
      this._showAuthError('Open from Telegram to access admin')
      return
    }
    try {
      const data = await this.api('/auth', {
        method: 'POST',
        body: { shop_id: this.shopId },
      })
      this.chatId = data.chat_id
      this.username = data.username
      this.shopTitle = data.shop_title
      this.shopCurrency = data.shop_currency
      this.enableOrderTracking = data.enable_order_tracking
      this.allowReturns = data.allow_returns
      this.authenticated = true

      // Load initial stats
      await this.loadStats()
    } catch (e) {
      console.warn('Auth failed:', e)
      this.authenticated = false
      this._showAuthError('Could not connect. Please reopen the app.')
    }
  },

  _showAuthError(msg) {
    const screen = document.getElementById('screen-auth')
    screen.innerHTML = '<div class="empty-state">' +
      '<div class="empty-icon">\ud83d\udd12</div>' +
      '<h3>Access Denied</h3>' +
      '<p class="text-hint">' + this.escapeHtml(msg) + '</p></div>'
  },

  async loadStats() {
    if (!this.authenticated) return
    try {
      this.stats = await this.api('/' + this.shopId + '/stats')
      this.updateBadges()
    } catch {
      this.stats = null
    }
  },

  // --- Stats Refresh ---
  _statsTimer: null,

  _startStatsRefresh() {
    this._stopStatsRefresh()
    this._statsTimer = setInterval(() => this.loadStats(), 30000)
  },

  _stopStatsRefresh() {
    if (this._statsTimer) {
      clearInterval(this._statsTimer)
      this._statsTimer = null
    }
  },

  // --- Thread Polling ---
  _threadTimer: null,
  _threadHash: null,

  _startThreadPoll(chatId, orderId) {
    this._stopThreadPoll()
    this._threadTimer = setInterval(async () => {
      if (this.currentScreen !== 'thread') {
        this._stopThreadPoll()
        return
      }
      try {
        let path = '/' + this.shopId + '/messages/thread?chat_id=' + chatId
        if (orderId) path += '&order_id=' + orderId
        const msgs = await this.api(path)
        const hash = msgs.length + ':' + (msgs.length ? msgs[msgs.length - 1].timestamp : '')
        if (this._threadHash && this._threadHash !== hash) {
          this._renderThreadMessages(msgs, chatId, orderId)
        }
        this._threadHash = hash
      } catch { /* silent */ }
    }, 5000)
  },

  _stopThreadPoll() {
    if (this._threadTimer) {
      clearInterval(this._threadTimer)
      this._threadTimer = null
    }
    this._threadHash = null
  },

  // --- Badges ---
  updateBadges() {
    if (!this.stats) return
    const ordersBadge = document.getElementById('orders-badge')
    const msgBadge = document.getElementById('messages-badge')
    const returnsBadge = document.getElementById('returns-badge')

    const pendingOrders = this.stats.orders_pending || 0
    if (ordersBadge) {
      if (pendingOrders > 0) {
        ordersBadge.textContent = pendingOrders
        ordersBadge.style.display = ''
      } else {
        ordersBadge.style.display = 'none'
      }
    }
    if (msgBadge) {
      const unread = this.stats.unread_messages || 0
      if (unread > 0) {
        msgBadge.textContent = unread
        msgBadge.style.display = ''
      } else {
        msgBadge.style.display = 'none'
      }
    }
    if (returnsBadge) {
      const openReturns = this.stats.open_returns || 0
      if (openReturns > 0) {
        returnsBadge.textContent = openReturns
        returnsBadge.style.display = ''
      } else {
        returnsBadge.style.display = 'none'
      }
    }
  },

  // --- Routing ---
  navigate(hash) {
    window.location.hash = hash
  },

  route() {
    if (!this.authenticated) return

    const hash = window.location.hash || '#/'
    const parts = hash.split('/')
    const route = parts[1] || ''

    // Stop thread polling when navigating away
    this._stopThreadPoll()
    this._startStatsRefresh()

    window.scrollTo(0, 0)

    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'))
    document.querySelectorAll('.tab-bar .tab').forEach(t => t.classList.remove('active'))

    const tg = window.Telegram && window.Telegram.WebApp

    // BackButton: show/hide
    const tabScreens = ['', 'orders', 'messages', 'returns']
    if (tg && tg.BackButton) {
      if (tabScreens.includes(route)) {
        tg.BackButton.hide()
      } else {
        tg.BackButton.show()
      }
    }

    switch (route) {
      case '':
        this.showScreen('dashboard')
        this.renderDashboard()
        this.setActiveTab('dashboard')
        break
      case 'orders':
        this.showScreen('orders')
        this.renderOrders()
        this.setActiveTab('orders')
        break
      case 'order':
        this.showScreen('order-detail')
        this.renderOrderDetail(parts[2])
        break
      case 'messages':
        this.showScreen('messages')
        this.renderMessages()
        this.setActiveTab('messages')
        break
      case 'thread':
        this._stopStatsRefresh()
        this.showScreen('thread')
        this.renderThread(parts[2], parts[3] || null)
        break
      case 'returns':
        this.showScreen('returns')
        this.renderReturns()
        this.setActiveTab('returns')
        break
      case 'return':
        this.showScreen('return-detail')
        this.renderReturnDetail(parts[2])
        break
      case 'customers':
        this.showScreen('customers')
        this.renderCustomers()
        break
      case 'customer':
        this.showScreen('customer')
        this.renderCustomerProfile(parts[2])
        break
      default:
        this.showScreen('dashboard')
        this.renderDashboard()
        this.setActiveTab('dashboard')
    }

    this.currentScreen = route || 'dashboard'
  },

  showScreen(id) {
    const el = document.getElementById('screen-' + id)
    if (el) el.classList.add('active')
  },

  setActiveTab(name) {
    document.querySelectorAll('.tab-bar .tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === name)
    })
  },

  // ===== Render: Dashboard =====
  async renderDashboard() {
    const container = document.getElementById('dashboard-content')
    const s = this.stats || {}

    let html = '<div class="dashboard-header">' +
      '<div class="dashboard-title">' + this.escapeHtml(this.shopTitle) + '</div>' +
      '<div class="dashboard-subtitle">Admin Dashboard</div>' +
      '</div>'

    // Primary stat cards (2x2)
    html += '<div class="stats-grid">' +
      this._statCard('\ud83d\udce6', s.orders_today || 0, 'Orders Today', '#/orders') +
      this._statCard('\u26a1', this._compactSats(s.revenue_sats || 0) + ' sats', 'Revenue', '#/orders') +
      this._statCard('\ud83d\udcac', s.unread_messages || 0, 'Unread Msgs', '#/messages') +
      this._statCard('\u21a9\ufe0f', s.open_returns || 0, 'Open Returns', '#/returns') +
      '</div>'

    // Additional row
    html += '<div class="stats-row">' +
      this._statCard('\ud83d\udcca', s.orders_paid || 0, 'Total Orders', '#/orders') +
      this._statCard('\ud83d\udc65', s.customers || 0, 'Customers', '#/customers') +
      '</div>'

    // Revenue chart placeholder (loaded async)
    html += '<div id="revenue-chart-container"></div>'

    // Quick actions
    html += '<div class="section-label mt-md">Quick Actions</div>' +
      '<div class="quick-actions">'

    const pendingOrders = (s.orders_total || 0) - (s.orders_paid || 0)
    if (pendingOrders > 0) {
      html += this._quickAction('\ud83d\udce6', pendingOrders + ' pending order' + (pendingOrders !== 1 ? 's' : ''), '#/orders')
    }

    if (s.unread_messages > 0) {
      html += this._quickAction('\ud83d\udcac', s.unread_messages + ' unread message' + (s.unread_messages !== 1 ? 's' : ''), '#/messages')
    }

    if (s.open_returns > 0) {
      html += this._quickAction('\u21a9\ufe0f', s.open_returns + ' return request' + (s.open_returns !== 1 ? 's' : ''), '#/returns')
    }

    if (pendingOrders === 0 && (s.unread_messages || 0) === 0 && (s.open_returns || 0) === 0) {
      html += '<div class="empty-state" style="padding:20px 0">' +
        '<p class="text-hint">All caught up! No pending items.</p></div>'
    }

    html += '</div>'

    container.innerHTML = html

    // Load revenue chart async
    this._loadRevenueChart()
  },

  async _loadRevenueChart() {
    const chartContainer = document.getElementById('revenue-chart-container')
    if (!chartContainer) return

    try {
      const data = await this.api('/' + this.shopId + '/stats/revenue-daily?days=7')
      if (!data || data.length === 0) return

      const maxRevenue = Math.max(...data.map(d => d.revenue_sats), 1)
      const today = new Date().toISOString().substring(0, 10)
      const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

      let barsHtml = ''
      data.forEach(d => {
        const pct = Math.max((d.revenue_sats / maxRevenue) * 100, 3)
        const dayDate = new Date(d.date + 'T12:00:00')
        const dayLabel = dayNames[dayDate.getDay()]
        const isToday = d.date === today
        const valueLabel = d.revenue_sats > 0 ? this._compactSats(d.revenue_sats) : ''

        barsHtml += '<div class="chart-bar-col">' +
          '<div class="chart-bar-value">' + valueLabel + '</div>' +
          '<div class="chart-bar-wrap">' +
          '<div class="chart-bar' + (isToday ? ' today' : '') +
          '" style="height:' + pct + '%"></div>' +
          '</div>' +
          '<div class="chart-bar-label">' + dayLabel + '</div>' +
          '</div>'
      })

      chartContainer.innerHTML = '<div class="revenue-chart">' +
        '<div class="revenue-chart-title">Revenue (7 days)</div>' +
        '<div class="chart-bars">' + barsHtml + '</div>' +
        '</div>'
    } catch {
      // Silent fail for chart
    }
  },

  _compactSats(amount) {
    if (amount >= 1000000) return (amount / 1000000).toFixed(1) + 'M'
    if (amount >= 1000) return (amount / 1000).toFixed(1) + 'k'
    return String(amount)
  },

  _statCard(icon, value, label, href) {
    const clickAttr = href
      ? ' style="cursor:pointer" onclick="Admin.haptic(\'selection\');Admin.navigate(\'' + href + '\')"'
      : ''
    return '<div class="stat-card"' + clickAttr + '>' +
      '<div class="stat-icon">' + icon + '</div>' +
      '<div class="stat-value">' + value + '</div>' +
      '<div class="stat-label">' + label + '</div>' +
      '</div>'
  },

  _quickAction(icon, text, href) {
    return '<div class="quick-action" onclick="Admin.haptic(\'selection\');Admin.navigate(\'' + href + '\')">' +
      '<div class="quick-action-left">' +
      '<div class="quick-action-icon">' + icon + '</div>' +
      '<div class="quick-action-text">' + this.escapeHtml(text) + '</div>' +
      '</div>' +
      '<div class="quick-action-arrow">\u203a</div>' +
      '</div>'
  },

  // ===== Render: Orders =====
  async renderOrders() {
    const container = document.getElementById('orders-content')

    // On first load, show full spinner. On search re-renders, only update the list.
    const isRerender = !!container.querySelector('#order-search')
    if (!isRerender) {
      container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'
    }

    try {
      let apiPath = '/' + this.shopId + '/orders'
      const params = []
      if (this._searchQuery) {
        params.push('q=' + encodeURIComponent(this._searchQuery))
      } else if (this.orderFilter !== 'all') {
        params.push('status=' + this.orderFilter)
      }
      if (params.length) apiPath += '?' + params.join('&')

      const orders = await this.api(apiPath)
      this.orders = orders

      // If re-rendering from search, only update the list below the controls
      if (isRerender) {
        this._renderOrderList(orders)
        return
      }

      let html = '<h2 class="section-title">Orders</h2>'

      // Search bar
      html += '<div class="search-bar">' +
        '<span class="search-icon">\ud83d\udd0d</span>' +
        '<input type="text" class="form-input" id="order-search" ' +
        'placeholder="Search by ID, @username, email\u2026" ' +
        'value="' + this.escapeHtml(this._searchQuery) + '" ' +
        'oninput="Admin._onSearchInput(this.value)" autocomplete="off">' +
        '<button class="search-clear" id="search-clear-btn" ' +
        'onclick="Admin._clearSearch()" style="' +
        (this._searchQuery ? '' : 'display:none') + '">\u2715</button>' +
        '</div>'

      // Filter chips (hidden during search)
      html += '<div class="filter-chips" id="order-filter-chips" style="' +
        (this._searchQuery ? 'display:none' : '') + '">'
      const filters = [
        { key: 'all', label: 'All' },
        { key: 'paid', label: 'Paid' },
        { key: 'pending', label: 'Pending' },
        { key: 'expired', label: 'Expired' },
      ]
      filters.forEach(f => {
        html += '<div class="chip ' + (this.orderFilter === f.key ? 'active' : '') +
          '" onclick="Admin.filterOrders(\'' + f.key + '\')">' + f.label + '</div>'
      })
      html += '</div>'

      // Order list container (re-rendered independently on search)
      html += '<div id="order-list"></div>'

      container.innerHTML = html
      this._renderOrderList(orders)
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load orders</p>' +
        '<button class="btn-text mt-md" onclick="Admin.renderOrders()">Try again</button></div>'
    }
  },

  _renderOrderList(orders) {
    const listEl = document.getElementById('order-list')
    if (!listEl) return

    if (orders.length === 0) {
      listEl.innerHTML = '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\udce6</div>' +
        '<h3>' + (this._searchQuery ? 'No results' : 'No orders') + '</h3>' +
        '<p class="text-hint">' + (this._searchQuery
          ? 'Try a different search term'
          : 'Orders will appear here when customers purchase') + '</p></div>'
      return
    }

    let html = ''
    orders.forEach(order => {
      html += this._renderOrderCard(order)
    })
    listEl.innerHTML = html
  },

  _effectiveStatus(order) {
    if (order.status === 'pending') {
      const ts = parseInt(order.timestamp, 10) || (new Date(order.timestamp).getTime() / 1000)
      if (Date.now() / 1000 - ts > INVOICE_EXPIRY_SECONDS) return 'expired'
    }
    return order.status
  },

  _renderOrderCard(order) {
    const fulfillmentLabels = {
      preparing: '\ud83d\udccb Preparing',
      shipping: '\ud83d\ude9a Shipping',
      delivered: '\u2705 Delivered'
    }

    const displayStatus = this._effectiveStatus(order)

    let items = []
    try { items = JSON.parse(order.cart_json) } catch (e) { console.warn('Failed to parse cart JSON:', e) }
    const itemsSummary = items.map(i => i.quantity + '\u00d7 ' + i.title).join(', ')
    const customer = order.telegram_username
      ? '@' + order.telegram_username
      : 'Chat #' + order.telegram_chat_id

    let html = '<div class="order-card" onclick="Admin.navigate(\'#/order/' + order.id + '\')">' +
      '<div class="order-header">' +
      '<span class="order-id">#' + order.id.substring(0, 8) + '</span>' +
      '<span class="status-badge ' + displayStatus + '">' + displayStatus + '</span>' +
      '</div>' +
      '<div class="order-customer">' + this._emojiAvatarHtml(order.telegram_chat_id, order.telegram_username) + '</div>' +
      '<div class="order-items-summary">' + this.escapeHtml(itemsSummary) + '</div>' +
      '<div class="order-footer">' +
      '<span class="order-amount">' + this.formatSats(order.amount_sats) + '</span>' +
      '<span class="order-date">' + this.formatDate(order.timestamp) + '</span>' +
      '</div>'

    if (order.fulfillment_status) {
      html += '<div class="order-badges">' +
        '<span class="fulfillment-badge ' + order.fulfillment_status + '">' +
        (fulfillmentLabels[order.fulfillment_status] || order.fulfillment_status) +
        '</span></div>'
    }

    html += '<div class="order-card-arrow">\u203a</div></div>'
    return html
  },

  _onSearchInput(value) {
    if (this._searchTimer) clearTimeout(this._searchTimer)
    // Toggle clear button and filter chips immediately
    const clearBtn = document.getElementById('search-clear-btn')
    const chips = document.getElementById('order-filter-chips')
    if (clearBtn) clearBtn.style.display = value.trim() ? '' : 'none'
    if (chips) chips.style.display = value.trim() ? 'none' : ''

    this._searchTimer = setTimeout(() => {
      this._searchQuery = value.trim()
      this.renderOrders()
    }, 350)
  },

  _clearSearch() {
    this._searchQuery = ''
    const input = document.getElementById('order-search')
    if (input) { input.value = ''; input.focus() }
    const clearBtn = document.getElementById('search-clear-btn')
    if (clearBtn) clearBtn.style.display = 'none'
    const chips = document.getElementById('order-filter-chips')
    if (chips) chips.style.display = ''
    this.renderOrders()
    requestAnimationFrame(() => {
      const el = document.getElementById('order-search')
      if (el) el.focus()
    })
  },

  filterOrders(status) {
    this.orderFilter = status
    this._searchQuery = ''
    this.haptic('selection')
    this.renderOrders()
  },

  // ===== Render: Order Detail =====
  async renderOrderDetail(orderId) {
    const container = document.getElementById('order-detail-content')
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const order = await this.api('/' + this.shopId + '/orders/' + orderId)

      let items = []
      try { items = JSON.parse(order.cart_json) } catch (e) { console.warn('Failed to parse cart JSON:', e) }

      const displayStatus = this._effectiveStatus(order)

      let html = '<div class="order-detail">' +
        '<button class="back-link" onclick="Admin.navigate(\'#/orders\')">\u2190 Back to orders</button>' +
        '<div class="order-detail-header">' +
        '<h2>Order #' + order.id.substring(0, 8) + '</h2>' +
        '<span class="status-badge ' + displayStatus + '">' + displayStatus + '</span>' +
        '</div>'

      // Customer info
      html += '<div class="section-label">Customer</div>' +
        '<div class="buyer-info">' +
        '<div class="buyer-row">' + this._emojiAvatarHtml(order.telegram_chat_id, order.telegram_username) + '</div>'
      if (order.buyer_email) {
        html += '<div class="buyer-row">\ud83d\udce7 ' + this.escapeHtml(order.buyer_email) + '</div>'
      }
      if (order.buyer_name) {
        html += '<div class="buyer-row">\ud83d\udcdd ' + this.escapeHtml(order.buyer_name) + '</div>'
      }
      if (order.buyer_address) {
        html += '<div class="buyer-row">\ud83d\udccd ' + this.escapeHtml(order.buyer_address).replace(/\n/g, '<br>') + '</div>'
      }
      html += '</div>'

      // Fulfillment stepper (only for paid orders with tracking enabled)
      if (displayStatus === 'paid' && this.enableOrderTracking) {
        html += '<div class="section-label">Fulfillment</div>'
        html += this._renderFulfillmentStepper(order)
      }

      // Items
      html += '<div class="section-label mt-md">Items</div>' +
        '<div class="order-items-list">'
      items.forEach(item => {
        let itemDetail = item.quantity + '\u00d7 ' + this.escapeHtml(item.title)
        if (item.sku) itemDetail += ' <span class="text-hint">[' + this.escapeHtml(item.sku) + ']</span>'
        html += '<div class="order-item-row">' +
          '<span>' + itemDetail + '</span>' +
          '<span>' + this.formatPrice(item.price * item.quantity) + '</span>' +
          '</div>'
      })
      html += '</div>'

      // Summary
      html += '<div class="cart-summary">' +
        '<div class="summary-row total">' +
        '<span>Total</span>' +
        '<span>' + this.formatSats(order.amount_sats) + '</span>' +
        '</div>'
      if (order.credit_used > 0) {
        html += '<div class="summary-row">' +
          '<span>Credit applied</span>' +
          '<span>' + this.formatSats(order.credit_used) + '</span>' +
          '</div>'
      }
      html += '</div>'

      html += '<div class="order-date-full mt-md">Placed ' + this.formatDateAbsolute(order.timestamp) + '</div>'

      // Action: message customer
      const customerLabel = order.telegram_username
        ? '@' + this.escapeHtml(order.telegram_username)
        : 'customer'
      html += '<div class="mt-md">' +
        '<button class="btn-secondary" onclick="Admin.navigate(\'#/thread/' + order.telegram_chat_id + '\')">' +
        '\ud83d\udcac Message ' + customerLabel + '</button>' +
        '</div>'

      html += '</div>'

      container.innerHTML = html
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load order</p>' +
        '<button class="btn-text mt-md" onclick="Admin.navigate(\'#/orders\')">Back to orders</button></div>'
    }
  },

  _renderFulfillmentStepper(order) {
    const steps = ['preparing', 'shipping', 'delivered']
    const icons = ['\ud83d\udccb', '\ud83d\ude9a', '\u2705']
    const labels = ['Preparing', 'Shipping', 'Delivered']
    const currentIdx = steps.indexOf(order.fulfillment_status || '')

    let html = '<div class="fulfillment-stepper">' +
      '<div class="fulfillment-steps">'

    steps.forEach((step, i) => {
      let state = 'pending'
      if (i < currentIdx) state = 'done'
      else if (i === currentIdx) state = 'current done'

      html += '<div class="fulfillment-step ' + state + '" onclick="Admin.setFulfillment(\'' +
        order.id + '\', \'' + step + '\')">' +
        '<div class="step-icon">' + icons[i] + '</div>' +
        '<div class="step-label">' + labels[i] + '</div>' +
        '</div>'
      if (i < steps.length - 1) {
        html += '<div class="step-line ' + (i < currentIdx ? 'done' : 'pending') + '"></div>'
      }
    })

    html += '</div>'

    if (order.fulfillment_note) {
      html += '<p class="text-hint" style="text-align:center;margin-top:8px;font-size:13px">' +
        '\ud83d\udcdd ' + this.escapeHtml(order.fulfillment_note) + '</p>'
    }

    // Note input
    html += '<div class="fulfillment-note-input">' +
      '<input type="text" class="form-input" id="fulfillment-note-' + order.id + '" ' +
      'placeholder="Add a note (optional)" value="' + this.escapeHtml(order.fulfillment_note || '') + '">' +
      '</div>'

    html += '</div>'
    return html
  },

  async setFulfillment(orderId, status) {
    this.haptic('selection')
    const noteInput = document.getElementById('fulfillment-note-' + orderId)
    const note = noteInput ? noteInput.value.trim() : null

    const labels = { preparing: 'Preparing', shipping: 'Shipping', delivered: 'Delivered' }
    if (!confirm('Set fulfillment to "' + (labels[status] || status) + '"?\nThe customer will be notified.')) {
      return
    }

    try {
      await this.api('/' + this.shopId + '/orders/' + orderId + '/fulfillment', {
        method: 'PUT',
        body: { status, note: note || null },
      })
      this.haptic('notification', 'success')
      this.showToast('Fulfillment updated')
      this.renderOrderDetail(orderId)
      this.loadStats()
    } catch (e) {
      this.showToast('Could not update order status. Please try again.')
    }
  },

  // ===== Render: Messages (Conversations) =====
  async renderMessages() {
    const container = document.getElementById('messages-content')
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const conversations = await this.api('/' + this.shopId + '/conversations')
      this.conversations = conversations

      let html = '<h2 class="section-title">Messages</h2>'

      if (conversations.length === 0) {
        html += '<div class="empty-state">' +
          '<div class="empty-icon">\ud83d\udcac</div>' +
          '<h3>No messages</h3>' +
          '<p class="text-hint">Customer messages will appear here</p></div>'
        container.innerHTML = html
        return
      }

      conversations.forEach(conv => {
        const username = conv.username || ('Chat #' + conv.chat_id)
        const initial = (conv.username || String(conv.chat_id))[0]
        const threadRoute = conv.order_id
          ? '#/thread/' + conv.chat_id + '/' + conv.order_id
          : '#/thread/' + conv.chat_id

        // Preview text
        let preview = conv.last_content || ''
        if (preview.length > 50) preview = preview.substring(0, 50) + '\u2026'
        const previewPrefix = conv.last_direction === 'out'
          ? '<span class="preview-you">You: </span>'
          : ''

        const hasUnread = conv.unread_count > 0
        html += '<div class="conversation-card" onclick="Admin.haptic(\'selection\');Admin.navigate(\'' + threadRoute + '\')">' +
          this._avatarHtml(conv.chat_id, initial, 'conversation-avatar') +
          '<div class="conversation-info"' + (hasUnread ? ' style="padding-right:36px"' : '') + '>' +
          '<div class="conversation-top">' +
          '<div class="conversation-username">' + this.escapeHtml(username) + '</div>' +
          '<div class="conversation-time">' + this.formatDate(conv.last_timestamp) + '</div>' +
          '</div>' +
          '<div class="conversation-preview">' + previewPrefix + this.escapeHtml(preview) + '</div>' +
          (conv.order_id ? '<div class="conversation-order">\ud83d\udce6 #' + conv.order_id.substring(0, 8) + '</div>' : '') +
          '</div>'

        if (conv.unread_count > 0) {
          html += '<div class="unread-dot">' + conv.unread_count + '</div>'
        }

        html += '</div>'
      })

      container.innerHTML = html
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load messages</p>' +
        '<button class="btn-text mt-md" onclick="Admin.renderMessages()">Try again</button></div>'
    }
  },

  // ===== Render: Thread =====
  async renderThread(chatId, orderId) {
    const container = document.getElementById('thread-content')
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    chatId = parseInt(chatId)
    if (isNaN(chatId)) {
      container.innerHTML = '<div class="empty-state"><h3>Invalid thread</h3></div>'
      return
    }

    try {
      let path = '/' + this.shopId + '/messages/thread?chat_id=' + chatId
      if (orderId) path += '&order_id=' + orderId
      const messages = await this.api(path)

      // Find username from first message or conversations
      let username = null
      for (const m of messages) {
        if (m.username && m.direction === 'in') { username = m.username; break }
      }
      if (!username) {
        const conv = this.conversations.find(c =>
          c.chat_id === chatId && (orderId ? c.order_id === orderId : !c.order_id)
        )
        if (conv) username = conv.username
      }
      const displayName = username ? '@' + username : 'Chat #' + chatId
      const initial = (username || String(chatId))[0]

      let html = '<button class="back-link" onclick="Admin.navigate(\'#/messages\')">\u2190 Back to messages</button>'

      // Thread header
      html += '<div class="thread-header">' +
        this._avatarHtml(chatId, initial, 'thread-header-avatar') +
        '<div class="thread-header-info">' +
        '<div class="thread-header-name">' +
        this._usernameHtml(username, chatId) +
        '</div>' +
        (orderId ? '<div class="thread-header-order">\ud83d\udce6 Order #' + orderId.substring(0, 8) + '</div>' : '') +
        '</div></div>'

      html += '<div class="message-thread" id="message-thread">'
      html += this._renderBubbles(messages)
      html += '</div>'

      // Reply form
      html += '<form class="message-form" onsubmit="Admin.handleSendReply(event, ' + chatId + ', ' +
        (orderId ? '\'' + orderId + '\'' : 'null') + ')">' +
        '<input type="text" class="form-input message-input" id="reply-input" ' +
        'placeholder="Reply\u2026" required autocomplete="off" maxlength="1000">' +
        '<button type="submit" class="btn-send">\u2191</button>' +
        '</form>'

      container.innerHTML = html

      // Scroll to bottom
      const thread = document.getElementById('message-thread')
      if (thread) thread.scrollTop = thread.scrollHeight

      // Start polling
      this._startThreadPoll(chatId, orderId)

      // Refresh badges (messages just got marked as read)
      this.loadStats()
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load thread</p>' +
        '<button class="btn-text mt-md" onclick="Admin.navigate(\'#/messages\')">Back to messages</button></div>'
    }
  },

  _renderBubbles(messages) {
    if (messages.length === 0) {
      return '<div class="empty-state" style="padding:24px 0">' +
        '<div class="empty-icon">\ud83d\udcac</div>' +
        '<p class="text-hint">No messages in this thread</p></div>'
    }
    let html = ''
    messages.forEach(msg => {
      const isAdmin = msg.direction === 'out'
      html += '<div class="message-bubble ' + (isAdmin ? 'msg-admin' : 'msg-customer') + '">' +
        (msg.order_id ? '<div class="message-order">\ud83d\udce6 #' + msg.order_id.substring(0, 8) + '</div>' : '') +
        '<div class="message-text">' + this._formatMessageText(msg.content) + '</div>' +
        '<div class="message-time">' + this.formatDate(msg.timestamp) + '</div>' +
        '</div>'
    })
    return html
  },

  _renderThreadMessages(messages, chatId, orderId) {
    const thread = document.getElementById('message-thread')
    if (!thread) return
    const wasAtBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 50
    thread.innerHTML = this._renderBubbles(messages)
    if (wasAtBottom) thread.scrollTop = thread.scrollHeight
  },

  _formatMessageText(text) {
    if (!text) return ''
    return this.escapeHtml(text).replace(/\n/g, '<br>')
  },

  async handleSendReply(e, chatId, orderId) {
    e.preventDefault()
    const input = document.getElementById('reply-input')
    const sendBtn = e.target.querySelector('.btn-send')
    const content = input.value.trim()
    if (!content) return

    input.disabled = true
    let originalBtnContent = ''
    if (sendBtn) {
      sendBtn.disabled = true
      originalBtnContent = sendBtn.innerHTML
      sendBtn.innerHTML = '<div class="spinner" style="width:16px;height:16px"></div>'
    }
    try {
      await this.api('/' + this.shopId + '/messages', {
        method: 'POST',
        body: { chat_id: chatId, content, order_id: orderId },
      })
      input.value = ''
      input.disabled = false
      if (sendBtn) { sendBtn.disabled = false; sendBtn.innerHTML = originalBtnContent }
      this.haptic('impact', 'light')
      this.renderThread(chatId, orderId)
    } catch (e) {
      input.disabled = false
      if (sendBtn) { sendBtn.disabled = false; sendBtn.innerHTML = originalBtnContent }
      this.showToast('Message could not be sent. Please try again.')
    }
  },

  // ===== Render: Returns =====
  async renderReturns() {
    const container = document.getElementById('returns-content')

    if (!this.allowReturns) {
      container.innerHTML = '<h2 class="section-title">Returns</h2>' +
        '<div class="empty-state">' +
        '<div class="empty-icon">\u21a9\ufe0f</div>' +
        '<h3>Returns disabled</h3>' +
        '<p class="text-hint">Returns are turned off in shop settings</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const statusParam = this.returnFilter !== 'all' ? '?status=' + this.returnFilter : ''
      const returns = await this.api('/' + this.shopId + '/returns' + statusParam)

      let html = '<h2 class="section-title">Returns</h2>'

      // Filter chips
      const filters = [
        { key: 'all', label: 'All' },
        { key: 'requested', label: 'Requested' },
        { key: 'approved', label: 'Approved' },
        { key: 'refunded', label: 'Refunded' },
        { key: 'denied', label: 'Denied' },
      ]
      html += '<div class="filter-chips">'
      filters.forEach(f => {
        html += '<div class="chip ' + (this.returnFilter === f.key ? 'active' : '') +
          '" onclick="Admin.filterReturns(\'' + f.key + '\')">' + f.label + '</div>'
      })
      html += '</div>'

      if (returns.length === 0) {
        html += '<div class="empty-state">' +
          '<div class="empty-icon">\u21a9\ufe0f</div>' +
          '<h3>No returns</h3>' +
          '<p class="text-hint">Return requests will appear here</p></div>'
        container.innerHTML = html
        return
      }

      returns.forEach(ret => {
        const customer = ret.telegram_username
          ? '@' + ret.telegram_username
          : 'Chat #' + ret.chat_id

        let reason = ret.reason || ''
        if (reason.length > 60) reason = reason.substring(0, 60) + '\u2026'

        html += '<div class="return-card" onclick="Admin.navigate(\'#/return/' + ret.id + '\')">' +
          '<div class="return-header">' +
          '<span class="order-id">\ud83d\udce6 #' + ret.order_id.substring(0, 8) + '</span>' +
          '<span class="return-badge ' + ret.status + '">' + ret.status + '</span>' +
          '</div>' +
          '<div class="return-customer">' + this._emojiAvatarHtml(ret.chat_id, ret.telegram_username) + '</div>' +
          (reason ? '<div class="return-reason">' + this.escapeHtml(reason) + '</div>' : '') +
          '<div class="return-footer">' +
          '<span class="order-amount">' + this.formatSats(ret.refund_amount_sats) + '</span>' +
          '<span class="order-date">' + this.formatDate(ret.timestamp) + '</span>' +
          '</div>' +
          '<div class="return-card-arrow">\u203a</div>' +
          '</div>'
      })

      container.innerHTML = html
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load returns</p>' +
        '<button class="btn-text mt-md" onclick="Admin.renderReturns()">Try again</button></div>'
    }
  },

  filterReturns(status) {
    this.returnFilter = status
    this.haptic('selection')
    this.renderReturns()
  },

  // ===== Render: Return Detail =====
  _selectedRefundMethod: 'credit',

  async renderReturnDetail(returnId) {
    const container = document.getElementById('return-detail-content')
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const ret = await this.api('/' + this.shopId + '/returns/' + returnId)

      const customer = ret.telegram_username
        ? '@' + ret.telegram_username
        : 'Chat #' + ret.chat_id

      let returnItems = []
      try { returnItems = JSON.parse(ret.items_json) } catch (e) { console.warn('Failed to parse items JSON:', e) }

      let html = '<div class="return-detail">' +
        '<button class="back-link" onclick="Admin.navigate(\'#/returns\')">\u2190 Back to returns</button>' +
        '<div class="return-detail-header">' +
        '<h2>Return Request</h2>' +
        '<span class="return-badge ' + ret.status + '">' + ret.status + '</span>' +
        '</div>'

      // Linked order
      html += '<div class="section-label">Order</div>' +
        '<div class="buyer-info">' +
        '<div class="buyer-row">' +
        '<a onclick="Admin.haptic(\'selection\');Admin.navigate(\'#/order/' + ret.order_id + '\')" style="cursor:pointer">' +
        '\ud83d\udce6 #' + ret.order_id.substring(0, 8) + '</a>' +
        '</div>' +
        '<div class="buyer-row">' + this._emojiAvatarHtml(ret.chat_id, ret.telegram_username) + '</div>' +
        '</div>'

      // Reason
      if (ret.reason) {
        html += '<div class="section-label">Reason</div>' +
          '<div class="return-reason-full">' + this.escapeHtml(ret.reason) + '</div>'
      }

      // Return items
      if (returnItems.length > 0) {
        html += '<div class="section-label">Items</div>' +
          '<div class="order-items-list">'
        returnItems.forEach(item => {
          html += '<div class="order-item-row">' +
            '<span>' + (item.quantity || 1) + '\u00d7 ' + this.escapeHtml(item.title || item.product_id || 'Item') + '</span>' +
            '</div>'
        })
        html += '</div>'
      }

      // Refund amount
      html += '<div class="cart-summary">' +
        '<div class="summary-row total">' +
        '<span>Refund Amount</span>' +
        '<span>' + this.formatSats(ret.refund_amount_sats) + '</span>' +
        '</div></div>'

      // Admin note (if denied)
      if (ret.admin_note) {
        html += '<div class="section-label mt-md">Admin Note</div>' +
          '<div class="admin-note">' + this.escapeHtml(ret.admin_note) + '</div>'
      }

      html += '<div class="order-date-full mt-md">Requested ' + this.formatDateAbsolute(ret.timestamp) + '</div>'

      // Actions (only for "requested" status)
      if (ret.status === 'requested') {
        html += this._renderReturnActions(ret)
      }

      html += '</div>'

      container.innerHTML = html
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load return</p>' +
        '<button class="btn-text mt-md" onclick="Admin.navigate(\'#/returns\')">Back to returns</button></div>'
    }
  },

  _renderReturnActions(ret) {
    let html = '<div class="section-label mt-md">Action</div>'

    // Refund method selector
    html += '<div class="form-group">' +
      '<label class="form-label">Refund Method</label>' +
      '<div class="refund-method-chips">' +
      '<div class="refund-chip ' + (this._selectedRefundMethod === 'credit' ? 'active' : '') +
      '" data-method="credit" onclick="Admin._selectRefundMethod(\'credit\')">' +
      '\ud83d\udcb3 Store Credit</div>' +
      '<div class="refund-chip ' + (this._selectedRefundMethod === 'lightning' ? 'active' : '') +
      '" data-method="lightning" onclick="Admin._selectRefundMethod(\'lightning\')">' +
      '\u26a1 Lightning</div>' +
      '</div></div>'

    // Refund amount input
    html += '<div class="form-group">' +
      '<label class="form-label">Refund Amount (sats)</label>' +
      '<input type="number" class="form-input" id="refund-amount" ' +
      'value="' + ret.refund_amount_sats + '" min="1" max="' + ret.refund_amount_sats + '">' +
      '</div>'

    // Approve button
    html += '<button class="btn-approve" onclick="Admin.approveReturn(\'' + ret.id + '\')">' +
      'Approve Return</button>'

    // Deny section
    html += '<div class="form-group mt-md">' +
      '<label class="form-label">Or deny with a note</label>' +
      '<textarea class="form-input form-textarea" id="deny-note" ' +
      'placeholder="Explain why the return is denied\u2026"></textarea>' +
      '</div>' +
      '<button class="btn-deny" onclick="Admin.denyReturn(\'' + ret.id + '\')">' +
      'Deny Return</button>'

    return html
  },

  _selectRefundMethod(method) {
    this._selectedRefundMethod = method
    document.querySelectorAll('.refund-chip').forEach(c => {
      c.classList.toggle('active', c.dataset.method === method)
    })
    this.haptic('selection')
  },

  async approveReturn(returnId) {
    const amountInput = document.getElementById('refund-amount')
    const amount = amountInput ? parseInt(amountInput.value) : null

    if (!amount || amount <= 0) {
      this.showToast('Invalid refund amount')
      return
    }

    const methodLabel = this._selectedRefundMethod === 'credit' ? 'store credit' : 'Lightning'
    if (!confirm('Approve refund of ' + amount.toLocaleString() + ' sats via ' + methodLabel + '?')) {
      return
    }

    try {
      await this.api('/' + this.shopId + '/returns/' + returnId + '/approve', {
        method: 'PUT',
        body: {
          refund_method: this._selectedRefundMethod,
          refund_amount_sats: amount,
        },
      })
      this.haptic('notification', 'success')
      this.showToast('Return approved')
      this.renderReturnDetail(returnId)
      this.loadStats()
    } catch (e) {
      this.showToast('Could not approve return. Please try again.')
    }
  },

  async denyReturn(returnId) {
    const noteInput = document.getElementById('deny-note')
    const note = noteInput ? noteInput.value.trim() : ''

    if (!note) {
      this.showToast('Please add a note explaining the denial')
      return
    }

    if (!confirm('Deny this return request?')) {
      return
    }

    try {
      await this.api('/' + this.shopId + '/returns/' + returnId + '/deny', {
        method: 'PUT',
        body: { admin_note: note },
      })
      this.haptic('notification', 'success')
      this.showToast('Return denied')
      this.renderReturnDetail(returnId)
      this.loadStats()
    } catch (e) {
      this.showToast('Could not process denial. Please try again.')
    }
  },

  // ===== Render: Customers List =====
  _customerSearchQuery: '',
  _customerSearchTimer: null,

  async renderCustomers() {
    const container = document.getElementById('customers-content')
    const isRerender = !!container.querySelector('#customer-search')
    if (!isRerender) {
      container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'
    }

    try {
      let apiPath = '/' + this.shopId + '/customers'
      if (this._customerSearchQuery) {
        apiPath += '?q=' + encodeURIComponent(this._customerSearchQuery)
      }

      const customers = await this.api(apiPath)

      if (isRerender) {
        this._renderCustomerList(customers)
        return
      }

      let html = '<button class="back-link" onclick="window.history.back()">\u2190 Back</button>' +
        '<h2 class="section-title">Customers</h2>'

      // Search bar
      html += '<div class="search-bar">' +
        '<span class="search-icon">\ud83d\udd0d</span>' +
        '<input type="text" class="form-input" id="customer-search" ' +
        'placeholder="Search by @username or name\u2026" ' +
        'value="' + this.escapeHtml(this._customerSearchQuery) + '" ' +
        'oninput="Admin._onCustomerSearchInput(this.value)" autocomplete="off">' +
        '<button class="search-clear" id="customer-search-clear-btn" ' +
        'onclick="Admin._clearCustomerSearch()" style="' +
        (this._customerSearchQuery ? '' : 'display:none') + '">\u2715</button>' +
        '</div>'

      html += '<div id="customer-list"></div>'
      container.innerHTML = html
      this._renderCustomerList(customers)
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load customers</p>' +
        '<button class="btn-text mt-md" onclick="Admin.renderCustomers()">Try again</button></div>'
    }
  },

  _renderCustomerList(customers) {
    const listEl = document.getElementById('customer-list')
    if (!listEl) return

    if (customers.length === 0) {
      listEl.innerHTML = '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\udc65</div>' +
        '<h3>' + (this._customerSearchQuery ? 'No results' : 'No customers yet') + '</h3>' +
        '<p class="text-hint">' + (this._customerSearchQuery
          ? 'Try a different search term'
          : 'Customers will appear here when they interact with your shop') + '</p></div>'
      return
    }

    let html = ''
    customers.forEach(c => {
      const name = c.first_name || c.username || 'User'
      const initial = (name[0] || '?').toUpperCase()
      const displayName = c.first_name || (c.username ? '@' + c.username : 'User ' + c.chat_id)
      const subtitle = c.username && c.first_name ? '@' + c.username : ''
      const lastActive = c.last_active ? this.formatDate(c.last_active) : ''
      const orderCount = c.order_count || 0
      const totalSpent = c.total_spent_sats || 0

      html += '<div class="customer-list-card" onclick="Admin.haptic(\'selection\');Admin.navigate(\'#/customer/' + c.chat_id + '\')">' +
        this._avatarHtml(c.chat_id, initial, 'customer-list-avatar') +
        '<div class="customer-list-info">' +
        '<div class="customer-list-name">' + this.escapeHtml(displayName) + '</div>' +
        (subtitle ? '<div class="customer-list-username">' + this.escapeHtml(subtitle) + '</div>' : '') +
        (lastActive ? '<div class="customer-list-hint">Last active ' + lastActive + '</div>' : '') +
        '</div>' +
        '<div class="customer-list-stats">' +
        '<div class="customer-list-stat-value">' + orderCount + '</div>' +
        '<div class="customer-list-stat-label">orders</div>' +
        (totalSpent > 0 ? '<div class="customer-list-stat-sats">' + this._compactSats(totalSpent) + ' sats</div>' : '') +
        '</div>' +
        '<div class="order-card-arrow">\u203a</div>' +
        '</div>'
    })
    listEl.innerHTML = html
  },

  _onCustomerSearchInput(value) {
    if (this._customerSearchTimer) clearTimeout(this._customerSearchTimer)
    const clearBtn = document.getElementById('customer-search-clear-btn')
    if (clearBtn) clearBtn.style.display = value.trim() ? '' : 'none'

    this._customerSearchTimer = setTimeout(() => {
      this._customerSearchQuery = value.trim()
      this.renderCustomers()
    }, 350)
  },

  _clearCustomerSearch() {
    this._customerSearchQuery = ''
    const input = document.getElementById('customer-search')
    if (input) { input.value = ''; input.focus() }
    const clearBtn = document.getElementById('customer-search-clear-btn')
    if (clearBtn) clearBtn.style.display = 'none'
    this.renderCustomers()
    requestAnimationFrame(() => {
      const el = document.getElementById('customer-search')
      if (el) el.focus()
    })
  },

  // ===== Render: Customer Profile =====
  async renderCustomerProfile(chatId) {
    const container = document.getElementById('customer-content')
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    chatId = parseInt(chatId)
    if (isNaN(chatId)) {
      container.innerHTML = '<div class="empty-state"><h3>Invalid customer</h3></div>'
      return
    }

    try {
      const profile = await this.api('/' + this.shopId + '/customers/' + chatId + '/profile')

      const displayName = profile.username ? '@' + profile.username : (profile.first_name || 'Chat #' + chatId)
      const initial = (profile.username || profile.first_name || String(chatId))[0]

      let html = '<div class="customer-profile">' +
        '<button class="back-link" onclick="window.history.back()">\u2190 Back</button>'

      // Profile header
      html += '<div class="profile-header">' +
        this._avatarHtml(chatId, initial, 'profile-avatar') +
        '<div class="profile-info">' +
        '<h2>' + this.escapeHtml(displayName) + '</h2>' +
        (profile.first_seen
          ? '<p>Customer since ' + this.formatDateAbsolute(profile.first_seen) + '</p>'
          : '') +
        '</div></div>'

      // Stats grid
      html += '<div class="profile-stats">' +
        '<div class="profile-stat">' +
        '<div class="profile-stat-value">' + profile.order_count + '</div>' +
        '<div class="profile-stat-label">Orders</div>' +
        '</div>' +
        '<div class="profile-stat">' +
        '<div class="profile-stat-value">' + this._compactSats(profile.total_spent_sats) + '</div>' +
        '<div class="profile-stat-label">Spent</div>' +
        '</div>' +
        '<div class="profile-stat">' +
        '<div class="profile-stat-value">' + this._compactSats(profile.credit_balance_sats) + '</div>' +
        '<div class="profile-stat-label">Credit</div>' +
        '</div>' +
        '</div>'

      // Additional stats row
      html += '<div class="stats-row mb-md">' +
        this._statCard('\ud83d\udcac', profile.message_count, 'Messages') +
        this._statCard('\u21a9\ufe0f', profile.return_count, 'Returns') +
        '</div>'

      // Quick actions
      html += '<div class="profile-actions">' +
        '<button class="btn-secondary" onclick="Admin.haptic(\'selection\');Admin.navigate(\'#/thread/' + chatId + '\')">' +
        '\ud83d\udcac Message</button>' +
        '</div>'

      // Recent orders
      if (profile.recent_orders && profile.recent_orders.length > 0) {
        html += '<div class="section-label mt-md">Recent Orders</div>'
        profile.recent_orders.forEach(order => {
          let items = []
          try { items = JSON.parse(order.cart_json) } catch (e) { console.warn('Failed to parse cart JSON:', e) }
          const itemsSummary = items.map(i => (i.quantity || 1) + '\u00d7 ' + (i.title || 'Item')).join(', ')

          html += '<div class="order-card" onclick="Admin.navigate(\'#/order/' + order.id + '\')">' +
            '<div class="order-header">' +
            '<span class="order-id">#' + order.id.substring(0, 8) + '</span>' +
            '<span class="status-badge ' + order.status + '">' + order.status + '</span>' +
            '</div>' +
            '<div class="order-items-summary">' + this.escapeHtml(itemsSummary) + '</div>' +
            '<div class="order-footer">' +
            '<span class="order-amount">' + this.formatSats(order.amount_sats) + '</span>' +
            '<span class="order-date">' + this.formatDate(order.timestamp) + '</span>' +
            '</div>' +
            '<div class="order-card-arrow">\u203a</div>' +
            '</div>'
        })
      } else {
        html += '<div class="empty-state" style="padding:20px 0">' +
          '<p class="text-hint">No orders yet</p></div>'
      }

      html += '</div>'

      container.innerHTML = html
    } catch (e) {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load customer profile</p>' +
        '<button class="btn-text mt-md" onclick="window.history.back()">Go back</button></div>'
    }
  },

  // ===== Avatar Helpers =====
  _avatarHtml(chatId, initial, sizeClass) {
    const url = this.baseUrl + '/' + this.shopId + '/avatar/' + chatId +
      '?t=' + encodeURIComponent(this.initData || '')
    return '<div class="' + sizeClass + ' avatar-with-photo">' +
      '<img src="' + url + '" alt="" class="avatar-photo" ' +
      'onload="this.style.opacity=1" onerror="this.remove()">' +
      '<span class="avatar-initial">' + this.escapeHtml(initial) + '</span>' +
      '</div>'
  },

  _emojiAvatarHtml(chatId, username) {
    const url = this.baseUrl + '/' + this.shopId + '/avatar/' + chatId +
      '?t=' + encodeURIComponent(this.initData || '')
    return '<span class="inline-avatar-wrap">' +
      '<img src="' + url + '" alt="" class="inline-avatar-photo" ' +
      'onload="this.style.opacity=1;this.nextElementSibling.style.display=\'none\'" ' +
      'onerror="this.style.display=\'none\'">' +
      '<span class="inline-avatar-emoji">\ud83d\udc64</span>' +
      '</span> ' + this._usernameHtml(username, chatId)
  },

  // ===== Username Link Helper =====
  _usernameHtml(username, chatId) {
    if (username) {
      return '<span class="username-link" onclick="event.stopPropagation();Admin.navigate(\'#/customer/' +
        chatId + '\')">@' + this.escapeHtml(username) + '</span>'
    }
    return '<span class="username-link" onclick="event.stopPropagation();Admin.navigate(\'#/customer/' +
      chatId + '\')">Chat #' + chatId + '</span>'
  },

  // ===== Helpers =====
  escapeHtml(str) {
    if (!str) return ''
    const div = document.createElement('div')
    div.textContent = str
    return div.innerHTML
  },

  formatDate(val) {
    if (!val) return ''
    let d
    if (/^\d{9,13}$/.test(String(val))) {
      const n = Number(val)
      d = new Date(n < 1e12 ? n * 1000 : n)
    } else {
      d = new Date(String(val).includes('T') || String(val).includes('Z') ? val : val + 'Z')
    }
    if (isNaN(d.getTime())) return ''
    const now = new Date()
    const diff = now - d
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return mins + 'm ago'
    const hours = Math.floor(mins / 60)
    if (hours < 24) return hours + 'h ago'
    const days = Math.floor(hours / 24)
    if (days < 7) return days + 'd ago'
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  },

  formatDateAbsolute(val) {
    if (!val) return ''
    let d
    if (/^\d{9,13}$/.test(String(val))) {
      const n = Number(val)
      d = new Date(n < 1e12 ? n * 1000 : n)
    } else {
      d = new Date(String(val).includes('T') || String(val).includes('Z') ? val : val + 'Z')
    }
    if (isNaN(d.getTime())) return ''
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  },

  formatSats(amount) {
    return amount.toLocaleString() + ' sats'
  },

  formatPrice(amount) {
    if (this.shopCurrency === 'sat') {
      return amount.toLocaleString() + ' sats'
    }
    return amount.toFixed(2) + ' ' + this.shopCurrency.toUpperCase()
  },

  showToast(message) {
    const existing = document.querySelector('.toast')
    if (existing) existing.remove()
    const toast = document.createElement('div')
    toast.className = 'toast'
    toast.textContent = message
    document.body.appendChild(toast)
    setTimeout(() => toast.remove(), 2000)
  },

  haptic(type, style) {
    const tg = window.Telegram && window.Telegram.WebApp
    if (!tg || !tg.HapticFeedback) return
    if (type === 'impact') {
      tg.HapticFeedback.impactOccurred(style || 'medium')
    } else if (type === 'notification') {
      tg.HapticFeedback.notificationOccurred(style || 'success')
    } else if (type === 'selection') {
      tg.HapticFeedback.selectionChanged()
    }
  },
}

// --- Boot ---
document.addEventListener('DOMContentLoaded', () => Admin.init())
