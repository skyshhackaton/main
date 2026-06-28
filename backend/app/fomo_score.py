"""FOMO Score domain logic.

The score is a market-state observation value, not investment advice.

X1~X7: CNN 공포탐욕지수 7개 지표 베이스라인
X8: 연속 상승일 (초보자 FOMO 핵심 신호)
모든 지표는 시점 t 기준 과거 정보만 사용 (look-ahead bias 없음)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FomoWeights:
    price_momentum: float = 0.10     # X1
    price_strength: float = 0.10     # X2
    market_breadth: float = 0.10     # X3
    clv_pressure: float = 0.15       # X4
    rsi: float = 0.10                # X5
    volatility_inverse: float = 0.05 # X6
    volume_momentum: float = 0.20    # X7 — 초보 FOMO 핵심
    win_streak: float = 0.20         # X8 — 초보 FOMO 핵심


WEIGHTS = FomoWeights()


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def classify_grade(score: float) -> tuple[str, str]:
    if score <= 20:
        return "극단적 공포", "시장 불안과 패닉 심리가 강한 상태"
    if score <= 40:
        return "공포", "하락 우려와 관망 심리가 우세한 상태"
    if score <= 60:
        return "중립", "특정 방향의 심리 쏠림이 약한 상태"
    if score <= 80:
        return "탐욕", "매수 심리와 FOMO 조짐이 우세한 상태"
    return "극단적 탐욕", "과열과 추격매수 심리가 강한 상태"


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    """Wilder 단순 평균 RSI. closes는 oldest-first."""
    if len(closes) < period + 1:
        return 50.0
    window = closes[-(period + 1):]
    gains = [max(window[i] - window[i - 1], 0.0) for i in range(1, len(window))]
    losses = [max(window[i - 1] - window[i], 0.0) for i in range(1, len(window))]
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def _calc_indicators(candles: list[dict]) -> dict[str, float]:
    """candles 마지막 원소를 시점 t로 보고 X1~X8 산출 (각 0~100)."""
    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    vols   = [c["volume"] for c in candles]
    c = closes[-1]

    # X1 가격 모멘텀: 120일 이동평균 대비
    ma120 = _mean(closes[-120:])
    x1 = clamp(50 + (c / ma120 - 1) * 200) if ma120 else 50.0

    # X2 가격 강도: 365일 고저 범위 내 위치
    hi365 = max(highs[-365:])
    lo365 = min(lows[-365:])
    x2 = clamp((c - lo365) / (hi365 - lo365) * 100) if hi365 > lo365 else 50.0

    # X3 시장 폭: 20일간 상승일 거래량 비율
    up_v = dn_v = 0.0
    for i in range(len(candles) - 20, len(candles)):
        if i <= 0:
            continue
        if closes[i] >= closes[i - 1]:
            up_v += vols[i]
        else:
            dn_v += vols[i]
    x3 = up_v / (up_v + dn_v) * 100 if (up_v + dn_v) else 50.0

    # X4 매수 압력 (CLV 14일 평균): -1~1 → 0~100
    clvs = []
    for i in range(len(candles) - 14, len(candles)):
        if i < 0:
            continue
        rng = highs[i] - lows[i]
        clvs.append(
            ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng if rng else 0.0
        )
    x4 = clamp((_mean(clvs) + 1) / 2 * 100)

    # X5 RSI(14)
    x5 = _calc_rsi(closes, 14)

    # X6 변동성(역): 20일 수익률 표준편차가 클수록 낮은 점수
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes)) if i > 0]
    if rets:
        mu  = _mean(rets)
        std = _mean([(r - mu) ** 2 for r in rets]) ** 0.5
        x6  = clamp(100 - std * 100 * 20)
    else:
        x6 = 50.0

    # X7 거래량 모멘텀: 5일 평균 / 20일 평균
    v5  = _mean(vols[-5:])
    v20 = _mean(vols[-20:])
    r   = v5 / v20 if v20 else 1.0
    x7  = clamp(50 + (r - 1) * 100)

    # X8 연속 상승일: 최근 5일 중 상승 마감 비율
    recent = closes[-6:]
    if len(recent) >= 2:
        up_days = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        x8 = up_days / (len(recent) - 1) * 100
    else:
        x8 = 50.0

    return {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5, "X6": x6, "X7": x7, "X8": x8}


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

MIN_WINDOW = 365  # score_at() 호출에 필요한 최소 캔들 수


def score_at(candles: list[dict]) -> dict:
    """candles 마지막 시점의 FOMO 스코어와 세부 지표 반환."""
    ind = _calc_indicators(candles)
    w = WEIGHTS
    score = (
        ind["X1"] * w.price_momentum
        + ind["X2"] * w.price_strength
        + ind["X3"] * w.market_breadth
        + ind["X4"] * w.clv_pressure
        + ind["X5"] * w.rsi
        + ind["X6"] * w.volatility_inverse
        + ind["X7"] * w.volume_momentum
        + ind["X8"] * w.win_streak
    )
    grade, description = classify_grade(score)
    return {
        "score": round(score, 2),
        "grade": grade,
        "description": description,
        "indicators": {k: round(v, 2) for k, v in ind.items()},
    }


def score_series(candles: list[dict], days: int = 200) -> list[dict]:
    """
    최근 days일에 대해 각 시점 기준 스코어 시계열 반환 (oldest-first).
    각 시점 t는 candles[:t+1]만 사용 → look-ahead bias 없음.
    """
    n = len(candles)
    start = max(MIN_WINDOW, n - days)
    series = []
    for t in range(start, n):
        res = score_at(candles[: t + 1])
        series.append(
            {
                "date": candles[t].get("date_utc"),
                "close": candles[t]["close"],
                "score": res["score"],
                "grade": res["grade"],
                "description": res["description"],
            }
        )
    return series
