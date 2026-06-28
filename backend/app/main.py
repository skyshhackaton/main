from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.fomo_score import score_at, score_series
from app.historical_mirror import build_historical_mirror
from app.upbit_client import DEFAULT_MARKET, load_candles

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
HISTORY_DISCLAIMER = "과거 데이터는 참고용이며 미래 성과를 보장하지 않습니다."


def _load_or_404(market: str) -> list[dict]:
    candles = load_candles(market)
    if not candles:
        raise HTTPException(
            status_code=404,
            detail=f"'{market}' 캔들 데이터가 없습니다. 먼저 데이터를 수집해주세요.",
        )
    return candles


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fomo-break-api"}


@app.get("/api/fomo-score")
def get_fomo_score(market: str = DEFAULT_MARKET) -> dict:
    candles = _load_or_404(market)
    result = score_at(candles)
    return {
        "market": market,
        **result,
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/fomo-history")
def get_fomo_history(market: str = DEFAULT_MARKET, days: int = 200) -> dict:
    candles = _load_or_404(market)
    return {
        "market": market,
        "days": days,
        "items": score_series(candles, days),
        "disclaimer": HISTORY_DISCLAIMER,
    }


@app.get("/api/historical-mirror")
def get_historical_mirror(
    market: str = DEFAULT_MARKET,
    tolerance: float = 10.0,
    days: int = 200,
    max_periods: int = 20,
) -> dict:
    candles = _load_or_404(market)
    try:
        mirror = build_historical_mirror(
            candles,
            tolerance=tolerance,
            days=days,
            max_periods=max_periods,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "market": market,
        **mirror,
        "disclaimer": HISTORY_DISCLAIMER,
    }
