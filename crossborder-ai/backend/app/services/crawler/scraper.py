"""商品网页抓取与结构化提取服务。

VeyaShip - Web Scraper Service.

Competitor analysis, product research, and market data collection
using httpx, BeautifulSoup, and Playwright for JavaScript-rendered pages."""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


class WebScraper:
    """Web scraping service for e-commerce data collection."""

    def __init__(self):
        self.http_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

    async def fetch_page(self, url: str) -> str:
        """Fetch HTML content from a URL.

        For static pages uses httpx; for JS-rendered pages,
        Playwright should be used instead.

        Args:
            url: Target URL to scrape.

        Returns:
            HTML content as string.
        """
        response = await self.http_client.get(url)
        response.raise_for_status()
        return response.text

    async def parse_product_page(self, url: str) -> Dict[str, Any]:
        """Parse a product page and extract key information.

        Works with common e-commerce platforms.

        Args:
            url: Product page URL.

        Returns:
            Dict with extracted product data.
        """
        html = await self.fetch_page(url)
        soup = BeautifulSoup(html, "lxml")

        domain = urlparse(url).netloc

        product_data = {
            "url": url,
            "domain": domain,
            "title": self._extract_title(soup),
            "price": self._extract_price(soup),
            "description": self._extract_description(soup),
            "images": self._extract_images(soup),
            "specs": self._extract_specs(soup),
        }

        return product_data

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from common HTML patterns."""
        selectors = [
            "h1[class*='product']",
            "h1[class*='title']",
            "h1[class*='name']",
            "h1",
            "[class*='product-title']",
            "[class*='product-name']",
            "[class*='product__title']",
            "meta[property='og:title']",
        ]

        for selector in selectors:
            if selector.startswith("meta"):
                tag = soup.find("meta", property="og:title")
                if tag and tag.get("content"):
                    return tag["content"]
            else:
                tag = soup.select_one(selector)
                if tag:
                    return tag.get_text(strip=True)

        return soup.title.string if soup.title else None

    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract product price."""
        selectors = [
            "[class*='price'] [class*='current']",
            "[class*='price'][class*='current']",
            "[class*='product-price']",
            "[class*='product__price']",
            "[class*='sale-price']",
            "meta[property='product:price:amount']",
        ]

        for selector in selectors:
            if selector.startswith("meta"):
                tag = soup.find("meta", property="product:price:amount")
                if tag and tag.get("content"):
                    try:
                        return float(tag["content"])
                    except ValueError:
                        continue
            else:
                tag = soup.select_one(selector)
                if tag:
                    text = tag.get_text(strip=True).replace("$", "").replace(",", "")
                    try:
                        return float(text)
                    except ValueError:
                        continue

        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product description."""
        selectors = [
            "[class*='product-description']",
            "[class*='product__description']",
            "[class*='description']",
            "meta[property='og:description']",
            "meta[name='description']",
        ]

        for selector in selectors:
            if "meta" in selector:
                prop = "property" if "property=" in selector else "name"
                tag = soup.find("meta", attrs={prop: selector.split("=")[1].strip("']")})
                if tag and tag.get("content"):
                    return tag["content"]
            else:
                tag = soup.select_one(selector)
                if tag:
                    return tag.get_text(strip=True)[:2000]

        return None

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract product image URLs."""
        images = []

        # Open Graph image
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            images.append(og_image["content"])

        # Product gallery images
        img_selectors = [
            "[class*='product-gallery'] img",
            "[class*='product__image'] img",
            "[class*='product-image'] img",
            ".gallery img",
            "[class*='product'] img[src*='product']",
        ]

        for selector in img_selectors:
            for img in soup.select(selector):
                src = img.get("src") or img.get("data-src")
                if src and src not in images and not src.endswith(".svg"):
                    images.append(src)
                if len(images) >= 5:
                    break
            if len(images) >= 5:
                break

        return images[:5]

    def _extract_specs(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract product specifications from tables or lists."""
        specs = {}

        # Spec tables
        for table in soup.select("table[class*='spec'], [class*='specifications'] table"):
            for row in table.select("tr"):
                cells = row.select("td, th")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        specs[key] = value

        # Spec lists
        for ul in soup.select("[class*='spec'] ul, [class*='attribute'] ul"):
            for li in ul.select("li"):
                text = li.get_text(strip=True)
                if ":" in text:
                    key, value = text.split(":", 1)
                    specs[key.strip()] = value.strip()

        return specs

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
