"""KNN FOMO 패턴 매칭 시각화.

두 장의 PNG를 생성한다.
1. knn_pattern_forecast.png  — 최근 FOMO 궤적 + 가장 닮은 과거 k개의 anchored 후보
   시나리오 + 평균/분위수 밴드(스파게티 플롯).
2. knn_pattern_skill.png     — horizon별 패턴매칭 skill(=1-analog/persist) 비교.

라벨은 폰트 호환을 위해 영문. 결과는 과거 사례 분포이며 예측이 아니다(관찰 도구).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 헤드리스 렌더링
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.knn_pattern import (  # noqa: E402
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TEST_SIZE,
    DEFAULT_TRAIN_RATIO,
    build_fomo_pattern_forecast,
    compare_configs,
    compare_holdout,
    fomo_score_series,
    load_candles_from_csv,
    validate_holdout,
)

GRADE_ZONES = [
    (0, 20, "#3b6ea5", "Extreme Fear"),
    (20, 40, "#6fa8dc", "Fear"),
    (40, 60, "#b7b7b7", "Neutral"),
    (60, 80, "#e69138", "Greed"),
    (80, 100, "#cc0000", "Extreme Greed"),
]
DISCLAIMER_EN = (
    "Past analog distribution of a market-state index (FOMO Score), "
    "not a price/return prediction. Observation tool only."
)
GRADE_EN = {
    "극단적 공포": "Extreme Fear",
    "공포": "Fear",
    "중립": "Neutral",
    "탐욕": "Greed",
    "극단적 탐욕": "Extreme Greed",
}


def plot_forecast(scores: np.ndarray, fc: dict, market: str, path: Path) -> None:
    w, h, k = fc["window"], fc["horizon"], fc["k"]
    lookback = min(len(scores), max(w, 20))
    recent = scores[-lookback:]
    x_hist = list(range(-(lookback - 1), 1))
    x_fut = list(range(1, h + 1))

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for lo, hi, color, label in GRADE_ZONES:
        ax.axhspan(lo, hi, color=color, alpha=0.08)
        ax.text(x_fut[-1], (lo + hi) / 2, label, va="center", ha="right",
                fontsize=7, color=color, alpha=0.8)

    for i, cand in enumerate(fc["candidates"]):
        ax.plot(x_fut, cand["anchored_future"], color="gray", alpha=0.35, lw=1,
                label="analog scenarios" if i == 0 else None)
    ax.fill_between(x_fut, fc["band"]["p10"], fc["band"]["p90"],
                    color="#3d85c6", alpha=0.18, label="p10-p90 band")
    ax.plot(x_fut, fc["band"]["mean"], color="#1155cc", lw=2.5, marker="o",
            ms=3, label="mean scenario")
    ax.plot(x_hist, recent, color="black", lw=2, marker="o", ms=3, label="recent FOMO")
    ax.axvline(0, color="black", ls="--", lw=1, alpha=0.6)
    ax.scatter([0], [fc["current_score"]], color="black", zorder=5)

    ax.set_ylim(0, 100)
    ax.set_xlim(x_hist[0], x_fut[-1])
    ax.set_xlabel("days from now")
    ax.set_ylabel("FOMO Score")
    ax.set_title(
        f"{market}  FOMO pattern forecast  (W={w}, H={h}, k={k}, {fc['metric']})\n"
        f"now {fc['current_score']} ({GRADE_EN.get(fc['current_grade'], fc['current_grade'])})  ->  {h}d mean "
        f"{fc['band']['mean'][-1]}  (p10 {fc['band']['p10'][-1]}, p90 {fc['band']['p90'][-1]})",
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=8)
    fig.text(0.5, 0.01, DISCLAIMER_EN, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_skill(comparison: list[dict], market: str, path: Path) -> None:
    ks = sorted({c["k"] for c in comparison})
    k_pick = ks[-1]
    horizons = sorted({c["horizon"] for c in comparison})
    windows = sorted({c["window"] for c in comparison})
    palette = ["#cc0000", "#e69138", "#1155cc", "#38761d"]
    colors = {w: palette[i % len(palette)] for i, w in enumerate(windows)}

    fig, ax = plt.subplots(figsize=(8, 5))
    for w in windows:
        for metric, ls in (("raw", "-"), ("znorm", "--")):
            ys = []
            for h in horizons:
                match = next(
                    (c for c in comparison if c["window"] == w and c["horizon"] == h
                     and c["k"] == k_pick and c["metric"] == metric),
                    None,
                )
                ys.append(match["skill"] if match and match["skill"] is not None else np.nan)
            ax.plot(horizons, ys, ls, color=colors[w], marker="o",
                    label=f"W={w} {metric}")

    ax.axhline(0, color="black", lw=1)
    ax.set_xticks(horizons)
    ax.set_xlabel("horizon (days)")
    ax.set_ylabel("skill = 1 - analog_MAE / persist_MAE")
    ax.set_title(f"{market}  pattern-matching skill vs persistence baseline  (k={k_pick})\n"
                 "above 0 = better than 'assume FOMO stays the same'", fontsize=10)
    ax.legend(fontsize=7, ncol=len(windows))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_validation(scores: np.ndarray, detail: dict, market: str, path: Path) -> None:
    """Holdout 검증 시각화: (위) 검증구간 실제 vs 샘플 예측경로, (아래) per-step MAE / scatter."""
    cutoff = detail["cutoff_index"]
    h = detail["horizon"]
    n = len(scores)
    val_x = list(range(cutoff, n))
    val_y = scores[cutoff:n]

    fig = plt.figure(figsize=(11, 7.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.1, 1.0], hspace=0.32, wspace=0.25)

    # (1) 타임라인: 검증 구간 실제 + train 패턴 기반 샘플 예측 경로
    ax0 = fig.add_subplot(gs[0, :])
    for lo, hi, color, _ in GRADE_ZONES:
        ax0.axhspan(lo, hi, color=color, alpha=0.06)
    ax0.plot(val_x, val_y, color="black", lw=1.3, label="actual FOMO (validation)")
    for i, s in enumerate(detail["samples"]):
        t = s["origin_index"]
        ax0.plot(range(t + 1, t + 1 + h), s["pred"], color="#1155cc", lw=1.6,
                 alpha=0.8, marker="o", ms=2,
                 label="predicted path (train analogs)" if i == 0 else None)
        ax0.scatter([t], [scores[t]], color="#cc0000", s=18, zorder=5)
    ax0.set_ylim(0, 100)
    ax0.set_xlabel("scored-day index")
    ax0.set_ylabel("FOMO Score")
    ax0.set_title(
        f"{market}  holdout validation  (train {int(detail['train_ratio']*100)}% / "
        f"val {detail['val_origins']} origins;  W={detail['window']}, H={h}, "
        f"k={detail['k']}, {detail['metric']})\nanalog pool = TRAIN only;  "
        f"skill={detail['skill']:+.3f}  (analog MAE {detail['analog_mae']} vs "
        f"persistence {detail['persist_mae']})",
        fontsize=9.5,
    )
    ax0.legend(loc="upper left", fontsize=8)

    # (2) per-step MAE
    ax1 = fig.add_subplot(gs[1, 0])
    steps = detail["per_step"]["steps"]
    ax1.plot(steps, detail["per_step"]["analog_mae"], color="#1155cc", marker="o",
             ms=3, label="analog")
    ax1.plot(steps, detail["per_step"]["persist_mae"], color="gray", ls="--",
             marker="o", ms=3, label="persistence")
    ax1.set_xlabel("steps ahead (days)")
    ax1.set_ylabel("MAE")
    ax1.set_title("per-step error (lower = better)", fontsize=9)
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    # (3) scatter: 예측 vs 실제 (horizon H 끝점)
    ax2 = fig.add_subplot(gs[1, 1])
    pa = detail["scatter"]
    ax2.scatter(pa["actual_h"], pa["pred_h"], s=8, alpha=0.35, color="#1155cc")
    lims = [0, 100]
    ax2.plot(lims, lims, color="black", lw=1, ls="--")
    ax2.set_xlim(lims)
    ax2.set_ylim(lims)
    ax2.set_xlabel(f"actual FOMO at +{h}d")
    ax2.set_ylabel(f"predicted FOMO at +{h}d")
    ax2.set_title("predicted vs actual (validation)", fontsize=9)

    fig.text(0.5, 0.005, DISCLAIMER_EN, ha="center", fontsize=7, color="gray")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
    test_size: int = DEFAULT_TEST_SIZE,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores, _ = fomo_score_series(candles)
    comparison = compare_configs(candles, test_size=test_size)
    best = next((c for c in comparison if c["skill"] is not None), None)
    if best is None:
        raise ValueError("표본 부족으로 추천 설정을 산출하지 못했습니다.")

    fc = build_fomo_pattern_forecast(
        candles, window=best["window"], horizon=best["horizon"],
        k=best["k"], metric=best["metric"],
    )

    # holdout: 어느 설정이 train/val 분리에서 일반화되는지로 검증 설정을 고른다.
    holdout = compare_holdout(candles, train_ratio=train_ratio)
    best_h = next((c for c in holdout if c["skill"] is not None), best)
    detail = validate_holdout(
        scores, best_h["window"], best_h["horizon"], best_h["k"],
        best_h["metric"], train_ratio=train_ratio, collect=True,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    forecast_png = out_dir / "knn_pattern_forecast.png"
    skill_png = out_dir / "knn_pattern_skill.png"
    validation_png = out_dir / "knn_pattern_validation.png"
    plot_forecast(scores, fc, market, forecast_png)
    plot_skill(comparison, market, skill_png)
    plot_validation(scores, detail, market, validation_png)
    return {
        "recommended_config": best,
        "holdout_best": best_h,
        "forecast_png": forecast_png,
        "skill_png": skill_png,
        "validation_png": validation_png,
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="KNN FOMO 패턴 매칭 시각화 (PNG)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--test-size", type=int, default=DEFAULT_TEST_SIZE)
    parser.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    result = generate(Path(args.csv), args.market, Path(args.out), args.test_size, args.train_ratio)
    rec = result["recommended_config"]
    bh = result["holdout_best"]
    print(f"walk-forward best: W={rec['window']} H={rec['horizon']} k={rec['k']} "
          f"{rec['metric']} (skill={rec['skill']:+.3f})")
    print(f"holdout best:      W={bh['window']} H={bh['horizon']} k={bh['k']} "
          f"{bh['metric']} (skill={bh['skill']:+.3f})")
    print(f"저장: {result['forecast_png']}\n      {result['skill_png']}\n      {result['validation_png']}")


if __name__ == "__main__":
    main()
