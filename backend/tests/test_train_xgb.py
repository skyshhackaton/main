import csv

import pytest

from app.train_xgb import (
    evaluate_xgb_holdout,
    run_xgb,
    train_xgb_fomo,
    tune_xgb_fomo,
)


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


def test_train_xgb_fomo_reports_metrics_and_importances():
    result = train_xgb_fomo(_make_candles(), horizons=(1, 3), lags=5, n_splits=3)
    assert len(result["feature_names"]) == 5 + 3
    for h in ("1", "3"):
        info = result["horizons"][h]
        assert info["cv_mae"] >= 0
        assert "baseline_persist_mae" in info
        assert set(info["feature_importances"]) == set(result["feature_names"])


def test_train_xgb_fomo_rejects_bad_args():
    candles = _make_candles()
    with pytest.raises(ValueError):
        train_xgb_fomo(candles, lags=0)
    with pytest.raises(ValueError):
        train_xgb_fomo(candles, horizons=(0,))


def test_tune_xgb_fomo_selects_best_params():
    grid = {"n_estimators": [50], "max_depth": [2, 3], "learning_rate": [0.1]}
    result = tune_xgb_fomo(_make_candles(), horizons=(1,), lags=5, param_grid=grid, n_splits=3)
    assert result["n_candidates"] == 2
    info = result["horizons"]["1"]
    assert info["best_params"]["max_depth"] in (2, 3)
    assert info["cv_mae"] >= 0
    assert set(info["feature_importances"]) == set(result["feature_names"])


def test_evaluate_xgb_holdout_reports_skill():
    res = evaluate_xgb_holdout(_make_candles(), horizon=3, lags=5, train_ratio=0.7)
    assert res["val_mae"] >= 0
    assert res["persist_mae"] >= 0
    assert res["skill"] is not None


def test_run_xgb_includes_tuning(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    report = run_xgb(csv_path=csv_path, market="KRW-BTC", horizons=(1,), n_splits=3, tune=True)
    assert "xgboost_tuned" in report
    assert "1" in report["xgboost_tuned"]["horizons"]
