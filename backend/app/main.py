import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.fomo_score import score_at, score_series
from app.forecast_score import build_score_forecast
from app.historical_mirror import build_historical_mirror
from app.knn_mirror import build_knn_mirror
from app.knn_pattern import (
    DISCLAIMER as PATTERN_DISCLAIMER,
    METRICS as PATTERN_METRICS,
    build_fomo_pattern_forecast,
)
from app.train_common import DEFAULT_CSV, load_candles_from_csv
from app.upbit_client import DEFAULT_MARKET, load_candles

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

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
    if candles:
        return candles

    try:
        if DEFAULT_CSV.exists():
            return load_candles_from_csv(DEFAULT_CSV, market)
    except (FileNotFoundError, ValueError):
        pass

    raise HTTPException(
        status_code=404,
        detail=f"'{market}' 캔들 데이터가 없습니다. 먼저 데이터를 수집해주세요.",
    )


def _require_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"{name} must be positive")


def _require_non_negative_number(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise HTTPException(status_code=400, detail=f"{name} must be non-negative")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "fomo-break-api",
        "disclaimer": DISCLAIMER,
    }


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
    _require_positive_int("days", days)
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
    include_knn: bool = False,
    knn_neighbors: int = 5,
) -> dict:
    _require_positive_int("history_days", history_days)
    _require_positive_int("mirror_days", mirror_days)
    _require_non_negative_number("tolerance", tolerance)
    _require_positive_int("max_periods", max_periods)
    if include_knn:
        _require_positive_int("knn_neighbors", knn_neighbors)

    candles = _load_or_404(market)
    try:
        mirror = build_historical_mirror(
            candles,
            tolerance=tolerance,
            days=mirror_days,
            max_periods=max_periods,
        )
        knn_mirror = (
            build_knn_mirror(
                candles,
                n_neighbors=knn_neighbors,
                days=mirror_days,
            )
            if include_knn
            else None
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
        "knn_mirror": knn_mirror,
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
    _require_non_negative_number("tolerance", tolerance)
    _require_positive_int("days", days)
    _require_positive_int("max_periods", max_periods)
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


FORECAST_DISCLAIMER = (
    "FOMO Score 흐름 참고값은 시장 심리 상태 관찰용이며 가격·수익률 예측이 아닙니다. "
    "투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
)


@app.get("/api/score-forecast")
def get_score_forecast(
    market: str = DEFAULT_MARKET,
    lags: int = 5,
    days: int = 200,
) -> dict:
    _require_positive_int("lags", lags)
    _require_positive_int("days", days)
    candles = _load_or_404(market)
    try:
        forecast = build_score_forecast(
            candles,
            lags=lags,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "market": market,
        **forecast,
        "disclaimer": FORECAST_DISCLAIMER,
    }


@app.get("/api/knn-mirror")
def get_knn_mirror(
    market: str = DEFAULT_MARKET,
    n_neighbors: int = 5,
    days: int = 200,
) -> dict:
    _require_positive_int("n_neighbors", n_neighbors)
    _require_positive_int("days", days)
    candles = _load_or_404(market)
    try:
        mirror = build_knn_mirror(
            candles,
            n_neighbors=n_neighbors,
            days=days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "market": market,
        **mirror,
        "disclaimer": HISTORY_DISCLAIMER,
    }


@app.get("/api/knn-pattern")
def get_knn_pattern(
    market: str = DEFAULT_MARKET,
    window: int = 10,
    horizon: int = 30,
    k: int = 10,
    metric: str = "raw",
) -> dict:
    """현재 FOMO 패턴과 닮은 과거 k개의 이후 흐름을 후보 시나리오로 반환.

    기본값은 holdout 검증에서 가장 일반화가 좋았던 설정(W=10, H=30, k=10, raw).
    """
    _require_positive_int("window", window)
    _require_positive_int("horizon", horizon)
    _require_positive_int("k", k)
    if metric not in PATTERN_METRICS:
        raise HTTPException(
            status_code=400, detail=f"metric must be one of {list(PATTERN_METRICS)}"
        )
    candles = _load_or_404(market)
    try:
        forecast = build_fomo_pattern_forecast(
            candles, window=window, horizon=horizon, k=k, metric=metric
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "market": market,
        **forecast,
        "disclaimer": PATTERN_DISCLAIMER,
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
