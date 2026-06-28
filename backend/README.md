# Backend

FastAPI 기반 FOMO Break API 서버입니다.

## 예정 기능

- Upbit 공개 일봉 캔들 수집
- FOMO Score 계산
- 200일 히스토리 반환
- Historical Mirror 후보 구간 반환
- KNN Mirror 후보 구간 반환
- FOMO Score 흐름 참고값 반환
- Decision Pause 질문 반환
- MVP 시연용 통합 응답 반환

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API

- `GET /api/health`
- `GET /api/fomo-score?market=KRW-BTC`
- `GET /api/fomo-history?market=KRW-BTC`
- `GET /api/decision-pause`
- `GET /api/mvp-overview?market=KRW-BTC`
- `GET /api/historical-mirror?market=KRW-BTC`
- `GET /api/knn-mirror?market=KRW-BTC`
- `GET /api/score-forecast?market=KRW-BTC`

`/api/score-forecast`는 가격이나 수익률이 아니라 FOMO Score 자체의 참고 흐름과 백테스트 오차 범위를 반환합니다.
