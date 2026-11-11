"""VeyaShip - Shopify Integration Service.

REST API integration for importing products, syncing listings,
and managing Shopify stores.
"""

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

from app.core.config import settings


class ShopifyService:
    """Service for Shopify REST API integration.

    Handles OAuth token exchange, product import, listing sync,
    and order management.
    """

    def __init__(self, shop_name: str, access_token: str):
        self.shop_name = shop_name
        self.access_token = access_token
        self.api_version = settings.SHOPIFY_API_VERSION
        self.base_url = f"https://{shop_name}.myshopify.com/admin/api/{self.api_version}"

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }

    async def get_products(
        self,
        limit: int = 50,
        since_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch products from Shopify.

        Args:
            limit: Products per page (max 250).
            since_id: Pagination cursor.

        Returns:
            List of Shopify product dicts.
        """
        params: Dict[str, Any] = {"limit": min(limit, 250)}
        if since_id:
            params["since_id"] = since_id

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products.json",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("products", [])

    async def get_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Get a single product from Shopify."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products/{product_id}.json",
                headers=self._headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("product")

    async def create_product(
        self,
        title: str,
        body_html: Optional[str] = None,
        vendor: Optional[str] = None,
        product_type: Optional[str] = None,
        status: str = "draft",
        variants: Optional[List[Dict]] = None,
        images: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Create a new product in Shopify."""
        product_data: Dict[str, Any] = {
            "product": {
                "title": title,
                "status": status,
            }
        }

        if body_html:
            product_data["product"]["body_html"] = body_html
        if vendor:
            product_data["product"]["vendor"] = vendor
        if product_type:
            product_data["product"]["product_type"] = product_type
        if variants:
            product_data["product"]["variants"] = variants
        if images:
            product_data["product"]["images"] = images

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/products.json",
                headers=self._headers(),
                json=product_data,
            )
            response.raise_for_status()
            return response.json().get("product", {})

    async def update_product(
        self,
        product_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """Update an existing product in Shopify."""
        update_data: Dict[str, Any] = {"product": kwargs}

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/products/{product_id}.json",
                headers=self._headers(),
                json=update_data,
            )
            response.raise_for_status()
            return response.json().get("product", {})

    async def get_orders(
        self,
        status: str = "any",
        limit: int = 50,
        fulfillment_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch orders from Shopify.

        Args:
            status: Order status (open, closed, cancelled, any).
            limit: Max results per page.
            fulfillment_status: Filter by fulfillment (shipped, partial, unshipped).

        Returns:
            List of order dicts.
        """
        params: Dict[str, Any] = {
            "status": status,
            "limit": min(limit, 250),
        }
        if fulfillment_status:
            params["fulfillment_status"] = fulfillment_status

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders.json",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json().get("orders", [])

    async def get_shop_info(self) -> Dict[str, Any]:
        """Get Shopify shop information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/shop.json",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json().get("shop", {})
