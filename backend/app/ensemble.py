"""모델 앙상블: XGBoost + LSTM 블렌드로 성능 최대화.

두 모델의 예측을 **target 시점(FOMO score 시계열 인덱스)으로 정렬**한 뒤 합친다.
(KNN 패턴은 중·장기 skill이 상대적으로 낮아 평균을 끌어내려 제외했다.)
- equal     : 단순 평균 (가중치 학습 없음 → 과적합 없음, 배포용 정직 기준)
- weighted  : 개별 skill에 비례한 가중 평균 (가중치를 val에서 뽑아 약간 낙관적)

평가는 holdout 또는 expanding(운영) backtest 예측을 그대로 재사용한다. persistence
baseline = "horizon 뒤도 현재값과 같다". 대상은 가격이 아니라 시장 심리 상태값
(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.train_common import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    DISCLAIMER,
    fomo_scores,
    load_candles_from_csv,
)

HORIZONS = (1, 3, 7, 14, 30)
LSTM_CFG = dict(window=20, hidden=50, input_dense=32, dropout=0.1, epochs=120)
MODELS = ("XGB", "LSTM")
COLOR_MAP = {"XGB": "#e69138", "LSTM": "#cc0000"}


def _holdout_preds(candles, scores, horizon, train_ratio):
    from app.train_lstm import train_lstm
    from app.train_xgb import evaluate_xgb_holdout

    xgb = evaluate_xgb_holdout(candles, horizon, train_ratio=train_ratio, collect=True)
    lstm = train_lstm(scores, horizon=horizon, train_ratio=train_ratio, collect=True, **LSTM_CFG)
    return {
        "XGB": dict(zip(xgb["target_index"], xgb["pred"])),
        "LSTM": dict(zip(lstm["target_index"], lstm["pred"])),
    }


def _expanding_preds(candles, scores, horizon, train_ratio):
    from app.backtest_expanding import expanding_backtest_lstm, expanding_backtest_xgb

    xgb = expanding_backtest_xgb(candles, horizon, start_ratio=train_ratio, collect=True)["stitched"]
    lstm = expanding_backtest_lstm(scores, horizon, start_ratio=train_ratio, collect=True)["stitched"]
    return {
        "XGB": dict(zip(xgb["target_index"], xgb["pred"])),
        "LSTM": dict(zip(lstm["target_index"], lstm["pred"])),
    }


def ensemble_at(
    candles: list[dict],
    scores: np.ndarray,
    horizon: int,
    mode: str = "holdout",
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict | None:
    """horizon에서 세 모델 예측을 정렬·블렌드하고 개별/앙상블 skill 반환."""
    preds = (_expanding_preds if mode == "expanding" else _holdout_preds)(
        candles, scores, horizon, train_ratio
    )
    common = sorted(set.intersection(*[set(d) for d in preds.values()]))
    if len(common) < 5:
        return None

    actual = np.array([scores[i] for i in common], dtype=float)
    persist = np.array([scores[i - horizon] for i in common], dtype=float)
    persist_mae = float(np.mean(np.abs(persist - actual)))
    M = {name: np.array([preds[name][i] for i in common], dtype=float) for name in MODELS}

    def skill(p):
        mae = float(np.mean(np.abs(p - actual)))
        return (1.0 - mae / persist_mae) if persist_mae > 0 else None

    individual = {name: skill(M[name]) for name in MODELS}
    equal_pred = np.mean([M[name] for name in MODELS], axis=0)

    # skill 비례 가중치 (음수 skill은 0). 합이 0이면 equal로 폴백.
    w = {name: max(0.0, individual[name] or 0.0) for name in MODELS}
    wsum = sum(w.values())
    if wsum > 0:
        weighted_pred = sum(w[name] * M[name] for name in MODELS) / wsum
        weights = {name: round(w[name] / wsum, 3) for name in MODELS}
    else:
        weighted_pred = equal_pred
        weights = {name: round(1 / len(MODELS), 3) for name in MODELS}

    best_single = max((v for v in individual.values() if v is not None), default=None)
    return {
        "horizon": horizon,
        "mode": mode,
        "n_aligned": len(common),
        "persist_mae": round(persist_mae, 4),
        "individual": {k: (round(v, 4) if v is not None else None) for k, v in individual.items()},
        "best_single": round(best_single, 4) if best_single is not None else None,
        "equal": round(skill(equal_pred), 4),
        "weighted": round(skill(weighted_pred), 4),
        "weights": weights,
    }


def run_ensemble(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    horizons: tuple[int, ...] = HORIZONS,
    mode: str = "holdout",
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    rows = [r for r in (ensemble_at(candles, scores, h, mode, train_ratio)
                        for h in sorted(set(horizons))) if r is not None]
    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_scored": len(scores),
        "mode": mode,
        "results": rows,
        "disclaimer": DISCLAIMER,
    }


def format_report_md(report: dict) -> str:
    lines = [
        f"# 모델 앙상블 리포트 ({report['mode']})",
        "",
        f"- market: `{report['market']}`  ·  scored: {report['n_scored']}  ·  mode: {report['mode']}",
        "- 앙상블 = XGBoost + LSTM (KNN 제외)",
        "- equal = 단순평균(배포용) · weighted = skill 비례 가중(약간 낙관적)",
        "",
        "| horizon | " + " | ".join(MODELS) + " | best single | **equal** | **weighted** |",
        "|---:|" + "---:|" * len(MODELS) + "---:|---:|---:|",
    ]

    def f(v):
        return "-" if v is None else f"{v:+.3f}"

    for r in report["results"]:
        ind = r["individual"]
        cells = " | ".join(f(ind[m]) for m in MODELS)
        lines.append(
            f"| {r['horizon']}d | {cells} | "
            f"{f(r['best_single'])} | {f(r['equal'])} | {f(r['weighted'])} |"
        )
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def plot_ensemble(report: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = report["results"]
    hs = [r["horizon"] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for name in MODELS:
        ax.plot(hs, [r["individual"][name] for r in rows], color=COLOR_MAP[name], ls="--",
                marker="o", ms=4, alpha=0.6, label=name)
    ax.plot(hs, [r["equal"] for r in rows], color="black", marker="s", lw=2.4, label="ensemble (equal)")
    ax.plot(hs, [r["weighted"] for r in rows], color="#38761d", marker="^", lw=2.0,
            label="ensemble (weighted)")
    ax.axhline(0, color="black", lw=1)
    ax.text(hs[-1], 0, " persistence", va="bottom", ha="right", fontsize=8)
    ax.set_xticks(hs)
    ax.set_xlabel("horizon (days)")
    ax.set_ylabel("skill = 1 - MAE / persistence_MAE")
    ax.set_title(f"{report['market']}  model ensemble vs individuals ({report['mode']})\n"
                 "ensemble (solid) blends XGBoost + LSTM", fontsize=10)
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    try:
        import torch

        torch.set_num_threads(1)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="모델 앙상블 (KNN+XGBoost+LSTM)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--mode", choices=["holdout", "expanding"], default="holdout")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    report = run_ensemble(Path(args.csv), args.market, mode=args.mode)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.mode
    (out_dir / f"ensemble_report_{suffix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(report)
    (out_dir / f"ensemble_report_{suffix}.md").write_text(md + "\n", encoding="utf-8")
    plot_ensemble(report, out_dir / f"ensemble_skill_{suffix}.png")
    print(md)
    print(f"\n저장: {out_dir / f'ensemble_report_{suffix}.json'}\n      {out_dir / f'ensemble_skill_{suffix}.png'}")


if __name__ == "__main__":
    main()
