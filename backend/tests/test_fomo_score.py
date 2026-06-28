from app.fomo_score import classify_grade, clamp, score_at, score_series


# ---------------------------------------------------------------------------
# 팀원 기존 테스트 (유지)
# ---------------------------------------------------------------------------

def test_clamp_bounds_values():
    assert clamp(-1) == 0
    assert clamp(101) == 100
    assert clamp(42) == 42


def test_grade_copy_uses_observation_language():
    grade, description = classify_grade(85)
    assert grade == "극단적 탐욕"
    assert "상태" in description
    assert "수익" not in description


# ---------------------------------------------------------------------------
# 계산 로직 테스트
# ---------------------------------------------------------------------------

def _make_candles(closes, vols=None):
    vols = vols or [100.0] * len(closes)
    candles, prev = [], closes[0]
    for i, c in enumerate(closes):
        candles.append({
            "date_utc": f"2024-01-{(i % 28) + 1:02d}T00:00:00",
            "open": prev, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": vols[i],
        })
        prev = c
    return candles


def test_score_in_range():
    candles = _make_candles([100.0 + i for i in range(400)])
    res = score_at(candles)
    assert 0 <= res["score"] <= 100
    assert "grade" in res and "description" in res
    assert set(res["indicators"]) == {"X1","X2","X3","X4","X5","X6","X7","X8"}


def test_uptrend_scores_higher_than_downtrend():
    up   = _make_candles([100.0 + i for i in range(400)])
    down = _make_candles([500.0 - i for i in range(400)])
    assert score_at(up)["score"] > score_at(down)["score"]


def test_x8_all_up_days():
    closes = [100.0] * 395 + [101.0, 102.0, 103.0, 104.0, 105.0]
    assert score_at(_make_candles(closes))["indicators"]["X8"] == 100.0


def test_score_series_length_and_no_lookahead():
    candles = _make_candles([100.0 + (i % 10) for i in range(500)])
    series = score_series(candles, days=100)
    assert len(series) == 100
    # 시계열 첫 항목이 해당 시점까지 데이터로만 계산되는지 재현성 확인
    assert series[0]["score"] == score_at(candles[:401])["score"]


def test_weights_sum_to_one():
    from app.fomo_score import WEIGHTS
    import dataclasses
    total = sum(dataclasses.asdict(WEIGHTS).values())
    assert abs(total - 1.0) < 1e-9
