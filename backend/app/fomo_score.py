"""FOMO Score domain logic.

The score is a market-state observation value, not investment advice.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FomoWeights:
    price_momentum: float = 0.10
    price_strength: float = 0.10
    market_breadth: float = 0.10
    clv_pressure: float = 0.15
    rsi: float = 0.10
    volatility_inverse: float = 0.05
    volume_momentum: float = 0.20
    win_streak: float = 0.20


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
