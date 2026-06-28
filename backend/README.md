# Backend

FastAPI 기반 FOMO Break API 서버입니다.

## 예정 기능

- Upbit 공개 일봉 캔들 수집
- FOMO Score 계산
- 200일 히스토리 반환
- Historical Mirror 후보 구간 반환

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
- `GET /api/historical-mirror?market=KRW-BTC`
