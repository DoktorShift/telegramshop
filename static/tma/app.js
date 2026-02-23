/* ===== TMA (Telegram Mini App) SPA ===== */

const TMA = {
  // --- State ---
  shopId: null,
  initData: null,
  chatId: null,
  username: null,
  botUsername: null,
  shopTitle: '',
  shopCurrency: 'sat',
  checkoutMode: 'none',
  allowReturns: false,
  welcomeText: '',
  products: [],
  cart: [],
  categories: [],
  activeCategory: 'all',
  searchQuery: '',
  authenticated: false,
  creditBalance: 0,
  creditEntries: [],
  currentScreen: 'home',

  // --- Base URL (derived from current page location) ---
  get baseUrl() {
    return window.location.origin + '/telegramshop/api/v1/tma'
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

    // BackButton: single handler, we swap the fn reference
    this._backHandler = () => window.history.back()
    if (tg && tg.BackButton) {
      tg.BackButton.onClick(this._backHandler)
    }
    // MainButton: single handler
    this._mainHandler = () => this.startCheckout()
    if (tg && tg.MainButton) {
      tg.MainButton.onClick(this._mainHandler)
    }

    window.addEventListener('hashchange', () => this.route())

    await this.authenticate()
    await this.loadProducts()
    await this.loadCart()

    // Deep link via startapp parameter (e.g. ?startapp=product_abc123)
    const startParam = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || ''
    if (startParam.startsWith('product_') && !window.location.hash) {
      window.location.hash = '#/product/' + startParam.slice(8)
    } else {
      this.route()
    }
  },

  _showDevBanner() {
    const banner = document.createElement('div')
    banner.style.cssText =
      'background:#fff3cd;color:#856404;padding:8px 16px;font-size:13px;'
      + 'text-align:center;border-bottom:1px solid #ffc107;position:sticky;top:0;z-index:999'
    banner.textContent =
      'Browser preview \u2014 products visible, cart/checkout requires Telegram'
    document.body.prepend(banner)
  },

  // --- API Client ---
  async api(path, options = {}) {
    const url = this.baseUrl + path
    const headers = options.headers || {}
    headers['Content-Type'] = 'application/json'
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
      return
    }
    try {
      const data = await this.api('/auth', {
        method: 'POST',
        body: { init_data: this.initData, shop_id: this.shopId },
      })
      this.chatId = data.chat_id
      this.username = data.username
      this.botUsername = data.bot_username || null
      this.shopTitle = data.shop_title
      this.shopCurrency = data.shop_currency
      this.checkoutMode = data.checkout_mode
      this.allowReturns = data.allow_returns
      this.welcomeText = data.welcome_text || ''
      this.authenticated = true
      this.loadCredits()
    } catch (e) {
      console.warn('Auth failed:', e)
      this.authenticated = false
    }
  },

  async loadCredits() {
    if (!this.authenticated) return
    try {
      const data = await this.api('/' + this.shopId + '/credits')
      this.creditBalance = data.balance_sats || 0
      this.creditEntries = data.credits || []
    } catch {
      this.creditBalance = 0
      this.creditEntries = []
    }
  },

  // --- Products ---
  async loadProducts() {
    const loading = document.getElementById('products-loading')
    try {
      this.products = await this.api('/' + this.shopId + '/products')
      const cats = new Set()
      this.products.forEach(p => { if (p.category) cats.add(p.category) })
      this.categories = Array.from(cats).sort()

      // Extract shop title from first product category or keep existing
      // (for unauthenticated users who can't call /auth)
    } catch (e) {
      this.products = []
      const container = document.getElementById('products-grid')
      if (container) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--hint-color)">' +
          '<p>Could not load products</p>' +
          '<button class="btn-secondary" onclick="TMA.loadProducts()">Retry</button></div>'
      }
    }
    if (loading) loading.style.display = 'none'
  },

  getFilteredProducts() {
    let list = this.products
    if (this.activeCategory !== 'all') {
      list = list.filter(p => p.category === this.activeCategory)
    }
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase()
      list = list.filter(p =>
        p.title.toLowerCase().includes(q) ||
        (p.description && p.description.toLowerCase().includes(q))
      )
    }
    return list
  },

  // --- Cart (persistent via API) ---
  async loadCart() {
    if (!this.authenticated) return
    try {
      const data = await this.api('/' + this.shopId + '/cart')
      this.cart = data.items || []
    } catch {
      this.cart = []
    }
    this.updateCartBadge()
  },

  async saveCart() {
    if (!this.authenticated) return
    try {
      await this.api('/' + this.shopId + '/cart', {
        method: 'PUT',
        body: { items: this.cart },
      })
    } catch (e) {
      console.error('Save cart failed:', e)
      this.showToast('Could not save cart')
    }
  },

  addToCart(productId) {
    if (!this.authenticated) {
      this.showToast('Open from Telegram to add items')
      return
    }
    const product = this.products.find(p => p.id === productId)
    if (!product) return
    if (product.inventory !== null && product.inventory <= 0) return

    const existing = this.cart.find(i => i.product_id === productId)
    if (existing) {
      if (product.inventory !== null && existing.quantity >= product.inventory) {
        this.showToast('Max stock reached')
        return
      }
      existing.quantity++
    } else {
      this.cart.push({
        product_id: product.id,
        title: product.title,
        quantity: 1,
        price: product.price,
        sku: product.sku,
      })
    }

    this.saveCart()
    this.updateCartBadge()
    this.haptic('impact', 'light')
    this.showToast('Added to cart')

    // Re-render product detail if we're on that screen
    if (this.currentScreen === 'product') {
      this.renderProductDetail(productId)
    }
  },

  updateQuantity(productId, delta) {
    const idx = this.cart.findIndex(i => i.product_id === productId)
    if (idx === -1) return

    const item = this.cart[idx]
    const newQty = item.quantity + delta

    if (newQty <= 0) {
      this.cart.splice(idx, 1)
    } else {
      const product = this.products.find(p => p.id === productId)
      if (product && product.inventory !== null && newQty > product.inventory) {
        this.showToast('Max stock reached')
        return
      }
      item.quantity = newQty
    }

    this.haptic('selection')
    this.saveCart()
    this.updateCartBadge()

    // Re-render whichever screen is active
    if (this.currentScreen === 'cart') {
      this.renderCart()
    } else if (this.currentScreen === 'product') {
      this.renderProductDetail(productId)
    }
  },

  clearCart() {
    if (this.cart.length === 0) return

    const doClear = () => {
      this.cart = []
      if (this.authenticated) {
        this.api('/' + this.shopId + '/cart', { method: 'DELETE' }).catch(() => {})
      }
      this.updateCartBadge()
      this.renderCart()
    }

    // Use native Telegram confirm if available
    const tg = window.Telegram && window.Telegram.WebApp
    if (tg && tg.showConfirm) {
      tg.showConfirm('Remove all items from your cart?', (confirmed) => {
        if (confirmed) doClear()
      })
    } else {
      if (confirm('Remove all items from your cart?')) doClear()
    }
  },

  cartTotal() {
    return this.cart.reduce((sum, i) => sum + i.price * i.quantity, 0)
  },

  cartItemCount() {
    return this.cart.reduce((sum, i) => sum + i.quantity, 0)
  },

  updateCartBadge() {
    const badge = document.getElementById('cart-badge')
    const count = this.cartItemCount()
    if (badge) {
      badge.textContent = count
      badge.style.display = count > 0 ? '' : 'none'
    }
  },

  // --- Price formatting ---
  formatPrice(amount) {
    if (this.shopCurrency === 'sat') {
      return amount.toLocaleString() + ' sats'
    }
    return amount.toFixed(2) + ' ' + this.shopCurrency.toUpperCase()
  },

  // --- Routing ---
  navigate(hash) {
    window.location.hash = hash
  },

  route() {
    const hash = window.location.hash || '#/'
    const parts = hash.split('/')
    const route = parts[1] || ''

    // Stop any active payment polling when navigating away
    this._stopPolling()

    // Scroll to top on screen change
    window.scrollTo(0, 0)

    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'))
    document.querySelectorAll('.tab-bar .tab').forEach(t => t.classList.remove('active'))

    const tg = window.Telegram && window.Telegram.WebApp

    // MainButton: hide unless cart screen re-shows it
    if (tg && tg.MainButton) {
      tg.MainButton.hide()
    }

    // Closing confirmation: enable during checkout/payment to prevent data loss
    const protectedScreens = ['checkout', 'payment']
    if (tg) {
      if (protectedScreens.includes(route)) {
        tg.enableClosingConfirmation()
      } else {
        tg.disableClosingConfirmation()
      }
    }

    // BackButton: show/hide based on tab vs detail screens
    const tabScreens = ['', 'cart', 'orders', 'messages']
    if (tg && tg.BackButton) {
      if (tabScreens.includes(route)) {
        tg.BackButton.hide()
      } else {
        tg.BackButton.show()
      }
    }

    switch (route) {
      case '':
        this.showScreen('home')
        this.renderHome()
        this.setActiveTab('home')
        break
      case 'product':
        this.showScreen('product')
        this.renderProductDetail(parts[2])
        break
      case 'cart':
        this.showScreen('cart')
        this.renderCart()
        this.setActiveTab('cart')
        this.updateMainButton()
        break
      case 'checkout':
        this.showScreen('checkout')
        this.renderCheckout()
        break
      case 'payment':
        this.showScreen('payment')
        // Restore payment screen if we have pending data
        if (this._pendingPayment) {
          this.showPaymentScreen(this._pendingPayment)
        } else {
          document.getElementById('payment-content').innerHTML =
            '<div class="empty-state">' +
            '<div class="empty-icon">\u26a1</div>' +
            '<p class="text-hint">No pending payment</p>' +
            '<button class="btn-secondary mt-md" onclick="TMA.navigate(\'#/orders\')">View Orders</button>' +
            '</div>'
        }
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
      case 'return':
        this.showScreen('return')
        this.renderReturn(parts[2])
        break
      case 'returns':
        this.showScreen('returns')
        this.renderReturns()
        break
      case 'credits':
        this.showScreen('credits')
        this.renderCredits()
        break
      case 'messages':
        this.showScreen('messages')
        this.renderMessages()
        this.setActiveTab('messages')
        break
      default:
        this.showScreen('home')
        this.renderHome()
        this.setActiveTab('home')
    }

    this.currentScreen = route || 'home'
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

  updateMainButton() {
    const tg = window.Telegram && window.Telegram.WebApp
    if (!tg || !tg.MainButton) return

    if (this.currentScreen === 'cart' && this.cart.length > 0) {
      const total = this.cartTotal()
      const afterCredit = Math.max(0, total - this.creditBalance)
      tg.MainButton.setText('Checkout \u2013 ' + this.formatPrice(afterCredit))
      tg.MainButton.show()
    } else {
      tg.MainButton.hide()
    }
  },

  // ===== Render: Home =====
  renderHome() {
    const banner = document.getElementById('welcome-banner')
    const titleEl = document.getElementById('shop-title')
    const textEl = document.getElementById('welcome-text')
    if (this.shopTitle) {
      titleEl.textContent = this.shopTitle
      textEl.textContent = this.welcomeText || 'Browse and pay with Lightning \u26a1'
      banner.style.display = ''
    }

    // Search bar
    const searchEl = document.getElementById('search-bar')
    if (searchEl) {
      searchEl.value = this.searchQuery
    }

    // Category chips
    const chipsEl = document.getElementById('category-chips')
    let chipsHtml = '<div class="chip ' + (this.activeCategory === 'all' ? 'active' : '') +
      '" onclick="TMA.filterCategory(\'all\')">All</div>'
    this.categories.forEach(cat => {
      const active = this.activeCategory === cat ? 'active' : ''
      chipsHtml += '<div class="chip ' + active +
        '" onclick="TMA.filterCategory(\'' + this.escapeHtml(cat) + '\')">' +
        this.escapeHtml(cat) + '</div>'
    })
    chipsEl.innerHTML = chipsHtml

    this.renderProductGrid()
  },

  filterCategory(cat) {
    this.activeCategory = cat
    this.haptic('selection')
    this.renderHome()
  },

  handleSearch(value) {
    this.searchQuery = value.trim()
    this.renderProductGrid()
  },

  renderProductGrid() {
    const grid = document.getElementById('product-grid')
    const products = this.getFilteredProducts()

    if (products.length === 0) {
      grid.innerHTML =
        '<div class="empty-state" style="grid-column:1/-1">' +
        '<div class="empty-icon">\ud83d\udd0d</div>' +
        '<h3>No products found</h3>' +
        '<p class="text-hint">Try a different category or search term</p>' +
        '</div>'
      return
    }

    let html = ''
    products.forEach(p => {
      const outOfStock = p.inventory !== null && p.inventory <= 0
      const imgUrl = (p.image_urls && p.image_urls.length > 0) ? p.image_urls[0] : p.image_url
      const imgHtml = imgUrl
        ? '<img class="product-img" src="' + this.escapeHtml(imgUrl) + '" alt="" loading="lazy">'
        : '<div class="product-img-placeholder">\ud83d\udce6</div>'

      // Image count badge for multi-image products
      const imgCount = (p.image_urls && p.image_urls.length > 1) ? p.image_urls.length : 0

      let badgeHtml = ''
      if (outOfStock) {
        badgeHtml = '<span class="product-badge sold-out">Sold out</span>'
      } else if (p.discount_percentage && p.discount_percentage > 0) {
        badgeHtml = '<span class="product-badge discount">-' + p.discount_percentage.toFixed(0) + '%</span>'
      }

      if (imgCount > 1 && !outOfStock) {
        badgeHtml += '<span class="product-badge img-count">' + imgCount + ' \ud83d\uddbc</span>'
      }

      let priceHtml = ''
      if (outOfStock) {
        priceHtml = '<div class="product-price sold-out-price">Sold out</div>'
      } else {
        if (p.discount_percentage && p.discount_percentage > 0) {
          const original = p.price / (1 - p.discount_percentage / 100)
          priceHtml = '<div class="product-price">' +
            '<span class="original-price">' + this.formatPrice(original) + '</span>' +
            this.formatPrice(p.price) + '</div>'
        } else {
          priceHtml = '<div class="product-price">' + this.formatPrice(p.price) + '</div>'
        }
        if (p.inventory !== null && p.inventory <= 5) {
          priceHtml += '<div class="product-stock low">' + p.inventory + ' left</div>'
        }
      }

      // Show "in cart" indicator on grid card
      const inCart = this.cart.find(i => i.product_id === p.id)
      const cartIndicator = inCart
        ? '<div class="product-cart-indicator">' + inCart.quantity + ' in cart</div>'
        : ''

      html += '<div class="product-card' + (outOfStock ? ' out-of-stock-card' : '') +
        '" onclick="TMA.navigate(\'#/product/' + p.id + '\')">' +
        '<div class="product-img-wrap">' + imgHtml + badgeHtml + '</div>' +
        '<div class="product-info">' +
        '<div class="product-title">' + this.escapeHtml(p.title) + '</div>' +
        priceHtml +
        cartIndicator +
        '</div></div>'
    })
    grid.innerHTML = html
  },

  // ===== Render: Product Detail =====
  renderProductDetail(productId) {
    const container = document.getElementById('product-detail')
    const product = this.products.find(p => p.id === productId)

    if (!product) {
      container.innerHTML = '<div class="empty-state"><h3>Product not found</h3></div>'
      return
    }

    const images = (product.image_urls && product.image_urls.length > 0)
      ? product.image_urls
      : (product.image_url ? [product.image_url] : [])

    let galleryHtml = ''
    if (images.length > 0) {
      let slidesHtml = ''
      images.forEach((url, i) => {
        slidesHtml += '<div class="gallery-slide">' +
          '<img src="' + this.escapeHtml(url) + '" alt="" onclick="TMA.openLightbox(' + i + ')">' +
          '</div>'
      })

      let dotsHtml = ''
      if (images.length > 1) {
        dotsHtml = '<div class="gallery-dots">'
        images.forEach((_, i) => {
          dotsHtml += '<div class="gallery-dot ' + (i === 0 ? 'active' : '') + '"></div>'
        })
        dotsHtml += '</div>' +
          '<div class="gallery-counter">1 / ' + images.length + '</div>'
      }

      galleryHtml = '<div class="detail-gallery" id="detail-gallery">' +
        '<div class="gallery-track" id="gallery-track">' + slidesHtml + '</div>' +
        dotsHtml +
        '</div>'
    }

    const outOfStock = product.inventory !== null && product.inventory <= 0

    let priceHtml = ''
    if (outOfStock) {
      priceHtml = '<div class="detail-price" style="color:var(--tg-theme-destructive-text-color,#e53935)">Out of Stock</div>'
    } else if (product.discount_percentage && product.discount_percentage > 0) {
      const original = product.price / (1 - product.discount_percentage / 100)
      priceHtml = '<div class="detail-price">' +
        '<span class="original-price" style="text-decoration:line-through;opacity:0.5;font-size:16px;margin-right:8px">' +
        this.formatPrice(original) + '</span>' + this.formatPrice(product.price) +
        '<span style="font-size:13px;margin-left:6px;opacity:0.7">-' + product.discount_percentage.toFixed(0) + '%</span></div>'
    } else {
      priceHtml = '<div class="detail-price">' + this.formatPrice(product.price) + '</div>'
    }

    let metaHtml = '<div class="detail-meta">'
    if (product.inventory !== null && !outOfStock) {
      const stockClass = product.inventory <= 5 ? 'meta-tag low-stock' : 'meta-tag'
      metaHtml += '<span class="' + stockClass + '">\ud83d\udce6 ' + product.inventory + ' in stock</span>'
    }
    if (product.sku) {
      metaHtml += '<span class="meta-tag">SKU: ' + this.escapeHtml(product.sku) + '</span>'
    }
    if (product.tax_rate && product.tax_rate > 0) {
      const taxLabel = product.is_tax_inclusive
        ? product.tax_rate + '% tax incl.'
        : '+' + product.tax_rate + '% tax'
      metaHtml += '<span class="meta-tag">' + taxLabel + '</span>'
    }
    if (product.requires_shipping) {
      metaHtml += '<span class="meta-tag">\ud83d\ude9a Shipping required</span>'
    }
    metaHtml += '</div>'

    // Check if already in cart
    const inCart = this.cart.find(i => i.product_id === productId)
    let buttonHtml = ''
    if (outOfStock) {
      buttonHtml = '<button class="btn-primary mt-md" disabled>Out of Stock</button>'
    } else if (inCart) {
      buttonHtml = '<div class="detail-cart-controls mt-md">' +
        '<button class="qty-btn" onclick="event.stopPropagation(); TMA.updateQuantity(\'' + productId + '\', -1)">\u2212</button>' +
        '<span class="qty-value">' + inCart.quantity + ' in cart</span>' +
        '<button class="qty-btn" onclick="event.stopPropagation(); TMA.updateQuantity(\'' + productId + '\', 1)">+</button>' +
        '</div>' +
        '<button class="btn-secondary mt-sm" onclick="TMA.navigate(\'#/cart\')">View Cart \u2014 ' +
        this.formatPrice(this.cartTotal()) + '</button>'
    } else {
      buttonHtml = '<button class="btn-primary mt-md" onclick="TMA.addToCart(\'' + productId + '\')">Add to Cart</button>'
    }

    // Back link for browser (no Telegram BackButton)
    const backHtml = '<button class="back-link" onclick="TMA.navigate(\'#/\')">\u2190 Back to shop</button>'

    let shareHtml = ''
    if (this.botUsername) {
      shareHtml = '<button class="btn-share" onclick="TMA.shareProduct(\'' + productId + '\')" title="Share">' +
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>' +
        '<polyline points="16 6 12 2 8 6"/>' +
        '<line x1="12" y1="2" x2="12" y2="15"/>' +
        '</svg>' +
        '</button>'
    }

    container.innerHTML = backHtml + galleryHtml +
      '<div class="detail-title-row">' +
        '<h1>' + this.escapeHtml(product.title) + '</h1>' +
        shareHtml +
      '</div>' +
      (product.category ? '<div class="detail-category">' + this.escapeHtml(product.category) + '</div>' : '') +
      priceHtml +
      (product.description ? '<div class="detail-desc">' + this.escapeHtml(product.description) + '</div>' : '') +
      metaHtml +
      '<div class="detail-actions">' + buttonHtml + '</div>'

    this._galleryImages = images
    this._galleryIndex = 0

    // Bind swipe after DOM renders
    if (images.length > 1) {
      requestAnimationFrame(() => this._initGallerySwipe())
    }
  },

  _galleryImages: [],
  _galleryIndex: 0,

  _initGallerySwipe() {
    const gallery = document.getElementById('detail-gallery')
    const track = document.getElementById('gallery-track')
    if (!gallery || !track) return

    let startX = 0
    let startY = 0
    let currentX = 0
    let dragging = false
    let isHorizontal = null
    const threshold = 40

    const onStart = (x, y) => {
      startX = x
      startY = y
      currentX = 0
      dragging = true
      isHorizontal = null
      track.classList.add('swiping')
    }

    const onMove = (x, y, e) => {
      if (!dragging) return
      const dx = x - startX
      const dy = y - startY

      if (isHorizontal === null && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
        isHorizontal = Math.abs(dx) > Math.abs(dy)
      }
      if (!isHorizontal) return

      if (e) e.preventDefault()
      currentX = dx
      const offset = -(this._galleryIndex * gallery.offsetWidth) + currentX
      track.style.transform = 'translateX(' + offset + 'px)'
    }

    const onEnd = () => {
      if (!dragging) return
      dragging = false
      track.classList.remove('swiping')

      if (isHorizontal && Math.abs(currentX) > threshold) {
        if (currentX < 0 && this._galleryIndex < this._galleryImages.length - 1) {
          this._galleryIndex++
        } else if (currentX > 0 && this._galleryIndex > 0) {
          this._galleryIndex--
        }
      }
      this._updateGalleryPosition()
    }

    // Touch events
    track.addEventListener('touchstart', (e) => onStart(e.touches[0].clientX, e.touches[0].clientY), { passive: true })
    track.addEventListener('touchmove', (e) => onMove(e.touches[0].clientX, e.touches[0].clientY, e), { passive: false })
    track.addEventListener('touchend', onEnd, { passive: true })

    // Mouse events (desktop)
    track.addEventListener('mousedown', (e) => { e.preventDefault(); onStart(e.clientX, e.clientY) })
    track.addEventListener('mousemove', (e) => onMove(e.clientX, e.clientY, e))
    track.addEventListener('mouseup', onEnd)
    track.addEventListener('mouseleave', () => { if (dragging) onEnd() })

    // Arrow buttons
    this._addGalleryArrows(gallery)
  },

  _addGalleryArrows(gallery) {
    const leftBtn = document.createElement('button')
    leftBtn.className = 'gallery-arrow gallery-arrow-left'
    leftBtn.innerHTML = '&#8249;'
    leftBtn.onclick = (e) => { e.stopPropagation(); this.galleryPrev() }

    const rightBtn = document.createElement('button')
    rightBtn.className = 'gallery-arrow gallery-arrow-right'
    rightBtn.innerHTML = '&#8250;'
    rightBtn.onclick = (e) => { e.stopPropagation(); this.galleryNext() }

    gallery.appendChild(leftBtn)
    gallery.appendChild(rightBtn)
  },

  galleryPrev() {
    if (this._galleryIndex > 0) {
      this._galleryIndex--
      this._updateGalleryPosition()
    }
  },

  galleryNext() {
    if (this._galleryIndex < this._galleryImages.length - 1) {
      this._galleryIndex++
      this._updateGalleryPosition()
    }
  },

  _updateGalleryPosition() {
    const gallery = document.getElementById('detail-gallery')
    const track = document.getElementById('gallery-track')
    if (!gallery || !track) return

    const offset = -(this._galleryIndex * gallery.offsetWidth)
    track.style.transform = 'translateX(' + offset + 'px)'

    // Update dots
    document.querySelectorAll('.gallery-dot').forEach((dot, i) => {
      dot.classList.toggle('active', i === this._galleryIndex)
    })

    // Update counter
    const counter = gallery.querySelector('.gallery-counter')
    if (counter) {
      counter.textContent = (this._galleryIndex + 1) + ' / ' + this._galleryImages.length
    }
  },

  // --- Lightbox (fullscreen image viewer) ---
  openLightbox(index) {
    if (!this._galleryImages.length) return
    this._lightboxIndex = typeof index === 'number' ? index : this._galleryIndex

    const overlay = document.createElement('div')
    overlay.className = 'lightbox-overlay'
    overlay.id = 'lightbox'

    let slidesHtml = ''
    this._galleryImages.forEach((url) => {
      slidesHtml += '<div class="lightbox-slide">' +
        '<img src="' + this.escapeHtml(url) + '" alt="">' +
        '</div>'
    })

    const counterHtml = this._galleryImages.length > 1
      ? '<div class="lightbox-counter" id="lightbox-counter">' +
        (this._lightboxIndex + 1) + ' / ' + this._galleryImages.length +
        '</div>'
      : ''

    overlay.innerHTML = '<div class="lightbox-close" onclick="TMA.closeLightbox()">&times;</div>' +
      counterHtml +
      '<div class="lightbox-track" id="lightbox-track">' + slidesHtml + '</div>'

    document.body.appendChild(overlay)

    // Tap backdrop to close
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) this.closeLightbox()
    })

    // Position to current image
    requestAnimationFrame(() => {
      this._positionLightbox()
      overlay.classList.add('visible')
      if (this._galleryImages.length > 1) {
        this._initLightboxSwipe()
      }
    })
  },

  _lightboxIndex: 0,

  _positionLightbox() {
    const track = document.getElementById('lightbox-track')
    if (!track) return
    const w = window.innerWidth
    track.style.transform = 'translateX(' + -(this._lightboxIndex * w) + 'px)'

    const counter = document.getElementById('lightbox-counter')
    if (counter) {
      counter.textContent = (this._lightboxIndex + 1) + ' / ' + this._galleryImages.length
    }
  },

  _initLightboxSwipe() {
    const track = document.getElementById('lightbox-track')
    const overlay = document.getElementById('lightbox')
    if (!track) return

    let startX = 0
    let currentX = 0
    let dragging = false
    const threshold = 50

    const onStart = (x) => {
      startX = x
      currentX = 0
      dragging = true
      track.style.transition = 'none'
    }

    const onMove = (x) => {
      if (!dragging) return
      currentX = x - startX
      const w = window.innerWidth
      track.style.transform = 'translateX(' + (-(this._lightboxIndex * w) + currentX) + 'px)'
    }

    const onEnd = () => {
      if (!dragging) return
      dragging = false
      track.style.transition = 'transform 0.3s ease'

      if (Math.abs(currentX) > threshold) {
        if (currentX < 0 && this._lightboxIndex < this._galleryImages.length - 1) {
          this._lightboxIndex++
        } else if (currentX > 0 && this._lightboxIndex > 0) {
          this._lightboxIndex--
        }
      }
      this._positionLightbox()
    }

    // Touch events
    track.addEventListener('touchstart', (e) => onStart(e.touches[0].clientX), { passive: true })
    track.addEventListener('touchmove', (e) => onMove(e.touches[0].clientX), { passive: true })
    track.addEventListener('touchend', onEnd, { passive: true })

    // Mouse events (desktop)
    track.addEventListener('mousedown', (e) => { e.preventDefault(); onStart(e.clientX) })
    track.addEventListener('mousemove', (e) => onMove(e.clientX))
    track.addEventListener('mouseup', onEnd)
    track.addEventListener('mouseleave', () => { if (dragging) onEnd() })

    // Arrow buttons
    if (this._galleryImages.length > 1 && overlay) {
      const leftBtn = document.createElement('button')
      leftBtn.className = 'lightbox-arrow lightbox-arrow-left'
      leftBtn.innerHTML = '&#8249;'
      leftBtn.onclick = (e) => { e.stopPropagation(); this.lightboxPrev() }

      const rightBtn = document.createElement('button')
      rightBtn.className = 'lightbox-arrow lightbox-arrow-right'
      rightBtn.innerHTML = '&#8250;'
      rightBtn.onclick = (e) => { e.stopPropagation(); this.lightboxNext() }

      overlay.appendChild(leftBtn)
      overlay.appendChild(rightBtn)
    }

    // Keyboard navigation
    this._lightboxKeyHandler = (e) => {
      if (e.key === 'ArrowLeft') this.lightboxPrev()
      else if (e.key === 'ArrowRight') this.lightboxNext()
      else if (e.key === 'Escape') this.closeLightbox()
    }
    document.addEventListener('keydown', this._lightboxKeyHandler)
  },

  _lightboxKeyHandler: null,

  lightboxPrev() {
    if (this._lightboxIndex > 0) {
      this._lightboxIndex--
      this._positionLightbox()
    }
  },

  lightboxNext() {
    if (this._lightboxIndex < this._galleryImages.length - 1) {
      this._lightboxIndex++
      this._positionLightbox()
    }
  },

  closeLightbox() {
    if (this._lightboxKeyHandler) {
      document.removeEventListener('keydown', this._lightboxKeyHandler)
      this._lightboxKeyHandler = null
    }
    const el = document.getElementById('lightbox')
    if (el) {
      el.classList.remove('visible')
      setTimeout(() => el.remove(), 200)
    }
  },

  // ===== Render: Cart =====
  renderCart() {
    const container = document.getElementById('cart-content')

    if (this.cart.length === 0) {
      container.innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\uded2</div>' +
        '<h3>Your cart is empty</h3>' +
        '<p class="text-hint">Browse products and add items to get started</p>' +
        '<button class="btn-secondary mt-md" onclick="TMA.navigate(\'#/\')">Browse Products</button>' +
        '</div>'
      return
    }

    // Credit banner
    let creditBanner = ''
    if (this.authenticated && this.creditBalance > 0) {
      creditBanner = '<div class="credit-banner" onclick="TMA.navigate(\'#/credits\')">' +
        '<span class="credit-banner-icon">\u2728</span>' +
        '<span class="credit-banner-text">You have <strong>' +
        this.creditBalance.toLocaleString() + ' sats</strong> in store credit</span>' +
        '<span class="credit-banner-arrow">\u203a</span>' +
        '</div>'
    }

    let itemsHtml = creditBanner
    this.cart.forEach(item => {
      const product = this.products.find(p => p.id === item.product_id)
      const imgUrl = product
        ? ((product.image_urls && product.image_urls.length > 0) ? product.image_urls[0] : product.image_url)
        : null
      const imgHtml = imgUrl
        ? '<img class="cart-item-img" src="' + this.escapeHtml(imgUrl) + '" alt="">'
        : '<div class="cart-item-img-placeholder">\ud83d\udce6</div>'
      const lineTotal = item.price * item.quantity

      // Stock warning in cart
      let stockWarning = ''
      if (product && product.inventory !== null && item.quantity >= product.inventory) {
        stockWarning = '<div class="cart-stock-warn">Max available</div>'
      }

      itemsHtml += '<div class="cart-item">' +
        '<div class="cart-item-img-wrap" onclick="TMA.navigate(\'#/product/' + item.product_id + '\')">' +
        imgHtml +
        '</div>' +
        '<div class="cart-item-info" onclick="TMA.navigate(\'#/product/' + item.product_id + '\')">' +
        '<div class="cart-item-title">' + this.escapeHtml(item.title) + '</div>' +
        '<div class="cart-item-price">' + this.formatPrice(item.price) + ' each</div>' +
        stockWarning +
        '</div>' +
        '<div class="cart-item-right">' +
        '<div class="cart-item-line-total">' + this.formatPrice(lineTotal) + '</div>' +
        '<div class="qty-controls">' +
        '<button class="qty-btn" onclick="TMA.updateQuantity(\'' + item.product_id + '\', -1)">\u2212</button>' +
        '<span class="qty-value">' + item.quantity + '</span>' +
        '<button class="qty-btn" onclick="TMA.updateQuantity(\'' + item.product_id + '\', 1)">+</button>' +
        '</div>' +
        '</div>' +
        '</div>'
    })

    const total = this.cartTotal()
    const count = this.cartItemCount()
    let summaryHtml = '<div class="cart-summary">' +
      '<div class="summary-row">' +
      '<span>' + count + ' item' + (count !== 1 ? 's' : '') + '</span>' +
      '<span>' + this.formatPrice(total) + '</span>' +
      '</div>'

    if (this.creditBalance > 0) {
      const creditApplied = Math.min(this.creditBalance, total)
      summaryHtml += '<div class="summary-row credit">' +
        '<span>\u2728 Store credit</span>' +
        '<span>\u2212' + creditApplied.toLocaleString() + ' sats</span>' +
        '</div>'
    }

    const finalTotal = Math.max(0, total - this.creditBalance)
    summaryHtml += '<div class="summary-row total">' +
      '<span>Total</span>' +
      '<span>' + this.formatPrice(finalTotal) + '</span>' +
      '</div></div>'

    container.innerHTML = itemsHtml + summaryHtml +
      '<button class="btn-primary mt-md" onclick="TMA.startCheckout()">Checkout \u2013 ' +
      this.formatPrice(finalTotal) + '</button>' +
      '<button class="btn-text mt-sm" onclick="TMA.clearCart()">Clear cart</button>'

    // Also update MainButton
    this.updateMainButton()
  },

  // ===== Checkout Flow =====
  _cartHasPhysical() {
    return this.cart.some(item => {
      const p = this.products.find(pr => pr.id === item.product_id)
      return p && p.requires_shipping
    })
  },

  startCheckout() {
    if (!this.authenticated) {
      this.showToast('Please open from Telegram')
      return
    }
    if (this.cart.length === 0) return

    if (this.checkoutMode === 'none' && !this._cartHasPhysical()) {
      this.submitCheckout({})
    } else {
      this.navigate('#/checkout')
    }
  },

  renderCheckout() {
    const container = document.getElementById('checkout-content')
    const hasPhysical = this._cartHasPhysical()
    const needsEmail = this.checkoutMode === 'email' || this.checkoutMode === 'address'
    const needsAddress = this.checkoutMode === 'address' || hasPhysical

    // Order summary at top
    const total = this.cartTotal()
    const creditApplied = this.creditBalance > 0 ? Math.min(this.creditBalance, total) : 0
    const finalTotal = Math.max(0, total - creditApplied)

    let html = '<div class="checkout-summary">'
    this.cart.forEach(item => {
      html += '<div class="checkout-item">' +
        '<span>' + item.quantity + '\u00d7 ' + this.escapeHtml(item.title) + '</span>' +
        '<span>' + this.formatPrice(item.price * item.quantity) + '</span>' +
        '</div>'
    })

    if (creditApplied > 0) {
      html += '<div class="checkout-item credit">' +
        '<span>\u2728 Store credit</span>' +
        '<span>\u2212' + creditApplied.toLocaleString() + ' sats</span>' +
        '</div>'
    }

    html += '<div class="checkout-item total">' +
      '<span>Total</span>' +
      '<span>' + this.formatPrice(finalTotal) + '</span>' +
      '</div></div>'

    html += '<form id="checkout-form" onsubmit="TMA.handleCheckoutSubmit(event)">'

    if (needsEmail) {
      html += '<div class="form-group">' +
        '<label class="form-label">Email</label>' +
        '<input type="email" class="form-input" id="checkout-email" required placeholder="you@email.com">' +
        '</div>'
    }

    if (needsAddress) {
      html += '<div class="form-group">' +
        '<label class="form-label">Full Name</label>' +
        '<input type="text" class="form-input" id="checkout-name" required placeholder="Your full name">' +
        '</div>' +
        '<div class="form-group">' +
        '<label class="form-label">Street Address</label>' +
        '<input type="text" class="form-input" id="checkout-street" required placeholder="123 Main St">' +
        '</div>' +
        '<div class="form-group">' +
        '<label class="form-label">Apt / Suite (optional)</label>' +
        '<input type="text" class="form-input" id="checkout-street2" placeholder="Apt 4B">' +
        '</div>' +
        '<div class="form-group">' +
        '<label class="form-label">City</label>' +
        '<input type="text" class="form-input" id="checkout-city" required placeholder="City">' +
        '</div>' +
        '<div class="form-row">' +
        '<div class="form-group flex-1">' +
        '<label class="form-label">State / Province</label>' +
        '<input type="text" class="form-input" id="checkout-state" placeholder="State">' +
        '</div>' +
        '<div class="form-group flex-1">' +
        '<label class="form-label">ZIP / Postal</label>' +
        '<input type="text" class="form-input" id="checkout-zip" required placeholder="12345">' +
        '</div></div>' +
        '<div class="form-group">' +
        '<label class="form-label">Country</label>' +
        '<input type="text" class="form-input" id="checkout-country" required placeholder="Country">' +
        '</div>'
    }

    html += '<button type="submit" class="btn-primary mt-md" id="checkout-submit-btn">Pay ' +
      this.formatPrice(finalTotal) + ' \u26a1</button>' +
      '<button type="button" class="btn-text mt-sm" onclick="TMA.navigate(\'#/cart\')">Back to cart</button>' +
      '</form>'

    container.innerHTML = html
  },

  handleCheckoutSubmit(e) {
    e.preventDefault()

    // Disable button to prevent double-tap
    const btn = document.getElementById('checkout-submit-btn')
    if (btn) {
      btn.disabled = true
      btn.textContent = 'Processing\u2026'
    }

    const body = {}
    const emailEl = document.getElementById('checkout-email')
    if (emailEl) body.buyer_email = emailEl.value

    if (this.checkoutMode === 'address' || this._cartHasPhysical()) {
      body.buyer_name = (document.getElementById('checkout-name') || {}).value || ''
      const parts = [
        (document.getElementById('checkout-street') || {}).value || '',
        (document.getElementById('checkout-street2') || {}).value || '',
        ((document.getElementById('checkout-city') || {}).value || '') + ', ' +
          ((document.getElementById('checkout-state') || {}).value || ''),
        (document.getElementById('checkout-zip') || {}).value || '',
        (document.getElementById('checkout-country') || {}).value || '',
      ].filter(Boolean)
      body.buyer_address = parts.join('\n')
    }

    this.submitCheckout(body)
  },

  async submitCheckout(body) {
    // Show MainButton loading spinner if available
    const tg = window.Telegram && window.Telegram.WebApp
    if (tg && tg.MainButton && tg.MainButton.isVisible) {
      tg.MainButton.showProgress(false)
    }

    try {
      const url = this.baseUrl + '/' + this.shopId + '/checkout'
      const headers = { 'Content-Type': 'application/json' }
      if (this.initData) headers['Authorization'] = 'tma ' + this.initData

      const resp = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      })

      if (resp.status === 409) {
        const data = await resp.json().catch(() => ({}))
        const issues = (data.detail && data.detail.stock_issues) || []
        const msg = issues.length
          ? issues.join('\n')
          : 'Some items are no longer available'
        this.showToast(msg)
        await this.loadProducts()
        this.navigate('#/cart')
        return
      }

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || 'HTTP ' + resp.status)
      }

      const result = await resp.json()

      if (result.status === 'paid') {
        this.cart = []
        this.updateCartBadge()
        if (tg && tg.MainButton) tg.MainButton.hideProgress()
        this.haptic('notification', 'success')
        this.showToast('Order placed!')
        this.loadProducts()
        this.loadCredits()
        this.navigate('#/order/' + result.order_id)
        return
      }

      if (tg && tg.MainButton) tg.MainButton.hideProgress()
      this._pendingPayment = result
      this.navigate('#/payment')
      this.showPaymentScreen(result)
    } catch (e) {
      if (tg && tg.MainButton) tg.MainButton.hideProgress()
      this.showToast('Checkout failed: ' + e.message)
      const btn = document.getElementById('checkout-submit-btn')
      if (btn) {
        btn.disabled = false
        btn.textContent = 'Pay with Lightning \u26a1'
      }
    }
  },

  _pendingPayment: null,

  showPaymentScreen(result) {
    const container = document.getElementById('payment-content')
    const bolt11 = result.bolt11 || ''
    const amount = result.amount_sats || 0

    // Generate QR code as SVG
    const qrHtml = bolt11
      ? '<div class="payment-qr" id="payment-qr"></div>'
      : ''

    container.innerHTML = '<div class="payment-screen">' +
      '<div class="payment-icon">\u26a1</div>' +
      '<h2 class="payment-amount">Pay ' + amount.toLocaleString() + ' sats</h2>' +
      '<p class="text-hint mb-md">Scan the QR code or copy the invoice</p>' +
      (result.credit_used > 0
        ? '<div class="payment-credit">\u2728 Store credit applied: \u2212' + result.credit_used.toLocaleString() + ' sats</div>'
        : '') +
      qrHtml +
      '<div class="payment-bolt11" onclick="TMA.copyBolt11()">' +
      '<span id="bolt11-text"></span>' +
      '<div class="bolt11-tap-hint">Tap to copy</div>' +
      '</div>' +
      '<div class="payment-actions">' +
      '<button class="btn-tap-to-pay" onclick="TMA.openPayLink()">\u26a1 Tap to Pay</button>' +
      '<button class="btn-secondary mb-sm" onclick="TMA.copyBolt11()">Copy Invoice</button>' +
      '</div>' +
      '<p class="text-hint mt-md" style="font-size:12px">Invoice expires in 15 minutes</p>' +
      '<div class="payment-status" id="payment-status">' +
      '<div class="spinner" style="width:16px;height:16px;display:inline-block;vertical-align:middle;margin-right:8px"></div>' +
      'Waiting for payment\u2026' +
      '</div></div>'

    // Set bolt11 text safely (no HTML escaping needed)
    const bolt11El = document.getElementById('bolt11-text')
    if (bolt11El) bolt11El.textContent = bolt11

    // Generate QR code
    if (bolt11) {
      this._renderQR(bolt11)
    }

    this.pollPayment(result.order_id)
  },

  _renderQR(data) {
    const container = document.getElementById('payment-qr')
    if (!container) return

    // Use LNbits core QR endpoint (SVG, no external dependency)
    const size = 220
    const url = '/api/v1/qrcode/' + encodeURIComponent(data.toUpperCase())
    container.innerHTML = '<img src="' + url + '" alt="QR Code" width="' + size +
      '" height="' + size + '" style="border-radius:12px;background:#fff;padding:8px">'
  },

  copyBolt11(bolt11) {
    if (!bolt11) bolt11 = this._pendingPayment && this._pendingPayment.bolt11
    if (!bolt11) return
    navigator.clipboard.writeText(bolt11).then(() => {
      this.showToast('Invoice copied!')
      this.haptic('notification', 'success')
    }).catch(() => {
      const ta = document.createElement('textarea')
      ta.value = bolt11
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      this.showToast('Invoice copied!')
    })
  },

  openPayLink() {
    const bolt11 = this._pendingPayment && this._pendingPayment.bolt11
    if (!bolt11) return
    const uri = 'lightning:' + bolt11
    const tg = window.Telegram && window.Telegram.WebApp
    if (tg && tg.openLink) {
      tg.openLink(uri)
    } else {
      window.location.href = uri
    }
  },

  shareProduct(productId) {
    if (!this.botUsername) return
    const product = this.products.find(p => p.id === productId)
    if (!product) return

    const url = 'https://t.me/' + this.botUsername + '?startapp=product_' + productId
    const text = product.title + ' — ' + this.formatPrice(product.price)

    // Use Telegram's native share if available
    const tg = window.Telegram && window.Telegram.WebApp
    if (tg && tg.switchInlineQuery) {
      // switchInlineQuery opens the inline query picker with pre-filled text
      tg.switchInlineQuery(product.title, ['users', 'groups', 'channels'])
      return
    }

    // Fallback: copy link to clipboard
    navigator.clipboard.writeText(url).then(() => {
      this.showToast('Link copied!')
      this.haptic('notification', 'success')
    }).catch(() => {
      const ta = document.createElement('textarea')
      ta.value = url
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      this.showToast('Link copied!')
    })
  },

  _pollTimer: null,

  _stopPolling() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer)
      this._pollTimer = null
    }
  },

  async pollPayment(orderId) {
    this._stopPolling()
    const startTime = Date.now()
    const maxDuration = 15 * 60 * 1000  // 15 minutes

    const getInterval = () => {
      const elapsed = Date.now() - startTime
      if (elapsed < 2 * 60 * 1000) return 5000     // 5s for first 2 min
      if (elapsed < 5 * 60 * 1000) return 10000     // 10s until 5 min
      return 30000                                    // 30s until 15 min
    }

    const poll = async () => {
      if (Date.now() - startTime > maxDuration) {
        this._stopPolling()
        const el = document.getElementById('payment-status')
        if (el) el.innerHTML = '\u23f0 Invoice expired. <button class="btn-text" onclick="TMA.navigate(\'#/cart\')">Back to cart</button>'
        return
      }
      try {
        const result = await this.api('/' + this.shopId + '/orders/' + orderId + '/status')
        if (result.status === 'paid') {
          this._stopPolling()
          this._pendingPayment = null
          this.cart = []
          this.updateCartBadge()
          this.haptic('notification', 'success')
          const el = document.getElementById('payment-status')
          if (el) {
            el.className = 'payment-status confirmed'
            el.innerHTML = '\u2705 Payment confirmed!'
          }
          this.loadProducts()
          this.loadCredits()
          setTimeout(() => this.navigate('#/order/' + orderId), 1200)
          return
        }
      } catch {
        // Silent
      }
      this._pollTimer = setTimeout(poll, getInterval())
    }

    this._pollTimer = setTimeout(poll, getInterval())
  },

  // ===== Render: Orders =====
  async renderOrders() {
    const container = document.getElementById('orders-content')

    if (!this.authenticated) {
      container.innerHTML = '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\udd12</div>' +
        '<p class="text-hint">Open from Telegram to view orders</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const orders = await this.api('/' + this.shopId + '/orders')

      if (orders.length === 0) {
        container.innerHTML = '<div class="empty-state">' +
          '<div class="empty-icon">\ud83d\udce6</div>' +
          '<h3>No orders yet</h3>' +
          '<p class="text-hint">Your orders will appear here after checkout</p>' +
          '<button class="btn-secondary mt-md" onclick="TMA.navigate(\'#/\')">Start shopping</button>' +
          '</div>'
        return
      }

      const fulfillmentLabels = {
        preparing: '\ud83d\udccb Preparing',
        shipping: '\ud83d\ude9a Shipping',
        delivered: '\u2705 Delivered'
      }

      let html = ''
      orders.forEach(order => {
        let items = []
        try { items = JSON.parse(order.cart_json) } catch {}
        const itemsSummary = items.map(i => i.quantity + '\u00d7 ' + i.title).join(', ')

        html += '<div class="order-card" onclick="TMA.navigate(\'#/order/' + order.id + '\')">' +
          '<div class="order-header">' +
          '<span class="order-id">#' + order.id.substring(0, 8) + '</span>' +
          '<span class="order-status ' + order.status + '">' + order.status + '</span>' +
          '</div>' +
          '<div class="order-items">' + this.escapeHtml(itemsSummary) + '</div>' +
          '<div class="order-footer">' +
          '<span class="order-amount">' + order.amount_sats.toLocaleString() + ' sats</span>' +
          '<span class="order-date">' + this.formatDate(order.timestamp) + '</span>' +
          '</div>' +
          (order.fulfillment_status
            ? '<div class="order-fulfillment">' +
              (fulfillmentLabels[order.fulfillment_status] || order.fulfillment_status) +
              '</div>'
            : '') +
          '<div class="order-card-arrow">\u203a</div>' +
          '</div>'
      })

      // Link to returns if allowed
      if (this.allowReturns) {
        html += '<button class="btn-text mt-md" onclick="TMA.navigate(\'#/returns\')">View return requests</button>'
      }

      container.innerHTML = html
    } catch {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load orders</p>' +
        '<button class="btn-text mt-md" onclick="TMA.renderOrders()">Try again</button></div>'
    }
  },

  // ===== Render: Order Detail =====
  async renderOrderDetail(orderId) {
    const container = document.getElementById('order-detail-content')
    if (!this.authenticated) {
      container.innerHTML = '<div class="empty-state"><p class="text-hint">Open from Telegram to view orders</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const [orders, returns] = await Promise.all([
        this.api('/' + this.shopId + '/orders'),
        this.api('/' + this.shopId + '/returns').catch(() => []),
      ])
      const order = orders.find(o => o.id === orderId)

      if (!order) {
        container.innerHTML = '<div class="empty-state"><h3>Order not found</h3></div>'
        return
      }

      let items = []
      try { items = JSON.parse(order.cart_json) } catch {}

      let html = '<div class="order-detail">' +
        '<button class="back-link" onclick="TMA.navigate(\'#/orders\')">\u2190 Back to orders</button>' +
        '<div class="order-detail-header">' +
        '<h2>Order #' + order.id.substring(0, 8) + '</h2>' +
        '<span class="order-status ' + order.status + '">' + order.status + '</span>' +
        '</div>'

      // Fulfillment tracking
      if (order.fulfillment_status) {
        html += '<div class="fulfillment-tracker">' +
          this._renderFulfillmentSteps(order.fulfillment_status) +
          (order.fulfillment_note
            ? '<p class="fulfillment-note">' + this.escapeHtml(order.fulfillment_note) + '</p>'
            : '') +
          '</div>'
      }

      // Items
      html += '<div class="section-label">Items</div>' +
        '<div class="order-items-list">'
      items.forEach(item => {
        html += '<div class="order-item-row">' +
          '<span>' + item.quantity + '\u00d7 ' + this.escapeHtml(item.title) + '</span>' +
          '<span>' + this.formatPrice(item.price * item.quantity) + '</span>' +
          '</div>'
      })
      html += '</div>'

      html += '<div class="cart-summary">' +
        '<div class="summary-row total">' +
        '<span>Total paid</span>' +
        '<span>' + order.amount_sats.toLocaleString() + ' sats</span>' +
        '</div></div>'

      html += '<div class="order-date-full">Placed ' + this.formatDate(order.timestamp) + '</div>'

      // Return status for this order
      const orderReturns = returns.filter(r => r.order_id === orderId)
      if (orderReturns.length > 0) {
        html += '<div class="section-label mt-md">Returns</div>'
        orderReturns.forEach(r => {
          const statusColors = {
            requested: 'pending',
            approved: 'paid',
            refunded: 'paid',
            denied: 'expired'
          }
          const statusLabels = {
            requested: 'Under review',
            approved: 'Approved',
            refunded: 'Refunded',
            denied: 'Denied'
          }
          let returnItems = []
          try { returnItems = JSON.parse(r.items_json) } catch {}

          html += '<div class="return-card" style="cursor:default">' +
            '<div class="return-header">' +
            '<span class="order-status ' + (statusColors[r.status] || '') + '">' +
            (statusLabels[r.status] || r.status) + '</span>' +
            '<span class="text-hint">' + this.formatDate(r.timestamp) + '</span>' +
            '</div>' +
            '<div class="return-items">' +
            returnItems.map(i => i.quantity + '\u00d7 ' + this.escapeHtml(i.title)).join(', ') +
            '</div>' +
            (r.refund_amount_sats
              ? '<div class="return-refund">Refund: ' + r.refund_amount_sats.toLocaleString() + ' sats' +
                (r.refund_method ? ' (' + r.refund_method + ')' : '') + '</div>'
              : '') +
            (r.admin_note
              ? '<div class="return-note">\ud83d\udcac ' + this.escapeHtml(r.admin_note) + '</div>'
              : '') +
            (r.reason
              ? '<div class="return-note">Reason: ' + this.escapeHtml(r.reason) + '</div>'
              : '') +
            '</div>'
        })
      }

      // Action buttons
      html += '<div class="order-actions mt-md">'
      if (this.allowReturns && order.status === 'paid' && orderReturns.length === 0) {
        html += '<button class="btn-secondary" onclick="TMA.navigate(\'#/return/' + order.id + '\')">Request return</button>'
      }
      html += '<button class="btn-text mt-sm" onclick="TMA.navigate(\'#/messages?order=' + order.id + '\')">Message about this order</button>'
      html += '</div></div>'

      container.innerHTML = html
    } catch {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load order</p>' +
        '<button class="btn-text mt-md" onclick="TMA.navigate(\'#/orders\')">Back to orders</button></div>'
    }
  },

  _renderFulfillmentSteps(current) {
    const steps = ['preparing', 'shipping', 'delivered']
    const icons = ['\ud83d\udccb', '\ud83d\ude9a', '\u2705']
    const labels = ['Preparing', 'Shipping', 'Delivered']
    const currentIdx = steps.indexOf(current)

    let html = '<div class="fulfillment-steps">'
    steps.forEach((_, i) => {
      const state = i <= currentIdx ? 'done' : 'pending'
      html += '<div class="fulfillment-step ' + state + '">' +
        '<div class="step-icon">' + icons[i] + '</div>' +
        '<div class="step-label">' + labels[i] + '</div>' +
        '</div>'
      if (i < steps.length - 1) {
        html += '<div class="step-line ' + (i < currentIdx ? 'done' : 'pending') + '"></div>'
      }
    })
    html += '</div>'
    return html
  },

  // ===== Render: Returns List =====
  async renderReturns() {
    const container = document.getElementById('returns-content')
    if (!this.authenticated) {
      container.innerHTML = '<div class="empty-state"><p class="text-hint">Open from Telegram to view returns</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const returns = await this.api('/' + this.shopId + '/returns')

      if (returns.length === 0) {
        container.innerHTML = '<div class="empty-state">' +
          '<div class="empty-icon">\u21a9\ufe0f</div>' +
          '<h3>No return requests</h3>' +
          '<p class="text-hint">You haven\'t submitted any returns</p>' +
          '<button class="btn-secondary mt-md" onclick="TMA.navigate(\'#/orders\')">View orders</button>' +
          '</div>'
        return
      }

      const statusColors = {
        requested: 'pending',
        approved: 'paid',
        refunded: 'paid',
        denied: 'expired'
      }
      const statusLabels = {
        requested: 'Under review',
        approved: 'Approved',
        refunded: 'Refunded',
        denied: 'Denied'
      }

      let html = ''
      returns.forEach(r => {
        let items = []
        try { items = JSON.parse(r.items_json) } catch {}

        html += '<div class="return-card" onclick="TMA.navigate(\'#/order/' + r.order_id + '\')">' +
          '<div class="return-header">' +
          '<span class="order-id">#' + r.order_id.substring(0, 8) + '</span>' +
          '<span class="order-status ' + (statusColors[r.status] || '') + '">' +
          (statusLabels[r.status] || r.status) + '</span>' +
          '</div>' +
          '<div class="return-items">' +
          items.map(i => i.quantity + '\u00d7 ' + this.escapeHtml(i.title)).join(', ') +
          '</div>' +
          (r.refund_amount_sats
            ? '<div class="return-refund">' + r.refund_amount_sats.toLocaleString() + ' sats' +
              (r.refund_method === 'credit' ? ' (store credit)' : '') + '</div>'
            : '') +
          (r.admin_note
            ? '<div class="return-note">' + this.escapeHtml(r.admin_note) + '</div>'
            : '') +
          '<div class="return-date">' + this.formatDate(r.timestamp) + '</div>' +
          '<div class="order-card-arrow">\u203a</div>' +
          '</div>'
      })

      container.innerHTML = html
    } catch {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load returns</p>' +
        '<button class="btn-text mt-md" onclick="TMA.renderReturns()">Try again</button></div>'
    }
  },

  // ===== Render: Credits =====
  async renderCredits() {
    const container = document.getElementById('credits-content')
    if (!this.authenticated) {
      container.innerHTML = '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\udd12</div>' +
        '<p class="text-hint">Open from Telegram to view credits</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    // Refresh credit data
    await this.loadCredits()

    let html = '<button class="back-link" onclick="TMA.navigate(\'#/cart\')">\u2190 Back to cart</button>'

    // Balance hero
    html += '<div class="credit-balance-card">' +
      '<div class="credit-balance-icon">\u2728</div>' +
      '<div class="credit-balance-amount">' + this.creditBalance.toLocaleString() + '</div>' +
      '<div class="credit-balance-label">sats available</div>' +
      '</div>'

    if (this.creditBalance > 0) {
      html += '<p class="text-hint" style="text-align:center;margin-bottom:16px">' +
        'Credits are automatically applied at checkout</p>'
    }

    // Credit entries
    if (this.creditEntries.length === 0) {
      html += '<div class="empty-state" style="padding:24px 0">' +
        '<p class="text-hint">No credits yet</p>' +
        '<p class="text-hint" style="font-size:12px">Credits can come from returns or promotions</p>' +
        '</div>'
    } else {
      html += '<div class="section-label">Credit history</div>'
      this.creditEntries.forEach(c => {
        const remaining = c.remaining_sats
        const total = c.amount_sats
        const used = c.used_sats
        const sourceLabel = c.source === 'return' ? 'Return refund' : 'Store credit'
        const sourceIcon = c.source === 'return' ? '\u21a9\ufe0f' : '\ud83c\udf81'
        const isFullyUsed = remaining <= 0

        html += '<div class="credit-entry' + (isFullyUsed ? ' used' : '') + '">' +
          '<div class="credit-entry-left">' +
          '<div class="credit-entry-source">' + sourceIcon + ' ' + sourceLabel + '</div>' +
          '<div class="credit-entry-date">' + this.formatDate(c.timestamp) + '</div>' +
          '</div>' +
          '<div class="credit-entry-right">' +
          '<div class="credit-entry-amount">' + remaining.toLocaleString() + ' sats</div>' +
          (used > 0
            ? '<div class="credit-entry-used">' + used.toLocaleString() + ' used of ' + total.toLocaleString() + '</div>'
            : '<div class="credit-entry-total">' + total.toLocaleString() + ' sats total</div>'
          ) +
          '</div>' +
          '</div>'
      })
    }

    html += '<button class="btn-secondary mt-md" onclick="TMA.navigate(\'#/\')">Browse products</button>'

    container.innerHTML = html
  },

  // ===== Render: Return Form =====
  async renderReturn(orderId) {
    const container = document.getElementById('return-content')
    if (!this.authenticated || !orderId) {
      container.innerHTML = '<div class="empty-state"><p class="text-hint">Invalid return request</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    try {
      const orders = await this.api('/' + this.shopId + '/orders')
      const order = orders.find(o => o.id === orderId)

      if (!order) {
        container.innerHTML = '<div class="empty-state"><h3>Order not found</h3></div>'
        return
      }

      let items = []
      try { items = JSON.parse(order.cart_json) } catch {}

      let html = '<button class="back-link" onclick="TMA.navigate(\'#/order/' + orderId + '\')">\u2190 Back to order</button>' +
        '<form id="return-form" onsubmit="TMA.handleReturnSubmit(event, \'' + orderId + '\')">' +
        '<p class="text-hint mb-md">Select items to return from order #' + orderId.substring(0, 8) + '</p>'

      items.forEach(item => {
        html += '<label class="return-item-check">' +
          '<input type="checkbox" name="return_item" value="' + this.escapeHtml(item.product_id) +
          '" data-item=\'' + this.escapeHtml(JSON.stringify(item)) + '\'>' +
          '<span>' + item.quantity + '\u00d7 ' + this.escapeHtml(item.title) +
          ' \u2014 ' + this.formatPrice(item.price * item.quantity) + '</span>' +
          '</label>'
      })

      html += '<div class="form-group mt-md">' +
        '<label class="form-label">Reason for return</label>' +
        '<textarea class="form-input form-textarea" id="return-reason" required ' +
        'placeholder="Please describe why you want to return these items..." rows="4"></textarea>' +
        '</div>'

      html += '<button type="submit" class="btn-primary mt-md" id="return-submit-btn">Submit Return</button>' +
        '<button type="button" class="btn-text mt-sm" onclick="TMA.navigate(\'#/order/' + orderId + '\')">Cancel</button>' +
        '</form>'

      container.innerHTML = html
    } catch {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load order</p></div>'
    }
  },

  async handleReturnSubmit(e, orderId) {
    e.preventDefault()
    const checkboxes = document.querySelectorAll('input[name="return_item"]:checked')
    if (checkboxes.length === 0) {
      this.showToast('Select at least one item')
      return
    }

    const returnItems = []
    checkboxes.forEach(cb => {
      try { returnItems.push(JSON.parse(cb.dataset.item)) } catch {}
    })

    const reason = document.getElementById('return-reason').value.trim()
    if (reason.length < 5) {
      this.showToast('Please provide a more detailed reason')
      return
    }

    // Disable button
    const btn = document.getElementById('return-submit-btn')
    if (btn) {
      btn.disabled = true
      btn.textContent = 'Submitting\u2026'
    }

    try {
      await this.api('/' + this.shopId + '/returns', {
        method: 'POST',
        body: {
          order_id: orderId,
          items_json: JSON.stringify(returnItems),
          reason: reason,
        },
      })
      this.haptic('notification', 'success')
      this.showToast('Return request submitted!')
      this.navigate('#/order/' + orderId)
    } catch (e) {
      this.showToast('Return failed: ' + e.message)
      if (btn) {
        btn.disabled = false
        btn.textContent = 'Submit Return'
      }
    }
  },

  // ===== Render: Messages =====
  async renderMessages() {
    const container = document.getElementById('messages-content')

    if (!this.authenticated) {
      container.innerHTML = '<div class="empty-state">' +
        '<div class="empty-icon">\ud83d\udd12</div>' +
        '<p class="text-hint">Open from Telegram to view messages</p></div>'
      return
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>'

    // Check if opened with order context
    const hash = window.location.hash || ''
    const orderMatch = hash.match(/[?&]order=([^&]+)/)
    const contextOrderId = orderMatch ? orderMatch[1] : null

    try {
      const messages = await this.api('/' + this.shopId + '/messages')

      let html = ''

      if (contextOrderId) {
        html += '<div class="message-context">' +
          '\ud83d\udce6 About order #' + contextOrderId.substring(0, 8) +
          '<button class="btn-text" style="display:inline;width:auto;padding:0 0 0 8px;font-size:12px" ' +
          'onclick="TMA.navigate(\'#/messages\')">Clear filter</button>' +
          '</div>'
      }

      html += '<div class="message-thread" id="message-thread">'

      if (messages.length === 0) {
        html += '<div class="empty-state" style="padding:24px 0">' +
          '<div class="empty-icon">\ud83d\udcac</div>' +
          '<p class="text-hint">No messages yet</p>' +
          '<p class="text-hint" style="font-size:12px">Send a message and the shop will reply here</p>' +
          '</div>'
      } else {
        messages.forEach(msg => {
          // direction stored from shop perspective: 'in' = customer→shop, 'out' = shop→customer
          // In TMA (customer view): customer's own messages ('in') show on right as msg-out
          const isOut = msg.direction === 'in'
          html += '<div class="message-bubble ' + (isOut ? 'msg-out' : 'msg-in') + '">' +
            (msg.order_id && !contextOrderId
              ? '<div class="message-order">\ud83d\udce6 #' + msg.order_id.substring(0, 8) + '</div>'
              : '') +
            '<div class="message-text">' + this._formatMessageText(msg.content) + '</div>' +
            '<div class="message-time">' + this.formatDate(msg.timestamp) + '</div>' +
            '</div>'
        })
      }

      html += '</div>'

      // Send form
      html += '<form class="message-form" onsubmit="TMA.handleSendMessage(event)">' +
        '<input type="text" class="form-input message-input" id="message-input" ' +
        'placeholder="Type a message\u2026" required autocomplete="off" maxlength="1000">' +
        '<button type="submit" class="btn-send">\u2191</button>' +
        '</form>'

      container.innerHTML = html

      // Scroll to bottom
      const thread = document.getElementById('message-thread')
      if (thread) thread.scrollTop = thread.scrollHeight
    } catch {
      container.innerHTML = '<div class="empty-state">' +
        '<p style="color:var(--tg-theme-destructive-text-color,#e53935)">Failed to load messages</p>' +
        '<button class="btn-text mt-md" onclick="TMA.renderMessages()">Try again</button></div>'
    }
  },

  _formatMessageText(text) {
    if (!text) return ''
    // Escape HTML, then convert newlines to <br>
    return this.escapeHtml(text).replace(/\n/g, '<br>')
  },

  async handleSendMessage(e) {
    e.preventDefault()
    const input = document.getElementById('message-input')
    const content = input.value.trim()
    if (!content) return

    // Check for order context
    const hash = window.location.hash || ''
    const orderMatch = hash.match(/[?&]order=([^&]+)/)
    const orderId = orderMatch ? orderMatch[1] : undefined

    // Disable input while sending
    input.disabled = true

    try {
      await this.api('/' + this.shopId + '/messages', {
        method: 'POST',
        body: { content, order_id: orderId },
      })
      input.value = ''
      input.disabled = false
      this.haptic('impact', 'light')
      await this.renderMessages()
    } catch (e) {
      input.disabled = false
      this.showToast('Failed to send: ' + e.message)
    }
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
    const d = new Date(val.includes('T') || val.includes('Z') ? val : val + 'Z')
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
document.addEventListener('DOMContentLoaded', () => TMA.init())
