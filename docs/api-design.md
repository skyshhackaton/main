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
  "fomo_score": 73.2,
  "grade": "탐욕",
  "grade_description": "매수 심리와 FOMO 조짐이 우세한 상태",
  "components": {
    "price_momentum": 68.0,
    "price_strength": 82.0,
    "market_breadth": 71.0,
    "clv_pressure": 65.0,
    "rsi": 74.0,
    "volatility_inverse": 55.0,
    "volume_momentum": 77.0,
    "win_streak": 80.0
  },
  "current_price": 98500000,
  "timestamp": "2026-06-28T12:00:00Z",
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천이 아닙니다."
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
      "fomo_score": 73.2,
      "grade": "탐욕"
    }
  ],
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

## GET /api/historical-mirror

현재와 유사한 과거 구간을 반환합니다.

MVP에서는 FOMO Score와 주요 구성 요소 벡터의 거리 또는 코사인 유사도를 사용합니다.

```json
{
  "market": "KRW-BTC",
  "current_date": "2026-06-28",
  "similar_periods": [
    {
      "date": "2025-11-09",
      "similarity": 0.91,
      "score": 78.4,
      "summary": "당시에도 거래량 모멘텀과 연속 상승 점수가 높았습니다."
    }
  ]
}
```

주의: UI에는 미래 수익률 예측처럼 보이는 문구를 노출하지 않습니다.
