# API Design

## Base URL

```text
http://localhost:8000
```

## GET /api/health

서버 상태 확인용 엔드포인트입니다.

```json
{
  "status": "ok",
  "service": "fomo-break-api",
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
}
```

## GET /api/fomo-score

현재 FOMO Score를 반환합니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |

Response draft:

```json
{
  "market": "KRW-BTC",
  "score": 73.2,
  "grade": "탐욕",
  "description": "매수 심리와 FOMO 조짐이 우세한 상태",
  "indicators": {
    "X1": 68.0,
    "X2": 82.0,
    "X3": 71.0,
    "X4": 65.0,
    "X5": 74.0,
    "X6": 55.0,
    "X7": 77.0,
    "X8": 80.0
  },
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
}
```

## GET /api/fomo-history

최근 200일 FOMO Score 시계열을 반환합니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| days | 200 | 반환 일수, 양수 |

Response draft:

```json
{
  "market": "KRW-BTC",
  "items": [
    {
      "date": "2026-06-28",
      "close": 98500000,
      "score": 73.2,
      "grade": "탐욕",
      "description": "매수 심리와 FOMO 조짐이 우세한 상태"
    }
  ],
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

## GET /api/decision-pause

투자 판단을 지시하지 않고 사용자가 근거와 감정 반응을 구분하도록 돕는 성찰 질문을 반환합니다.

```json
{
  "items": [
    {
      "id": "reason_check",
      "category": "근거 확인",
      "question": "지금 판단의 근거가 새 정보인지, 가격 변동에 대한 감정 반응인지 구분해보세요."
    }
  ],
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
}
```

## GET /api/mvp-overview

MVP 첫 화면과 발표 시연에서 필요한 현재 점수, 최근 히스토리, Historical Mirror, Decision Pause 질문을 한 번에 반환합니다. 프론트엔드가 여러 엔드포인트를 순차 호출하지 않아도 되도록 만든 통합 응답이며, 각 섹션은 기존 개별 API와 같은 구조를 유지합니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| history_days | 200 | 히스토리 차트 반환 일수, 양수 |
| mirror_days | 200 | 유사 구간 탐색 시계열 길이, 양수 |
| tolerance | 10 | 현재 점수와 유사하다고 볼 점수 범위, 0 이상 |
| max_periods | 10 | 응답에 포함할 최대 유사 구간 수, 양수 |
| include_knn | false | KNN Mirror 섹션 포함 여부 |
| knn_neighbors | 5 | KNN 이웃 수, `include_knn=true`일 때 양수 |

```json
{
  "market": "KRW-BTC",
  "current": {
    "score": 73.2,
    "grade": "탐욕",
    "description": "매수 심리와 FOMO 조짐이 우세한 상태",
    "indicators": {"X1": 68.0, "X7": 77.0, "X8": 80.0}
  },
  "history": {
    "days": 200,
    "items": []
  },
  "historical_mirror": {
    "current_score": 73.2,
    "method": "score_tolerance",
    "method_label": "조건 매칭",
    "comparison_basis": ["fomo_score"],
    "similar_periods": [],
    "stats": {"sample_count": 0}
  },
  "knn_mirror": null,
  "decision_pause": {
    "items": [
      {
        "id": "reason_check",
        "category": "근거 확인",
        "question": "지금 판단의 근거가 새 정보인지, 가격 변동에 대한 감정 반응인지 구분해보세요."
      }
    ]
  },
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.",
  "history_disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

`include_knn=true`이면 `knn_mirror`에 `/api/knn-mirror`와 같은 구조의 결과가 들어갑니다.
기본값은 `false`라서 기존 MVP 화면은 Historical Mirror만으로도 동작합니다.

## GET /api/historical-mirror

현재와 유사한 과거 구간을 반환합니다.

MVP에서는 현재 FOMO Score와 ± tolerance 범위로 유사했던 과거 구간을 찾고, 해당 과거 구간 이후의 3일/7일/30일 변동을 참고 통계로 집계합니다. 이 통계는 과거 참고 사례이며 미래 예측으로 표현하지 않습니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| tolerance | 10 | 현재 점수와 유사하다고 볼 점수 범위, 0 이상 |
| days | 200 | 탐색할 최근 시계열 길이, 양수 |
| max_periods | 20 | 응답에 포함할 최대 유사 구간 수, 양수 |

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28T00:00:00",
  "current_score": 73.2,
  "current_grade": "탐욕",
  "method": "score_tolerance",
  "method_label": "조건 매칭",
  "comparison_basis": ["fomo_score"],
  "tolerance": 10,
  "similar_periods": [
    {
      "date": "2025-11-09",
      "score": 78.4,
      "grade": "탐욕",
      "score_gap": 5.2,
      "ret_3d": -0.021,
      "ret_7d": -0.084,
      "ret_30d": 0.052,
      "summary": "당시 FOMO Score는 78.4점(탐욕)으로 현재와 유사한 시장 심리 구간이었습니다."
    }
  ],
  "stats": {
    "sample_count": 12,
    "mean_3d": -0.012,
    "std_3d": 0.041,
    "positive_rate_3d": 0.42,
    "sample_count_3d": 12
  },
  "summary": "최근 시계열에서 현재 점수와 ±10 범위로 유사한 과거 구간 12개를 찾았습니다. 과거 참고 통계이며 미래 성과를 보장하지 않습니다.",
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

주의: UI에는 미래 수익률 예측처럼 보이는 문구를 노출하지 않습니다.

## GET /api/knn-mirror

현재와 가까웠던 과거 구간을 FOMO Score, 1일 변화율, 거래량 비율, RSI 피처 유사도로 반환합니다.
Historical Mirror와 같은 화면에서 비교할 수 있도록 공통 필드와 `similar_periods`, `stats` 구조를 유지합니다.

KNN은 `/api/mvp-overview`에서 기본 실행되지 않으며, 통합 응답에 포함하려면 `include_knn=true`를 사용합니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| n_neighbors | 5 | 반환할 가까운 과거 구간 수, 양수 |
| days | 200 | 탐색할 최근 시계열 길이, 양수 |

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28T00:00:00",
  "current_score": 73.2,
  "current_grade": "탐욕",
  "method": "feature_knn",
  "method_label": "피처 유사도",
  "comparison_basis": ["fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14"],
  "n_neighbors": 5,
  "features": ["fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14"],
  "similar_periods": [
    {
      "date": "2025-11-09T00:00:00",
      "close": 98500000,
      "score": 78.4,
      "grade": "탐욕",
      "score_gap": 5.2,
      "distance": 0.4312,
      "ret_3d": -0.021,
      "ret_7d": -0.084,
      "ret_30d": 0.052,
      "summary": "당시 FOMO Score는 78.4점(탐욕)으로 현재와 유사한 시장 심리 구간이었습니다."
    }
  ],
  "stats": {
    "sample_count": 5,
    "mean_3d": -0.012,
    "std_3d": 0.041,
    "positive_rate_3d": 0.42,
    "sample_count_3d": 5
  },
  "summary": "KNN(피처 4종, 표준화 적용)으로 현재와 가장 유사한 과거 구간 5개를 찾았습니다. 과거 참고 통계이며 미래 성과를 보장하지 않습니다.",
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

## GET /api/score-forecast

FOMO Score 자체의 단기 참고 흐름을 반환합니다. 가격, 수익률, 매수/매도 행동을 예측하지 않으며, 백테스트 MAE를 오차 범위로 함께 내려 변화폭을 방향으로 해석해도 되는지 확인할 수 있게 합니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| lags | 5 | 모델 입력에 사용할 최근 FOMO Score 개수, 양수 |
| days | 200 | 학습과 참고값 산출에 사용할 최근 시계열 길이, 양수 |

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28T00:00:00",
  "current_score": 42.33,
  "current_grade": "중립",
  "lags": 5,
  "method": "XGBRegressor (per-horizon direct forecast)",
  "method_label": "FOMO Score 흐름 참고",
  "comparison_basis": ["fomo_score_lags", "change_rate_1d", "volume_ratio_5_20", "rsi_14"],
  "forecast": [
    {
      "horizon_days": 7,
      "predicted_score": 38.52,
      "grade": "공포",
      "score_delta": -3.81,
      "error_band": 5.096,
      "trend_direction": "within_error_band",
      "trend_label": "오차 범위 내",
      "confidence_level": "medium",
      "confidence_label": "보통",
      "backtest_mae": 5.096,
      "train_samples": 189,
      "interpretation": "현재 점수와의 차이가 백테스트 오차 범위 안에 있어 방향으로 단정하지 않습니다. 시장 상태 관찰과 자기 점검을 위한 참고값입니다."
    }
  ],
  "summary": "현재 FOMO Score 42.33점 기준, 7일 참고값은 백테스트 오차 범위 안에 있습니다. 방향을 단정하기보다 지금 판단의 근거를 점검하는 데 사용하세요.",
  "caution": "FOMO Score 참고 흐름은 시장 상태 관찰값이며 가격/수익률 예측이나 투자 추천이 아닙니다.",
  "disclaimer": "FOMO Score 흐름 참고값은 시장 심리 상태 관찰용이며 가격·수익률 예측이 아닙니다. 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
}
```

주의: UI에서는 `predicted_score`만 단독으로 강조하지 않고 `error_band`, `trend_label`, `interpretation`을 함께 노출합니다.
