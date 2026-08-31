import asyncio
import json
import os
import re
from html import unescape
from urllib.parse import quote, urljoin

import aiohttp
from bs4 import BeautifulSoup

from models import Listing, SearchFilters


UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


class AvitoProvider:
    async def search(self, filters: SearchFilters) -> list[Listing]:
        raise NotImplementedError


class PublicAvitoProvider(AvitoProvider):
    """
    Без AVITO_API_URL и AVITO_API_TOKEN.
    Использует публичные страницы Avito. Avito может ограничивать автоматические запросы,
    поэтому парсер имеет несколько fallback-стратегий.
    """

    def __init__(self):
        self.timeout = int(os.getenv("AVITO_TIMEOUT", "25"))
        self.limit = int(os.getenv("MAX_RESULTS", "10"))

    @staticmethod
    def _city_slug(city: str | None) -> str:
        if not city:
            return "rossiya"
        mapping = {
            "москва": "moskva",
            "санкт-петербург": "sankt-peterburg",
            "спб": "sankt-peterburg",
            "екатеринбург": "ekaterinburg",
            "казань": "kazan",
            "новосибирск": "novosibirsk",
            "нижний новгород": "nizhniy_novgorod",
            "краснодар": "krasnodar",
            "самара": "samara",
            "ростов-на-дону": "rostov-na-donu",
        }
        return mapping.get(city.strip().lower(), quote(city.strip().lower().replace(" ", "-")))

    def _search_urls(self, filters: SearchFilters) -> list[str]:
        city = self._city_slug(filters.city)
        urls = []
        for model in filters.models or ["iPhone"]:
            query = quote(model)
            # Основная публичная категория Avito.
            urls.append(
                f"https://www.avito.ru/{city}/telefony?q={query}"
            )
            urls.append(
                f"https://www.avito.ru/{city}/telefony/iphone?q={query}"
            )
        return list(dict.fromkeys(urls))

    @staticmethod
    def _number(value) -> int:
        if value is None:
            return 0
        m = re.search(r"\d[\d\s]*", str(value).replace("\xa0", " "))
        return int(re.sub(r"\D", "", m.group(0))) if m else 0

    @staticmethod
    def _first(d: dict, *keys, default=None):
        for k in keys:
            if d.get(k) not in (None, ""):
                return d[k]
        return default

    @staticmethod
    def _extract_jsonld(soup: BeautifulSoup) -> list[dict]:
        result = []
        for node in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(node.string or node.get_text())
                if isinstance(data, list):
                    result.extend(x for x in data if isinstance(x, dict))
                elif isinstance(data, dict):
                    result.append(data)
            except Exception:
                pass
        return result

    def _parse_search_page(self, html: str, base_url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "html.parser")
        out = []

        # JSON-LD: наиболее стабильный fallback.
        for item in self._extract_jsonld(soup):
            if item.get("@type") not in {"Product", "Offer"}:
                continue
            offers = item.get("offers") or {}
            url = item.get("url") or offers.get("url")
            price = self._number(offers.get("price") or item.get("price"))
            name = item.get("name") or "iPhone"
            if url and price:
                out.append(Listing(
                    id=self._id_from_url(url),
                    title=unescape(str(name)),
                    model=str(name),
                    price=price,
                    url=urljoin(base_url, url),
                    description=str(item.get("description") or ""),
                    photos=self._images_from_jsonld(item),
                ))

        # Обычные ссылки на объявления.
        seen = {x.url for x in out}
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/item/" not in href and not re.search(r"/\d{6,}", href):
                continue
            url = urljoin(base_url, href.split("?")[0])
            if "avito.ru" not in url or url in seen:
                continue
            text = " ".join(a.stripped_strings)
            price = self._number(text)
            if not price:
                parent = a.find_parent()
                text = " ".join(parent.stripped_strings) if parent else text
                price = self._number(text)
            if not price:
                continue
            title = " ".join(text.split())[:250] or "iPhone"
            out.append(Listing(
                id=self._id_from_url(url),
                title=title,
                model=title,
                price=price,
                url=url,
                description="",
            ))
            seen.add(url)
            if len(out) >= self.limit * 3:
                break

        return self._dedupe(out)

    @staticmethod
    def _images_from_jsonld(item: dict) -> list[str]:
        images = item.get("image") or []
        if isinstance(images, str):
            images = [images]
        return [str(x) for x in images if isinstance(x, str)][:10]

    @staticmethod
    def _id_from_url(url: str) -> str:
        m = re.search(r"/(\d{6,})(?:\?|$)", url)
        return m.group(1) if m else str(abs(hash(url)))

    @staticmethod
    def _dedupe(items: list[Listing]) -> list[Listing]:
        seen = set()
        result = []
        for item in items:
            key = item.url or item.id
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        async with session.get(
            url,
            headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"},
            allow_redirects=True,
        ) as response:
            text = await response.text(errors="ignore")
            if response.status != 200:
                raise RuntimeError(f"Avito HTTP {response.status}")
            return text

    async def _enrich(self, session: aiohttp.ClientSession, listing: Listing) -> Listing:
        try:
            html = await self._fetch(session, listing.url)
        except Exception:
            return listing

        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h1")
        if title:
            listing.title = " ".join(title.stripped_strings)[:300]
            listing.model = listing.title

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            listing.description = unescape(meta_desc["content"])[:5000]

        # Собираем изображения из meta/og и JSON-LD.
        photos = []
        for tag in soup.find_all("meta", property="og:image"):
            if tag.get("content"):
                photos.append(tag["content"])
        for item in self._extract_jsonld(soup):
            photos.extend(self._images_from_jsonld(item))
            offers = item.get("offers") or {}
            price = self._number(offers.get("price") or item.get("price"))
            if price:
                listing.price = price
            if item.get("description") and len(str(item["description"])) > len(listing.description):
                listing.description = str(item["description"])[:5000]
        listing.photos = list(dict.fromkeys(photos))[:10]

        text = normalize_text(" ".join(soup.stripped_strings))
        listing.storage_gb = listing.storage_gb or extract_storage(text)
        listing.battery_percent = listing.battery_percent or extract_battery(text)
        listing.repair_info = listing.repair_info or extract_section(text, ["ремонт", "замен"])
        listing.screen_info = listing.screen_info or extract_section(text, ["экран", "дисплей"])
        return listing

    async def search(self, filters: SearchFilters) -> list[Listing]:
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=8, ssl=False)
        headers = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"}

        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
            all_items = []
            for url in self._search_urls(filters):
                try:
                    html = await self._fetch(session, url)
                    all_items.extend(self._parse_search_page(html, url))
                except Exception as exc:
                    print("AVITO SEARCH:", exc)

            # Обогащаем первые кандидаты параллельно.
            all_items = self._dedupe(all_items)
            all_items = [
                x for x in all_items
                if x.price and (not filters.max_price or x.price <= filters.max_price)
            ][: max(self.limit * 2, 20)]

            enriched = await asyncio.gather(
                *(self._enrich(session, item) for item in all_items),
                return_exceptions=True,
            )
            result = []
            for item in enriched:
                if isinstance(item, Listing):
                    result.append(item)
            return result[:self.limit * 2]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def extract_storage(text: str) -> int | None:
    m = re.search(r"\b(64|128|256|512|1024)\s*(?:гб|gb|гб\.|tb|тб)\b", text, re.I)
    if not m:
        return None
    value = int(m.group(1))
    if m.group(0).lower().find("tb") >= 0 or "тб" in m.group(0).lower():
        value *= 1024
    return value


def extract_battery(text: str) -> int | None:
    patterns = [
        r"(?:аккумулятор|батаре[яи]|состояние аккумулятора|ёмкость)\D{0,30}(\d{2,3})\s*%",
        r"(\d{2,3})\s*%\s*(?:акб|аккумулятор)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 100:
                return n
    return None


def extract_section(text: str, words: list[str]) -> str | None:
    for word in words:
        idx = text.find(word)
        if idx >= 0:
            return text[max(0, idx): idx + 350]
    return None


APIAvitoProvider = PublicAvitoProvider
