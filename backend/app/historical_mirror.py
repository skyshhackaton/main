"""Historical Mirror analysis.

This module finds past market states whose FOMO Score was close to the current
score, then summarizes what happened after those historical dates. The future
return fields are retrospective statistics for past samples only; they are not
investment advice or a forecast.
"""

from __future__ import annotations

from statistics import pstdev
from typing import Iterable

from app.fomo_score import score_at, score_series

DEFAULT_HORIZONS = (3, 7, 30)


def _future_return(candles: list[dict], index: int, horizon: int) -> float | None:
    future_index = index + horizon
    if future_index >= len(candles):
        return None

    base_close = candles[index]["close"]
    if base_close == 0:
        return None

    future_close = candles[future_index]["close"]
    return (future_close - base_close) / base_close


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round_optional(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _summarize_returns(
    periods: Iterable[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict:
    stats: dict[str, float | int | None] = {"sample_count": 0}
    period_list = list(periods)
    stats["sample_count"] = len(period_list)

    for horizon in horizons:
        key = f"ret_{horizon}d"
        values = [p[key] for p in period_list if p[key] is not None]
        positive = [v for v in values if v > 0]

        stats[f"mean_{horizon}d"] = _round_optional(_mean(values))
        stats[f"std_{horizon}d"] = _round_optional(pstdev(values) if len(values) > 1 else 0.0 if values else None)
        stats[f"positive_rate_{horizon}d"] = _round_optional(len(positive) / len(values) if values else None)
        stats[f"sample_count_{horizon}d"] = len(values)

    return stats


def build_historical_mirror(
    candles: list[dict],
    current_score: float | None = None,
    tolerance: float = 10.0,
    days: int = 200,
    max_periods: int = 20,
) -> dict:
    """Return past periods whose score is close to the current FOMO Score.

    `score_series` computes every historical score with candles available only
    up to that date. Return calculations intentionally use later closes, but
    only after a historical candidate date has been selected.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    if days <= 0:
        raise ValueError("days must be positive")
    if max_periods <= 0:
        raise ValueError("max_periods must be positive")

    series = score_series(candles, days=days)
    if not series:
        raise ValueError("not enough candles to build score series")

    current = score_at(candles)
    target_score = current["score"] if current_score is None else current_score
    series_start_index = len(candles) - len(series)

    matches = []
    for offset, item in enumerate(series[:-1]):
        candle_index = series_start_index + offset
        score_gap = abs(item["score"] - target_score)
        if score_gap > tolerance:
            continue

        period = {
            "date": item["date"],
            "close": item["close"],
            "score": item["score"],
            "grade": item["grade"],
            "score_gap": round(score_gap, 2),
            "summary": _build_period_summary(item),
        }
        for horizon in DEFAULT_HORIZONS:
            period[f"ret_{horizon}d"] = _round_optional(_future_return(candles, candle_index, horizon))
        matches.append(period)

    matches.sort(key=lambda p: (p["score_gap"], p["date"]))
    visible_periods = matches[:max_periods]

    return {
        "current_date": series[-1]["date"],
        "current_score": round(target_score, 2),
        "current_grade": current["grade"],
        "tolerance": tolerance,
        "similar_periods": visible_periods,
        "stats": _summarize_returns(matches),
        "summary": _build_overall_summary(len(matches), tolerance),
    }


def _build_period_summary(item: dict) -> str:
    return f"당시 FOMO Score는 {item['score']}점({item['grade']})으로 현재와 유사한 시장 심리 구간이었습니다."


def _build_overall_summary(sample_count: int, tolerance: float) -> str:
    if sample_count == 0:
        return f"최근 시계열에서 현재 점수와 ±{tolerance:g} 범위로 유사한 과거 구간을 찾지 못했습니다."
    return f"최근 시계열에서 현재 점수와 ±{tolerance:g} 범위로 유사한 과거 구간 {sample_count}개를 찾았습니다. 과거 참고 통계이며 미래 성과를 보장하지 않습니다."
