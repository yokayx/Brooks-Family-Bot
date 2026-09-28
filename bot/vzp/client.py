from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from bot.config import (
    VZP_API_BASE,
    VZP_FETCH_LIMIT,
    VZP_FETCH_PAGES,
    VZP_HTTP_TIMEOUT,
    VZP_RETRIES,
)

log = logging.getLogger("brooks.vzp.client")

# JSON лежит открыто, но без «браузерных» заголовков сайт отдаёт 403/429.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Referer": "https://vzp-launcher.pro/",
}


class VzpClient:
    """Клиент vzp-launcher.pro: список войн по страницам + детали войны."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self.last_error: str | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=VZP_HTTP_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout, headers=_HEADERS)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def recent_wars(self, pages: int = VZP_FETCH_PAGES) -> list[dict[str, Any]]:
        """Свежие войны: несколько страниц `/wars`, без дублей по id.

        100 войн — это примерно 2–3 часа эфира всех серверов, Brooks играет
        редко, поэтому смотрим сразу `pages` страниц (≈8 часов), иначе итог
        успевает уехать за окно между опросами.
        """
        wars: list[dict[str, Any]] = []
        seen: set[str] = set()

        for page in range(1, max(1, pages) + 1):
            payload = await self._get(
                "/wars", params={"limit": str(VZP_FETCH_LIMIT), "page": str(page)}
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or not data:
                break
            for item in data:
                if not isinstance(item, dict):
                    continue
                war_id = str(item.get("id") or "")
                if war_id:
                    if war_id in seen:
                        continue
                    seen.add(war_id)
                wars.append(item)
            if len(data) < VZP_FETCH_LIMIT:
                break
            await asyncio.sleep(0.2)

        return wars

    async def war_detail(self, war_id: str) -> dict[str, Any]:
        payload = await self._get(f"/wars/{war_id}")
        if isinstance(payload, dict) and payload.get("id"):
            return payload
        raise RuntimeError(f"empty war detail {war_id}")

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        if self._session is None:
            await self.start()
        assert self._session is not None
        url = f"{VZP_API_BASE}{path}"
        last: Exception | None = None

        for attempt in range(1, VZP_RETRIES + 1):
            try:
                async with self._session.get(url, params=params) as resp:
                    if resp.status >= 400:
                        body = (await resp.text())[:200]
                        raise RuntimeError(f"HTTP {resp.status} {url}: {body}")
                    payload = await resp.json(content_type=None)
                self.last_error = None
                return payload
            except Exception as exc:  # сеть, таймаут, 4xx/5xx, кривой JSON
                last = exc
                log.warning("vzp %s attempt %s/%s failed: %s", url, attempt, VZP_RETRIES, exc)
                if attempt < VZP_RETRIES:
                    await asyncio.sleep(1.5 * attempt)

        self.last_error = str(last)
        raise RuntimeError(f"{url} не отвечает: {last}") from last
