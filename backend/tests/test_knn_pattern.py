import csv

import numpy as np
import pytest

from app.knn_pattern import (
    METRICS,
    _window_matrix,
    _znorm_rows,
    backtest_config,
    build_fomo_pattern_forecast,
    compare_configs,
    compare_holdout,
    fomo_score_series,
    load_candles_from_csv,
    run_pattern_analysis,
    validate_holdout,
)


def _make_candles(length: int = 430) -> list[dict]:
    candles = []
    for i in range(length):
        close = 100.0 + (i % 20) + (i % 7) * 0.3  # 약간의 변동/주기
        candles.append(
            {
                "date_utc": f"2024-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00-{i:04d}",
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100.0 + (i % 9),
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
            for c in candles:
                w.writerow({
                    "market": mkt, "date_utc": c["date_utc"], "date_kst": c["date_utc"],
                    "open": c["open"], "high": c["high"], "low": c["low"],
                    "close": c["close"], "volume": c["volume"],
                    "trade_price": c["close"], "source": "test", "crawled_at": "now",
                })


def test_window_matrix_shape_and_content():
    scores = np.arange(10.0)
    mat = _window_matrix(scores, 3)
    assert mat.shape == (8, 3)
    assert list(mat[0]) == [0.0, 1.0, 2.0]
    assert list(mat[-1]) == [7.0, 8.0, 9.0]  # 끝점 e=9


def test_znorm_rows_zero_mean_unit_std():
    mat = np.array([[1.0, 2.0, 3.0], [10.0, 10.0, 10.0]])  # 두 번째는 상수행
    z = _znorm_rows(mat)
    assert np.allclose(z[0].mean(), 0.0)
    assert np.isclose(z[0].std(), 1.0)
    assert np.allclose(z[1], 0.0)  # 상수행은 0 (0분산 보호)


def test_build_forecast_structure_and_no_lookahead():
    fc = build_fomo_pattern_forecast(
        _make_candles(), window=10, horizon=7, k=5, metric="raw"
    )
    assert fc["k"] == 5
    assert len(fc["candidates"]) == 5
    assert len(fc["band"]["mean"]) == 7
    for cand in fc["candidates"]:
        # 후보는 현재보다 과거여야 하고, horizon만큼 실현된 미래가 있어야 한다.
        assert cand["match_end_date"] < fc["current_date"]
        assert len(cand["future_scores"]) == 7
        assert len(cand["anchored_future"]) == 7
        assert all(0.0 <= v <= 100.0 for v in cand["anchored_future"])  # clamp
    assert "보장하지 않습니다" in fc["summary"]


def test_build_forecast_rejects_bad_args():
    candles = _make_candles()
    with pytest.raises(ValueError):
        build_fomo_pattern_forecast(candles, window=1)
    with pytest.raises(ValueError):
        build_fomo_pattern_forecast(candles, horizon=0)
    with pytest.raises(ValueError):
        build_fomo_pattern_forecast(candles, k=0)
    with pytest.raises(ValueError):
        build_fomo_pattern_forecast(candles, metric="cosine")


def test_backtest_config_reports_skill_vs_baseline():
    scores, _ = fomo_score_series(_make_candles())
    res = backtest_config(scores, window=5, horizon=3, k=3, metric="raw", test_size=20)
    assert res["origins"] > 0
    assert res["analog_mae"] >= 0
    assert res["persist_mae"] >= 0
    # skill = 1 - analog/persist
    assert np.isclose(res["skill"], 1.0 - res["analog_mae"] / res["persist_mae"], atol=1e-3)


def test_compare_configs_sorted_by_skill_desc():
    results = compare_configs(
        _make_candles(), windows=(5, 10), horizons=(3, 7),
        ks=(3,), metrics=METRICS, test_size=20,
    )
    assert len(results) == 2 * 2 * 1 * 2  # w*h*k*metric
    skills = [r["skill"] for r in results if r["skill"] is not None]
    assert skills == sorted(skills, reverse=True)


def test_validate_holdout_pool_is_train_only():
    """검증 원점은 cutoff 이후, analog 풀은 train 구간(미래가 cutoff 전)만 사용."""
    scores, _ = fomo_score_series(_make_candles())
    res = validate_holdout(scores, window=5, horizon=3, k=3, metric="raw",
                           train_ratio=0.7, collect=True)
    n = len(scores)
    cutoff = int(n * 0.7)
    assert res["cutoff_index"] == cutoff
    assert res["val_origins"] > 0
    # train 풀 크기 = cutoff-1-H-(W-1)+1 = cutoff-H-W+1
    assert res["train_pool"] == cutoff - 3 - 5 + 1
    assert res["skill"] is not None
    assert len(res["per_step"]["analog_mae"]) == 3
    assert len(res["scatter"]["pred_h"]) == res["val_origins"]


def test_validate_holdout_rejects_bad_ratio():
    scores, _ = fomo_score_series(_make_candles())
    with pytest.raises(ValueError):
        validate_holdout(scores, 5, 3, 3, "raw", train_ratio=0.0)
    with pytest.raises(ValueError):
        validate_holdout(scores, 5, 3, 3, "raw", train_ratio=1.0)


def test_compare_holdout_sorted_and_complete():
    results = compare_holdout(
        _make_candles(), windows=(5, 10), horizons=(3, 7),
        ks=(3,), metrics=METRICS, train_ratio=0.7,
    )
    assert len(results) == 2 * 2 * 1 * 2
    skills = [r["skill"] for r in results if r["skill"] is not None]
    assert skills == sorted(skills, reverse=True)


def test_run_pattern_analysis_end_to_end(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles())
    report = run_pattern_analysis(csv_path, market="KRW-BTC", test_size=20, train_ratio=0.7)
    assert report["market"] == "KRW-BTC"
    assert report["n_candles"] == 430
    assert report["recommended_config"] is not None
    assert report["holdout_best"] is not None
    assert report["holdout_comparison"]
    assert report["current_forecast"] is not None
    assert "심리" in report["disclaimer"]


def test_load_candles_missing_market_raises(tmp_path):
    csv_path = tmp_path / "hist.csv"
    _write_csv(csv_path, _make_candles(20))
    with pytest.raises(ValueError):
        load_candles_from_csv(csv_path, market="KRW-DOGE")
