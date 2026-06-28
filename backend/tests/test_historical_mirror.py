import pytest

from app.historical_mirror import build_historical_mirror


def _make_candles(length: int = 430) -> list[dict]:
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


def test_historical_mirror_returns_periods_and_stats():
    result = build_historical_mirror(
        _make_candles(),
        current_score=50.0,
        tolerance=100.0,
        days=60,
        max_periods=5,
    )

    assert result["current_score"] == 50.0
    assert len(result["similar_periods"]) == 5
    assert result["stats"]["sample_count"] == 59
    assert result["stats"]["sample_count_3d"] == 57
    assert result["stats"]["sample_count_7d"] == 53
    assert result["stats"]["sample_count_30d"] == 30
    assert "미래 성과를 보장하지 않습니다" in result["summary"]


def test_future_return_boundary_uses_none_when_horizon_exceeds_data():
    result = build_historical_mirror(
        _make_candles(),
        current_score=50.0,
        tolerance=100.0,
        days=5,
        max_periods=10,
    )

    periods = result["similar_periods"]
    assert periods[-1]["ret_3d"] is None
    assert all(p["ret_30d"] is None for p in periods)
    assert result["stats"]["sample_count_30d"] == 0
    assert result["stats"]["mean_30d"] is None


def test_invalid_arguments_are_rejected():
    candles = _make_candles()

    with pytest.raises(ValueError):
        build_historical_mirror([], current_score=50.0)
    with pytest.raises(ValueError):
        build_historical_mirror(candles, tolerance=-1)
    with pytest.raises(ValueError):
        build_historical_mirror(candles, days=0)
    with pytest.raises(ValueError):
        build_historical_mirror(candles, max_periods=0)
