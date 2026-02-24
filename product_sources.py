from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from loguru import logger

from lnbits.helpers import create_access_token
from lnbits.settings import settings

from .helpers import image_hash
from .models import ShopProduct


def _internal_token(user_id: str) -> str:
    """Create a short-lived access token for internal cross-extension calls."""
    return create_access_token(
        {"sub": "", "usr": user_id}, token_expire_minutes=1
    )


def _internal_url(path: str) -> str:
    """Build internal URL using host:port (not lnbits_baseurl)."""
    return f"http://{settings.host}:{settings.port}{path}"

# In-memory image cache for proxied data-URI images
_image_cache: dict[str, bytes] = {}

_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_telegram_reachable_url(url: str) -> bool:
    """Return True if *url* is an HTTP(S) URL reachable from Telegram's servers.

    Rejects data URIs, bare strings, localhost, and private RFC-1918 IPs.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    if host in _PRIVATE_HOSTS:
        return False
    # Reject RFC-1918 / link-local ranges
    if host.startswith(("10.", "192.168.", "172.")):
        return False
    if host.startswith("169.254."):
        return False
    return True


def _parse_csv_tags(csv_str: Optional[str]) -> List[str]:
    """Parse a comma-separated tag string into a lowercase list."""
    if not csv_str:
        return []
    return [t.strip().lower() for t in csv_str.split(",") if t.strip()]


class InventorySettings:
    """Inventory-level settings that apply to all items."""

    def __init__(
        self,
        omit_tags: List[str],
        global_discount_percentage: float = 0.0,
        default_tax_rate: float = 0.0,
        is_tax_inclusive: bool = True,
        currency: str = "sat",
    ):
        self.omit_tags = omit_tags
        self.global_discount_percentage = global_discount_percentage
        self.default_tax_rate = default_tax_rate
        self.is_tax_inclusive = is_tax_inclusive
        self.currency = currency


async def fetch_inventory_settings(
    user_id: str,
) -> InventorySettings:
    """
    Fetch settings from the Inventory extension.

    Returns omit_tags, global_discount_percentage, default_tax_rate,
    is_tax_inclusive, and currency from the Inventory object.

    Endpoint: GET /inventory/api/v1
    Auth: check_user_exists — uses internal access token
    Returns: single Inventory object or null
    """
    url = _internal_url("/inventory/api/v1")
    token = _internal_token(user_id)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                inventory = resp.json()
                if inventory:
                    return InventorySettings(
                        omit_tags=_parse_csv_tags(
                            inventory.get("omit_tags")
                        ),
                        global_discount_percentage=float(
                            inventory.get(
                                "global_discount_percentage", 0
                            )
                        ),
                        default_tax_rate=float(
                            inventory.get("default_tax_rate", 0)
                        ),
                        is_tax_inclusive=inventory.get(
                            "is_tax_inclusive", True
                        ),
                        currency=inventory.get("currency", "sat"),
                    )
    except Exception as e:
        logger.warning(f"Failed to fetch inventory settings: {e}")
    return InventorySettings(omit_tags=[])


async def fetch_inventory_products(
    inventory_id: str,
    user_id: str,
    include_tags: Optional[str] = None,
    omit_tags: Optional[str] = None,
) -> List[ShopProduct]:
    """
    Fetch products from the Inventory extension, honouring omit_tags.

    1. Fetch the inventory's omit_tags (exclusion filter).
    2. Fetch all active, approved items via the paginated endpoint.
    3. Skip any item whose tags overlap with the omit_tags.

    Endpoint: GET /inventory/api/v1/items/{inventory_id}/paginated
    Auth: optional_user_id — uses internal access token
    Response: Page format {"data": [...], "total": int}

    Tags are comma-separated strings.
    Images are ||| delimited strings.
    """
    # Step 1 — fetch inventory-level settings (omit_tags, defaults)
    inv = await fetch_inventory_settings(user_id)

    # Step 2 — fetch all items (paginated)
    url = _internal_url(
        f"/inventory/api/v1/items/{inventory_id}/paginated"
    )
    all_items: list[dict] = []
    offset = 0
    limit = 50
    token = _internal_token(user_id)

    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "limit": limit,
                    "offset": offset,
                    "is_active": True,
                    "is_approved": True,
                },
            )
            resp.raise_for_status()
            page = resp.json()

            items = page.get("data", [])
            all_items.extend(items)

            total = page.get("total", 0)
            offset += limit
            if offset >= total or not items:
                break

    products = []
    omit_set = set(inv.omit_tags)
    skipped = 0
    for item in all_items:
        # Parse images — inventory stores as ||| or comma separated.
        # Values can be: full URLs, data: URIs, or bare asset IDs.
        images_str = item.get("images") or ""
        sep = "|||" if "|||" in images_str else ","
        image_list = (
            [img.strip() for img in images_str.split(sep) if img.strip()]
            if images_str
            else []
        )
        resolved_urls: List[str] = []
        for raw_img in image_list[:5]:
            if raw_img.startswith("data:"):
                # Only proxy data URIs if lnbits_baseurl is reachable
                proxy_url = (
                    f"{settings.lnbits_baseurl}"
                    f"/telegramshop/api/v1/image/{image_hash(raw_img)}"
                )
                if _is_telegram_reachable_url(proxy_url):
                    img_id = image_hash(raw_img)
                    _image_cache[img_id] = _decode_data_uri(raw_img)
                    resolved_urls.append(proxy_url)
            elif raw_img.startswith(("http://", "https://")):
                resolved_urls.append(raw_img)
            elif raw_img.startswith("/api/"):
                # Relative API path — make absolute so Telegram can reach it
                resolved_urls.append(
                    f"{settings.lnbits_baseurl.rstrip('/')}{raw_img}"
                )
            else:
                # Bare asset ID from inventory — resolve to assets API
                resolved_urls.append(
                    f"{settings.lnbits_baseurl.rstrip('/')}"
                    f"/api/v1/assets/{raw_img}/binary"
                )
        image_url = resolved_urls[0] if resolved_urls else None

        # Parse tags (comma-separated)
        tags_str = item.get("tags") or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        tags_lower = [t.lower() for t in tags]

        # Also check per-item omit_tags
        item_omit = _parse_csv_tags(item.get("omit_tags"))

        # Step 3 — skip items whose tags overlap with omit_tags
        if omit_set and any(t in omit_set for t in tags_lower):
            skipped += 1
            continue

        category = tags[0] if tags else None

        # Determine shipping requirement
        weight = item.get("weight_grams") or 0
        has_physical_tag = any(
            t.lower() in ("physical", "shipping") for t in tags
        )
        requires_shipping = weight > 0 or has_physical_tag

        # Apply inventory-level defaults for tax and discount
        item_tax = (
            float(item["tax_rate"])
            if item.get("tax_rate") is not None
            else (inv.default_tax_rate if inv.default_tax_rate > 0 else None)
        )
        item_discount = (
            float(item["discount_percentage"])
            if item.get("discount_percentage") is not None
            else (
                inv.global_discount_percentage
                if inv.global_discount_percentage > 0
                else None
            )
        )

        products.append(
            ShopProduct(
                id=item["id"],
                title=item.get("name", "Unnamed"),
                description=item.get("description"),
                price=float(item.get("price", 0)),
                image_url=image_url,
                image_urls=resolved_urls,
                category=category,
                tags=tags,
                sku=item.get("sku"),
                tax_rate=item_tax,
                is_tax_inclusive=inv.is_tax_inclusive,
                inventory=item.get("quantity_in_stock"),
                discount_percentage=item_discount,
                disabled=not item.get("is_active", True),
                requires_shipping=requires_shipping,
                weight_grams=weight,
            )
        )
    if skipped > 0:
        logger.info(
            f"Omit filter: excluded {skipped} item(s) "
            f"matching tags {inv.omit_tags}"
        )

    # Shop-level tag filtering
    shop_include = set(_parse_csv_tags(include_tags))
    shop_omit = set(_parse_csv_tags(omit_tags))

    if shop_include or shop_omit:
        filtered = []
        for p in products:
            p_tags = {t.lower() for t in p.tags}
            if shop_include and not p_tags.intersection(shop_include):
                continue
            if shop_omit and p_tags.intersection(shop_omit):
                continue
            filtered.append(p)
        shop_filtered = len(products) - len(filtered)
        if shop_filtered > 0:
            logger.info(
                f"Shop tag filter: excluded {shop_filtered} item(s) "
                f"(include={list(shop_include)}, omit={list(shop_omit)})"
            )
        products = filtered

    return products


async def deduct_inventory_stock(
    inventory_id: str,
    items: List[Tuple[str, int]],
    user_id: str,
) -> None:
    """
    Deduct stock via Inventory extension.

    Endpoint: PATCH /inventory/api/v1/items/{inventory_id}/quantities
    Auth: check_user_exists — uses internal access token
    Params: ids (list), quantities (list), source (str) — as QUERY PARAMS
    """
    if not items:
        return

    ids = [item_id for item_id, _ in items]
    quantities = [qty for _, qty in items]
    token = _internal_token(user_id)

    url = _internal_url(
        f"/inventory/api/v1/items/{inventory_id}/quantities"
    )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "ids": ids,
                "quantities": quantities,
                "source": "telegramshop",
            },
        )
        if resp.status_code != 200:
            logger.warning(
                f"Stock deduction failed ({resp.status_code}): {resp.text}"
            )


def get_cached_image(img_id: str) -> Optional[bytes]:
    return _image_cache.get(img_id)


def _decode_data_uri(data_uri: str) -> bytes:
    import base64

    _, data = data_uri.split(",", 1)
    return base64.b64decode(data)
