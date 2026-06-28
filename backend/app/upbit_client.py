"""Upbit public quotation API client.

MVP rule: use public endpoints only. Do not accept or store user API keys.
"""

import asyncio
import sqlite3
from pathlib import Path

import httpx

UPBIT_BASE_URL = "https://api.upbit.com/v1"
DEFAULT_MARKET = "KRW-BTC"
DB_PATH = Path(__file__).parent.parent / "upbit_data.db"
TARGET_COUNT = 565  # 200일 스코어 + 365일 룩백 윈도우


async def fetch_day_candles(market: str, count: int = 200, to: str | None = None) -> list[dict]:
    params: dict[str, str | int] = {"market": market, "count": count}
    if to:
        params["to"] = to

    async with httpx.AsyncClient(base_url=UPBIT_BASE_URL, timeout=10.0) as client:
        response = await client.get("/candles/days", params=params)
        response.raise_for_status()
        return response.json()


async def fetch_all_candles(market: str = DEFAULT_MARKET, target: int = TARGET_COUNT) -> list[dict]:
    """to= 파라미터로 페이지네이션하여 target개 캔들 수집 (oldest-first 반환)."""
    collected: list[dict] = []
    to: str | None = None

    while len(collected) < target:
        remaining = target - len(collected)
        count = min(200, remaining)
        page = await fetch_day_candles(market, count, to)
        if not page:
            break
        collected.extend(page)
        oldest = page[-1]["candle_date_time_utc"]
        to = oldest.replace("T", " ")
        await asyncio.sleep(0.15)  # rate limit 보호

    dedup = {c["candle_date_time_utc"]: c for c in collected}
    return sorted(dedup.values(), key=lambda c: c["candle_date_time_utc"])


# ---------------------------------------------------------------------------
# SQLite 캐시
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candles (
            market   TEXT NOT NULL,
            date_utc TEXT NOT NULL,
            open     REAL NOT NULL,
            high     REAL NOT NULL,
            low      REAL NOT NULL,
            close    REAL NOT NULL,
            volume   REAL NOT NULL,
            PRIMARY KEY (market, date_utc)
        )
        """
    )
    conn.commit()


def _normalize(raw: dict) -> dict:
    return {
        "date_utc": raw["candle_date_time_utc"],
        "open":     raw["opening_price"],
        "high":     raw["high_price"],
        "low":      raw["low_price"],
        "close":    raw["trade_price"],
        "volume":   raw["candle_acc_trade_volume"],
    }


def save_candles(candles: list[dict], market: str, db_path: Path = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)
        rows = [
            (market, c["date_utc"], c["open"], c["high"], c["low"], c["close"], c["volume"])
            for c in candles
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO candles (market,date_utc,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def load_candles(market: str = DEFAULT_MARKET, db_path: Path = DB_PATH) -> list[dict]:
    """DB에서 oldest-first 순으로 캔들 로드."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT date_utc,open,high,low,close,volume FROM candles WHERE market=? ORDER BY date_utc ASC",
            (market,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def refresh_candles(market: str = DEFAULT_MARKET) -> int:
    """API에서 최신 캔들 수집 후 DB 저장. 저장된 개수 반환."""
    raw = await fetch_all_candles(market)
    normalized = [_normalize(c) for c in raw]
    return save_candles(normalized, market)
