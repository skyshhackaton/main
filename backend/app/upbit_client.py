"""Upbit public quotation API client.

MVP rule: use public endpoints only. Do not accept or store user API keys.
"""

import httpx

UPBIT_BASE_URL = "https://api.upbit.com/v1"


async def fetch_day_candles(market: str, count: int = 200, to: str | None = None) -> list[dict]:
    params: dict[str, str | int] = {"market": market, "count": count}
    if to:
        params["to"] = to

    async with httpx.AsyncClient(base_url=UPBIT_BASE_URL, timeout=10.0) as client:
        response = await client.get("/candles/days", params=params)
        response.raise_for_status()
        return response.json()
