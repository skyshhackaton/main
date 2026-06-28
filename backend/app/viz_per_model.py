"""모델별 3-패널 시각화: forecast | validation | skill.

각 모델(KNN 패턴 / XGBoost / LSTM)마다 한 장(3패널)을 그린다.
- forecast   : 현재 시점 기준 horizon별 FOMO Score 예측 (KNN은 시나리오 밴드).
- validation : holdout 예측 vs 실제 산점도 (+ skill).
- skill      : horizon별 holdout skill (persistence 대비, 0보다 크면 우위).

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from app.knn_pattern import build_fomo_pattern_forecast, validate_holdout  # noqa: E402
from app.train_common import (  # noqa: E402
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    fomo_scores,
    load_candles_from_csv,
)
from app.train_xgb import evaluate_xgb_holdout, forecast_xgb  # noqa: E402
from app.viz_pattern import DISCLAIMER_EN, GRADE_ZONES  # noqa: E402

HORIZONS = (1, 3, 7, 14, 30)
VAL_HORIZON = 7
LOOKBACK = 20
# 모델별 색
COLORS = {"KNN pattern": "#1155cc", "XGBoost": "#e69138", "LSTM": "#cc0000"}
# viz용 고정 LSTM 설정 (튜닝은 train_lstm.py에서, 여기선 일관 표시)
LSTM_CFG = dict(window=20, hidden=50, input_dense=32, dropout=0.1, epochs=120)


def _forecast_panel(ax, recent, current, forecast, color):
    for lo, hi, c, _ in GRADE_ZONES:
        ax.axhspan(lo, hi, color=c, alpha=0.06)
    x_hist = list(range(-(len(recent) - 1), 1))
    ax.plot(x_hist, recent, color="black", lw=1.6, marker="o", ms=2, label="recent FOMO")
    ax.axvline(0, color="black", ls="--", lw=1, alpha=0.5)

    if forecast["kind"] == "band":
        xf = forecast["x"]
        ax.fill_between(xf, forecast["p10"], forecast["p90"], color=color, alpha=0.18,
                        label="p10-p90")
        ax.plot(xf, forecast["mean"], color=color, lw=2.2, marker="o", ms=2, label="mean scenario")
    else:
        xs = [0] + [p["horizon"] for p in forecast["points"]]
        ys = [current] + [p["predicted_score"] for p in forecast["points"]]
        ax.plot(xs, ys, color=color, lw=2.2, marker="o", ms=4, label="forecast")
    ax.scatter([0], [current], color="black", zorder=5)
    ax.set_ylim(0, 100)
    ax.set_xlabel("days from now")
    ax.set_ylabel("FOMO Score")
    ax.set_title("forecast", fontsize=10)
    ax.legend(fontsize=7, loc="upper left")


def _validation_panel(ax, pred, actual, horizon, skill, color):
    ax.scatter(actual, pred, s=8, alpha=0.35, color=color)
    ax.plot([0, 100], [0, 100], color="black", lw=1, ls="--")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel(f"actual FOMO at +{horizon}d")
    ax.set_ylabel(f"predicted FOMO at +{horizon}d")
    skill_txt = "n/a" if skill is None else f"{skill:+.3f}"
    ax.set_title(f"validation (+{horizon}d, skill {skill_txt})", fontsize=10)


def _skill_panel(ax, horizons, skills, color):
    ys = [s if s is not None else np.nan for s in skills]
    ax.plot(horizons, ys, color=color, marker="o", lw=2)
    ax.axhline(0, color="black", lw=1)
    ax.text(horizons[-1], 0, " persistence", va="bottom", ha="right", fontsize=7)
    ax.set_xticks(horizons)
    ax.set_xlabel("horizon (days)")
    ax.set_ylabel("holdout skill")
    ax.set_title("skill vs persistence", fontsize=10)
    ax.grid(alpha=0.3)


def _figure(model_name, recent, current, forecast, validation, skill, market, path):
    color = COLORS[model_name]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    _forecast_panel(axes[0], recent, current, forecast, color)
    _validation_panel(axes[1], validation["pred"], validation["actual"],
                      validation["horizon"], validation["skill"], color)
    _skill_panel(axes[2], skill["horizons"], skill["skills"], color)
    fig.suptitle(f"{market}  —  {model_name}  (forecast · validation · skill)", fontsize=12)
    fig.text(0.5, 0.005, DISCLAIMER_EN, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _knn_views(candles, scores, train_ratio):
    fc = build_fomo_pattern_forecast(candles, window=10, horizon=30, k=10, metric="raw")
    forecast = {"kind": "band", "x": fc["band"]["steps"], "mean": fc["band"]["mean"],
                "p10": fc["band"]["p10"], "p90": fc["band"]["p90"]}
    detail = validate_holdout(scores, 10, VAL_HORIZON, 10, "raw", train_ratio, collect=True)
    validation = {"pred": detail["scatter"]["pred_h"], "actual": detail["scatter"]["actual_h"],
                  "horizon": VAL_HORIZON, "skill": detail["skill"]}
    skills = [validate_holdout(scores, 10, h, 10, "raw", train_ratio)["skill"] for h in HORIZONS]
    return forecast, validation, {"horizons": list(HORIZONS), "skills": skills}


def _xgb_views(candles, train_ratio):
    fc = forecast_xgb(candles, horizons=HORIZONS)
    forecast = {"kind": "points", "points": fc["horizons"]}
    val = evaluate_xgb_holdout(candles, VAL_HORIZON, train_ratio=train_ratio, collect=True)
    validation = {"pred": val["pred"], "actual": val["actual"], "horizon": VAL_HORIZON,
                  "skill": val["skill"]}
    skills = [evaluate_xgb_holdout(candles, h, train_ratio=train_ratio)["skill"] for h in HORIZONS]
    return forecast, validation, {"horizons": list(HORIZONS), "skills": skills}


def _lstm_views(scores, train_ratio):
    try:
        from app.train_lstm import forecast_lstm, train_lstm
    except ImportError as exc:  # pragma: no cover - exercised in torch-free envs
        raise RuntimeError(
            "LSTM visualization requires optional dependency torch. "
            "Install torch to render LSTM charts."
        ) from exc

    fc = forecast_lstm(scores, horizons=HORIZONS, **LSTM_CFG)
    forecast = {"kind": "points", "points": fc["horizons"]}
    cfg = {k: v for k, v in LSTM_CFG.items() if k != "epochs"}
    val = train_lstm(scores, horizon=VAL_HORIZON, train_ratio=train_ratio,
                     epochs=LSTM_CFG["epochs"], collect=True, **cfg)
    validation = {"pred": val["pred"], "actual": val["actual"], "horizon": VAL_HORIZON,
                  "skill": val["skill"]}
    skills = [train_lstm(scores, horizon=h, train_ratio=train_ratio,
                         epochs=LSTM_CFG["epochs"], **cfg)["skill"] for h in HORIZONS]
    return forecast, validation, {"horizons": list(HORIZONS), "skills": skills}


def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    recent = scores[-LOOKBACK:]
    current = float(scores[-1])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {}
    for name, builder in (
        ("KNN pattern", lambda: _knn_views(candles, scores, train_ratio)),
        ("XGBoost", lambda: _xgb_views(candles, train_ratio)),
        ("LSTM", lambda: _lstm_views(scores, train_ratio)),
    ):
        forecast, validation, skill = builder()
        slug = name.split()[0].lower()
        path = out_dir / f"model_{slug}.png"
        _figure(name, recent, current, forecast, validation, skill, market, path)
        paths[name] = path
    return paths


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="모델별 forecast/validation/skill 3-패널 차트")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    try:
        import torch
    except ImportError as exc:
        raise SystemExit("torch가 필요합니다. LSTM 차트를 렌더링하려면 torch를 설치하세요.") from exc

    torch.set_num_threads(1)
    paths = generate(Path(args.csv), args.market, Path(args.out))
    for name, path in paths.items():
        print(f"{name:12s} -> {path}")


if __name__ == "__main__":
    main()
