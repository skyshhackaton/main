from app.fomo_score import classify_grade, clamp


def test_clamp_bounds_values():
    assert clamp(-1) == 0
    assert clamp(101) == 100
    assert clamp(42) == 42


def test_grade_copy_uses_observation_language():
    grade, description = classify_grade(85)
    assert grade == "극단적 탐욕"
    assert "상태" in description
    assert "수익" not in description
