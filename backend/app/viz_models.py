"""모델 비교 시각화: KNN 패턴매칭 vs XGBoost vs LSTM.

같은 holdout(train/val) 기준으로 horizon별 skill(=1 - model_MAE / persistence_MAE)을
계산해 한 장의 차트로 비교한다. 0보다 크면 "FOMO가 그대로 유지된다(persistence)"
baseline보다 나음을 뜻한다.

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
    DISCLAIMER,
    fomo_scores,
    load_candles_from_csv,
)
from app.train_lstm import tune_lstm  # noqa: E402
from app.train_xgb import evaluate_xgb_holdout  # noqa: E402

DEFAULT_HORIZONS = (1, 3, 7, 14, 30)
# 비교용 LSTM 소격자 (각 모델을 best-effort로 튜닝해 공정 비교).
LSTM_COMPARE_GRID = {"hidden": [50], "input_dense": [0, 32], "dropout": [0.0, 0.2], "lr": [0.01]}
DISCLAIMER_EN = (
    "Holdout skill on a market-state index (FOMO Score), not price/return prediction. "
    "Observation tool only."
)


def compare_models(
    candles: list[dict],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    knn_window: int = 10,
    knn_k: int = 10,
    knn_metric: str = "raw",
    lstm_window: int = 20,
    lstm_grid: dict | None = None,
    lstm_epochs: int = 150,
) -> list[dict]:
    """horizon별 세 모델의 holdout skill을 같은 기준으로 계산.

    각 모델을 best-effort로(LSTM은 소격자 튜닝, XGB는 holdout, KNN은 검증된 설정)
    평가해 같은 train/val 분리·persistence baseline 위에서 비교한다.
    """
    scores = fomo_scores(candles)
    grid = lstm_grid or LSTM_COMPARE_GRID
    rows = []
    for h in sorted(set(horizons)):
        knn = validate_holdout(scores, knn_window, h, knn_k, knn_metric, train_ratio)
        xgb = evaluate_xgb_holdout(candles, h, train_ratio=train_ratio)
        try:
            best = tune_lstm(scores, horizon=h, window=lstm_window, param_grid=grid,
                             train_ratio=train_ratio, epochs=lstm_epochs)["best"]
            lstm_skill, lstm_mae = best["skill"], best["val_mae"]
        except ValueError:
            lstm_skill, lstm_mae = None, None
        rows.append({
            "horizon": h,
            "knn_skill": knn["skill"], "knn_mae": knn["analog_mae"],
            "xgb_skill": xgb["skill"], "xgb_mae": xgb["val_mae"],
            "lstm_skill": lstm_skill, "lstm_mae": lstm_mae,
            "persist_mae": xgb["persist_mae"],
        })
    return rows


def plot_model_comparison(rows: list[dict], market: str, path: Path) -> None:
    horizons = [r["horizon"] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    series = [
        ("KNN pattern", "knn_skill", "#1155cc", "o"),
        ("XGBoost", "xgb_skill", "#e69138", "s"),
        ("LSTM", "lstm_skill", "#cc0000", "^"),
    ]
    for label, key, color, marker in series:
        ys = [r[key] if r[key] is not None else np.nan for r in rows]
        ax.plot(horizons, ys, color=color, marker=marker, lw=2, label=label)
    ax.axhline(0, color="black", lw=1.2)
    ax.text(horizons[-1], 0, " persistence", va="bottom", ha="right", fontsize=8, color="black")

    ax.set_xticks(horizons)
    ax.set_xlabel("horizon (days)")
    ax.set_ylabel("holdout skill = 1 - model_MAE / persistence_MAE")
    ax.set_title(
        f"{market}  model comparison: skill vs persistence (holdout)\n"
        "above 0 = better than 'assume FOMO stays the same'",
        fontsize=10,
    )
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.text(0.5, 0.005, DISCLAIMER_EN, ha="center", fontsize=7, color="gray")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    rows = compare_models(candles, horizons=horizons, train_ratio=train_ratio)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart = out_dir / "model_comparison.png"
    plot_model_comparison(rows, market, chart)

    import json
    report = {"market": market, "csv_path": str(csv_path), "train_ratio": train_ratio,
              "comparison": rows, "disclaimer": DISCLAIMER}
    (out_dir / "model_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"chart": chart, "comparison": rows}


def main(argv: list[str] | None = None) -> None:
    import argparse

    import torch

    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description="모델 비교 차트 (KNN/XGBoost/LSTM)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    result = generate(Path(args.csv), args.market, Path(args.out))
    print("horizon | KNN | XGBoost | LSTM   (holdout skill vs persistence)")
    for r in result["comparison"]:
        def fmt(v):
            return "  n/a " if v is None else f"{v:+.3f}"
        print(f"{r['horizon']:>5}d  | {fmt(r['knn_skill'])} | {fmt(r['xgb_skill'])} | {fmt(r['lstm_skill'])}")
    print(f"\n저장: {result['chart']}")


if __name__ == "__main__":
    main()
