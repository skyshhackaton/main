# FOMO Break – 2026 SKYSH Hackathon MVP

> 당신이 지금 사려는 이유는 정말 정보 때문인가, 아니면 감정 때문인가?

**FOMO Break**는 업비트 공개 데이터를 기반으로 시장의 공포·탐욕 상태를 해석하고, 초보 투자자가 감정적인 추격 매수나 패닉셀을 하기 전에 한 번 멈춰 생각하도록 돕는 **투자 심리 관찰 도구**입니다.

이 저장소는 [2026 SKYSH Hackathon](https://skysh-official.github.io/2026-web/#tracks) 수상을 목표로 하는 MVP 개발 레포지토리입니다. 1차 개발 밋업에서는 아이디어와 프로토타입의 선명함을, 2차 최종 발표에서는 프로덕트 완성도와 BM 타당성을 보여주는 것을 목표로 합니다.

본 프로젝트는 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다. 모든 점수와 문구는 시장 상태 관찰 및 자기 점검을 위한 참고 정보입니다.

---

## 프로젝트 포지션

2026 SKYSH Hackathon의 핵심 주제는 업비트 생태계 위에서 다음 문제를 기술로 다루는 것입니다.

- 기술로 공포와 탐욕을 다루기
- 정보·시간·경험의 비대칭을 넘어가기
- 개인정보, 보안, 관련 법령, 사용자 보호를 고려한 현실적인 서비스 설계
- 사용자 API Key 또는 Secret Key를 서버에 직접 저장하지 않는 구조

FOMO Break는 이 중 **공포와 탐욕** 및 **초보 투자자의 경험 비대칭**에 집중합니다.

초보자는 시장이 급등하거나 주변 추천이 많아질 때 “정보 기반 판단”과 “감정 기반 판단”을 구분하기 어렵습니다. FOMO Break는 시장 데이터를 점수와 질문으로 번역해 사용자가 행동하기 전에 판단 근거를 점검하게 합니다.

---

## 핵심 기능

### 1. Emotion Score

업비트 공개 일봉 캔들 데이터를 기반으로 자체 FOMO Score를 계산합니다.

- 가격 모멘텀
- 가격 강도
- 상승봉 거래량 비율
- CLV 기반 매수 압력
- RSI
- 변동성 역수
- 거래량 모멘텀
- 연속 상승일

모든 지표는 0~100으로 정규화하고, 초보 투자자가 크게 반응하는 **거래량 급증**과 **연속 상승**에 더 높은 가중치를 둡니다.

### 2. Historical Mirror

현재 시장 상태와 유사한 과거 구간을 보여줍니다.

중요한 점은 “미래 예측”이 아니라 “과거 참고 사례”로만 표현한다는 것입니다. 예를 들어 “이후 수익률이 높다”가 아니라 “당시에도 거래량 모멘텀과 연속 상승 점수가 높았다”처럼 설명합니다.

### 3. Decision Pause

사용자에게 매수/매도 답을 주지 않고, 결정을 멈추게 하는 질문을 제공합니다.

예시:

```text
지금 판단의 근거가 정보인가요, 감정인가요?
가격이 오른 뒤에야 관심이 생긴 것은 아닌가요?
손실 허용 범위와 판단 근거를 말로 설명할 수 있나요?
```

---

## 수상 전략

### 1차: 아이디어 및 프로토타입 심사

1차에서는 완성된 거대한 서비스보다 **문제 정의, 차별점, 시연 가능성**이 중요합니다.

- 문제: 초보 투자자는 공포·탐욕 구간에서 정보와 감정을 구분하기 어렵다.
- 해결: 시장 데이터를 쉬운 점수와 성찰 질문으로 번역한다.
- 시연: KRW-BTC 현재 FOMO Score, 구성 요소, 과거 유사 구간, Decision Pause를 한 화면에서 보여준다.
- 안정성: 공개 API만 사용하고 투자 권유 문구를 배제한다.

### 2차: 프로덕트 및 BM 심사

2차에서는 실제 서비스 가능성을 강조합니다.

- 거래소 내 투자자 보호 위젯
- 초보 투자자 교육용 대시보드
- 리스크 커뮤니케이션 API 또는 B2B 리포트
- 사용자 행동을 지시하지 않는 안전한 UX 패턴
- API Key/Secret Key를 서버에 저장하지 않는 구조

---

## 기술 스택

### Backend

- Framework: FastAPI
- Language: Python
- HTTP Client: httpx
- Test: pytest
- Data Source: Upbit public quotation API

### Frontend

MVP 구현 후보:

- Framework: Vite + React
- Language: TypeScript
- Chart: Recharts 또는 lightweight chart library
- Styling: Tailwind CSS 또는 CSS Modules

### Data / API

MVP 필수 데이터는 업비트 공개 일봉 캔들입니다.

```text
GET https://api.upbit.com/v1/candles/days?market={market}&count=200
```

서버는 사용자 API Key 또는 Secret Key를 받거나 저장하지 않습니다.

---

## 프로젝트 구조

```text
.
├─ README.md
├─ CONTRIBUTING.md
├─ .env.example
├─ .gitignore
│
├─ backend/
│  ├─ README.md
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ main.py              # FastAPI 엔트리포인트
│  │  ├─ upbit_client.py      # 업비트 공개 API 클라이언트
│  │  └─ fomo_score.py        # FOMO Score 도메인 로직
│  └─ tests/
│     └─ test_fomo_score.py
│
├─ frontend/
│  └─ README.md               # MVP 웹 클라이언트 작업 공간
│
├─ docs/
│  ├─ product-brief.md        # 제품 문제 정의와 MVP 범위
│  ├─ fomo-score-spec.md      # X1~X8 산식과 가중치
│  ├─ api-design.md           # API 응답 설계
│  ├─ compliance.md           # 보안/규정/금지 문구
│  └─ team-workflow.md        # 팀 협업 방식
│
├─ .github/
│  ├─ pull_request_template.md
│  └─ ISSUE_TEMPLATE/
│
└─ fear_greed_tool/           # 초기 실험 코드, 추후 backend로 흡수 예정
```

---

## 실행 방법

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

기본 확인:

```text
GET http://localhost:8000/api/health
GET http://localhost:8000/api/fomo-score?market=KRW-BTC
GET http://localhost:8000/api/fomo-history?market=KRW-BTC
GET http://localhost:8000/api/decision-pause
GET http://localhost:8000/api/mvp-overview?market=KRW-BTC
GET http://localhost:8000/api/historical-mirror?market=KRW-BTC
GET http://localhost:8000/api/knn-mirror?market=KRW-BTC
GET http://localhost:8000/api/score-forecast?market=KRW-BTC
```

### Frontend

정적 HTML/CSS/JS 기반 MVP 화면입니다. 백엔드를 먼저 실행한 뒤 별도 터미널에서 프론트엔드 정적 서버를 띄웁니다.

```powershell
cd frontend
python -m http.server 5173
```

브라우저에서 확인:

```text
http://127.0.0.1:5173
```

화면은 현재 FOMO Score, 시장 레이더, 최근 흐름, Historical Mirror, FOMO Score 흐름 참고, Decision Pause를 한 페이지에 묶습니다. 차별화 포인트는 점수만 보여주는 것이 아니라 `세 마켓 비교`, `오차 범위`, `과거 유사 구간`, `자기 점검 체크리스트`를 함께 보여주어 감정적 판단 전에 근거를 확인하게 하는 흐름입니다.

---

## API 설계 초안

### GET /api/fomo-score

현재 시장의 FOMO Score를 반환합니다.

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

### GET /api/fomo-history

최근 200일의 FOMO Score 시계열을 반환합니다.

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

### GET /api/decision-pause

판단을 지시하지 않고 사용자가 근거와 감정 반응을 구분하도록 돕는 질문을 반환합니다.

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

### GET /api/mvp-overview

MVP 첫 화면에 필요한 현재 점수, 히스토리, Historical Mirror, Decision Pause 질문을 한 번에 반환합니다. 발표 시연이나 프론트엔드 연결에서는 이 엔드포인트를 우선 사용할 수 있습니다.

```json
{
  "market": "KRW-BTC",
  "current": {
    "score": 73.2,
    "grade": "탐욕",
    "description": "매수 심리와 FOMO 조짐이 우세한 상태"
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
    "items": []
  },
  "disclaimer": "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.",
  "history_disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

`include_knn=true`를 붙이면 KNN Mirror 결과도 함께 받을 수 있습니다.

### GET /api/historical-mirror

현재 FOMO Score와 유사했던 과거 구간 및 참고 통계를 반환합니다.

```json
{
  "market": "KRW-BTC",
  "current_score": 73.2,
  "current_grade": "탐욕",
  "method": "score_tolerance",
  "method_label": "조건 매칭",
  "comparison_basis": ["fomo_score"],
  "similar_periods": [
    {
      "date": "2025-11-09T00:00:00",
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
    "positive_rate_7d": 0.42
  },
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

### GET /api/knn-mirror

Historical Mirror와 같은 화면에서 비교 가능한 KNN 기반 과거 참고 사례를 반환합니다. 기본 MVP 통합 응답에는 포함되지 않으며, `/api/mvp-overview?include_knn=true`일 때 선택적으로 함께 내려갑니다.

```json
{
  "market": "KRW-BTC",
  "current_score": 73.2,
  "current_grade": "탐욕",
  "method": "feature_knn",
  "method_label": "피처 유사도",
  "comparison_basis": ["fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14"],
  "n_neighbors": 5,
  "features": ["fomo_score", "change_rate_1d", "volume_ratio_5_20", "rsi_14"],
  "similar_periods": [],
  "stats": {"sample_count": 5},
  "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."
}
```

### GET /api/score-forecast

FOMO Score 자체의 단기 참고 흐름을 반환합니다. 가격, 수익률, 매수/매도 행동을 예측하지 않으며, 백테스트 MAE를 오차 범위로 함께 보여주어 변화폭이 방향으로 해석 가능한 수준인지 확인할 수 있게 합니다.

```json
{
  "market": "KRW-BTC",
  "current_score": 42.33,
  "current_grade": "중립",
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
      "interpretation": "현재 점수와의 차이가 백테스트 오차 범위 안에 있어 방향으로 단정하지 않습니다. 시장 상태 관찰과 자기 점검을 위한 참고값입니다."
    }
  ],
  "summary": "현재 FOMO Score 42.33점 기준, 7일 참고값은 백테스트 오차 범위 안에 있습니다. 방향을 단정하기보다 지금 판단의 근거를 점검하는 데 사용하세요.",
  "caution": "FOMO Score 참고 흐름은 시장 상태 관찰값이며 가격/수익률 예측이나 투자 추천이 아닙니다.",
  "disclaimer": "FOMO Score 흐름 참고값은 시장 심리 상태 관찰용이며 가격·수익률 예측이 아닙니다. 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
}
```

---

## 규정 및 보안 원칙

### 반드시 지키는 것

- 업비트 공개 API만 사용합니다.
- 사용자 API Key 또는 Secret Key를 서버에 저장하지 않습니다.
- 개인정보를 수집하지 않습니다.
- UI와 API 응답에 면책 문구를 포함합니다.
- 점수는 투자 판단이 아니라 시장 상태 관찰값으로 표현합니다.

### 사용하지 않는 표현

```text
지금 사세요
지금 파세요
매수 기회입니다
매도 신호입니다
7일 뒤 수익률이 높습니다
손실을 피할 수 있습니다
수익을 보장합니다
```

### 사용하는 표현

```text
매수 심리와 FOMO 조짐이 우세한 상태입니다.
과열과 추격매수 심리가 강한 상태입니다.
이 수치는 시장 상태 관찰을 위한 참고값입니다.
지금 판단의 근거가 정보인지 감정인지 확인해보세요.
과거 유사 구간은 참고 사례이며 미래를 보장하지 않습니다.
```

---

## LLM 개발 가이드 프롬프트

아래 내용을 Codex 또는 다른 LLM에 입력하여 개발을 이어갈 수 있습니다.

```text
너는 2026 SKYSH Hackathon 수상을 목표로 하는 FOMO Break 팀의 개발자다.

프로젝트 조건은 다음과 같다:

1. 서비스는 업비트 공개 데이터 기반 시장 심리 관찰 도구다.
2. 투자 추천, 투자 자문, 수익 보장 문구를 절대 사용하지 않는다.
3. 사용자 API Key 또는 Secret Key를 서버에 저장하지 않는다.
4. MVP 핵심 기능은 Emotion Score, Historical Mirror, Decision Pause다.
5. Backend는 FastAPI와 Python으로 구현한다.
6. 점수 계산은 backend/app/fomo_score.py에 둔다.
7. 업비트 공개 API 호출은 backend/app/upbit_client.py에 둔다.
8. API 엔드포인트는 backend/app/main.py에 둔다.
9. Frontend는 현재 점수, 구성 요소, 히스토리, 유사 구간, 성찰 질문을 한 화면에서 보여준다.
10. Historical Mirror는 미래 예측이 아니라 과거 참고 사례로 표현한다.
11. 모든 화면과 API 응답에는 면책 문구가 포함되어야 한다.
12. 기존 docs/ 문서의 산식과 규정 원칙을 우선한다.

이 조건을 항상 유지하면서 코드를 작성하거나 수정해라.
```

---

## 주요 문서

- [제품 요약](docs/product-brief.md)
- [FOMO Score 산식](docs/fomo-score-spec.md)
- [API 설계](docs/api-design.md)
- [데이터 핸드오프](docs/data-handoff.md)
- [KNN Mirror 연동 계약](docs/knn-integration-contract.md)
- [규정/보안 체크](docs/compliance.md)
- [팀 협업 방식](docs/team-workflow.md)

---

## 면책 문구

본 지수는 업비트 공개 데이터 기반 시장 상태 관찰 도구입니다. 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
