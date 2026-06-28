"""FOMO Score 시계열 추세 예측.

**가격이 아니라 FOMO Score(시장 심리 상태값) 자체의 향후 추세를 예측한다.**
compliance.md의 금지 표현("N일 뒤 수익률이 높습니다", 미래 가격 예측)을 피하기 위해
예측 대상은 의도적으로 가격/수익률이 아닌 '관찰값'인 FOMO Score로 한정한다.
결과는 '예상 심리 추세' 참고값일 뿐 투자 추천/수익 예측이 아니다.

방식:
- 각 시점 t의 피처(점수 lag + 시장 피처)로 t+h 시점의 FOMO Score를 맞히는
  horizon별 direct forecast. 피처는 시점 t 기준 과거 정보만 사용(look-ahead 없음).
- 모델은 그래디언트 부스팅. xgboost가 설치돼 있으면 XGBRegressor를 쓰고,
  없으면 sklearn GradientBoostingRegressor로 폴백한다(CI/팀원 환경 안전).
  표본이 작아(~190개) 과적합 방지를 위해 보수적 파라미터를 사용한다.
- 신뢰도 참고용으로 시간 순서 기반 워크포워드 백테스트 MAE를 함께 반환한다.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from app.fomo_score import clamp, classify_grade
from app.knn_mirror import build_feature_matrix

try:  # xgboost 우선 사용, 미설치 환경에서는 sklearn으로 폴백
    from xgboost import XGBRegressor

    _HAS_XGBOOST = True
except ImportError:  # pragma: no cover - 환경 의존
    _HAS_XGBOOST = False

DEFAULT_HORIZONS = (1, 3, 7)
DEFAULT_LAGS = 5
RANDOM_STATE = 42

# 표본이 ~190개로 작아 과적합을 막기 위한 보수적 파라미터.
_XGB_PARAMS = dict(
    n_estimators=200,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    random_state=RANDOM_STATE,
    n_jobs=1,
)

MODEL_NAME = (
    "XGBRegressor (per-horizon direct forecast)"
    if _HAS_XGBOOST
    else "GradientBoostingRegressor (per-horizon direct forecast)"
)


def _features_at(matrix: list[list[float]], scores: list[float], i: int, lags: int) -> list[float]:
    """시점 i의 예측 피처.

    [최근 lags개 점수(oldest..current), change_rate_1d, volume_ratio_5_20, rsi_14]
    matrix[i] == [fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14] 이므로
    시장 피처는 matrix[i][1:]를 그대로 재사용한다(점수는 lag로 따로 넣음).
    """
    lag_feats = scores[i - lags + 1 : i + 1]
    market_feats = list(matrix[i][1:])
    return list(lag_feats) + market_feats


def _build_supervised(
    matrix: list[list[float]], scores: list[float], lags: int, horizon: int
) -> tuple[list[list[float]], list[float]]:
    """(X, y) 학습셋 구성. y[k]는 해당 피처 시점 + horizon 의 실제 점수."""
    X: list[list[float]] = []
    y: list[float] = []
    for i in range(lags - 1, len(scores) - horizon):
        X.append(_features_at(matrix, scores, i, lags))
        y.append(scores[i + horizon])
    return X, y


def _new_model():
    """xgboost가 있으면 XGBRegressor, 없으면 sklearn GradientBoosting으로 폴백."""
    if _HAS_XGBOOST:
        return XGBRegressor(**_XGB_PARAMS)
    return GradientBoostingRegressor(random_state=RANDOM_STATE)


def _walk_forward_mae(
    X: list[list[float]], y: list[float], test_fraction: float = 0.2, min_test: int = 5
) -> float | None:
    """시간 순서를 보존한 holdout 백테스트 MAE.

    앞부분으로 학습하고 마지막 구간(미래)으로만 평가한다. 표본이 적으면 None.
    """
    n = len(X)
    test_size = max(min_test, int(round(n * test_fraction)))
    train_size = n - test_size
    if train_size < min_test or test_size < 1:
        return None

    X_arr = np.asarray(X, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    model = _new_model()
    model.fit(X_arr[:train_size], y_arr[:train_size])
    preds = np.clip(model.predict(X_arr[train_size:]), 0.0, 100.0)
    return round(float(np.mean(np.abs(preds - y_arr[train_size:]))), 3)


def build_score_forecast(
    candles: list[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    days: int = 200,
) -> dict:
    """현재 시점 기준 향후 horizon일들의 FOMO Score(심리 상태) 추세를 예측."""
    if not candles:
        raise ValueError("candles must not be empty")
    if lags < 1:
        raise ValueError("lags must be positive")
    if days <= 0:
        raise ValueError("days must be positive")
    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must be positive integers")

    fm = build_feature_matrix(candles, days=days)
    series = fm["series"]
    matrix = fm["matrix"]
    scores = [item["score"] for item in series]

    if len(scores) <= lags:
        raise ValueError("not enough samples to build lag features")

    current = series[-1]
    latest_features = [_features_at(matrix, scores, len(scores) - 1, lags)]

    forecast = []
    for horizon in sorted(set(horizons)):
        X, y = _build_supervised(matrix, scores, lags, horizon)
        if len(X) < lags + 1:
            # 해당 horizon을 학습할 표본이 부족하면 예측 생략(투명하게 표기).
            forecast.append(
                {
                    "horizon_days": horizon,
                    "predicted_score": None,
                    "grade": None,
                    "backtest_mae": None,
                    "train_samples": len(X),
                }
            )
            continue

        model = _new_model()
        model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))
        predicted = clamp(float(model.predict(latest_features)[0]))
        grade, _ = classify_grade(predicted)
        forecast.append(
            {
                "horizon_days": horizon,
                "predicted_score": round(predicted, 2),
                "grade": grade,
                "backtest_mae": _walk_forward_mae(X, y),
                "train_samples": len(X),
            }
        )

    return {
        "current_date": current["date"],
        "current_score": round(current["score"], 2),
        "current_grade": current["grade"],
        "lags": lags,
        "method": MODEL_NAME,
        "forecast": forecast,
        "summary": _build_summary(current["score"], forecast),
    }


def _build_summary(current_score: float, forecast: list[dict]) -> str:
    usable = [f for f in forecast if f["predicted_score"] is not None]
    if not usable:
        return "예측에 필요한 데이터가 부족합니다."
    longest = max(usable, key=lambda f: f["horizon_days"])
    direction = "상승" if longest["predicted_score"] > current_score else "하락"
    if abs(longest["predicted_score"] - current_score) < 1.0:
        direction = "횡보"
    return (
        f"현재 FOMO Score {round(current_score, 2)}점 기준, 모델이 추정한 향후 "
        f"{longest['horizon_days']}일 예상 심리 추세는 '{direction}'입니다. "
        "이는 시장 상태 관찰을 위한 참고값이며 가격/수익률 예측이나 투자 추천이 아닙니다."
    )
