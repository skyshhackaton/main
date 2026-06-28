import csv

import pytest

from app.backtest_expanding import (
    expanding_backtest_knn,
    expanding_backtest_xgb,
    run_expanding,
)
from app.train_common import fomo_scores


def _make_candles(length: int = 460) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20) + (i % 7) * 0.3
        candles.append(
            {
                "date_utc": f"2024-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00-{i:04d}",
                "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
                "close": close, "volume": 100.0 + (i % 9),
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


def test_expanding_xgb_reports_skill_and_no_lookahead():
    res = expanding_backtest_xgb(_make_candles(), horizon=3, retrain_every=5, collect=True)
    assert res["origins"] > 0
    assert res["mae"] >= 0 and res["persist_mae"] >= 0
    assert res["skill"] is not None
    st = res["stitched"]
    assert len(st["target_index"]) == res["origins"] == len(st["pred"])
    # target 시점은 단조 증가(시간순 워크포워드)
    assert st["target_index"] == sorted(st["target_index"])


def test_expanding_knn_reports_skill():
    scores = fomo_scores(_make_candles())
    res = expanding_backtest_knn(scores, horizon=3, window=10, k=5, collect=True)
    assert res["origins"] > 0
    assert res["skill"] is not None
    assert len(res["stitched"]["pred"]) == res["origins"]


def test_expanding_lstm_reports_skill():
    pytest.importorskip("torch")
    from app.backtest_expanding import expanding_backtest_lstm

    scores = fomo_scores(_make_candles())
    res = expanding_backtest_lstm(scores, horizon=3, window=10, hidden=8, input_dense=0,
                                  epochs=5, retrain_every=5)
    assert res["origins"] > 0
    assert res["mae"] >= 0
    assert res["skill"] is not None


def test_run_expanding_compares_holdout_and_expanding(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    report = run_expanding(csv_path, market="KRW-BTC", horizons=(1, 3), include_lstm=False)
    assert len(report["comparison"]) == 2
    for r in report["comparison"]:
        for key in ("knn_holdout", "knn_expanding", "xgb_holdout", "xgb_expanding"):
            assert key in r
