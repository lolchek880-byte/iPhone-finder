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


class APIAvitoProvider(
    AvitoProvider
):

    def __init__(self):

        self.url = os.getenv(
            "AVITO_API_URL"
        )

        self.token = os.getenv(
            "AVITO_API_TOKEN"
        )

    async def search(
        self,
        filters: SearchFilters,
    ) -> list[Listing]:

        if not self.url:
            raise RuntimeError(
                "AVITO_API_URL не настроен"
            )

        params = {
            "models": ",".join(
                filters.models
            ),
            "min_price":
                filters.min_price or "",
            "max_price":
                filters.max_price or "",
            "storage": ",".join(
                map(
                    str,
                    filters.storage,
                )
            ),
            "min_battery":
                filters.min_battery or "",
            "city":
                filters.city or "",
            "radius_km":
                filters.radius_km or "",
            "limit": 50,
        }

        headers = {}

        if self.token:
            headers[
                "Authorization"
            ] = f"Bearer {self.token}"

        async with aiohttp.ClientSession() as session:

            async with session.get(
                self.url,
                params=params,
                headers=headers,
                timeout=30,
            ) as response:

                if response.status != 200:

                    text = await response.text()

                    raise RuntimeError(
                        f"Avito API error "
                        f"{response.status}: "
                        f"{text[:500]}"
                    )

                data = await response.json()

        return self._parse(
            data
        )

    @staticmethod
    def _parse(
        data: Any,
    ) -> list[Listing]:

        """
        Ожидаемый формат адаптера:

        {
          "items": [
            {
              "id": "...",
              "title": "...",
              "model": "...",
              "price": 62000,
              "url": "...",
              "description": "...",
              "photos": [],
              "storage_gb": 256,
              "battery_percent": 91,
              "condition": "...",
              "repair_info": "...",
              "screen_info": "...",
              "seller_name": "...",
              "seller_rating": 4.9,
              "city": "Москва",
              "accessories": []
            }
          ]
        }
        """

        items = data.get(
            "items",
            []
        )

        result = []

        for item in items:

            try:

                result.append(
                    Listing(
                        id=str(
                            item["id"]
                        ),

                        title=item.get(
                            "title",
                            "iPhone",
                        ),

                        model=item.get(
                            "model",
                            "",
                        ),

                        price=int(
                            item.get(
                                "price",
                                0,
                            )
                        ),

                        url=item.get(
                            "url",
                            "",
                        ),

                        description=item.get(
                            "description",
                            "",
                        ),

                        photos=item.get(
                            "photos",
                            [],
                        ),

                        storage_gb=item.get(
                            "storage_gb"
                        ),

                        battery_percent=item.get(
                            "battery_percent"
                        ),

                        condition=item.get(
                            "condition"
                        ),

                        color=item.get(
                            "color"
                        ),

                        repair_info=item.get(
                            "repair_info"
                        ),

                        screen_info=item.get(
                            "screen_info"
                        ),

                        seller_name=item.get(
                            "seller_name"
                        ),

                        seller_rating=item.get(
                            "seller_rating"
                        ),

                        city=item.get(
                            "city"
                        ),

                        accessories=item.get(
                            "accessories",
                            [],
                        ),

                        raw=item,
                    )
                )

            except Exception as error:

                print(
                    "Listing parse error:",
                    error,
                )

        return result
