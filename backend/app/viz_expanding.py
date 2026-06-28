"""Expanding-window(최근 운영 backtest) 결과 시각화.

파일명에 `_expanding`을 붙여 holdout(1회 학습)이 아니라 매 스텝 재학습한 최근 실험
버전임을 드러낸다. 생성물:
- skill_holdout_vs_expanding.png : 모델별 holdout vs expanding skill (horizon별)
- val_{knn,xgboost,lstm}_expanding.png : 각 모델 best-expanding-skill horizon의
  stitched 워크포워드 예측 vs 실제 + 산점도

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.backtest_expanding import (  # noqa: E402
    expanding_backtest_knn,
    expanding_backtest_xgb,
)
from app.train_common import (  # noqa: E402
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    fomo_scores,
    load_candles_from_csv,
)
from app.viz_per_model import COLORS  # noqa: E402
from app.viz_validation import _plot as _stitched_plot  # noqa: E402

_MODELS = [("KNN pattern", "knn"), ("XGBoost", "xgb"), ("LSTM", "lstm")]


def plot_skill_comparison(comparison: list[dict], market: str, path: Path) -> None:
    """holdout(점선) vs expanding(실선) skill을 모델별 색으로 비교."""
    horizons = [r["horizon"] for r in comparison]
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    for name, key in _MODELS:
        if f"{key}_expanding" not in comparison[0]:
            continue
        color = COLORS[name]
        hold = [r.get(f"{key}_holdout") for r in comparison]
        exp = [r.get(f"{key}_expanding") for r in comparison]
        ax.plot(horizons, [v if v is not None else np.nan for v in hold],
                color=color, ls="--", marker="o", ms=4, alpha=0.55, label=f"{name} holdout")
        ax.plot(horizons, [v if v is not None else np.nan for v in exp],
                color=color, ls="-", marker="o", ms=5, lw=2.2, label=f"{name} expanding")
    ax.axhline(0, color="black", lw=1.2)
    ax.text(horizons[-1], 0, " persistence", va="bottom", ha="right", fontsize=8)
    ax.set_xticks(horizons)
    ax.set_xlabel("horizon (days)")
    ax.set_ylabel("skill = 1 - model_MAE / persistence_MAE")
    ax.set_title(f"{market}  holdout vs expanding-window (operational) backtest\n"
                 "solid = retrain every step (operational), dashed = single 70% holdout",
                 fontsize=10)
    ax.legend(fontsize=7, ncol=3)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _best_horizon(comparison: list[dict], key: str) -> int | None:
    valid = [(r["horizon"], r.get(f"{key}_expanding")) for r in comparison
             if r.get(f"{key}_expanding") is not None]
    return max(valid, key=lambda t: t[1])[0] if valid else None


def _load_comparison(report_json: Path | None) -> list[dict]:
    path = report_json or (DEFAULT_OUT / "expanding_backtest_report.json")
    if not Path(path).exists():
        raise FileNotFoundError(
            f"{path} 없음 — 먼저 `python -m app.backtest_expanding` 실행 필요"
        )
    return json.loads(Path(path).read_text(encoding="utf-8"))["comparison"]


def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
    comparison: list[dict] | None = None,
    report_json: Path | None = None,
    include_lstm: bool = True,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    comparison = comparison if comparison is not None else _load_comparison(report_json)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"skill": out_dir / "skill_holdout_vs_expanding.png"}
    plot_skill_comparison(comparison, market, paths["skill"])

    # 각 모델 best-expanding-skill horizon에서 stitched(운영 예측) 차트.
    builders = {
        "KNN pattern": lambda h: expanding_backtest_knn(scores, h, collect=True),
        "XGBoost": lambda h: expanding_backtest_xgb(candles, h, collect=True),
    }
    if include_lstm:
        from app.backtest_expanding import expanding_backtest_lstm
        builders["LSTM"] = lambda h: expanding_backtest_lstm(scores, h, collect=True)

    for name, key in _MODELS:
        if name not in builders:
            continue
        h = _best_horizon(comparison, key)
        if h is None:
            continue
        res = builders[name](h)
        stitched = res["stitched"]
        scatter = {"pred": stitched["pred"], "actual": stitched["actual"]}
        slug = name.split()[0].lower()
        path = out_dir / f"val_{slug}_expanding.png"
        _stitched_plot(name, scores, h, res["skill"], stitched, scatter, market, path)
        paths[name] = path
    return paths


def main(argv: list[str] | None = None) -> None:
    import argparse

    import torch

    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description="Expanding backtest 시각화 (holdout vs expanding + stitched)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--no-lstm", action="store_true")
    args = parser.parse_args(argv)

    paths = generate(Path(args.csv), args.market, Path(args.out), include_lstm=not args.no_lstm)
    for label, path in paths.items():
        print(f"{label:12s} -> {path}")


if __name__ == "__main__":
    main()
