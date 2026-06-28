# FOMO Break

> 당신이 지금 사려는 이유는 정말 정보 때문인가, 아니면 감정 때문인가?

FOMO Break는 2026 SKYSH Hackathon을 위한 업비트 공개 데이터 기반 시장 심리 관찰 도구입니다. 초보 투자자가 숫자로만 보이는 시장 분위기를 쉽게 이해하고, 감정적인 추격 매수나 패닉셀을 하기 전에 한 번 멈춰 생각할 수 있도록 돕습니다.

본 프로젝트는 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다. 모든 점수와 문구는 시장 상태 관찰 및 자기 점검을 위한 참고 정보입니다.

## 핵심 기능

1. Emotion Score
   - 업비트 공개 일봉 캔들 데이터로 FOMO Score를 계산합니다.
   - 가격 모멘텀, 가격 강도, 거래량 방향성, CLV, RSI, 변동성, 거래량 모멘텀, 연속 상승일을 0~100 점수로 정규화합니다.

2. Historical Mirror
   - 현재와 유사한 과거 시장 구간을 보여줍니다.
   - 결과는 예측이 아니라 과거 참고 사례로만 설명합니다.

3. Decision Pause
   - 사용자의 행동을 지시하지 않고, 결정을 잠시 멈추게 하는 질문을 제공합니다.
   - 예: "지금 판단의 근거가 정보인가요, 감정인가요?"

## 대회 적합성

2026 SKYSH 주제는 업비트 생태계 위에서 공포와 탐욕, 정보/시간/경험의 비대칭을 기술로 다루는 프로덕트를 제안하는 것입니다. FOMO Break는 업비트 공개 API만 사용하고, 서버에 사용자 API Key 또는 Secret Key를 저장하지 않는 구조를 지향합니다.

## 저장소 구조

```text
.
├── README.md
├── CONTRIBUTING.md
├── .env.example
├── .gitignore
├── backend/              # FastAPI API 서버
├── frontend/             # MVP 웹 클라이언트
├── docs/                 # 기획, 산식, API, 규정 문서
├── .github/              # 이슈/PR 템플릿
└── fear_greed_tool/      # 초기 실험 코드, 추후 backend로 흡수 예정
```

## 빠른 시작

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

프론트엔드 스택은 MVP 구현 시점에 확정합니다. 기본 후보는 Vite + React + TypeScript입니다.

```powershell
cd frontend
```

## 주요 문서

- [제품 요약](docs/product-brief.md)
- [FOMO Score 산식](docs/fomo-score-spec.md)
- [API 설계](docs/api-design.md)
- [규정/보안 체크](docs/compliance.md)
- [팀 협업 방식](docs/team-workflow.md)

## 면책 문구

본 지수는 업비트 공개 데이터 기반 시장 상태 관찰 도구입니다. 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
