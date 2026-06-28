"""KNN Mirror analysis.

조건 매칭(historical_mirror) 대비 더 정교하게, 여러 피처를 함께 본 거리 기반으로
현재와 가장 유사했던 과거 구간을 찾는다. 피처는 시점 t 기준 과거 정보만 사용하며
(look-ahead bias 없음), 미래 수익률 필드는 후보 시점이 정해진 뒤에만 계산하는
과거 회고 통계일 뿐 투자 추천/예측이 아니다.

출력 형식과 통계(stats) 산출은 historical_mirror와 1:1 비교가 가능하도록
동일한 헬퍼를 그대로 재사용한다. 차이는 유사도 측정 방식뿐이다.
- historical_mirror: 점수 한 축의 ±tolerance 조건 매칭
- knn_mirror: [fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14] 4피처를
  StandardScaler로 정규화한 뒤 NearestNeighbors로 탐색
"""

from __future__ import annotations

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from app.fomo_score import _calc_rsi, score_series

# historical_mirror와 동일한 통계/수익률 로직을 재사용해 결과를 1:1 비교 가능하게 둔다.
from app.historical_mirror import (
    DEFAULT_HORIZONS,
    _build_period_summary,
    _future_return,
    _round_optional,
    _summarize_returns,
)

FEATURE_NAMES = ("fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14")
KNN_METHOD = "feature_knn"
KNN_METHOD_LABEL = "피처 유사도"
RSI_PERIOD = 14
VOLUME_SHORT = 5
VOLUME_LONG = 20


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _change_rate_1d(closes: list[float], index: int) -> float:
    """시점 t의 1일 변화율. index==0이거나 직전 종가가 0이면 0.0."""
    if index <= 0:
        return 0.0
    prev = closes[index - 1]
    if prev == 0:
        return 0.0
    return closes[index] / prev - 1


def _volume_ratio(vols: list[float], index: int) -> float:
    """5일 평균 거래량 / 20일 평균 거래량 (시점 t까지의 과거만 사용)."""
    short = vols[max(0, index - VOLUME_SHORT + 1) : index + 1]
    long = vols[max(0, index - VOLUME_LONG + 1) : index + 1]
    long_mean = _mean(long)
    return _mean(short) / long_mean if long_mean else 1.0


def _feature_vector_at(
    closes: list[float], vols: list[float], index: int, fomo_score: float
) -> list[float]:
    """시점 t(=index)의 피처 벡터. look-ahead 없이 과거 정보만 사용."""
    return [
        fomo_score,
        _change_rate_1d(closes, index),
        _volume_ratio(vols, index),
        _calc_rsi(closes[: index + 1], RSI_PERIOD),
    ]


def build_feature_matrix(candles: list[dict], days: int = 200) -> dict:
    """최근 days일 각 시점의 피처 행렬을 score_series와 동일한 정렬로 구성.

    반환: {"series", "matrix", "candle_indices"} — matrix[i]는 series[i]에,
    candle_indices[i]는 원본 candles의 인덱스에 대응한다.
    """
    series = score_series(candles, days=days)
    if not series:
        raise ValueError("not enough candles to build score series")

    closes = [c["close"] for c in candles]
    vols = [c["volume"] for c in candles]
    series_start_index = len(candles) - len(series)

    matrix: list[list[float]] = []
    candle_indices: list[int] = []
    for offset, item in enumerate(series):
        index = series_start_index + offset
        matrix.append(_feature_vector_at(closes, vols, index, item["score"]))
        candle_indices.append(index)

    return {"series": series, "matrix": matrix, "candle_indices": candle_indices}


def _scale_features(matrix: list[list[float]]) -> np.ndarray:
    """StandardScaler로 피처 정규화.

    score(0~100)가 change_rate(±0.x) 같은 작은 스케일 피처를 거리에서 압도하는 것을
    막기 위한 **필수** 단계. 각 열을 평균0/분산1로 맞춘다.
    """
    return StandardScaler().fit_transform(np.asarray(matrix, dtype=float))


def build_knn_mirror(
    candles: list[dict],
    n_neighbors: int = 5,
    days: int = 200,
) -> dict:
    """현재 시점과 피처 공간에서 가장 가까운 과거 n개 구간을 반환.

    출력 구조는 historical_mirror.build_historical_mirror와 동일하게 맞춘다.
    (tolerance 대신 n_neighbors, score_gap에 더해 distance 필드를 추가)
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if n_neighbors <= 0:
        raise ValueError("n_neighbors must be positive")
    if days <= 0:
        raise ValueError("days must be positive")

    fm = build_feature_matrix(candles, days=days)
    series = fm["series"]
    matrix = fm["matrix"]
    candle_indices = fm["candle_indices"]

    if len(matrix) < 2:
        raise ValueError("not enough samples to run KNN (need at least 2 points)")

    scaled = _scale_features(matrix)
    # 마지막 점이 현재 시점, 그 이전이 과거 후보들.
    candidate_scaled = scaled[:-1]
    query = scaled[-1:]
    current = series[-1]

    k = min(n_neighbors, len(candidate_scaled))
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(candidate_scaled)
    distances, neighbor_idx = nn.kneighbors(query)

    target_score = current["score"]
    matches = []
    for distance, idx in zip(distances[0], neighbor_idx[0]):
        item = series[idx]
        candle_index = candle_indices[idx]
        period = {
            "date": item["date"],
            "close": item["close"],
            "score": item["score"],
            "grade": item["grade"],
            "score_gap": round(abs(item["score"] - target_score), 2),
            "distance": round(float(distance), 4),
            "summary": _build_period_summary(item),
        }
        for horizon in DEFAULT_HORIZONS:
            period[f"ret_{horizon}d"] = _round_optional(
                _future_return(candles, candle_index, horizon)
            )
        matches.append(period)

    # 가까운 순(거리 오름차순, 동률이면 날짜)으로 정렬.
    matches.sort(key=lambda p: (p["distance"], p["date"]))

    return {
        "current_date": current["date"],
        "current_score": round(target_score, 2),
        "current_grade": current["grade"],
        "method": KNN_METHOD,
        "method_label": KNN_METHOD_LABEL,
        "comparison_basis": list(FEATURE_NAMES),
        "n_neighbors": k,
        "features": list(FEATURE_NAMES),
        "similar_periods": matches,
        "stats": _summarize_returns(matches),
        "summary": _build_overall_summary(len(matches)),
    }


def _build_overall_summary(sample_count: int) -> str:
    if sample_count == 0:
        return "KNN으로 비교할 과거 구간을 찾지 못했습니다."
    return (
        f"KNN(피처 {len(FEATURE_NAMES)}종, 표준화 적용)으로 현재와 가장 유사한 과거 구간 "
        f"{sample_count}개를 찾았습니다. 과거 참고 통계이며 미래 성과를 보장하지 않습니다."
    )
