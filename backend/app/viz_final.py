"""최종 발표용 그래프 7장 생성 (각 단일 패널).

framing:
- KNN = '과거 패턴 기반' (최근 패턴과 닮은 과거 사례로 시나리오 제시)
- XGBoost / LSTM = '과거 데이터 기반' (과거 데이터로 학습해 예측)

생성물(report/):
  1. knn_forecast.png            - KNN 향후 시나리오 밴드
  2. xgb_stitched_holdout.png    - XGBoost holdout 이어붙인 예측 vs 실제
  3. lstm_stitched_holdout.png   - LSTM    holdout
  4. xgb_stitched_expanding.png  - XGBoost expanding(운영)
  5. lstm_stitched_expanding.png - LSTM    expanding(운영)
  6. ensemble_stitched_holdout.png   - XGBoost+LSTM 앙상블 이어붙인 예측 (holdout)
  7. ensemble_stitched_expanding.png - XGBoost+LSTM 앙상블 이어붙인 예측 (expanding)

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from app.knn_pattern import build_fomo_pattern_forecast  # noqa: E402
from app.train_common import (  # noqa: E402
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    fomo_scores,
    load_candles_from_csv,
)
from app.viz_pattern import GRADE_ZONES  # noqa: E402

PATTERN_LABEL = "과거 패턴 기반"
DATA_LABEL = "과거 데이터 기반"
COLOR = {"KNN": "#1155cc", "XGB": "#e69138", "LSTM": "#cc0000", "ENS": "#2e7d32"}
LSTM_CFG = dict(window=20, hidden=50, input_dense=32, dropout=0.1, epochs=120)
DISCLAIMER_KO = "FOMO Score(시장 심리 상태값) 기준이며 가격·수익률 예측이 아닙니다. 관찰 참고용."

# 개별 모델은 best-skill horizon (expanding 백테스트 기준), 앙상블은 14d 고정.
# (XGB·LSTM 둘 다 14d 부근에서 skill 최고, KNN은 중·장기 skill 낮아 앙상블 제외)
BEST = {"xgb_holdout": 14, "lstm_holdout": 30, "xgb_expanding": 14, "lstm_expanding": 30}
ENS_HORIZON = 14


def _set_korean_font():
    for name in ("Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.family"] = name
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False


def _best_horizon(comparison: list[dict], key: str) -> int:
    valid = [r for r in comparison if r.get(key) is not None]
    return max(valid, key=lambda r: r[key])["horizon"]


# ---------------------------------------------------------------------------
# 패널들
# ---------------------------------------------------------------------------

def _knn_forecast(candles, scores, market, path):
    fc = build_fomo_pattern_forecast(candles, window=10, horizon=30, k=10, metric="raw")
    h = fc["horizon"]
    recent = scores[-20:]
    x_hist = list(range(-(len(recent) - 1), 1))
    x_fut = fc["band"]["steps"]

    _set_korean_font()
    fig, ax = plt.subplots(figsize=(10, 5))
    for lo, hi, c, _ in GRADE_ZONES:
        ax.axhspan(lo, hi, color=c, alpha=0.07)
    ax.fill_between(x_fut, fc["band"]["p10"], fc["band"]["p90"], color=COLOR["KNN"],
                    alpha=0.18, label="p10~p90 범위")
    ax.plot(x_fut, fc["band"]["mean"], color=COLOR["KNN"], lw=2.4, marker="o", ms=3,
            label="평균 시나리오")
    ax.plot(x_hist, recent, color="black", lw=2, marker="o", ms=3, label="최근 FOMO")
    ax.axvline(0, color="black", ls="--", lw=1, alpha=0.6)
    ax.scatter([0], [fc["current_score"]], color="black", zorder=5)
    ax.set_ylim(0, 100)
    ax.set_xlabel("현재 기준 경과일")
    ax.set_ylabel("FOMO Score")
    ax.set_title(f"{market} · {PATTERN_LABEL} (KNN) — 향후 {h}일 예측 시나리오\n"
                 f"현재 {fc['current_score']} → {h}일 평균 {fc['band']['mean'][-1]}", fontsize=12)
    ax.legend(fontsize=9, loc="upper left")
    fig.text(0.5, 0.005, DISCLAIMER_KO, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _stitched(label, color, scores, stitched, horizon, skill, mode_label, market, path):
    """공통 stitched 타임라인: 실제 FOMO(회색) + 이어붙인 +h일 예측(색)."""
    _set_korean_font()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for lo, hi, c, _ in GRADE_ZONES:
        ax.axhspan(lo, hi, color=c, alpha=0.06)
    ax.plot(np.arange(len(scores)), scores, color="black", lw=1.0, alpha=0.45, label="실제 FOMO")
    ti = stitched["target_index"]
    ax.plot(ti, stitched["pred"], color=color, lw=1.5, label=f"+{horizon}일 예측(이어붙임)")
    if ti:
        ax.axvline(min(ti), color="gray", ls="--", lw=1, alpha=0.7)
        ax.text(min(ti), 3, " 검증구간", fontsize=8, color="gray", ha="left")
    ax.set_ylim(0, 100)
    ax.set_xlabel("일 인덱스 (scored)")
    ax.set_ylabel("FOMO Score")
    ax.set_title(f"{market} · {DATA_LABEL} ({label}) — {mode_label} +{horizon}일 예측 vs 실제 "
                 f"(skill {skill:+.3f})", fontsize=12)
    ax.legend(fontsize=9, loc="upper left")
    fig.text(0.5, 0.005, DISCLAIMER_KO, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _blend(tix_x, px, tix_l, pl, scores, horizon):
    """XGB·LSTM 예측을 target 시점으로 정렬·평균 → 앙상블 stitched + skill."""
    dx, dl = dict(zip(tix_x, px)), dict(zip(tix_l, pl))
    common = sorted(set(dx) & set(dl))
    pred = np.array([(dx[i] + dl[i]) / 2 for i in common])
    actual = np.array([scores[i] for i in common], dtype=float)
    persist = np.array([scores[i - horizon] for i in common], dtype=float)
    pmae = float(np.mean(np.abs(persist - actual)))
    skill = 1.0 - float(np.mean(np.abs(pred - actual))) / pmae if pmae > 0 else 0.0
    return {"target_index": common, "pred": [float(v) for v in pred]}, skill


# ---------------------------------------------------------------------------
# 통합 생성
# ---------------------------------------------------------------------------

def generate(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    out_dir: Path = DEFAULT_OUT,
) -> dict:
    from app.backtest_expanding import expanding_backtest_lstm, expanding_backtest_xgb
    from app.train_lstm import train_lstm
    from app.train_xgb import evaluate_xgb_holdout

    out_dir = Path(out_dir)
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # 1. KNN 향후 시나리오 (과거 패턴 기반)
    paths["knn"] = out_dir / "knn_forecast.png"
    _knn_forecast(candles, scores, market, paths["knn"])

    # --- holdout ---
    # XGB@14: 개별 그래프 + 앙상블(14d)에서 공용 재사용
    dxh = evaluate_xgb_holdout(candles, BEST["xgb_holdout"], train_ratio=0.7, collect=True)
    _stitched("XGB", COLOR["XGB"], scores, {"target_index": dxh["target_index"], "pred": dxh["pred"]},
              BEST["xgb_holdout"], dxh["skill"], "holdout(1회 학습)", market,
              out_dir / "xgb_stitched_holdout.png")
    paths["xgb_hold"] = out_dir / "xgb_stitched_holdout.png"

    dlh = train_lstm(scores, horizon=BEST["lstm_holdout"], train_ratio=0.7, collect=True, **LSTM_CFG)
    _stitched("LSTM", COLOR["LSTM"], scores, {"target_index": dlh["target_index"], "pred": dlh["pred"]},
              BEST["lstm_holdout"], dlh["skill"], "holdout(1회 학습)", market,
              out_dir / "lstm_stitched_holdout.png")
    paths["lstm_hold"] = out_dir / "lstm_stitched_holdout.png"

    # 앙상블 holdout @14 = XGB@14(재사용) + LSTM@14 단순평균
    dle = train_lstm(scores, horizon=ENS_HORIZON, train_ratio=0.7, collect=True, **LSTM_CFG)
    st, sk = _blend(dxh["target_index"], dxh["pred"], dle["target_index"], dle["pred"], scores, ENS_HORIZON)
    _stitched("앙상블 XGBoost+LSTM", COLOR["ENS"], scores, st, ENS_HORIZON, sk, "holdout(1회 학습)",
              market, out_dir / "ensemble_stitched_holdout.png")
    paths["ens_hold"] = out_dir / "ensemble_stitched_holdout.png"

    # --- expanding (운영 백테스트) ---
    # XGB@14: 개별 그래프 + 앙상블(14d)에서 공용 재사용
    rxe = expanding_backtest_xgb(candles, BEST["xgb_expanding"], collect=True)
    _stitched("XGB", COLOR["XGB"], scores, rxe["stitched"], BEST["xgb_expanding"], rxe["skill"],
              "expanding(운영)", market, out_dir / "xgb_stitched_expanding.png")
    paths["xgb_exp"] = out_dir / "xgb_stitched_expanding.png"

    rle = expanding_backtest_lstm(scores, BEST["lstm_expanding"], collect=True)
    _stitched("LSTM", COLOR["LSTM"], scores, rle["stitched"], BEST["lstm_expanding"], rle["skill"],
              "expanding(운영)", market, out_dir / "lstm_stitched_expanding.png")
    paths["lstm_exp"] = out_dir / "lstm_stitched_expanding.png"

    # 앙상블 expanding @14 = XGB@14(재사용) + LSTM@14 단순평균
    rle14 = expanding_backtest_lstm(scores, ENS_HORIZON, collect=True)["stitched"]
    st, sk = _blend(rxe["stitched"]["target_index"], rxe["stitched"]["pred"],
                    rle14["target_index"], rle14["pred"], scores, ENS_HORIZON)
    _stitched("앙상블 XGBoost+LSTM", COLOR["ENS"], scores, st, ENS_HORIZON, sk, "expanding(운영)",
              market, out_dir / "ensemble_stitched_expanding.png")
    paths["ens_exp"] = out_dir / "ensemble_stitched_expanding.png"

    return paths


def main(argv: list[str] | None = None) -> None:
    import argparse

    try:
        import torch

        torch.set_num_threads(1)
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="최종 발표용 그래프 7장 생성")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    paths = generate(Path(args.csv), args.market, Path(args.out))
    for key, path in paths.items():
        print(f"{key:10s} -> {path}")


if __name__ == "__main__":
    main()
