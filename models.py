from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class CheckoutMode(str, Enum):
    NONE = "none"
    EMAIL = "email"
    ADDRESS = "address"


class CommercialType(str, Enum):
    ABANDONED_CART = "abandoned_cart"
    BACK_IN_STOCK = "back_in_stock"
    PROMOTION = "promotion"
    POST_PURCHASE = "post_purchase"


class UserState(str, Enum):
    BROWSING = "browsing"


class FulfillmentStatus(str, Enum):
    PREPARING = "preparing"
    SHIPPING = "shipping"
    DELIVERED = "delivered"


class ReturnStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REFUNDED = "refunded"
    DENIED = "denied"


class RefundMethod(str, Enum):
    LIGHTNING = "lightning"
    CREDIT = "credit"


# --- DB Models ---


class CreateShop(BaseModel):
    title: str
    description: Optional[str] = None
    bot_token: str
    currency: str = "sat"
    inventory_id: str
    checkout_mode: CheckoutMode = CheckoutMode.NONE
    enable_order_tracking: bool = False
    use_webhook: bool = False
    admin_chat_id: Optional[str] = None
    allow_returns: bool = True
    allow_credit_refund: bool = True
    return_window_hours: int = 720
    shipping_flat_rate: float = 0
    shipping_free_threshold: float = 0
    shipping_per_kg: float = 0
    include_tags: Optional[str] = None
    omit_tags: Optional[str] = None


class Shop(CreateShop):
    id: str
    wallet: str
    is_enabled: bool = False
    webhook_secret: Optional[str] = None
    timestamp: str


class ShopResponse(BaseModel):
    """Shop data returned to the frontend — secrets excluded."""
    id: str
    wallet: str
    title: str
    description: Optional[str] = None
    currency: str = "sat"
    inventory_id: str
    checkout_mode: CheckoutMode = CheckoutMode.NONE
    enable_order_tracking: bool = False
    use_webhook: bool = False
    admin_chat_id: Optional[str] = None
    allow_returns: bool = True
    allow_credit_refund: bool = True
    return_window_hours: int = 720
    shipping_flat_rate: float = 0
    shipping_free_threshold: float = 0
    shipping_per_kg: float = 0
    include_tags: Optional[str] = None
    omit_tags: Optional[str] = None
    is_enabled: bool = False
    timestamp: str
    bot_username: Optional[str] = None

    @classmethod
    def from_shop(cls, shop: "Shop", bot_username: Optional[str] = None):
        d = shop.dict(exclude={"bot_token", "webhook_secret"})
        d["bot_username"] = bot_username
        return cls(**d)


class Order(BaseModel):
    id: str
    shop_id: str
    payment_hash: Optional[str] = None
    telegram_chat_id: int
    telegram_username: Optional[str] = None
    amount_sats: int
    currency: str
    currency_amount: float
    cart_json: str
    buyer_email: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    has_physical_items: bool = False
    credit_used: int = 0
    status: str = "pending"
    fulfillment_status: Optional[str] = None
    fulfillment_note: Optional[str] = None
    timestamp: str


class Message(BaseModel):
    id: str
    shop_id: str
    order_id: Optional[str] = None
    chat_id: int
    username: Optional[str] = None
    direction: str
    content: str
    is_read: bool = False
    telegram_message_id: Optional[int] = None
    timestamp: str


class Return(BaseModel):
    id: str
    shop_id: str
    order_id: str
    chat_id: int
    items_json: str
    reason: Optional[str] = None
    refund_method: Optional[str] = None
    refund_amount_sats: int
    status: str = "requested"
    admin_note: Optional[str] = None
    timestamp: str


class Credit(BaseModel):
    id: str
    shop_id: str
    chat_id: int
    amount_sats: int
    used_sats: int = 0
    source_return_id: Optional[str] = None
    timestamp: str


# --- Internal (not persisted) ---


