# KNN Mirror Integration Contract

## Purpose

KNN Mirror는 Historical Mirror의 보조 비교축입니다.

- Historical Mirror: 현재 FOMO Score와 가까운 과거 구간을 조건 매칭으로 찾습니다.
- KNN Mirror: FOMO Score 외 시장 피처를 함께 보고 가까운 과거 구간을 찾습니다.

두 결과는 같은 화면에서 나란히 비교할 수 있어야 하며, 모두 과거 참고 사례로만 표현합니다.
가격, 수익률, 매수/매도 여부를 예측하거나 보장하는 문구를 쓰지 않습니다.

## Feature Contract

각 과거 시점 `t`는 4차원 벡터로 표현합니다. 모든 피처는 시점 `t` 기준 과거 데이터만 사용합니다.

| 피처 | 의미 | 계산 방식 | 범위/스케일 |
|---|---|---|---|
| `fomo_score` | FOMO 종합 점수 | 기존 `score_series` 값 재사용 | 0~100 |
| `change_rate_1d` | 1일 종가 변화율 | `close[t] / close[t-1] - 1` | 대체로 +/-0.x |
| `volume_ratio_5_20` | 단기/중기 거래량 비율 | `mean(volume 최근 5일) / mean(volume 최근 20일)` | 보통 1 내외 |
| `rsi_14` | RSI(14) 과매수/과매도 | `fomo_score`와 같은 RSI 계산 기준 | 0~100 |

거리 계산 전에는 `StandardScaler`로 피처를 정규화합니다. 그렇지 않으면 0~100 범위의
`fomo_score`와 `rsi_14`가 작은 변화율 피처를 거리 계산에서 압도할 수 있습니다.

## Look-Ahead Rule

- 피처 생성 시점 `t`에서는 `candles[:t+1]`만 사용합니다.
- 현재 시점은 이웃 후보에서 제외합니다.
- `ret_3d`, `ret_7d`, `ret_30d`는 유사 과거 구간을 선택한 뒤에만 계산하는 회고 통계입니다.
- `t+N` 데이터가 없으면 해당 수익률 필드는 `None`으로 둡니다.

## Response Contract

KNN Mirror 응답은 Historical Mirror와 1:1 비교 가능해야 합니다.

공통 필드:

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28T00:00:00",
  "current_score": 73.2,
  "current_grade": "탐욕",
  "similar_periods": [
    {
      "date": "2025-11-09T00:00:00",
      "close": 98500000,
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
    "sample_count": 5,
    "mean_3d": -0.012,
    "std_3d": 0.041,
    "positive_rate_3d": 0.42
  },
  "summary": "과거 참고 통계이며 미래 성과를 보장하지 않습니다.",
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

KNN 전용 추가 필드:

- `n_neighbors`: 실제 사용한 이웃 수
- `features`: `["fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14"]`
- `similar_periods[].distance`: 표준화된 피처 공간에서의 거리

## MVP Integration

`feature/knn-and-ml`이 기준 브랜치에 머지된 뒤에는 다음 연결을 기준으로 둡니다.

1. `GET /api/knn-mirror`를 API 문서에 정식 추가합니다.
2. `GET /api/mvp-overview?include_knn=true`에 `knn_mirror` 섹션을 선택적으로 포함합니다.
3. 프론트는 Historical Mirror와 KNN Mirror를 "조건 매칭"과 "피처 유사도" 두 탭으로 비교합니다.
4. 화면 문구는 "가까웠던 과거 사례"로 표현하고, "예측", "기회", "신호" 표현은 쓰지 않습니다.

## Presentation Note

발표에서는 KNN을 "더 똑똑한 예측기"가 아니라 "현재와 비슷했던 과거 상태를 더 여러 관점에서 찾는 보조 렌즈"로 설명합니다.
