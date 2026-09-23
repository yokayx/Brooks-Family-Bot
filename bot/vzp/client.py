from __future__ import annotations

import logging

import aiohttp

from bot.config import VZP_API_BASE, VZP_FETCH_LIMIT

log = logging.getLogger("brooks.vzp.client")
_HEADERS = {"User-Agent": "BrooksFamilyBot/0.1 (+discord family bot)"}


class VzpClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self._session = aiohttp.ClientSession(timeout=timeout, headers=_HEADERS)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def recent_wars(self) -> list[dict]:
        payload = await self._get("/wars", params={"limit": str(VZP_FETCH_LIMIT)})
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    async def war_detail(self, war_id: str) -> dict:
        payload = await self._get(f"/wars/{war_id}")
        if isinstance(payload, dict) and payload.get("id"):
            return payload
        raise RuntimeError(f"empty war detail {war_id}")

    async def _get(self, path: str, params: dict[str, str] | None = None) -> object:
        if self._session is None:
            await self.start()
        assert self._session is not None
        url = f"{VZP_API_BASE}{path}"
        async with self._session.get(url, params=params) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"VZP {resp.status} {url}: {body[:200]}")
            return await resp.json()
