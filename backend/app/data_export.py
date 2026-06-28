"""팀원 공유용 데이터 export.

로컬에서 `python -m app.upbit_client`로 수집한 SQLite 데이터를
ML/KNN·통계 담당자가 바로 읽을 CSV와 QA용 검증 리포트 JSON으로 내보낸다.

MVP rule: 공개 API만 사용하며 이 모듈은 네트워크 호출을 하지 않는다
(이미 DB에 저장된 데이터만 읽어 변환). API Key/Secret은 사용하지 않는다.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .upbit_client import DEFAULT_MARKETS, DB_PATH, load_candles, validate_candles

SOURCE = "upbit"
KST = timezone(timedelta(hours=9))

CSV_COLUMNS = [
    "market",
    "date_utc",
    "date_kst",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_price",
    "source",
    "crawled_at",
    "run_id",
]


def _utc_to_kst(date_utc: str) -> str:
    """'YYYY-MM-DDTHH:MM:SS'(UTC) → KST(+9h) ISO 문자열."""
    dt = datetime.fromisoformat(date_utc).replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%dT%H:%M:%S")


def _run_id_from_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d_%H%M")


def _run_id_from_crawled_at(crawled_at: str) -> str:
    dt = datetime.fromisoformat(crawled_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _run_id_from_dt(dt)


def _build_export_metadata(
    crawled_at: str | None = None,
    run_id: str | None = None,
) -> tuple[str, str]:
    if crawled_at is None:
        now = datetime.now(timezone.utc)
        crawled_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        default_run_id = _run_id_from_dt(now)
    else:
        default_run_id = _run_id_from_crawled_at(crawled_at)
    return crawled_at, run_id or default_run_id


def _run_id_from_crawled_at(crawled_at: str) -> str:
    dt = datetime.fromisoformat(crawled_at.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%d_%H%M")


def export_candles_csv(
    out_path: Path,
    markets: list[str] | None = None,
    db_path: Path = DB_PATH,
    crawled_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, int]:
    """마켓별 캔들을 단일 CSV로 내보낸다. 반환: {market: row 수}."""
    markets = markets or DEFAULT_MARKETS
    crawled_at, run_id = _build_export_metadata(crawled_at, run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for market in markets:
            candles = load_candles(market, db_path)
            counts[market] = len(candles)
            for c in candles:
                close = c["close"]
                writer.writerow({
                    "market": market,
                    "date_utc": c["date_utc"],
                    "date_kst": _utc_to_kst(c["date_utc"]),
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": close,
                    "volume": c["volume"],
                    "trade_price": close,  # Upbit에서 trade_price == 종가
                    "source": SOURCE,
                    "crawled_at": crawled_at,
                    "run_id": run_id,
                })
    return counts


def build_crawl_report(
    markets: list[str] | None = None,
    db_path: Path = DB_PATH,
    crawled_at: str | None = None,
    run_id: str | None = None,
) -> dict:
    """QA용 검증 리포트 dict 생성."""
    markets = markets or DEFAULT_MARKETS
    crawled_at, run_id = _build_export_metadata(crawled_at, run_id)

    per_market: dict[str, dict] = {}
    for market in markets:
        candles = load_candles(market, db_path)
        validation = validate_candles(candles)
        per_market[market] = {
            "rows": len(candles),
            "validation": validation,
        }

    return {
        "crawled_at": crawled_at,
        "run_id": run_id,
        "source": SOURCE,
        "markets": markets,
        "results": per_market,
    }


def export_all(
    data_dir: Path,
    markets: list[str] | None = None,
    db_path: Path = DB_PATH,
    timestamp: bool = False,
    crawled_at: str | None = None,
    run_id: str | None = None,
) -> dict:
    """CSV + crawl_report.json을 함께 내보낸다. 반환: 요약 dict."""
    markets = markets or DEFAULT_MARKETS
    crawled_at, run_id = _build_export_metadata(crawled_at, run_id)
    data_dir.mkdir(parents=True, exist_ok=True)

    if timestamp:
        csv_path = data_dir / f"upbit_candles_{run_id}.csv"
        report_path = data_dir / f"crawl_report_{run_id}.json"
    else:
        csv_path = data_dir / "upbit_candles_snapshot.csv"
        report_path = data_dir / "crawl_report.json"

    counts = export_candles_csv(csv_path, markets, db_path, crawled_at, run_id)
    report = build_crawl_report(markets, db_path, crawled_at, run_id)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "csv_path": str(csv_path),
        "report_path": str(report_path),
        "csv_bytes": csv_path.stat().st_size,
        "run_id": run_id,
        "counts": counts,
        "report": report,
    }


def _format_summary(result: dict) -> str:
    lines = [
        f"Run ID : {result['run_id']}",
        f"CSV    : {result['csv_path']} ({result['csv_bytes']:,} bytes)",
        f"Report : {result['report_path']}",
    ]
    for market, info in result["report"]["results"].items():
        v = info["validation"]
        status = "OK" if v["ok"] else "ISSUES"
        lines.append(f"  [{market}] rows={info['rows']} validation={status}")
        if not v["ok"]:
            lines.append(
                f"      missing={len(v['missing_dates'])} duplicate={len(v['duplicate_dates'])} "
                f"ohlc_errors={len(v['ohlc_errors'])} value_errors={len(v['value_errors'])}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """CLI: DB에서 CSV 스냅샷 + 검증 리포트 JSON 생성."""
    import argparse

    parser = argparse.ArgumentParser(
        description="수집된 Upbit 캔들을 팀 공유용 CSV + 검증 리포트로 export"
    )
    parser.add_argument(
        "--markets", nargs="+", default=DEFAULT_MARKETS,
        help="export할 마켓 목록 (기본: KRW-BTC KRW-ETH KRW-XRP)",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH), help=f"SQLite DB 경로 (기본: {DB_PATH})"
    )
    parser.add_argument(
        "--out", default="data", help="출력 디렉터리 (기본: data)"
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="upbit_candles_YYYYMMDD_HHMM.csv / crawl_report_YYYYMMDD_HHMM.json 생성",
    )
    args = parser.parse_args(argv)

    result = export_all(
        Path(args.out), args.markets, Path(args.db), timestamp=args.timestamp
    )
    print(_format_summary(result))


if __name__ == "__main__":
    main()
