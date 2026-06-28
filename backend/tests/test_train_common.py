import csv

import numpy as np
import pytest

from app.train_common import fomo_scores, load_candles_from_csv, metrics


def _make_candles(length: int = 430) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20)
        candles.append(
            {
                "date_utc": f"2025-01-{(i % 28) + 1:02d}T00:00:00-{i:03d}",
                "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
                "close": close, "volume": 100.0 + (i % 7),
            }
        )
    return candles


def _write_csv(path, candles, market="KRW-BTC"):
    cols = ["market", "date_utc", "date_kst", "open", "high", "low",
            "close", "volume", "trade_price", "source", "crawled_at"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for mkt in ("KRW-ETH", market):
            for c in reversed(candles):  # 정렬 흐트러뜨려 로더 정렬 검증
                w.writerow({"market": mkt, "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                            "open": c["open"], "high": c["high"], "low": c["low"],
                            "close": c["close"], "volume": c["volume"],
                            "trade_price": c["close"], "source": "t", "crawled_at": "now"})


def test_load_candles_filters_and_sorts(tmp_path):
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, _make_candles(30))
    loaded = load_candles_from_csv(csv_path, market="KRW-BTC")
    assert len(loaded) == 30
    assert [c["date_utc"] for c in loaded] == sorted(c["date_utc"] for c in loaded)
    assert set(loaded[0]) == {"date_utc", "open", "high", "low", "close", "volume"}


def test_load_candles_missing_market_raises(tmp_path):
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, _make_candles(20))
    with pytest.raises(ValueError):
        load_candles_from_csv(csv_path, market="KRW-DOGE")


def test_fomo_scores_returns_array():
    scores = fomo_scores(_make_candles())
    assert isinstance(scores, np.ndarray)
    assert len(scores) == 430 - 365  # MIN_WINDOW=365
    assert np.all((scores >= 0) & (scores <= 100))


def test_metrics_mae_rmse():
    mae, rmse = metrics(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 5.0]))
    assert np.isclose(mae, 2.0 / 3)
    assert np.isclose(rmse, np.sqrt(4.0 / 3))
