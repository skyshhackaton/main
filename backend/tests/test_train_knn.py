import csv

import pytest

from app.knn_mirror import FEATURE_NAMES
from app.train_knn import (
    _cap_k_values,
    load_candles_from_csv,
    optimize_knn_k,
    run_training,
    train_xgb_fomo,
    tune_xgb_fomo,
)


def _make_candles(length: int = 460) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20)
        candles.append(
            {
                "date_utc": f"2025-01-{(i % 28) + 1:02d}T00:00:00-{i:03d}",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100.0 + (i % 7),
            }
        )
    return candles


def _write_csv(path, candles, market="KRW-BTC", extra_market="KRW-ETH"):
    cols = [
        "market", "date_utc", "date_kst", "open", "high", "low",
        "close", "volume", "trade_price", "source", "crawled_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        # 일부러 정렬을 흐트러뜨려 저장 — 로더가 정렬하는지 검증
        for mkt in (extra_market, market):
            for c in reversed(candles):
                w.writerow({
                    "market": mkt, "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                    "open": c["open"], "high": c["high"], "low": c["low"],
                    "close": c["close"], "volume": c["volume"],
                    "trade_price": c["close"], "source": "test", "crawled_at": "now",
                })


def test_load_candles_filters_market_and_sorts(tmp_path):
    candles = _make_candles(30)
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, candles)

    loaded = load_candles_from_csv(csv_path, market="KRW-BTC")

    assert len(loaded) == 30  # KRW-ETH 행은 제외
    dates = [c["date_utc"] for c in loaded]
    assert dates == sorted(dates)  # oldest-first 정렬
    assert isinstance(loaded[0]["close"], float)
    assert set(loaded[0]) == {"date_utc", "open", "high", "low", "close", "volume"}


def test_load_candles_missing_market_raises(tmp_path):
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, _make_candles(20))
    with pytest.raises(ValueError):
        load_candles_from_csv(csv_path, market="KRW-DOGE")


def test_cap_k_values_respects_fold_size():
    # n=64, n_splits=3 → first train fold = 64//4 = 16 → k<16만 허용
    capped = _cap_k_values((3, 5, 15, 17, 25), n_samples=64, n_splits=3)
    assert capped == [3, 5, 15]
    # 모두 너무 크면 최소 한 개는 보장
    assert _cap_k_values((100,), n_samples=64, n_splits=3)


def test_optimize_knn_k_returns_valid_best_k():
    result = optimize_knn_k(
        _make_candles(), k_values=(3, 5, 7), n_splits=3
    )
    assert result["best_k"] in result["k_values"]
    assert result["feature_set"] == list(FEATURE_NAMES)
    assert len(result["results"]) == len(result["k_values"])
    assert all(r["cv_mae"] >= 0 for r in result["results"])
    assert result["best_cv_mae"] >= 0


def test_optimize_knn_k_rejects_bad_horizon():
    with pytest.raises(ValueError):
        optimize_knn_k(_make_candles(), horizon=0)


def test_train_xgb_fomo_reports_metrics_and_importances():
    result = train_xgb_fomo(
        _make_candles(), horizons=(1, 3), lags=5, n_splits=3
    )
    assert result["lags"] == 5
    # 피처 이름 = lag 5개 + 시장 피처 3개
    assert len(result["feature_names"]) == 5 + 3

    for horizon in ("1", "3"):
        info = result["horizons"][horizon]
        assert info["cv_mae"] >= 0
        assert info["cv_rmse"] >= 0
        assert "baseline_persist_mae" in info
        imp = info["feature_importances"]
        assert set(imp.keys()) == set(result["feature_names"])
        assert all(v >= 0 for v in imp.values())


def test_train_xgb_fomo_rejects_bad_args():
    candles = _make_candles()
    with pytest.raises(ValueError):
        train_xgb_fomo(candles, lags=0)
    with pytest.raises(ValueError):
        train_xgb_fomo(candles, horizons=(0,))


def test_tune_xgb_fomo_selects_best_params():
    grid = {"n_estimators": [50], "max_depth": [2, 3], "learning_rate": [0.1]}
    result = tune_xgb_fomo(
        _make_candles(), horizons=(1,), lags=5, param_grid=grid, n_splits=3
    )
    assert result["n_candidates"] == 2  # 1*2*1
    info = result["horizons"]["1"]
    assert info["best_params"]["max_depth"] in (2, 3)
    assert info["cv_mae"] >= 0
    assert info["baseline_persist_mae"] >= 0
    assert set(info["feature_importances"].keys()) == set(result["feature_names"])


def test_run_training_can_include_tuning(tmp_path):
    import csv as _csv
    cols = ["market", "date_utc", "date_kst", "open", "high", "low",
            "close", "volume", "trade_price", "source", "crawled_at"]
    csv_path = tmp_path / "snap.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in _make_candles():
            w.writerow({"market": "KRW-BTC", "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                        "open": c["open"], "high": c["high"], "low": c["low"],
                        "close": c["close"], "volume": c["volume"],
                        "trade_price": c["close"], "source": "t", "crawled_at": "now"})
    report = run_training(csv_path=csv_path, market="KRW-BTC", k_values=(3, 5),
                          horizons=(1,), n_splits=3, tune_xgb=True)
    assert "xgboost_tuned" in report
    assert "1" in report["xgboost_tuned"]["horizons"]


def test_run_training_end_to_end(tmp_path):
    csv_path = tmp_path / "snap.csv"
    _write_csv(csv_path, _make_candles())
    report = run_training(
        csv_path=csv_path, market="KRW-BTC", k_values=(3, 5, 7),
        horizons=(1, 3), n_splits=3,
    )
    assert report["market"] == "KRW-BTC"
    assert report["n_candles"] == 460
    assert report["knn_k_optimization"]["best_k"] in (3, 5, 7)
    assert set(report["xgboost_fomo_forecast"]["horizons"]) == {"1", "3"}
    assert "심리 상태값" in report["disclaimer"]
