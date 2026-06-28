"""data_export 단위테스트.

네트워크 호출 없음 — DB(tmp_path)에 직접 캔들을 시드한 뒤 export 결과를 검증한다.
"""

import csv
import json

from app import data_export, upbit_client


def _seed(db_path, market, dates, close_offset=0.0):
    """oldest-first 날짜 목록으로 캔들을 DB에 저장."""
    candles = []
    for i, d in enumerate(dates):
        price = 100.0 + i + close_offset
        candles.append({
            "date_utc": f"{d}T00:00:00",
            "open": price, "high": price + 2, "low": price - 2,
            "close": price + 1, "volume": 10.0 + i,
        })
    upbit_client.save_candles(candles, market, db_path)


def _dates(start, end):
    return [f"2024-01-{d:02d}" for d in range(start, end + 1)]


def test_export_csv_has_expected_columns_and_rows(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", _dates(1, 3))
    out = tmp_path / "snap.csv"

    counts = data_export.export_candles_csv(out, ["KRW-BTC"], db)
    assert counts == {"KRW-BTC": 3}

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert list(rows[0].keys()) == data_export.CSV_COLUMNS
    # trade_price는 종가(close)와 동일
    assert rows[0]["trade_price"] == rows[0]["close"]
    assert rows[0]["source"] == "upbit"
    assert rows[0]["market"] == "KRW-BTC"


def test_export_csv_date_kst_is_utc_plus_9(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", ["2024-01-05"])
    out = tmp_path / "snap.csv"
    data_export.export_candles_csv(out, ["KRW-BTC"], db)

    with out.open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["date_utc"] == "2024-01-05T00:00:00"
    assert row["date_kst"] == "2024-01-05T09:00:00"  # +9h


def test_export_multi_market_keeps_markets_separate(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", _dates(1, 3))
    _seed(db, "KRW-ETH", _dates(1, 2), close_offset=10000.0)
    out = tmp_path / "snap.csv"

    counts = data_export.export_candles_csv(out, ["KRW-BTC", "KRW-ETH"], db)
    assert counts == {"KRW-BTC": 3, "KRW-ETH": 2}

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    markets = {r["market"] for r in rows}
    assert markets == {"KRW-BTC", "KRW-ETH"}
    assert len(rows) == 5


def test_build_crawl_report_includes_validation(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", _dates(1, 5))
    report = data_export.build_crawl_report(["KRW-BTC"], db)

    assert report["source"] == "upbit"
    assert "run_id" in report
    assert report["markets"] == ["KRW-BTC"]
    btc = report["results"]["KRW-BTC"]
    assert btc["rows"] == 5
    assert btc["validation"]["ok"] is True
    assert set(btc["validation"]) >= {
        "ok", "count", "missing_dates", "duplicate_dates",
        "ohlc_errors", "value_errors",
    }


def test_crawl_report_flags_missing_dates(tmp_path):
    db = tmp_path / "t.db"
    # 01-03 누락
    _seed(db, "KRW-BTC", ["2024-01-01", "2024-01-02", "2024-01-04"])
    report = data_export.build_crawl_report(["KRW-BTC"], db)
    v = report["results"]["KRW-BTC"]["validation"]
    assert v["ok"] is False
    assert "2024-01-03" in v["missing_dates"]


def test_export_all_writes_both_files(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", _dates(1, 4))
    data_dir = tmp_path / "data"

    result = data_export.export_all(data_dir, ["KRW-BTC"], db)

    csv_path = data_dir / "upbit_candles_snapshot.csv"
    report_path = data_dir / "crawl_report.json"
    assert csv_path.exists() and report_path.exists()
    assert result["counts"] == {"KRW-BTC": 4}

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["results"]["KRW-BTC"]["rows"] == 4
    assert saved["source"] == "upbit"
    assert saved["run_id"] == result["report"]["run_id"]


def test_export_empty_market_produces_header_only(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, "KRW-BTC", _dates(1, 2))
    out = tmp_path / "snap.csv"
    # 비어있는 마켓
    counts = data_export.export_candles_csv(out, ["KRW-XRP"], db)
    assert counts == {"KRW-XRP": 0}
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows == []
