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
DEFAULT_MARKETS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
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
    market: str, since_date_utc: str, inclusive: bool = True, max_pages: int = 20
) -> list[dict]:
    """
    since_date_utc 이후의 캔들 수집 (oldest-first 반환).
    inclusive=True면 since_date_utc 당일도 포함(>=) — DB에 저장된 마지막 날의
    partial candle(예: 오늘 일봉)을 최신 종가로 다시 받아 덮어쓰기 위함.
    inclusive=False면 다음 날부터(>).
    최신 페이지부터 거슬러 올라가다 경계(통과 못하는 캔들)에 닿으면 중단.

    참고: candle_date_time_utc는 'YYYY-MM-DDTHH:MM:SS' 고정폭 포맷이라
    문자열 사전식 비교가 시간순 비교와 동일하게 안전하다. 전 함수가 UTC 기준.
    """
    def keep(c: dict) -> bool:
        ts = c["candle_date_time_utc"]
        return ts >= since_date_utc if inclusive else ts > since_date_utc

    collected: list[dict] = []
    to: str | None = None

    for _ in range(max_pages):
        page = await fetch_day_candles(market, 200, to)
        if not page:
            break
        new = [c for c in page if keep(c)]
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
    증분 갱신. 신규로 추가된 날짜 수를 반환.
    - DB가 비어 있으면 전체 수집(refresh_candles)으로 폴백.
    - 마지막 저장일을 포함(inclusive)해 다시 받아 덮어씀 → 오늘 partial candle이
      종가로 갱신되어 stale 방지. INSERT OR REPLACE라 중복은 생기지 않음.
    - 신규 날짜가 없으면(오늘 캔들만 갱신) 0을 반환하지만, 오늘 캔들 값은 최신화됨.
    """
    existing = load_candles(market, db_path)
    if not existing:
        return await refresh_candles(market, db_path)

    existing_dates = {c["date_utc"] for c in existing}
    last_date = existing[-1]["date_utc"]
    raw_new = await fetch_new_candles(market, last_date, inclusive=True)
    if not raw_new:
        return 0

    normalized = [_normalize(c) for c in raw_new]
    save_candles(normalized, market, db_path)
    # 재수집한 마지막 날(덮어쓰기)은 제외하고 '진짜 신규' 날짜만 카운트
    return sum(1 for c in normalized if c["date_utc"] not in existing_dates)


async def refresh_markets(
    markets: list[str], db_path: Path = DB_PATH
) -> dict[str, int | dict]:
    """
    여러 마켓을 증분 갱신. 마켓별로 독립 처리하여 한 마켓 실패가 전체를
    중단시키지 않는다.
    반환: {market: 신규 캔들 수} (성공) 또는 {market: {"error": ...}} (실패).
    예: {"KRW-BTC": 3, "KRW-ETH": {"error": "ConnectError", "detail": "..."}, "KRW-XRP": 5}
    """
    results: dict[str, int | dict] = {}
    for market in markets:
        try:
            results[market] = await update_candles(market, db_path)
        except Exception as exc:  # noqa: BLE001 - 마켓별 격리가 목적
            results[market] = {"error": type(exc).__name__, "detail": str(exc)}
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


# ---------------------------------------------------------------------------
# 파이프라인 실행 (증분 갱신 + 검증) / CLI 엔트리포인트
# ---------------------------------------------------------------------------

async def run_pipeline(
    markets: list[str] | None = None, db_path: Path = DB_PATH
) -> dict[str, dict]:
    """
    여러 마켓을 증분 갱신한 뒤 각 마켓의 저장 데이터를 검증한다.
    smoke test / 스케줄러용 단일 진입점.
    반환: {market: {"added": int|None, "error": str|None, "validation": dict|None}}
    한 마켓의 네트워크 실패가 전체를 중단시키지 않는다(refresh_markets와 동일 격리).
    """
    markets = markets or DEFAULT_MARKETS
    refreshed = await refresh_markets(markets, db_path)

    report: dict[str, dict] = {}
    for market in markets:
        result = refreshed.get(market)
        if isinstance(result, dict):  # 갱신 단계 실패
            report[market] = {
                "added": None,
                "error": result.get("error"),
                "detail": result.get("detail"),
                "validation": None,
            }
            continue
        validation = validate_candles(load_candles(market, db_path))
        report[market] = {"added": result, "error": None, "validation": validation}
    return report


def _format_report(report: dict[str, dict]) -> str:
    lines: list[str] = []
    for market, info in report.items():
        if info["error"]:
            lines.append(f"[{market}] ERROR {info['error']}: {info.get('detail')}")
            continue
        v = info["validation"]
        status = "OK" if v["ok"] else "ISSUES"
        lines.append(
            f"[{market}] +{info['added']} new, total={v['count']}, validation={status}"
        )
        if not v["ok"]:
            lines.append(
                f"    missing={len(v['missing_dates'])} duplicate={len(v['duplicate_dates'])} "
                f"ohlc_errors={len(v['ohlc_errors'])} value_errors={len(v['value_errors'])}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """CLI: 공개 API에서 실데이터를 받아 DB 갱신 + 검증 리포트 출력."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Upbit 공개 일봉 캔들 증분 갱신 + 검증 (smoke test용)"
    )
    parser.add_argument(
        "--markets", nargs="+", default=DEFAULT_MARKETS,
        help="갱신할 마켓 목록 (기본: KRW-BTC KRW-ETH KRW-XRP)",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH), help=f"SQLite DB 경로 (기본: {DB_PATH})"
    )
    args = parser.parse_args(argv)

    report = asyncio.run(run_pipeline(args.markets, Path(args.db)))
    print(_format_report(report))


if __name__ == "__main__":
    main()
