"""Expanding-window walk-forward backtest (진짜 운영 backtest).

holdout(1회 학습)보다 엄격/현실적인 평가. 매 검증 원점에서 **그 시점까지 결과가
실현된 데이터로만** 모델을 (재)학습하고 horizon-step 예측을 한다.

핵심 규율 (no look-ahead, 경계 겹침 제거):
- 원점 시점 t에 "서서" 예측한다. 학습에 쓰는 샘플은 타깃까지 이미 관측된 것만:
  feature 시점 j 의 타깃 시점 = j + horizon ≤ t  →  j ≤ t - horizon.
- 그 뒤 시점 t 의 피처로 t+horizon 의 FOMO Score를 예측, 실제와 비교.
- persistence baseline = "horizon 뒤도 현재값(t)과 같다".

비용 제어: 매 스텝 재학습은 비싸므로 `retrain_every` 주기로 재학습하고 사이에는
직전 모델을 재사용한다(KNN은 학습이 없어 항상 최신 풀 사용).

대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.knn_pattern import _prep_matrix
from app.fomo_score import clamp
from app.train_common import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    DISCLAIMER,
    fomo_scores,
    load_candles_from_csv,
)
from app.train_xgb import _xgb_supervised

try:
    from xgboost import XGBRegressor

    _HAS_XGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor  # type: ignore

    _HAS_XGB = False

from app.forecast_score import RANDOM_STATE, _new_model

DEFAULT_START_RATIO = 0.7


def _skill(pred: list[float], actual: list[float], persist: list[float]) -> dict:
    if not pred:
        return {"origins": 0, "mae": None, "persist_mae": None, "skill": None}
    pred, actual, persist = np.asarray(pred), np.asarray(actual), np.asarray(persist)
    mae = float(np.mean(np.abs(pred - actual)))
    persist_mae = float(np.mean(np.abs(persist - actual)))
    skill = 1.0 - mae / persist_mae if persist_mae > 0 else None
    return {
        "origins": len(pred),
        "mae": round(mae, 4),
        "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }


# ---------------------------------------------------------------------------
# XGBoost
# ---------------------------------------------------------------------------

def expanding_backtest_xgb(
    candles: list[dict],
    horizon: int,
    lags: int = 5,
    params: dict | None = None,
    start_ratio: float = DEFAULT_START_RATIO,
    step: int = 1,
    retrain_every: int = 10,
    days: int | None = None,
    collect: bool = False,
) -> dict:
    """매 원점에서 실현 데이터로 재학습(주기) 후 horizon 예측."""
    X, y, _ = _xgb_supervised(candles, lags, horizon, days)
    n = len(X)
    start = max(int(n * start_ratio), 5 + horizon)
    preds, actuals, persist, tgt = [], [], [], []

    model, last_fit = None, None
    for k in range(start, n, step):
        train_hi = k - horizon  # 타깃이 실현된 마지막 샘플 인덱스
        if train_hi < 5:
            continue
        if model is None or last_fit is None or (k - last_fit) >= retrain_every:
            model = _new_model() if params is None else XGBRegressor(random_state=RANDOM_STATE, **params)
            model.fit(X[: train_hi + 1], y[: train_hi + 1])
            last_fit = k
        pred = float(np.clip(model.predict(X[k : k + 1])[0], 0.0, 100.0))
        preds.append(pred)
        actuals.append(float(y[k]))
        persist.append(float(X[k, lags - 1]))
        tgt.append((lags - 1) + k + horizon)

    out = {"model": "XGBoost", "horizon": horizon, "retrain_every": retrain_every, **_skill(preds, actuals, persist)}
    if collect:
        out["stitched"] = {"target_index": tgt, "pred": preds, "actual": actuals}
    return out


# ---------------------------------------------------------------------------
# KNN 패턴 (학습 없음 — 풀이 매 스텝 확장)
# ---------------------------------------------------------------------------

def expanding_backtest_knn(
    scores: np.ndarray,
    horizon: int,
    window: int = 10,
    k: int = 10,
    metric: str = "raw",
    start_ratio: float = DEFAULT_START_RATIO,
    step: int = 1,
    collect: bool = False,
) -> dict:
    """매 원점 t에서 풀 = e+horizon ≤ t 인 과거 패턴(확장)으로 예측."""
    n = len(scores)
    mat = _prep_matrix(scores, window, metric)
    start = max(int(n * start_ratio), window - 1 + horizon)
    preds, actuals, persist, tgt = [], [], [], []

    for t in range(start, n - horizon, step):
        pool_max_r = (t - horizon) - (window - 1)
        if pool_max_r < k - 1:
            continue
        q = mat[t - (window - 1)]
        pool = mat[: pool_max_r + 1]
        order = np.argsort(np.sqrt(((pool - q) ** 2).sum(axis=1)))[:k]
        current = float(scores[t])
        ends = [(current + (float(scores[int(r) + (window - 1) + horizon])
                            - float(scores[int(r) + (window - 1)]))) for r in order]
        preds.append(clamp(float(np.mean(ends))))
        actuals.append(float(scores[t + horizon]))
        persist.append(current)
        tgt.append(t + horizon)

    out = {"model": "KNN pattern", "horizon": horizon, "retrain_every": None, **_skill(preds, actuals, persist)}
    if collect:
        out["stitched"] = {"target_index": tgt, "pred": preds, "actual": actuals}
    return out


# ---------------------------------------------------------------------------
# LSTM (주기 재학습)
# ---------------------------------------------------------------------------

def expanding_backtest_lstm(
    scores: np.ndarray,
    horizon: int,
    window: int = 20,
    hidden: int = 50,
    input_dense: int = 32,
    dropout: float = 0.1,
    epochs: int = 120,
    lr: float = 0.01,
    start_ratio: float = DEFAULT_START_RATIO,
    step: int = 1,
    retrain_every: int = 25,
    collect: bool = False,
) -> dict:
    """매 원점에서 실현 시퀀스로 재학습(주기) 후 horizon 예측."""
    import torch
    from torch import nn

    from app.train_lstm import SCALE, LSTMRegressor, build_sequences

    X, y, ends = build_sequences(scores, window, horizon)
    n = len(X)
    start = max(int(n * start_ratio), 10 + horizon)
    Xs = (X / SCALE).astype("float32")
    ys = (y / SCALE).astype("float32")

    preds, actuals, persist, tgt = [], [], [], []
    model, last_fit = None, None
    for k in range(start, n, step):
        train_hi = k - horizon
        if train_hi < 10:
            continue
        if model is None or last_fit is None or (k - last_fit) >= retrain_every:
            torch.manual_seed(RANDOM_STATE)
            np.random.seed(RANDOM_STATE)
            model = LSTMRegressor(hidden=hidden, input_dense=input_dense, dropout=dropout)
            opt = torch.optim.Adam(model.parameters(), lr=lr)
            loss_fn = nn.MSELoss()
            Xt = torch.tensor(Xs[: train_hi + 1]).unsqueeze(-1)
            yt = torch.tensor(ys[: train_hi + 1])
            model.train()
            for _ in range(epochs):
                opt.zero_grad()
                loss_fn(model(Xt), yt).backward()
                opt.step()
            model.eval()
            last_fit = k
        with torch.no_grad():
            xk = torch.tensor(Xs[k]).reshape(1, window, 1)
            pred = float(np.clip(model(xk).item() * SCALE, 0.0, 100.0))
        preds.append(pred)
        actuals.append(float(y[k]))
        persist.append(float(scores[int(ends[k])]))
        tgt.append(int(ends[k]) + horizon)

    out = {"model": "LSTM", "horizon": horizon, "retrain_every": retrain_every, **_skill(preds, actuals, persist)}
    if collect:
        out["stitched"] = {"target_index": tgt, "pred": preds, "actual": actuals}
    return out


# ---------------------------------------------------------------------------
# 통합 실행: holdout vs expanding 비교 리포트
# ---------------------------------------------------------------------------

def run_expanding(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    horizons: tuple[int, ...] = (1, 3, 7, 14, 30),
    start_ratio: float = DEFAULT_START_RATIO,
    include_lstm: bool = True,
) -> dict:
    """holdout(1회 학습) vs expanding(매 스텝 재학습) skill 비교."""
    from app.knn_pattern import validate_holdout
    from app.train_xgb import evaluate_xgb_holdout

    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)

    rows = []
    for h in sorted(set(horizons)):
        knn_hold = validate_holdout(scores, 10, h, 10, "raw", start_ratio)["skill"]
        knn_exp = expanding_backtest_knn(scores, h, start_ratio=start_ratio)["skill"]
        xgb_hold = evaluate_xgb_holdout(candles, h, train_ratio=start_ratio)["skill"]
        xgb_exp = expanding_backtest_xgb(candles, h, start_ratio=start_ratio)["skill"]
        row = {"horizon": h, "knn_holdout": knn_hold, "knn_expanding": knn_exp,
               "xgb_holdout": xgb_hold, "xgb_expanding": xgb_exp}
        if include_lstm:
            from app.train_lstm import train_lstm
            row["lstm_holdout"] = train_lstm(scores, horizon=h, train_ratio=start_ratio,
                                             window=20, hidden=50, input_dense=32,
                                             dropout=0.1, epochs=120)["skill"]
            row["lstm_expanding"] = expanding_backtest_lstm(scores, h, start_ratio=start_ratio)["skill"]
        rows.append(row)

    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_scored": len(scores),
        "start_ratio": start_ratio,
        "comparison": rows,
        "disclaimer": DISCLAIMER,
    }


def format_report_md(report: dict) -> str:
    has_lstm = "lstm_holdout" in report["comparison"][0]
    lines = [
        "# Expanding-window backtest vs holdout",
        "",
        f"- market: `{report['market']}`  ·  scored: {report['n_scored']}  ·  start_ratio: {report['start_ratio']}",
        "- holdout = 앞 70% 1회 학습 / expanding = 매 스텝 실현 데이터로 재학습(진짜 운영 backtest)",
        "",
        "| horizon | KNN hold | KNN exp | XGB hold | XGB exp"
        + (" | LSTM hold | LSTM exp |" if has_lstm else " |"),
        "|---:|---:|---:|---:|---:" + ("|---:|---:|" if has_lstm else "|"),
    ]

    def f(v):
        return "-" if v is None else f"{v:+.3f}"

    for r in report["comparison"]:
        line = (f"| {r['horizon']}d | {f(r['knn_holdout'])} | {f(r['knn_expanding'])} | "
                f"{f(r['xgb_holdout'])} | {f(r['xgb_expanding'])}")
        if has_lstm:
            line += f" | {f(r['lstm_holdout'])} | {f(r['lstm_expanding'])} |"
        else:
            line += " |"
        lines.append(line)
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Expanding-window backtest vs holdout (CSV)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--no-lstm", action="store_true", help="LSTM expanding 생략(빠름)")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    report = run_expanding(Path(args.csv), args.market, include_lstm=not args.no_lstm)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "expanding_backtest_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(report)
    (out_dir / "expanding_backtest_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'expanding_backtest_report.json'}")


if __name__ == "__main__":
    main()
