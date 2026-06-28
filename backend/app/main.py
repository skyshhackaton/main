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
DECISION_PAUSE_QUESTIONS = [
    {
        "id": "reason_check",
        "category": "근거 확인",
        "question": "지금 판단의 근거가 새 정보인지, 가격 변동에 대한 감정 반응인지 구분해보세요.",
    },
    {
        "id": "late_attention",
        "category": "관심 시점",
        "question": "가격이 움직인 뒤에야 관심이 생긴 것은 아닌지 확인해보세요.",
    },
    {
        "id": "risk_boundary",
        "category": "위험 범위",
        "question": "손실을 감당할 수 있는 범위와 판단을 바꿀 조건을 말로 설명할 수 있나요?",
    },
    {
        "id": "time_horizon",
        "category": "시간 기준",
        "question": "이 판단이 단기 감정인지, 미리 정한 관찰 기간과 기준에 맞는지 점검해보세요.",
    },
]


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


@app.get("/api/decision-pause")
def get_decision_pause() -> dict:
    return {
        "items": DECISION_PAUSE_QUESTIONS,
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/mvp-overview")
def get_mvp_overview(
    market: str = DEFAULT_MARKET,
    history_days: int = 200,
    mirror_days: int = 200,
    tolerance: float = 10.0,
    max_periods: int = 10,
) -> dict:
    if history_days <= 0:
        raise HTTPException(status_code=400, detail="history_days must be positive")

    candles = _load_or_404(market)
    try:
        mirror = build_historical_mirror(
            candles,
            tolerance=tolerance,
            days=mirror_days,
            max_periods=max_periods,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "market": market,
        "current": score_at(candles),
        "history": {
            "days": history_days,
            "items": score_series(candles, history_days),
        },
        "historical_mirror": mirror,
        "decision_pause": {
            "items": DECISION_PAUSE_QUESTIONS,
        },
        "disclaimer": DISCLAIMER,
        "history_disclaimer": HISTORY_DISCLAIMER,
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
