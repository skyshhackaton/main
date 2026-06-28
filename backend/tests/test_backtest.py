from dataclasses import asdict

import pytest

from app.backtest import (
    DEFAULT_SNAPSHOT_PATH,
    evaluate_weights,
    format_sensitivity_table,
    load_snapshot_candles,
    run_snapshot_backtests,
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
    assert all(len(row["buckets"]) == 5 for row in rows)
    assert all(row["score_summary"]["min"] <= row["score_summary"]["mean"] <= row["score_summary"]["max"] for row in rows)
    assert all(sum(bucket["sample_count"] for bucket in row["buckets"]) == 193 for row in rows)


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


def test_official_snapshot_contains_three_oldest_first_markets():
    assert DEFAULT_SNAPSHOT_PATH.name == "upbit_candles_snapshot.csv"
    for market in ("KRW-BTC", "KRW-ETH", "KRW-XRP"):
        candles = load_snapshot_candles(market)
        assert len(candles) == 565
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
