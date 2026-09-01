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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


class AvitoProvider:

    async def search(
        self,
        filters: SearchFilters,
    ) -> list[Listing]:
        raise NotImplementedError


class PublicAvitoProvider(AvitoProvider):

    def __init__(self):
        self.timeout = int(
            os.getenv("AVITO_TIMEOUT", "30")
        )

        self.limit = int(
            os.getenv("MAX_RESULTS", "10")
        )

    # =========================================================
    # CITY
    # =========================================================

    @staticmethod
    def _city_slug(
        city: str | None,
    ) -> str:

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
            "воронеж": "voronezh",
            "пермь": "perm",
            "уфа": "ufa",
            "челябинск": "chelyabinsk",
            "омск": "omsk",
            "тюмень": "tyumen",
            "сочи": "sochi",
        }

        normalized = city.strip().lower()

        return mapping.get(
            normalized,
            quote(
                normalized.replace(
                    " ",
                    "-",
                )
            ),
        )

    # =========================================================
    # SEARCH URL
    # =========================================================

    def _search_urls(
        self,
        filters: SearchFilters,
    ) -> list[str]:

        city = self._city_slug(
            filters.city
        )

        models = (
            filters.models
            or ["iPhone"]
        )

        urls = []

        for model in models:

            query = quote(model)

            urls.append(
                f"https://www.avito.ru/"
                f"{city}/telefony"
                f"?q={query}"
            )

            urls.append(
                f"https://www.avito.ru/"
                f"{city}/telefony/iphone"
                f"?q={query}"
            )

        return list(
            dict.fromkeys(urls)
        )

    # =========================================================
    # NUMBER
    # =========================================================

    @staticmethod
    def _number(
        value,
    ) -> int:

        if value is None:
            return 0

        text = (
            str(value)
            .replace("\xa0", " ")
        )

        # Сначала ищем число рядом с ₽.
        price_match = re.search(
            r"(\d[\d\s]{2,})\s*(?:₽|руб)",
            text,
            re.I,
        )

        if price_match:

            digits = re.sub(
                r"\D",
                "",
                price_match.group(1),
            )

            if digits:
                return int(digits)

        # Обычный fallback.
        matches = re.findall(
            r"\d[\d\s]*",
            text,
        )

        for match in matches:

            digits = re.sub(
                r"\D",
                "",
                match,
            )

            if not digits:
                continue

            number = int(digits)

            if 1000 <= number <= 10000000:
                return number

        return 0

    # =========================================================
    # JSON-LD
    # =========================================================

    @staticmethod
    def _extract_jsonld(
        soup: BeautifulSoup,
    ) -> list[dict]:

        result = []

        for node in soup.find_all(
            "script",
            type="application/ld+json",
        ):

            try:

                raw = (
                    node.string
                    or node.get_text()
                )

                data = json.loads(
                    raw
                )

                if isinstance(
                    data,
                    list,
                ):

                    result.extend(
                        x
                        for x in data
                        if isinstance(
                            x,
                            dict,
                        )
                    )

                elif isinstance(
                    data,
                    dict,
                ):

                    result.append(
                        data
                    )

            except Exception:
                continue

        return result

    # =========================================================
    # JSON-LD PARSER
    # =========================================================

    def _parse_jsonld(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[Listing]:

        result = []

        for item in self._extract_jsonld(
            soup
        ):

            item_type = item.get(
                "@type"
            )

            if item_type not in {
                "Product",
                "Offer",
                "ProductGroup",
            }:
                continue

            offers = (
                item.get("offers")
                or {}
            )

            if isinstance(
                offers,
                list,
            ):

                offers = (
                    offers[0]
                    if offers
                    else {}
                )

            url = (
                item.get("url")
                or offers.get("url")
            )

            price = self._number(
                offers.get("price")
                or item.get("price")
            )

            title = (
                item.get("name")
                or "iPhone"
            )

            if not url:
                continue

            if not price:
                continue

            url = urljoin(
                base_url,
                str(url),
            )

            result.append(
                Listing(
                    id=self._id_from_url(
                        url
                    ),
                    title=unescape(
                        str(title)
                    ),
                    model=str(title),
                    price=price,
                    url=url,
                    description=str(
                        item.get(
                            "description",
                            "",
                        )
                    ),
                    photos=self._images_from_jsonld(
                        item
                    ),
                )
            )

        return result

    # =========================================================
    # CARD PARSER
    # =========================================================

    def _parse_card(
        self,
        card,
        base_url: str,
    ) -> Listing | None:

        # -----------------------------------------------------
        # TITLE + LINK
        # -----------------------------------------------------

        link = (
            card.find(
                "a",
                attrs={
                    "data-marker": "item-title"
                },
            )
            or card.find(
                "a",
                href=True,
            )
        )

        if not link:
            return None

        href = link.get(
            "href",
            "",
        )

        if not href:
            return None

        url = urljoin(
            base_url,
            href,
        )

        url = url.split("?")[0]

        if (
            "avito.ru" not in url
            or url.rstrip("/").endswith(
                "avito.ru"
            )
        ):
            return None

        # -----------------------------------------------------
        # TITLE
        # -----------------------------------------------------

        title_node = (
            card.find(
                "h3",
                attrs={
                    "data-marker": "item-title"
                },
            )
            or card.find("h3")
        )

        if title_node:

            title = " ".join(
                title_node.stripped_strings
            )

        else:

            title = " ".join(
                link.stripped_strings
            )

        title = (
            unescape(title)
            .strip()
        )

        if not title:
            title = "iPhone"

        # -----------------------------------------------------
        # PRICE
        # -----------------------------------------------------

        price = 0

        # itemprop price
        price_meta = card.find(
            attrs={
                "itemprop": "price"
            }
        )

        if price_meta:

            price = self._number(
                price_meta.get(
                    "content"
                )
            )

        # data-marker
        if not price:

            price_node = (
                card.find(
                    attrs={
                        "data-marker": re.compile(
                            r"item-price",
                            re.I,
                        )
                    }
                )
                or card.find(
                    class_=re.compile(
                        r"price",
                        re.I,
                    )
                )
            )

            if price_node:

                price = self._number(
                    price_node.get_text(
                        " ",
                        strip=True,
                    )
                )

        # Entire card fallback
        if not price:

            card_text = card.get_text(
                " ",
                strip=True,
            )

            price = self._number(
                card_text
            )

        if not price:
            return None

        # -----------------------------------------------------
        # DESCRIPTION
        # -----------------------------------------------------

        description = ""

        desc_node = (
            card.find(
                class_=re.compile(
                    r"description",
                    re.I,
                )
            )
        )

        if desc_node:

            description = " ".join(
                desc_node.stripped_strings
            )

        # -----------------------------------------------------
        # IMAGE
        # -----------------------------------------------------

        photos = []

        for image in card.find_all(
            "img"
        ):

            src = (
                image.get("src")
                or image.get(
                    "data-src"
                )
                or image.get(
                    "srcset"
                )
            )

            if src:

                if "," in src:
                    src = src.split(
                        ","
                    )[0].strip()

                photos.append(
                    urljoin(
                        base_url,
                        src,
                    )
                )

        return Listing(
            id=self._id_from_url(
                url
            ),
            title=title,
            model=title,
            price=price,
            url=url,
            description=description,
            photos=list(
                dict.fromkeys(
                    photos
                )
            )[:10],
        )

    # =========================================================
    # SEARCH PAGE PARSER
    # =========================================================

    def _parse_search_page(
        self,
        html: str,
        base_url: str,
    ) -> list[Listing]:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        result = []

        # -----------------------------------------------------
        # DEBUG
        # -----------------------------------------------------

        print(
            "AVITO HTML SIZE:",
            len(html),
        )

        if (
            "captcha" in html.lower()
            or "докажите, что вы человек"
            in html.lower()
        ):

            print(
                "AVITO: CAPTCHA DETECTED"
            )

        # -----------------------------------------------------
        # 1. data-marker=item
        # -----------------------------------------------------

        cards = soup.find_all(
            attrs={
                "data-marker": "item"
            }
        )

        print(
            "AVITO CARDS:",
            len(cards),
        )

        for card in cards:

            try:

                listing = self._parse_card(
                    card,
                    base_url,
                )

                if listing:
                    result.append(
                        listing
                    )

            except Exception as exc:

                print(
                    "AVITO CARD ERROR:",
                    repr(exc),
                )

        # -----------------------------------------------------
        # 2. catalog-serp
        # -----------------------------------------------------

        if not result:

            container = soup.find(
                attrs={
                    "data-marker": "catalog-serp"
                }
            )

            if container:

                cards = container.find_all(
                    "div",
                    attrs={
                        "data-marker": "item"
                    }
                )

                print(
                    "AVITO CATALOG CARDS:",
                    len(cards),
                )

                for card in cards:

                    try:

                        listing = (
                            self._parse_card(
                                card,
                                base_url,
                            )
                        )

                        if listing:
                            result.append(
                                listing
                            )

                    except Exception:
                        continue

        # -----------------------------------------------------
        # 3. JSON-LD
        # -----------------------------------------------------

        if not result:

            result.extend(
                self._parse_jsonld(
                    soup,
                    base_url,
                )
            )

        # -----------------------------------------------------
        # 4. LINKS WITH data-marker
        # -----------------------------------------------------

        if not result:

            links = soup.find_all(
                "a",
                attrs={
                    "data-marker": "item-title"
                },
            )

            print(
                "AVITO TITLE LINKS:",
                len(links),
            )

            for link in links:

                try:

                    href = link.get(
                        "href",
                        "",
                    )

                    if not href:
                        continue

                    url = urljoin(
                        base_url,
                        href,
                    )

                    parent = (
                        link.find_parent(
                            [
                                "div",
                                "article",
                                "li",
                            ]
                        )
                    )

                    text = " ".join(
                        (
                            parent
                            or link
                        ).stripped_strings
                    )

                    price = self._number(
                        text
                    )

                    if not price:
                        continue

                    title = " ".join(
                        link.stripped_strings
                    ) or "iPhone"

                    result.append(
                        Listing(
                            id=self._id_from_url(
                                url
                            ),
                            title=title,
                            model=title,
                            price=price,
                            url=url,
                        )
                    )

                except Exception:
                    continue

        # -----------------------------------------------------
        # 5. OLD FALLBACK
        # -----------------------------------------------------

        if not result:

            seen = set()

            for a in soup.find_all(
                "a",
                href=True,
            ):

                href = a.get(
                    "href",
                    "",
                )

                if not href:
                    continue

                # Более мягкое условие.
                if (
                    "/item/" not in href
                    and not re.search(
                        r"/\d{7,}",
                        href,
                    )
                    and "iphone" not in href.lower()
                ):
                    continue

                url = urljoin(
                    base_url,
                    href,
                )

                url = url.split("?")[0]

                if url in seen:
                    continue

                if (
                    "avito.ru" not in url
                ):
                    continue

                parent = (
                    a.find_parent(
                        [
                            "div",
                            "article",
                            "li",
                        ]
                    )
                )

                node = (
                    parent
                    or a
                )

                text = " ".join(
                    node.stripped_strings
                )

                price = self._number(
                    text
                )

                if not price:
                    continue

                title = " ".join(
                    a.stripped_strings
                ) or "iPhone"

                result.append(
                    Listing(
                        id=self._id_from_url(
                            url
                        ),
                        title=title[:250],
                        model=title[:250],
                        price=price,
                        url=url,
                    )
                )

                seen.add(url)

                if len(result) >= (
                    self.limit * 3
                ):
                    break

        result = self._dedupe(
            result
        )

        print(
            "AVITO FOUND:",
            len(result),
        )

        return result

    # =========================================================
    # IMAGES
    # =========================================================

    @staticmethod
    def _images_from_jsonld(
        item: dict,
    ) -> list[str]:

        images = (
            item.get("image")
            or []
        )

        if isinstance(
            images,
            str,
        ):
            images = [images]

        return [
            str(x)
            for x in images
            if isinstance(
                x,
                str,
            )
        ][:10]

    # =========================================================
    # ID
    # =========================================================

    @staticmethod
    def _id_from_url(
        url: str,
    ) -> str:

        match = re.search(
            r"/(\d{6,})(?:[/?#]|$)",
            url,
        )

        if match:
            return match.group(1)

        return str(
            abs(
                hash(url)
            )
        )

    # =========================================================
    # DEDUPE
    # =========================================================

    @staticmethod
    def _dedupe(
        items: list[Listing],
    ) -> list[Listing]:

        seen = set()
        result = []

        for item in items:

            key = (
                item.url
                or item.id
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(item)

        return result

    # =========================================================
    # HTTP
    # =========================================================

    async def _fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> str:

        async with session.get(
            url,
            headers={
                "User-Agent": UA,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/xml;q=0.9,"
                    "image/avif,"
                    "image/webp,"
                    "*/*;q=0.8"
                ),
                "Accept-Language": (
                    "ru-RU,ru;q=0.9"
                ),
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://www.avito.ru/",
            },
            allow_redirects=True,
        ) as response:

            text = await response.text(
                errors="ignore"
            )

            print(
                f"AVITO HTTP {response.status}: "
                f"{url}"
            )

            if response.status != 200:

                raise RuntimeError(
                    f"Avito HTTP {response.status}"
                )

            return text

    # =========================================================
    # ENRICH
    # =========================================================

    async def _enrich(
        self,
        session: aiohttp.ClientSession,
        listing: Listing,
    ) -> Listing:

        try:

            html = await self._fetch(
                session,
                listing.url,
            )

        except Exception as exc:

            print(
                "AVITO ENRICH:",
                repr(exc),
            )

            return listing

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        title = soup.find(
            "h1"
        )

        if title:

            listing.title = (
                " ".join(
                    title.stripped_strings
                )[:300]
            )

            listing.model = (
                listing.title
            )

        meta_desc = soup.find(
            "meta",
            attrs={
                "name": "description"
            },
        )

        if (
            meta_desc
            and meta_desc.get("content")
        ):

            listing.description = (
                unescape(
                    meta_desc["content"]
                )[:5000]
            )

        photos = []

        for tag in soup.find_all(
            "meta",
            property="og:image",
        ):

            if tag.get("content"):
                photos.append(
                    tag["content"]
                )

        for item in self._extract_jsonld(
            soup
        ):

            photos.extend(
                self._images_from_jsonld(
                    item
                )
            )

            offers = (
                item.get("offers")
                or {}
            )

            if isinstance(
                offers,
                list,
            ):

                offers = (
                    offers[0]
                    if offers
                    else {}
                )

            price = self._number(
                offers.get("price")
                or item.get("price")
            )

            if price:
                listing.price = price

            description = item.get(
                "description"
            )

            if description:

                description = str(
                    description
                )

                if len(description) > len(
                    listing.description
                ):

                    listing.description = (
                        description[:5000]
                    )

        listing.photos = list(
            dict.fromkeys(
                photos
            )
        )[:10]

        text = normalize_text(
            " ".join(
                soup.stripped_strings
            )
        )

        listing.storage_gb = (
            listing.storage_gb
            or extract_storage(text)
        )

        listing.battery_percent = (
            listing.battery_percent
            or extract_battery(text)
        )

        listing.repair_info = (
            listing.repair_info
            or extract_section(
                text,
                [
                    "ремонт",
                    "замен",
                ],
            )
        )

        listing.screen_info = (
            listing.screen_info
            or extract_section(
                text,
                [
                    "экран",
                    "дисплей",
                ],
            )
        )

        return listing

    # =========================================================
    # SEARCH
    # =========================================================

    async def search(
        self,
        filters: SearchFilters,
    ) -> list[Listing]:

        timeout = aiohttp.ClientTimeout(
            total=self.timeout
        )

        connector = aiohttp.TCPConnector(
            limit=8,
            ssl=False,
        )

        headers = {
            "User-Agent": UA,
            "Accept-Language": (
                "ru-RU,ru;q=0.9"
            ),
        }

        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=headers,
        ) as session:

            all_items = []

            urls = self._search_urls(
                filters
            )

            print(
                "AVITO SEARCH URLS:",
                urls,
            )

            for url in urls:

                try:

                    html = await self._fetch(
                        session,
                        url,
                    )

                    items = (
                        self._parse_search_page(
                            html,
                            url,
                        )
                    )

                    print(
                        "AVITO PAGE RESULTS:",
                        len(items),
                    )

                    all_items.extend(
                        items
                    )

                except Exception as exc:

                    print(
                        "AVITO SEARCH ERROR:",
                        repr(exc),
                    )

            all_items = self._dedupe(
                all_items
            )

            print(
                "AVITO TOTAL BEFORE PRICE:",
                len(all_items),
            )

            # ВАЖНО:
            # пока НЕ фильтруем по АКБ/памяти/ремонту.
            # Здесь только бюджет.
            if filters.max_price:

                all_items = [
                    item
                    for item in all_items
                    if item.price
                    and item.price
                    <= filters.max_price
                ]

            if filters.min_price:

                all_items = [
                    item
                    for item in all_items
                    if item.price
                    >= filters.min_price
                ]

            print(
                "AVITO TOTAL AFTER PRICE:",
                len(all_items),
            )

            candidates = all_items[
                :max(
                    self.limit * 2,
                    20,
                )
            ]

            if not candidates:
                return []

            enriched = await asyncio.gather(
                *(
                    self._enrich(
                        session,
                        item,
                    )
                    for item in candidates
                ),
                return_exceptions=True,
            )

            result = []

            for item in enriched:

                if isinstance(
                    item,
                    Listing,
                ):
                    result.append(
                        item
                    )

            print(
                "AVITO FINAL:",
                len(result),
            )

            return result[
                :self.limit * 2
            ]


