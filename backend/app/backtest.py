"""Utilities for validating FOMO Score weights on historical candles.

Scores at time t are calculated only from candles[:t+1]. Future prices are
used solely as evaluation labels, never as score inputs.
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Iterable

from . import fomo_score
from .fomo_score import FomoWeights, WEIGHTS


DEFAULT_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "upbit_candles_snapshot.csv"
DEFAULT_MARKETS = ("KRW-BTC", "KRW-ETH", "KRW-XRP")
RESCALED_WEIGHT_FIELDS = (
    "price_momentum",
    "price_strength",
    "market_breadth",
    "clv_pressure",
    "rsi",
    "volatility_inverse",
)

BUCKETS = (
    (0.0, 20.0, "0-20"),
    (20.0, 40.0, "20-40"),
    (40.0, 60.0, "40-60"),
    (60.0, 80.0, "60-80"),
    (80.0, 100.0, "80-100"),
)


def load_snapshot_candles(
    market: str,
    csv_path: Path = DEFAULT_SNAPSHOT_PATH,
) -> list[dict]:
    """Load one market from the tracked official snapshot in oldest-first order."""
    candles = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"market", "date_utc", "open", "high", "low", "close", "volume"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or ()))
            raise ValueError(f"snapshot is missing required columns: {missing}")
        for row in reader:
            if row["market"] != market:
                continue
            candles.append(
                {
                    "date_utc": row["date_utc"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
    return sorted(candles, key=lambda candle: candle["date_utc"])


def run_snapshot_backtests(
    markets: Iterable[str] = DEFAULT_MARKETS,
    csv_path: Path = DEFAULT_SNAPSHOT_PATH,
    days: int = 200,
    horizon: int = 7,
) -> dict[str, dict]:
    """Run baseline and sensitivity backtests from the official CSV snapshot."""
    results = {}
    for market in markets:
        candles = load_snapshot_candles(market, csv_path)
        if not candles:
            raise ValueError(f"snapshot has no candles for market: {market}")
        results[market] = {
            "source": str(csv_path),
            "candle_count": len(candles),
            "baseline": evaluate_weights(candles, days=days, horizon=horizon),
            "sensitivity": sensitivity_analysis(candles, days=days, horizon=horizon),
        }
    return results


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
    """Build a score series without mutating the production global weights."""
    if days <= 0:
        raise ValueError("days must be positive")
    if len(candles) <= fomo_score.MIN_WINDOW:
        raise ValueError(
            f"at least {fomo_score.MIN_WINDOW + 1} candles are required"
        )

    weight_values = asdict(weights)
    indicator_weights = {
        "X1": weight_values["price_momentum"],
        "X2": weight_values["price_strength"],
        "X3": weight_values["market_breadth"],
        "X4": weight_values["clv_pressure"],
        "X5": weight_values["rsi"],
        "X6": weight_values["volatility_inverse"],
        "X7": weight_values["volume_momentum"],
        "X8": weight_values["win_streak"],
    }
    start = max(fomo_score.MIN_WINDOW, len(candles) - days)
    series = []
    for index in range(start, len(candles)):
        indicators = fomo_score._calc_indicators(candles[: index + 1])
        score = round(
            sum(indicators[name] * indicator_weights[name] for name in indicator_weights),
            2,
        )
        grade, description = fomo_score.classify_grade(score)
        series.append(
            {
                "date": candles[index].get("date_utc"),
                "close": candles[index]["close"],
                "score": score,
                "grade": grade,
                "description": description,
            }
        )
    return series


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
        mean_return = _mean(returns)
        row = {
            "bucket": label,
            "sample_count": len(returns),
            "mean_forward_return": mean_return,
            "positive_rate": (
                sum(value > 0 for value in returns) / len(returns)
                if returns
                else None
            ),
        }
        # Preserve the original default-horizon contract without attaching a
        # misleading 7-day label to custom-horizon results.
        if horizon == 7:
            row["mean_7d_return"] = mean_return
        buckets.append(row)

    high_greed = next(row for row in buckets if row["bucket"] == "80-100")
    mean_return = high_greed["mean_forward_return"]
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
        "score_summary": {
            "mean": _mean([float(item["score"]) for item in series]),
            "min": min((float(item["score"]) for item in series), default=None),
            "max": max((float(item["score"]) for item in series), default=None),
        },
        "evaluated_count": sum(row["sample_count"] for row in buckets),
        "buckets": buckets,
        "high_greed_report": {
            "finding": finding,
            "sample_count": high_greed["sample_count"],
            "mean_forward_return": mean_return,
            "positive_rate": high_greed["positive_rate"],
            **({"mean_7d_return": mean_return} if horizon == 7 else {}),
        },
    }


def weights_for_sensitivity(x7: float, x8: float) -> FomoWeights:
    """Set X7/X8 and proportionally rescale X1-X6 so weights sum to one."""
    if x7 < 0 or x8 < 0 or x7 + x8 >= 1:
        raise ValueError("X7 and X8 must be non-negative and sum to less than 1")

    base = asdict(WEIGHTS)
    fixed_total = sum(base[name] for name in RESCALED_WEIGHT_FIELDS)
    scale = (1.0 - x7 - x8) / fixed_total
    values = {name: base[name] * scale for name in RESCALED_WEIGHT_FIELDS}
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
                "score_summary": result["score_summary"],
                "buckets": result["buckets"],
                "high_greed_sample_count": report["sample_count"],
                "high_greed_mean_forward_return": report["mean_forward_return"],
                "high_greed_positive_rate": report["positive_rate"],
                "finding": report["finding"],
                **(
                    {"high_greed_mean_7d_return": report["mean_7d_return"]}
                    if horizon == 7
                    else {}
                ),
            }
        )
    return rows


def format_sensitivity_table(rows: list[dict]) -> str:
    """Render score distribution and forward outcomes for every weight pair.

    Each bucket cell is ``sample count / mean forward return / positive rate``.
    This keeps the sensitivity comparison focused on the observed outcome, not
    merely on how changing weights moves scores between buckets.
    """

    def format_bucket(item: dict) -> str:
        count = item["sample_count"]
        mean_return = item["mean_forward_return"]
        positive_rate = item["positive_rate"]
        if mean_return is None or positive_rate is None:
            return f"{count} / N/A / N/A"
        return f"{count} / {mean_return:+.2%} / {positive_rate:.2%}"

    lines = [
        "| X7 | X8 | score mean | score range | 0-20 (n/ret/up) | 20-40 (n/ret/up) | 40-60 (n/ret/up) | 60-80 (n/ret/up) | 80-100 (n/ret/up) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        summary = row["score_summary"]
        buckets = {item["bucket"]: format_bucket(item) for item in row["buckets"]}
        lines.append(
            f"| {row['x7']:.2f} | {row['x8']:.2f} | "
            f"{summary['mean']:.2f} | {summary['min']:.2f}~{summary['max']:.2f} | "
            f"{buckets['0-20']} | {buckets['20-40']} | {buckets['40-60']} | "
            f"{buckets['60-80']} | {buckets['80-100']} |"
        )
    return "\n".join(lines)