class ShopProduct(BaseModel):
    """Normalized product from Inventory extension"""
    id: str
    title: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    image_urls: List[str] = []
    category: Optional[str] = None
    tags: List[str] = []
    sku: Optional[str] = None
    tax_rate: Optional[float] = None
    is_tax_inclusive: bool = True
    inventory: Optional[int] = None
    discount_percentage: Optional[float] = None
    disabled: bool = False
    requires_shipping: bool = False
    weight_grams: int = 0


class BuyerAddress(BaseModel):
    name: str
    street: str
    street2: Optional[str] = None
    po_box: Optional[str] = None
    city: str
    state: Optional[str] = None
    zip_code: str
    country: str


class CartItem(BaseModel):
    product_id: str
    title: str
    quantity: int
    price: float
    sku: Optional[str] = None


class UserSession:
    def __init__(self):
        self.state: UserState = UserState.BROWSING
        self.cart: List[CartItem] = []
        self.username: Optional[str] = None


# --- API Request Models ---


class UpdateFulfillment(BaseModel):
    status: FulfillmentStatus
    note: Optional[str] = None


class SendMessage(BaseModel):
    chat_id: int
    content: str
    order_id: Optional[str] = None


class ApproveReturn(BaseModel):
    refund_method: RefundMethod
    refund_amount_sats: Optional[int] = None


class DenyReturn(BaseModel):
    admin_note: str


class TestToken(BaseModel):
    bot_token: str


class CreateCommercial(BaseModel):
    shop_id: str
    type: CommercialType
    title: str
    content: str
    image_url: Optional[str] = None
    delay_minutes: int = 60


class UpdateCommercial(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    is_enabled: Optional[bool] = None
    delay_minutes: Optional[int] = None


# --- DB Models: TMA ---


class Cart(BaseModel):
    id: str
    shop_id: str
    chat_id: int
    cart_json: str
    updated_at: str


class Customer(BaseModel):
    id: str
    shop_id: str
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    first_seen: str
    last_active: str


class Commercial(BaseModel):
    id: str
    shop_id: str
    type: str
    title: str
    content: str
    image_url: Optional[str] = None
    is_enabled: bool = True
    delay_minutes: int = 60
    last_known_stock: Optional[str] = None
    created_at: str


class CommercialLog(BaseModel):
    id: str
    commercial_id: str
    shop_id: str
    chat_id: int
    order_id: Optional[str] = None
    sent_at: str


# --- TMA Request/Response Models ---


class TmaAuthRequest(BaseModel):
    init_data: str
    shop_id: str


class TmaAuthResponse(BaseModel):
    chat_id: int
    username: Optional[str] = None
    shop_title: str
    shop_currency: str
    checkout_mode: str
    allow_returns: bool
    welcome_text: Optional[str] = None
    bot_username: Optional[str] = None


class TmaCartUpdate(BaseModel):
    items: List[CartItem]


class TmaCheckoutRequest(BaseModel):
    buyer_email: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None


class TmaReturnRequest(BaseModel):
    order_id: str
    items_json: str
    reason: str


class TmaMessageRequest(BaseModel):
    content: str
    order_id: Optional[str] = None


class TmaUser(BaseModel):
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None


# --- TMA Admin Request/Response Models ---


class TmaAdminAuthResponse(BaseModel):
    chat_id: int
    username: Optional[str] = None
    shop_id: str
    shop_title: str
    shop_currency: str
    enable_order_tracking: bool = False
    allow_returns: bool = True


class TmaAdminReply(BaseModel):
    chat_id: int
    content: str
    order_id: Optional[str] = None


class TmaAdminFulfillment(BaseModel):
    status: FulfillmentStatus
    note: Optional[str] = None


class TmaAdminApproveReturn(BaseModel):
    refund_method: RefundMethod
    refund_amount_sats: Optional[int] = None


class TmaAdminDenyReturn(BaseModel):
    admin_note: str
