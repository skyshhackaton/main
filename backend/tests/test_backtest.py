from dataclasses import asdict

import pytest

from app.backtest import (
    DEFAULT_BACKTEST_DAYS,
    DEFAULT_SNAPSHOT_PATH,
    evaluate_weights,
    format_sensitivity_table,
    indicator_ablation_analysis,
    load_snapshot_candles,
    run_snapshot_backtests,
    sensitivity_analysis,
    weights_for_sensitivity,
    weights_without_indicator,
)


def _candles(count: int = 2200) -> list[dict]:
    result = []
    for i in range(count):
        close = 100.0 + i * 0.05 + (i % 12) * 0.4
        result.append(
            {
                "date_utc": f"day-{i:04d}",
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 100.0 + (i % 9) * 10,
            }
        )
    return result


def test_evaluate_weights_excludes_last_horizon_observations():
    result = evaluate_weights(_candles(), horizon=7)
    assert DEFAULT_BACKTEST_DAYS == 1835
    assert result["series_count"] == 1835
    assert result["evaluated_count"] == 1828
    assert sum(row["sample_count"] for row in result["buckets"]) == 1828


def test_bucket_statistics_have_valid_rates():
    result = evaluate_weights(_candles())
    for row in result["buckets"]:
        if row["positive_rate"] is not None:
            assert 0.0 <= row["positive_rate"] <= 1.0


@pytest.mark.parametrize("days", [0, -1])
def test_evaluate_weights_rejects_non_positive_days(days):
    with pytest.raises(ValueError, match="days must be positive"):
        evaluate_weights(_candles(), days=days)


def test_evaluate_weights_rejects_insufficient_candles():
    with pytest.raises(ValueError, match="at least 366 candles"):
        evaluate_weights(_candles(365))


def test_custom_horizon_uses_generic_return_name():
    result = evaluate_weights(_candles(), horizon=3)
    assert result["horizon"] == 3
    assert all("mean_forward_return" in row for row in result["buckets"])
    assert all("mean_7d_return" not in row for row in result["buckets"])
    assert "mean_forward_return" in result["high_greed_report"]
    assert "mean_7d_return" not in result["high_greed_report"]


def test_default_horizon_keeps_seven_day_compatibility_name():
    result = evaluate_weights(_candles(), horizon=7)
    assert all(
        row["mean_7d_return"] == row["mean_forward_return"]
        for row in result["buckets"]
    )


@pytest.mark.parametrize("x7,x8", [(0.15, 0.15), (0.20, 0.20), (0.25, 0.25)])
def test_sensitivity_weights_always_sum_to_one(x7, x8):
    weights = weights_for_sensitivity(x7, x8)
    assert sum(asdict(weights).values()) == pytest.approx(1.0)
    assert weights.volume_momentum == x7
    assert weights.win_streak == x8


def test_sensitivity_analysis_returns_nine_combinations():
    rows = sensitivity_analysis(_candles())
    assert len(rows) == 9
    assert all(row["weight_sum"] == pytest.approx(1.0) for row in rows)
    assert len(format_sensitivity_table(rows).splitlines()) == 11
    assert all(len(row["buckets"]) == 5 for row in rows)
    assert all(row["score_summary"]["min"] <= row["score_summary"]["mean"] <= row["score_summary"]["max"] for row in rows)
    assert all(sum(bucket["sample_count"] for bucket in row["buckets"]) == 1828 for row in rows)


@pytest.mark.parametrize("indicator", ["X3", "X6"])
def test_ablation_weights_remove_indicator_and_sum_to_one(indicator):
    weights = weights_without_indicator(indicator)
    values = asdict(weights)
    field = {"X3": "market_breadth", "X6": "volatility_inverse"}[indicator]
    assert values[field] == 0.0
    assert sum(values.values()) == pytest.approx(1.0)


def test_indicator_ablation_reports_score_and_bucket_changes():
    rows = indicator_ablation_analysis(_candles(), indicators=("X3", "X6"))
    assert [row["indicator"] for row in rows] == ["X3", "X6"]
    assert all(row["weight_sum"] == pytest.approx(1.0) for row in rows)
    assert all(row["mean_abs_score_change"] >= 0 for row in rows)
    assert all(row["max_abs_score_change"] >= row["mean_abs_score_change"] for row in rows)
    assert all(0 <= row["bucket_change_count"] <= DEFAULT_BACKTEST_DAYS for row in rows)
    assert all(len(row["buckets"]) == 5 for row in rows)


def test_indicator_ablation_rejects_unknown_indicator():
    with pytest.raises(ValueError, match="indicator must be one of"):
        weights_without_indicator("X9")


def test_sensitivity_table_includes_forward_outcomes():
    table = format_sensitivity_table(sensitivity_analysis(_candles()))
    assert "n/ret/up" in table
    assert "%" in table
    assert "N/A" in table


def test_baseline_backtest_matches_production_score_series():
    from app.backtest import _score_series_with_weights
    from app.fomo_score import WEIGHTS, score_series

    candles = _candles()
    assert _score_series_with_weights(candles, 200, WEIGHTS) == score_series(candles, 200)


def test_sensitivity_does_not_mutate_production_weights():
    from app import fomo_score

    original = fomo_score.WEIGHTS
    sensitivity_analysis(_candles())
    assert fomo_score.WEIGHTS is original


def test_future_mutation_does_not_change_past_scores():
    candles = _candles()
    from app.fomo_score import score_series

    before = score_series(candles, days=200)
    changed = [dict(candle) for candle in candles]
    changed[-1]["close"] *= 100
    after = score_series(changed, days=200)
    assert [row["score"] for row in before[:-1]] == [row["score"] for row in after[:-1]]


@pytest.mark.parametrize("future_offset", [25, 75, 150])
def test_suffix_mutation_does_not_change_earlier_scores(future_offset):
    candles = _candles()
    from app.fomo_score import score_series

    before = score_series(candles, days=200)
    changed = [dict(candle) for candle in candles]
    series_start = len(candles) - len(before)
    mutation_index = series_start + future_offset
    for candle in changed[mutation_index:]:
        candle["close"] *= 10

    after = score_series(changed, days=200)
    assert [row["score"] for row in before[:future_offset]] == [
        row["score"] for row in after[:future_offset]
    ]


def test_official_snapshot_contains_three_oldest_first_markets():
    assert DEFAULT_SNAPSHOT_PATH.name == "upbit_candles_snapshot.csv"
    for market in ("KRW-BTC", "KRW-ETH", "KRW-XRP"):
        candles = load_snapshot_candles(market)
        assert len(candles) == 2200
        assert candles == sorted(candles, key=lambda candle: candle["date_utc"])


def test_run_snapshot_backtests_uses_requested_csv(tmp_path):
    csv_path = tmp_path / "snapshot.csv"
    header = "market,date_utc,open,high,low,close,volume\n"
    rows = "".join(
        f"KRW-BTC,day-{i:04d},{100+i},{102+i},{99+i},{101+i},{1000+i}\n"
        for i in range(565)
    )
    csv_path.write_text(header + rows, encoding="utf-8")

    result = run_snapshot_backtests(("KRW-BTC",), csv_path)
    assert result["KRW-BTC"]["source"] == str(csv_path)
    assert result["KRW-BTC"]["candle_count"] == 565
    assert result["KRW-BTC"]["baseline"]["series_count"] == 200
