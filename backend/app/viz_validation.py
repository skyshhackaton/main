"""모델별 best-skill horizon 검증 시각화 (walk-forward stitched).

각 모델이 holdout skill이 가장 높은 horizon h*를 고른 뒤, 그 h*에 대해:
- (왼쪽) 매 미래 시점 t를 t-h* 시점 실제 데이터로 예측한 h*-step 예측을 시간축에
  이어붙여(stitched) 실제 FOMO 곡선과 겹쳐 본다. "운영 시 실제 예측" 관점.
  (각 점은 독립적인 h*-step direct 예측이며 recursive가 아님 → 누수 없음.
   모델은 train 구간에서만 학습, val 구간을 롤포워드로 예측.)
- (오른쪽) 같은 h*의 예측 vs 실제 산점도.

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.knn_pattern import validate_holdout  # noqa: E402
from app.train_common import (  # noqa: E402
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    fomo_scores,
    load_candles_from_csv,
)
from app.train_lstm import train_lstm  # noqa: E402
from app.train_xgb import evaluate_xgb_holdout  # noqa: E402
from app.viz_per_model import COLORS, HORIZONS, LSTM_CFG  # noqa: E402
from app.viz_pattern import DISCLAIMER_EN, GRADE_ZONES  # noqa: E402


def _best_horizon(skills: dict) -> int | None:
    valid = {h: s for h, s in skills.items() if s is not None}
    return max(valid, key=valid.get) if valid else None


def _knn_views(candles, scores, train_ratio):
    skills = {h: validate_holdout(scores, 10, h, 10, "raw", train_ratio)["skill"] for h in HORIZONS}
    h = _best_horizon(skills)
    d = validate_holdout(scores, 10, h, 10, "raw", train_ratio, collect=True)
    return h, skills[h], d["stitched"], {"pred": d["scatter"]["pred_h"], "actual": d["scatter"]["actual_h"]}


def _xgb_views(candles, scores, train_ratio):
    skills = {h: evaluate_xgb_holdout(candles, h, train_ratio=train_ratio)["skill"] for h in HORIZONS}
    h = _best_horizon(skills)
    d = evaluate_xgb_holdout(candles, h, train_ratio=train_ratio, collect=True)
    stitched = {"target_index": d["target_index"], "pred": d["pred"], "actual": d["actual"]}
    return h, skills[h], stitched, {"pred": d["pred"], "actual": d["actual"]}


def _lstm_views(candles, scores, train_ratio):
    skills = {h: train_lstm(scores, horizon=h, train_ratio=train_ratio, **LSTM_CFG)["skill"]
              for h in HORIZONS}
    h = _best_horizon(skills)
    d = train_lstm(scores, horizon=h, train_ratio=train_ratio, collect=True, **LSTM_CFG)
    stitched = {"target_index": d["target_index"], "pred": d["pred"], "actual": d["actual"]}
    return h, skills[h], stitched, {"pred": d["pred"], "actual": d["actual"]}


def _plot(model_name, scores, horizon, skill, stitched, scatter, market, path):
    color = COLORS[model_name]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [2, 1]})

    ax0 = axes[0]
    for lo, hi, c, _ in GRADE_ZONES:
        ax0.axhspan(lo, hi, color=c, alpha=0.06)
    ax0.plot(np.arange(len(scores)), scores, color="black", lw=1.0, alpha=0.45, label="actual FOMO")
    ti = stitched["target_index"]
    ax0.plot(ti, stitched["pred"], color=color, lw=1.5, label=f"+{horizon}d forecast (stitched)")
    if ti:
        ax0.axvline(min(ti), color="gray", ls="--", lw=1, alpha=0.7)
        ax0.text(min(ti), 3, " validation", fontsize=7, color="gray", ha="left")
    ax0.set_ylim(0, 100)
    ax0.set_xlabel("scored-day index")
    ax0.set_ylabel("FOMO Score")
    ax0.set_title(f"walk-forward +{horizon}d forecast vs actual (stitched)", fontsize=10)
    ax0.legend(fontsize=8, loc="upper left")

    ax1 = axes[1]
    ax1.scatter(scatter["actual"], scatter["pred"], s=8, alpha=0.35, color=color)
    ax1.plot([0, 100], [0, 100], "k--", lw=1)
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 100)
    ax1.set_xlabel(f"actual FOMO at +{horizon}d")
    ax1.set_ylabel(f"predicted FOMO at +{horizon}d")
    ax1.set_title("predicted vs actual", fontsize=10)

    fig.suptitle(
        f"{market} — {model_name}: best-skill validation  (+{horizon}d, skill {skill:+.3f})",
        fontsize=12,
    )
    fig.text(0.5, 0.005, DISCLAIMER_EN, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = {}
    for name, builder in (
        ("KNN pattern", _knn_views),
        ("XGBoost", _xgb_views),
        ("LSTM", _lstm_views),
    ):
        horizon, skill, stitched, scatter = builder(candles, scores, train_ratio)
        slug = name.split()[0].lower()
        path = out_dir / f"val_{slug}.png"
        _plot(name, scores, horizon, skill, stitched, scatter, market, path)
        out[name] = {"best_horizon": horizon, "skill": skill, "path": path}
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse

    import torch

    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description="모델별 best-skill horizon 검증 차트 (stitched)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = generate(Path(args.csv), args.market, Path(args.out))
    for name, info in out.items():
        print(f"{name:12s} best +{info['best_horizon']}d  skill {info['skill']:+.3f}  -> {info['path']}")


if __name__ == "__main__":
    main()
