import pytest

from app.fomo_score import classify_grade
from app.forecast_score import (
    DEFAULT_HORIZONS,
    _build_supervised,
    build_score_forecast,
)
from app.knn_mirror import build_feature_matrix


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


def test_supervised_target_is_future_score_no_leakage():
    """y[k]는 정확히 (피처 시점 + horizon)의 점수여야 한다(타깃 정렬 검증)."""
    fm = build_feature_matrix(_make_candles(), days=60)
    scores = [it["score"] for it in fm["series"]]
    lags, horizon = 5, 3

    X, y = _build_supervised(fm["matrix"], scores, lags, horizon)

    assert len(X) == len(y)
    # 첫 표본의 피처 시점은 i=lags-1, 타깃은 scores[i+horizon]
    assert y[0] == scores[(lags - 1) + horizon]
    assert y[-1] == scores[-1]  # 마지막 학습 타깃은 시계열 마지막 점수
    # 피처 길이 = lags(점수) + 3(시장 피처)
    assert len(X[0]) == lags + 3


def test_forecast_returns_entry_per_horizon_with_valid_grade():
    result = build_score_forecast(_make_candles(), days=120)

    horizons = [f["horizon_days"] for f in result["forecast"]]
    assert horizons == sorted(set(DEFAULT_HORIZONS))

    for entry in result["forecast"]:
        score = entry["predicted_score"]
        assert score is not None
        assert 0.0 <= score <= 100.0  # FOMO Score 범위로 clamp
        # grade가 예측 점수와 일관적인지
        assert entry["grade"] == classify_grade(score)[0]
        assert entry["backtest_mae"] is None or entry["backtest_mae"] >= 0.0


def test_forecast_is_deterministic():
    """random_state 고정 → 동일 입력은 동일 예측."""
    a = build_score_forecast(_make_candles(), days=120)
    b = build_score_forecast(_make_candles(), days=120)
    assert [f["predicted_score"] for f in a["forecast"]] == [
        f["predicted_score"] for f in b["forecast"]
    ]


def test_summary_avoids_price_language():
    """컴플라이언스: 요약 문구가 가격/수익률이 아닌 심리 상태 관찰로 표현되는지."""
    result = build_score_forecast(_make_candles(), days=120)
    assert "심리" in result["summary"]
    assert "수익률" not in result["summary"] or "예측이나" in result["summary"]
    assert "투자 추천" in result["summary"]


def test_invalid_arguments_are_rejected():
    candles = _make_candles()
    with pytest.raises(ValueError):
        build_score_forecast([], days=120)
    with pytest.raises(ValueError):
        build_score_forecast(candles, lags=0)
    with pytest.raises(ValueError):
        build_score_forecast(candles, days=0)
    with pytest.raises(ValueError):
        build_score_forecast(candles, horizons=(0,))
