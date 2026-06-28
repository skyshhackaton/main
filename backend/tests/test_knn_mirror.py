import math

import numpy as np
import pytest
from sklearn.neighbors import NearestNeighbors

from app.historical_mirror import build_historical_mirror
from app.knn_mirror import (
    FEATURE_NAMES,
    _scale_features,
    build_feature_matrix,
    build_knn_mirror,
)


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


def test_scale_features_normalizes_each_column():
    """StandardScaler 적용 검증: 각 피처 열이 평균0 / 분산1로 정규화되어야 한다."""
    matrix = build_feature_matrix(_make_candles(), days=60)["matrix"]

    scaled = _scale_features(matrix)

    means = scaled.mean(axis=0)
    stds = scaled.std(axis=0)
    assert np.allclose(means, 0.0, atol=1e-9)
    # 분산이 0이 아닌 열은 표준편차가 1이어야 한다(상수 열은 0으로 남음).
    for col in range(scaled.shape[1]):
        if np.std(np.asarray(matrix, dtype=float)[:, col]) > 0:
            assert math.isclose(stds[col], 1.0, abs_tol=1e-9)


def test_scaling_prevents_score_from_dominating_distance():
    """스케일링이 실제로 거리 지배를 막는지 검증.

    score 축은 스케일이 큰 값(±50), 나머지 피처는 미세한 차이만 갖도록 구성한다.
    - 원본(raw) 거리에서는 score가 가장 가까운 행이 선택된다.
    - 표준화 후에는 score 영향이 균등화되어 '다른' 행이 가장 가까워진다.
    이 차이가 곧 스케일링이 적용되고 있다는 증거다.
    """
    # 열: [score, change_rate, volume_ratio, rsi] — score만 스케일이 크다(~1000).
    candidate_a = [1000.0, 10.0, 10.0, 10.0]  # score는 쿼리와 동일, 나머지는 멀다
    candidate_b = [900.0, 0.0, 0.0, 0.0]      # score는 멀지만, 나머지 3개는 쿼리와 동일
    query_row = [1000.0, 0.0, 0.0, 0.0]
    matrix = [candidate_a, candidate_b, query_row]

    query = np.asarray(matrix[-1:], dtype=float)
    candidates_raw = np.asarray(matrix[:-1], dtype=float)

    raw_nn = NearestNeighbors(n_neighbors=1).fit(candidates_raw)
    raw_choice = int(raw_nn.kneighbors(query)[1][0][0])

    scaled = _scale_features(matrix)
    scaled_nn = NearestNeighbors(n_neighbors=1).fit(scaled[:-1])
    scaled_choice = int(scaled_nn.kneighbors(scaled[-1:])[1][0][0])

    # 원본 거리는 큰 스케일의 score에 지배되어 score가 일치하는 A(0)를 고른다.
    assert raw_choice == 0
    # 표준화 후에는 모든 피처 가중이 균등해져, 3개 피처가 일치하는 B(1)가 선택된다.
    assert scaled_choice == 1
    assert raw_choice != scaled_choice


def test_build_knn_mirror_structure_matches_historical_mirror():
    """출력 형식이 historical_mirror와 1:1 비교 가능해야 한다."""
    candles = _make_candles()
    knn = build_knn_mirror(candles, n_neighbors=5, days=60)
    mirror = build_historical_mirror(candles, tolerance=100.0, days=60, max_periods=5)

    # 공통 최상위 키
    for key in ("current_date", "current_score", "current_grade", "similar_periods", "stats", "summary"):
        assert key in knn

    assert knn["n_neighbors"] == 5
    assert len(knn["similar_periods"]) == 5
    assert list(knn["features"]) == list(FEATURE_NAMES)

    # similar_periods 항목 키가 historical_mirror와 동일(거리 필드만 추가)
    sample = knn["similar_periods"][0]
    for key in mirror["similar_periods"][0]:
        assert key in sample
    assert "distance" in sample

    # stats 블록은 동일 헬퍼 재사용 → 키 집합이 정확히 일치
    assert set(knn["stats"].keys()) == set(mirror["stats"].keys())
    assert knn["stats"]["sample_count"] == 5


def test_neighbors_sorted_by_distance():
    knn = build_knn_mirror(_make_candles(), n_neighbors=5, days=60)
    distances = [p["distance"] for p in knn["similar_periods"]]
    assert distances == sorted(distances)


def test_future_returns_use_none_past_data_boundary():
    knn = build_knn_mirror(_make_candles(), n_neighbors=5, days=5)
    # days=5 → 후보가 매우 적고, 일부는 30일 미래 데이터가 없어 None이 나올 수 있다.
    assert all(p["ret_3d"] is None or isinstance(p["ret_3d"], float) for p in knn["similar_periods"])


def test_invalid_arguments_are_rejected():
    candles = _make_candles()
    with pytest.raises(ValueError):
        build_knn_mirror([], n_neighbors=5)
    with pytest.raises(ValueError):
        build_knn_mirror(candles, n_neighbors=0)
    with pytest.raises(ValueError):
        build_knn_mirror(candles, days=0)
