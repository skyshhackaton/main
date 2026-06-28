"""FOMO Score 시계열 흐름 참고.

**가격이 아니라 FOMO Score(시장 심리 상태값) 자체의 참고 흐름을 추정한다.**
compliance.md의 금지 표현("N일 뒤 수익률이 높습니다", 미래 가격 예측)을 피하기 위해
대상은 의도적으로 가격/수익률이 아닌 '관찰값'인 FOMO Score로 한정한다.
결과는 시장 상태 관찰 참고값일 뿐 투자 추천/수익 예측이 아니다.

방식:
- 각 시점 t의 피처(점수 lag + 시장 피처)로 t+h 시점의 FOMO Score를 추정하는
  horizon별 direct forecast. 피처는 시점 t 기준 과거 정보만 사용(look-ahead 없음).
- 모델은 그래디언트 부스팅. xgboost가 설치돼 있으면 XGBRegressor를 쓰고,
  없으면 sklearn GradientBoostingRegressor로 폴백한다(CI/팀원 환경 안전).
  표본이 작아(~190개) 과적합 방지를 위해 보수적 파라미터를 사용한다.
- 신뢰도 참고용으로 시간 순서 기반 워크포워드 백테스트 MAE와 오차 범위 기반 해석을 함께 반환한다.
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
UNCERTAINTY_FLOOR = 1.0

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
METHOD_LABEL = "FOMO Score 흐름 참고"
FEATURES = (
    "fomo_score_lags",
    "change_rate_1d",
    "volume_ratio_5_20",
    "rsi_14",
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


def _confidence_level(backtest_mae: float | None, train_samples: int) -> tuple[str, str]:
    """백테스트 오차와 표본 수를 사용자에게 보여줄 안정성 등급으로 변환."""
    if backtest_mae is None or train_samples < 30:
        return "low", "낮음"
    if backtest_mae <= 3.0:
        return "high", "높음"
    if backtest_mae <= 6.0:
        return "medium", "보통"
    return "low", "낮음"


def _trend_direction(score_delta: float, backtest_mae: float | None) -> tuple[str, str]:
    error_band = max(UNCERTAINTY_FLOOR, backtest_mae or 0.0)
    if score_delta > error_band:
        return "rising", "상승 흐름"
    if score_delta < -error_band:
        return "falling", "하락 흐름"
    return "within_error_band", "오차 범위 내"


def _build_interpretation(entry: dict) -> str:
    if entry["predicted_score"] is None:
        return "표본이 부족해 해당 기간의 FOMO Score 참고값을 산출하지 않았습니다."
    if entry["trend_direction"] == "within_error_band":
        return (
            "현재 점수와의 차이가 백테스트 오차 범위 안에 있어 방향으로 단정하지 않습니다. "
            "시장 상태 관찰과 자기 점검을 위한 참고값입니다."
        )
    return (
        "현재 점수와의 차이가 백테스트 오차 범위를 넘지만 가격/수익률 전망이 아닙니다. "
        "FOMO Score 상태 변화를 관찰하는 참고값으로만 사용합니다."
    )


def build_score_forecast(
    candles: list[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lags: int = DEFAULT_LAGS,
    days: int = 200,
) -> dict:
    """현재 시점 기준 horizon별 FOMO Score(심리 상태) 참고 흐름을 추정."""
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
                    "score_delta": None,
                    "error_band": None,
                    "trend_direction": "insufficient_data",
                    "trend_label": "표본 부족",
                    "confidence_level": "low",
                    "confidence_label": "낮음",
                    "backtest_mae": None,
                    "train_samples": len(X),
                    "interpretation": "표본이 부족해 해당 기간의 FOMO Score 참고값을 산출하지 않았습니다.",
                }
            )
            continue

        model = _new_model()
        model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))
        predicted = clamp(float(model.predict(latest_features)[0]))
        grade, _ = classify_grade(predicted)
        backtest_mae = _walk_forward_mae(X, y)
        score_delta = round(predicted - current["score"], 2)
        trend_direction, trend_label = _trend_direction(score_delta, backtest_mae)
        confidence_level, confidence_label = _confidence_level(backtest_mae, len(X))
        entry = {
            "horizon_days": horizon,
            "predicted_score": round(predicted, 2),
            "grade": grade,
            "score_delta": score_delta,
            "error_band": backtest_mae,
            "trend_direction": trend_direction,
            "trend_label": trend_label,
            "confidence_level": confidence_level,
            "confidence_label": confidence_label,
            "backtest_mae": backtest_mae,
            "train_samples": len(X),
        }
        entry["interpretation"] = _build_interpretation(entry)
        forecast.append(
            entry
        )

    return {
        "current_date": current["date"],
        "current_score": round(current["score"], 2),
        "current_grade": current["grade"],
        "lags": lags,
        "method": MODEL_NAME,
        "method_label": METHOD_LABEL,
        "comparison_basis": list(FEATURES),
        "forecast": forecast,
        "summary": _build_summary(current["score"], forecast),
        "caution": "FOMO Score 참고 흐름은 시장 상태 관찰값이며 가격/수익률 예측이나 투자 추천이 아닙니다.",
    }


def _build_summary(current_score: float, forecast: list[dict]) -> str:
    usable = [f for f in forecast if f["predicted_score"] is not None]
    if not usable:
        return "FOMO Score 참고 흐름을 산출할 데이터가 부족합니다."
    longest = max(usable, key=lambda f: f["horizon_days"])
    if longest["trend_direction"] == "within_error_band":
        return (
            f"현재 FOMO Score {round(current_score, 2)}점 기준, "
            f"{longest['horizon_days']}일 참고값은 백테스트 오차 범위 안에 있습니다. "
            "방향을 단정하기보다 지금 판단의 근거를 점검하는 데 사용하세요."
        )
    return (
        f"현재 FOMO Score {round(current_score, 2)}점 기준, "
        f"{longest['horizon_days']}일 참고값은 '{longest['trend_label']}'로 분류됩니다. "
        "이는 시장 상태 관찰을 위한 참고값이며 가격/수익률 예측이나 투자 추천이 아닙니다."
    )
