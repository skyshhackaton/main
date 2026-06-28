"""Upbit public quotation API client.

MVP rule: use public endpoints only. Do not accept or store user API keys.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta
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


async def refresh_candles(market: str = DEFAULT_MARKET, db_path: Path = DB_PATH) -> int:
    """API에서 전체 캔들(target개) 수집 후 DB 저장. 저장된 개수 반환."""
    raw = await fetch_all_candles(market)
    normalized = [_normalize(c) for c in raw]
    return save_candles(normalized, market, db_path)


# ---------------------------------------------------------------------------
# 증분 갱신 / 멀티 마켓
# ---------------------------------------------------------------------------

async def fetch_new_candles(
    market: str, after_date_utc: str, max_pages: int = 20
) -> list[dict]:
    """
    after_date_utc(배타적)보다 최신인 캔들만 수집 (oldest-first 반환).
    최신 페이지부터 거슬러 올라가다 기존 경계에 닿으면 중단.
    """
    collected: list[dict] = []
    to: str | None = None

    for _ in range(max_pages):
        page = await fetch_day_candles(market, 200, to)
        if not page:
            break
        new = [c for c in page if c["candle_date_time_utc"] > after_date_utc]
        collected.extend(new)
        # 페이지 안에서 경계를 만났으면(이미 가진 데이터 도달) 중단
        if len(new) < len(page):
            break
        to = page[-1]["candle_date_time_utc"].replace("T", " ")
        await asyncio.sleep(0.15)  # rate limit 보호

    dedup = {c["candle_date_time_utc"]: c for c in collected}
    return sorted(dedup.values(), key=lambda c: c["candle_date_time_utc"])


async def update_candles(market: str = DEFAULT_MARKET, db_path: Path = DB_PATH) -> int:
    """
    DB의 마지막 날짜 이후 캔들만 증분 수집·저장. 추가 저장된 개수 반환.
    DB가 비어 있으면 전체 수집(refresh_candles)으로 폴백.
    새 데이터가 없으면 DB를 변경하지 않고 0 반환.
    """
    existing = load_candles(market, db_path)
    if not existing:
        return await refresh_candles(market, db_path)

    last_date = existing[-1]["date_utc"]
    raw_new = await fetch_new_candles(market, last_date)
    if not raw_new:
        return 0

    normalized = [_normalize(c) for c in raw_new]
    return save_candles(normalized, market, db_path)


async def refresh_markets(
    markets: list[str], db_path: Path = DB_PATH
) -> dict[str, int]:
    """여러 마켓을 증분 갱신. {market: 추가된 캔들 수} 반환."""
    results: dict[str, int] = {}
    for market in markets:
        results[market] = await update_candles(market, db_path)
    return results


# ---------------------------------------------------------------------------
# 데이터 검증
# ---------------------------------------------------------------------------

def validate_candles(candles: list[dict]) -> dict:
    """
    캔들 무결성 검증 리포트 반환.
    검증: 결측일 / 중복일 / OHLC 논리 위반 / 비정상 값.
    입력은 _normalize 형식 (date_utc, open, high, low, close, volume).
    """
    missing_dates: list[str] = []
    duplicate_dates: list[str] = []
    ohlc_errors: list[dict] = []
    value_errors: list[dict] = []

    dates = [c["date_utc"] for c in candles]

    # 중복 날짜
    seen: set[str] = set()
    for d in dates:
        if d in seen:
            duplicate_dates.append(d)
        seen.add(d)

    # 날짜 연속성 (일 단위 결측)
    parsed = sorted({datetime.fromisoformat(d).date() for d in dates})
    if parsed:
        present = set(parsed)
        cur, last = parsed[0], parsed[-1]
        while cur <= last:
            if cur not in present:
                missing_dates.append(cur.isoformat())
            cur += timedelta(days=1)

    # OHLC 논리 + 값 검증
    for c in candles:
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        date = c["date_utc"]
        if h < l:
            ohlc_errors.append({"date": date, "reason": "high < low"})
        else:
            if not (l <= o <= h):
                ohlc_errors.append({"date": date, "reason": "open out of [low, high]"})
            if not (l <= cl <= h):
                ohlc_errors.append({"date": date, "reason": "close out of [low, high]"})

        if any(c[k] <= 0 for k in ("open", "high", "low", "close")):
            value_errors.append({"date": date, "reason": "non-positive price"})
        if c["volume"] < 0:
            value_errors.append({"date": date, "reason": "negative volume"})

    ok = not (missing_dates or duplicate_dates or ohlc_errors or value_errors)
    return {
        "ok": ok,
        "count": len(candles),
        "missing_dates": missing_dates,
        "duplicate_dates": duplicate_dates,
        "ohlc_errors": ohlc_errors,
        "value_errors": value_errors,
    }
