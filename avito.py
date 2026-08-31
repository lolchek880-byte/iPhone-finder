import json
import os
from typing import Any

import aiohttp

from models import Listing, SearchFilters


class AvitoProvider:
    async def search(
        self,
        filters: SearchFilters,
    ) -> list[Listing]:
        raise NotImplementedError


class APIAvitoProvider(AvitoProvider):

    def __init__(self):

        self.url = os.getenv(
            "AVITO_API_URL",
            "",
        ).strip()

        self.token = os.getenv(
            "AVITO_API_TOKEN",
            "",
        ).strip()

        self.timeout = int(
            os.getenv(
                "AVITO_TIMEOUT",
                "30",
            )
        )

    def _params(
        self,
        filters: SearchFilters,
    ) -> dict[str, Any]:

        return {
            "models": ",".join(
                filters.models
            ),

            "min_price":
                filters.min_price or "",

            "max_price":
                filters.max_price or "",

            "storage": ",".join(
                str(x)
                for x in filters.storage
            ),

            "min_battery":
                filters.min_battery or "",

            "city":
                filters.city or "",

            "radius_km":
                filters.radius_km or "",

            "limit": 50,
        }

    async def search(
        self,
        filters: SearchFilters,
    ) -> list[Listing]:

        if not self.url:

            raise RuntimeError(
                "AVITO_API_URL не установлен. "
                "Подключи разрешённый API/feed "
                "в переменной окружения."
            )

        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "iPhoneFinder/1.0"
            ),
        }

        if self.token:

            headers[
                "Authorization"
            ] = (
                f"Bearer {self.token}"
            )

        timeout = aiohttp.ClientTimeout(
            total=self.timeout
        )

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
        ) as session:

            async with session.get(
                self.url,
                params=self._params(filters),
            ) as response:

                body = await response.text()

                if response.status != 200:

                    raise RuntimeError(
                        "Источник объявлений "
                        f"вернул HTTP "
                        f"{response.status}: "
                        f"{body[:500]}"
                    )

                try:
                    data = json.loads(body)

                except json.JSONDecodeError:

                    raise RuntimeError(
                        "Источник объявлений "
                        "вернул не JSON."
                    )

        return self._parse_response(
            data
        )

    @classmethod
    def _parse_response(
        cls,
        data: Any,
    ) -> list[Listing]:

        if isinstance(data, list):
            items = data

        elif isinstance(data, dict):

            items = (
                data.get("items")
                or data.get("results")
                or data.get("listings")
                or data.get("ads")
                or []
            )

        else:
            items = []

        result = []

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            try:

                listing = cls._parse_item(
                    item
                )

                if listing.id and listing.url:
                    result.append(
                        listing
                    )

            except Exception as error:

                print(
                    "Listing parse error:",
                    error,
                )

        return result

    @staticmethod
    def _first(
        data: dict,
        *keys,
        default=None,
    ):
        for key in keys:

            value = data.get(key)

            if value is not None:
                return value

        return default

    @classmethod
    def _parse_item(
        cls,
        item: dict,
    ) -> Listing:

        listing_id = cls._first(
            item,
            "id",
            "item_id",
            "ad_id",
            default="",
        )

        title = cls._first(
            item,
            "title",
            "name",
            default="iPhone",
        )

        model = cls._first(
            item,
            "model",
            "phone_model",
            default=title,
        )

        price = cls._first(
            item,
            "price",
            "cost",
            "amount",
            default=0,
        )

        url = cls._first(
            item,
            "url",
            "link",
            "href",
            default="",
        )

        description = cls._first(
            item,
            "description",
            "text",
            "body",
            default="",
        )

        photos = (
            item.get("photos")
            or item.get("images")
            or []
        )

        normalized_photos = []

        for photo in photos:

            if isinstance(
                photo,
                str,
            ):
                normalized_photos.append(
                    photo
                )

            elif isinstance(
                photo,
                dict,
            ):

                photo_url = cls._first(
                    photo,
                    "url",
                    "src",
                    "href",
                )

                if photo_url:
                    normalized_photos.append(
                        photo_url
                    )

        storage = cls._first(
            item,
            "storage_gb",
            "memory_gb",
            "storage",
        )

        battery = cls._first(
            item,
            "battery_percent",
            "battery",
            "battery_health",
        )

        seller_rating = cls._first(
            item,
            "seller_rating",
            "rating",
        )

        accessories = (
            item.get("accessories")
            or item.get("equipment")
            or []
        )

        if isinstance(
            accessories,
            str,
        ):
            accessories = [
                accessories
            ]

        return Listing(
            id=str(
                listing_id
            ),

            title=str(
                title
            ),

            model=str(
                model
            ),

            price=int(
                cls._number(
                    price
                )
            ),

            url=str(
                url
            ),

            description=str(
                description
            ),

            photos=normalized_photos,

            storage_gb=(
                int(
                    cls._number(storage)
                )
                if storage is not None
                else None
            ),

            battery_percent=(
                int(
                    cls._number(battery)
                )
                if battery is not None
                else None
            ),

            condition=cls._first(
                item,
                "condition",
                "state",
            ),

            color=cls._first(
                item,
                "color",
            ),

            repair_info=cls._first(
                item,
                "repair_info",
                "repairs",
                "repair",
            ),

            screen_info=cls._first(
                item,
                "screen_info",
                "screen",
            ),

            seller_name=cls._first(
                item,
                "seller_name",
                "seller",
            ),

            seller_rating=(
                float(
                    cls._number(
                        seller_rating
                    )
                )
                if seller_rating is not None
                else None
            ),

            city=cls._first(
                item,
                "city",
                "location",
            ),

            accessories=list(
                accessories
            ),

            posted_at=cls._first(
                item,
                "posted_at",
                "created_at",
                "date",
            ),

            views=(
                int(
                    cls._number(
                        item.get("views")
                    )
                )
                if item.get("views")
                is not None
                else None
            ),

            raw=item,
        )

    @staticmethod
    def _number(
        value: Any,
    ) -> float:

        if value is None:
            return 0

        if isinstance(
            value,
            (int, float),
        ):
            return value

        text = (
            str(value)
            .replace(" ", "")
            .replace("₽", "")
            .replace("%", "")
            .replace(",", ".")
        )

        try:
            return float(text)

        except ValueError:
            return 0
