from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FOMO Break API",
    description="Public Upbit data based market sentiment observation API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DISCLAIMER = "본 지수는 시장 상태 관찰 도구이며 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fomo-break-api"}


@app.get("/api/fomo-score")
def get_fomo_score(market: str = "KRW-BTC") -> dict:
    return {
        "market": market,
        "status": "not_implemented",
        "message": "FOMO Score calculation will be implemented in backend/app/fomo_score.py.",
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/fomo-history")
def get_fomo_history(market: str = "KRW-BTC", days: int = 200) -> dict:
    return {
        "market": market,
        "days": days,
        "items": [],
        "status": "not_implemented",
        "disclaimer": "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다.",
    }
