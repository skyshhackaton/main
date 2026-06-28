"""Utilities for validating FOMO Score weights on historical candles.

Scores at time t are calculated only from candles[:t+1]. Future prices are
used solely as evaluation labels, never as score inputs.
"""

from __future__ import annotations

from dataclasses import asdict
from itertools import product
from typing import Iterable

from . import fomo_score
from .fomo_score import FomoWeights, WEIGHTS


BUCKETS = (
    (0.0, 20.0, "0-20"),
    (20.0, 40.0, "20-40"),
    (40.0, 60.0, "40-60"),
    (60.0, 80.0, "60-80"),
    (80.0, 100.0, "80-100"),
)


def _bucket_label(score: float) -> str:
    """Use (lower, upper] boundaries, except that zero belongs to 0-20."""
    for lower, upper, label in BUCKETS:
        if (score > lower or score == 0.0) and score <= upper:
            return label
    raise ValueError(f"score outside 0..100: {score}")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _score_series_with_weights(
    candles: list[dict], days: int, weights: FomoWeights
) -> list[dict]:
    """Run the existing scorer with temporary weights, then always restore it.

    This keeps sensitivity-analysis concerns inside this offline backtest module
    without changing the production fomo_score interface.
    """
    original = fomo_score.WEIGHTS
    try:
        fomo_score.WEIGHTS = weights
        return fomo_score.score_series(candles, days=days)
    finally:
        fomo_score.WEIGHTS = original


def evaluate_weights(
    candles: list[dict],
    weights: FomoWeights = WEIGHTS,
    days: int = 200,
    horizon: int = 7,
) -> dict:
    """Return score-bucket statistics for a forward-return evaluation."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")

    series = _score_series_with_weights(candles, days, weights)
    grouped: dict[str, list[float]] = {label: [] for _, _, label in BUCKETS}

    for index, item in enumerate(series):
        future_index = index + horizon
        if future_index >= len(series):
            continue
        close = float(item["close"])
        if close <= 0:
            continue
        future_close = float(series[future_index]["close"])
        forward_return = future_close / close - 1.0
        grouped[_bucket_label(float(item["score"]))].append(forward_return)

    buckets = []
    for _, _, label in BUCKETS:
        returns = grouped[label]
        buckets.append(
            {
                "bucket": label,
                "sample_count": len(returns),
                "mean_7d_return": _mean(returns),
                "positive_rate": (
                    sum(value > 0 for value in returns) / len(returns)
                    if returns
                    else None
                ),
            }
        )

    high_greed = next(row for row in buckets if row["bucket"] == "80-100")
    mean_return = high_greed["mean_7d_return"]
    if mean_return is None:
        finding = "insufficient_data"
    elif mean_return < 0:
        finding = "short_term_pullback_observed"
    else:
        finding = "short_term_pullback_not_observed"

    return {
        "days": days,
        "horizon": horizon,
        "weights": asdict(weights),
        "series_count": len(series),
        "evaluated_count": sum(row["sample_count"] for row in buckets),
        "buckets": buckets,
        "high_greed_report": {
            "finding": finding,
            "sample_count": high_greed["sample_count"],
            "mean_7d_return": mean_return,
            "positive_rate": high_greed["positive_rate"],
        },
    }


def weights_for_sensitivity(x7: float, x8: float) -> FomoWeights:
    """Set X7/X8 and proportionally rescale X1-X6 so weights sum to one."""
    if x7 < 0 or x8 < 0 or x7 + x8 >= 1:
        raise ValueError("X7 and X8 must be non-negative and sum to less than 1")

    base = asdict(WEIGHTS)
    fixed_names = tuple(base)[:6]
    fixed_total = sum(base[name] for name in fixed_names)
    scale = (1.0 - x7 - x8) / fixed_total
    values = {name: base[name] * scale for name in fixed_names}
    values["volume_momentum"] = x7
    values["win_streak"] = x8
    return FomoWeights(**values)


def sensitivity_analysis(
    candles: list[dict],
    values: Iterable[float] = (0.15, 0.20, 0.25),
    days: int = 200,
    horizon: int = 7,
) -> list[dict]:
    """Compare all requested X7/X8 combinations using identical candles."""
    rows = []
    values = tuple(values)
    for x7, x8 in product(values, repeat=2):
        weights = weights_for_sensitivity(x7, x8)
        result = evaluate_weights(candles, weights, days, horizon)
        report = result["high_greed_report"]
        rows.append(
            {
                "x7": x7,
                "x8": x8,
                "weight_sum": sum(asdict(weights).values()),
                "high_greed_sample_count": report["sample_count"],
                "high_greed_mean_7d_return": report["mean_7d_return"],
                "high_greed_positive_rate": report["positive_rate"],
                "finding": report["finding"],
            }
        )
    return rows


def format_sensitivity_table(rows: list[dict]) -> str:
    """Render sensitivity results as a presentation-ready Markdown table."""
    lines = [
        "| X7 | X8 | 80+ samples | mean 7d return | positive rate | finding |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        mean_return = row["high_greed_mean_7d_return"]
        positive_rate = row["high_greed_positive_rate"]
        mean_text = "N/A" if mean_return is None else f"{mean_return:.2%}"
        rate_text = "N/A" if positive_rate is None else f"{positive_rate:.2%}"
        lines.append(
            f"| {row['x7']:.2f} | {row['x8']:.2f} | "
            f"{row['high_greed_sample_count']} | {mean_text} | {rate_text} | "
            f"{row['finding']} |"
        )
    return "\n".join(lines)
