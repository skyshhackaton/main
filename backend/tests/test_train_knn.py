import csv

import pytest

from app.knn_mirror import FEATURE_NAMES
from app.train_knn import _cap_k_values, optimize_knn_k, run_knn


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
        for c in candles:
            w.writerow({"market": market, "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                        "open": c["open"], "high": c["high"], "low": c["low"],
                        "close": c["close"], "volume": c["volume"],
                        "trade_price": c["close"], "source": "t", "crawled_at": "now"})


def test_cap_k_values_respects_fold_size():
    assert _cap_k_values((3, 5, 15, 17, 25), n_samples=64, n_splits=3) == [3, 5, 15]
    assert _cap_k_values((100,), n_samples=64, n_splits=3)  # 최소 한 개 보장


def test_optimize_knn_k_returns_valid_best_k():
    result = optimize_knn_k(_make_candles(), k_values=(3, 5, 7), n_splits=3)
    assert result["best_k"] in result["k_values"]
    assert result["feature_set"] == list(FEATURE_NAMES)
    assert len(result["results"]) == len(result["k_values"])
    assert all(r["cv_mae"] >= 0 for r in result["results"])


def test_optimize_knn_k_rejects_bad_horizon():
    with pytest.raises(ValueError):
        optimize_knn_k(_make_candles(), horizon=0)


def test_run_knn_end_to_end(tmp_path):
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, _make_candles())
    report = run_knn(csv_path=csv_path, market="KRW-BTC", k_values=(3, 5, 7), n_splits=3)
    assert report["market"] == "KRW-BTC"
    assert report["n_candles"] == 430
    assert report["knn_k_optimization"]["best_k"] in (3, 5, 7)
    assert "심리 상태값" in report["disclaimer"]
