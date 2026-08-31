import asyncio
import json
import os
from pathlib import Path
from typing import Any


class JSONStorage:
    def __init__(self, directory: str = "data"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

        self.users_file = self.directory / "users.json"
        self.searches_file = self.directory / "searches.json"
        self.favorites_file = self.directory / "favorites.json"

        self.lock = asyncio.Lock()

        self._ensure_file(self.users_file, {})
        self._ensure_file(self.searches_file, {})
        self._ensure_file(self.favorites_file, {})

    @staticmethod
    def _ensure_file(path: Path, default: Any):
        if not path.exists():
            path.write_text(
                json.dumps(
                    default,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    async def _read(self, path: Path):
        async with self.lock:
            try:
                return json.loads(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                return {}

    async def _write(self, path: Path, data: Any):
        async with self.lock:
            temp = path.with_suffix(".tmp")

            temp.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            temp.replace(path)

    async def get_user(self, user_id: int) -> dict:
        users = await self._read(self.users_file)

        key = str(user_id)

        if key not in users:
            users[key] = {
                "id": user_id,
                "search": {},
                "created_at": None,
            }

            await self._write(
                self.users_file,
                users,
            )

        return users[key]

    async def set_search(
        self,
        user_id: int,
        search: dict,
    ):
        users = await self._read(self.users_file)

        key = str(user_id)

        if key not in users:
            users[key] = {
                "id": user_id,
                "search": {},
            }

        users[key]["search"] = search

        await self._write(
            self.users_file,
            users,
        )

    async def get_search(
        self,
        user_id: int,
    ) -> dict:

        user = await self.get_user(user_id)

        return user.get("search", {})

    async def add_favorite(
        self,
        user_id: int,
        listing: dict,
    ):
        favorites = await self._read(
            self.favorites_file
        )

        key = str(user_id)

        favorites.setdefault(
            key,
            [],
        )

        existing_ids = {
            str(x.get("id"))
            for x in favorites[key]
        }

        if str(listing["id"]) not in existing_ids:
            favorites[key].append(listing)

        await self._write(
            self.favorites_file,
            favorites,
        )

    async def get_favorites(
        self,
        user_id: int,
    ) -> list:

        favorites = await self._read(
            self.favorites_file
        )

        return favorites.get(
            str(user_id),
            [],
        )