# =============================================================
# HELPERS
# =============================================================

def normalize_text(
    text: str,
) -> str:

    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip().lower()


def extract_storage(
    text: str,
) -> int | None:

    match = re.search(
        r"\b"
        r"(64|128|256|512|1024)"
        r"\s*"
        r"(?:гб|gb|tb|тб)"
        r"\b",
        text,
        re.I,
    )

    if not match:
        return None

    value = int(
        match.group(1)
    )

    unit = match.group(0).lower()

    if (
        "tb" in unit
        or "тб" in unit
    ):
        value *= 1024

    return value


def extract_battery(
    text: str,
) -> int | None:

    patterns = [
        (
            r"(?:аккумулятор|"
            r"батаре[яи]|"
            r"состояние аккумулятора|"
            r"ёмкость)"
            r"\D{0,30}"
            r"(\d{2,3})\s*%"
        ),
        (
            r"(\d{2,3})\s*%"
            r"\s*(?:акб|аккумулятор)"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I,
        )

        if not match:
            continue

        value = int(
            match.group(1)
        )

        if 1 <= value <= 100:
            return value

    return None


def extract_section(
    text: str,
    words: list[str],
) -> str | None:

    for word in words:

        index = text.find(
            word
        )

        if index >= 0:

            return text[
                max(0, index):
                index + 350
            ]

    return None


APIAvitoProvider = PublicAvitoProvider
