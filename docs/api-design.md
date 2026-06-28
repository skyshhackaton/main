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
  "service": "fomo-break-api"
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
| days | 200 | 반환 일수 |

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
| history_days | 200 | 히스토리 차트 반환 일수 |
| mirror_days | 200 | 유사 구간 탐색 시계열 길이 |
| tolerance | 10 | 현재 점수와 유사하다고 볼 점수 범위 |
| max_periods | 10 | 응답에 포함할 최대 유사 구간 수 |

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
    "similar_periods": [],
    "stats": {"sample_count": 0}
  },
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

## GET /api/historical-mirror

현재와 유사한 과거 구간을 반환합니다.

MVP에서는 현재 FOMO Score와 ± tolerance 범위로 유사했던 과거 구간을 찾고, 해당 과거 구간 이후의 3일/7일/30일 변동을 참고 통계로 집계합니다. 이 통계는 과거 참고 사례이며 미래 예측으로 표현하지 않습니다.

Query:

| 이름 | 기본값 | 설명 |
|---|---|---|
| market | KRW-BTC | 업비트 마켓 코드 |
| tolerance | 10 | 현재 점수와 유사하다고 볼 점수 범위 |
| days | 200 | 탐색할 최근 시계열 길이 |
| max_periods | 20 | 응답에 포함할 최대 유사 구간 수 |

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28T00:00:00",
  "current_score": 73.2,
  "current_grade": "탐욕",
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
