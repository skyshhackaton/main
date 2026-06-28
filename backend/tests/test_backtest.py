from dataclasses import asdict

import pytest

from app.backtest import (
    evaluate_weights,
    format_sensitivity_table,
    sensitivity_analysis,
    weights_for_sensitivity,
)


def _candles(count: int = 565) -> list[dict]:
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
    result = evaluate_weights(_candles(), days=200, horizon=7)
    assert result["series_count"] == 200
    assert result["evaluated_count"] == 193
    assert sum(row["sample_count"] for row in result["buckets"]) == 193


def test_bucket_statistics_have_valid_rates():
    result = evaluate_weights(_candles())
    for row in result["buckets"]:
        if row["positive_rate"] is not None:
            assert 0.0 <= row["positive_rate"] <= 1.0


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


def test_future_mutation_does_not_change_past_scores():
    candles = _candles()
    from app.fomo_score import score_series

    before = score_series(candles, days=200)
    changed = [dict(candle) for candle in candles]
    changed[-1]["close"] *= 100
    after = score_series(changed, days=200)
    assert [row["score"] for row in before[:-1]] == [row["score"] for row in after[:-1]]
