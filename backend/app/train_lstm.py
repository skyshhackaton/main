"""가벼운 LSTM FOMO Score 학습 + 하이퍼파라미터 튜닝 (실험).

아키텍처 (요청 사양, ~1.5k 데이터에 맞는 가벼운 크기):
- (선택) Input Dense(32) 투영  ->  LSTM(units=50, activation=tanh, return_sequences=False)
  ->  Dense(1)
- nn.LSTM의 기본 셀 활성은 tanh, 마지막 스텝 출력만 사용(return_sequences=False).

최근 W일 FOMO Score 시퀀스로 horizon 시점의 FOMO Score를 직접 예측한다. 대상은
가격이 아니라 시장 심리 상태값(FOMO Score)이다(compliance).

재현성: torch.manual_seed 고정. time-based train/val 분리(셔플 없음) → look-ahead 없음.
튜닝은 validation MAE로 설정을 고르므로 약간의 낙관 편향이 있을 수 있다(모델 간 비교는
동일 기준이라 공정).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

from app.train_common import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    DISCLAIMER,
    fomo_scores,
    load_candles_from_csv,
)

SEED = 42
DEFAULT_WINDOW = 20
DEFAULT_HORIZONS = (1, 7, 30)
DEFAULT_HIDDEN = 50
DEFAULT_INPUT_DENSE = 0  # 0 = direct scaling, >0 = Dense(input_dense) 투영
DEFAULT_DROPOUT = 0.0
DEFAULT_EPOCHS = 150
DEFAULT_LR = 0.01
SCALE = 100.0  # FOMO Score 0~100 → 0~1

# 하이퍼파라미터 격자 (학습이 느리므로 보수적으로).
LSTM_PARAM_GRID = {
    "hidden": [32, 50],
    "input_dense": [0, 32],
    "dropout": [0.0, 0.2],
    "lr": [0.01],
}


class LSTMRegressor(nn.Module):
    """(opt Dense -> ) LSTM(tanh, last step) -> Dense(1)."""

    def __init__(self, hidden: int = DEFAULT_HIDDEN, input_dense: int = DEFAULT_INPUT_DENSE,
                 dropout: float = DEFAULT_DROPOUT):
        super().__init__()
        in_size = 1
        self.proj = None
        if input_dense > 0:
            self.proj = nn.Linear(1, input_dense)
            in_size = input_dense
        self.lstm = nn.LSTM(input_size=in_size, hidden_size=hidden, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (B, W, 1)
        if self.proj is not None:
            x = torch.tanh(self.proj(x))
        out, _ = self.lstm(x)
        return self.head(self.drop(out[:, -1, :])).squeeze(-1)


def build_sequences(scores: np.ndarray, window: int, horizon: int):
    """(X, y, end_index). X[i]=scores[e-W+1..e], y[i]=scores[e+horizon]."""
    X, y, ends = [], [], []
    for e in range(window - 1, len(scores) - horizon):
        X.append(scores[e - window + 1 : e + 1])
        y.append(scores[e + horizon])
        ends.append(e)
    return np.asarray(X, dtype=float), np.asarray(y, dtype=float), np.asarray(ends)


def train_lstm(
    scores: np.ndarray,
    window: int = DEFAULT_WINDOW,
    horizon: int = 1,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    hidden: int = DEFAULT_HIDDEN,
    input_dense: int = DEFAULT_INPUT_DENSE,
    dropout: float = DEFAULT_DROPOUT,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    collect: bool = False,
) -> dict:
    """train/val 분리로 LSTM 학습 후 검증 MAE와 persistence baseline 비교."""
    if window < 2:
        raise ValueError("window must be >= 2")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be in (0, 1)")

    torch.manual_seed(SEED)
    np.random.seed(SEED)

    X, y, ends = build_sequences(scores, window, horizon)
    n = len(X)
    if n <= 10:
        raise ValueError("표본이 부족해 LSTM 학습을 할 수 없습니다.")
    split = int(n * train_ratio)
    if split < 5 or n - split < 1:
        raise ValueError("train/val 분할 표본이 부족합니다.")

    Xs, ys = X / SCALE, y / SCALE
    Xtr = torch.tensor(Xs[:split], dtype=torch.float32).unsqueeze(-1)
    ytr = torch.tensor(ys[:split], dtype=torch.float32)
    Xval = torch.tensor(Xs[split:], dtype=torch.float32).unsqueeze(-1)

    model = LSTMRegressor(hidden=hidden, input_dense=input_dense, dropout=dropout)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss_fn(model(Xtr), ytr).backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        pred = np.clip(model(Xval).numpy() * SCALE, 0.0, 100.0)

    actual = y[split:]
    current = scores[ends[split:]]  # persistence = 입력 시퀀스 마지막(현재) 값
    lstm_mae = float(np.mean(np.abs(pred - actual)))
    persist_mae = float(np.mean(np.abs(current - actual)))
    skill = 1.0 - lstm_mae / persist_mae if persist_mae > 0 else None
    n_params = sum(p.numel() for p in model.parameters())

    out = {
        "horizon": horizon,
        "window": window,
        "hidden": hidden,
        "input_dense": input_dense,
        "dropout": dropout,
        "epochs": epochs,
        "lr": lr,
        "n_params": int(n_params),
        "train_samples": split,
        "val_samples": n - split,
        "val_mae": round(lstm_mae, 4),
        "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }
    if collect:
        out["pred"] = [float(v) for v in pred]
        out["actual"] = [float(v) for v in actual]
    return out


def forecast_lstm(
    scores: np.ndarray,
    horizons: tuple[int, ...] = (1, 3, 7, 14, 30),
    window: int = DEFAULT_WINDOW,
    hidden: int = DEFAULT_HIDDEN,
    input_dense: int = 32,
    dropout: float = 0.1,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
) -> dict:
    """현재 시점에서 horizon별 FOMO Score 예측 (전체 시퀀스로 학습 후 최신 윈도 예측)."""
    latest = torch.tensor((scores[-window:] / SCALE), dtype=torch.float32).reshape(1, window, 1)
    points = []
    for h in sorted(set(horizons)):
        torch.manual_seed(SEED)
        np.random.seed(SEED)
        X, y, _ = build_sequences(scores, window, h)
        Xt = torch.tensor(X / SCALE, dtype=torch.float32).unsqueeze(-1)
        yt = torch.tensor(y / SCALE, dtype=torch.float32)
        model = LSTMRegressor(hidden=hidden, input_dense=input_dense, dropout=dropout)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()
        model.train()
        for _ in range(epochs):
            opt.zero_grad()
            loss_fn(model(Xt), yt).backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pred = float(np.clip(model(latest).item() * SCALE, 0.0, 100.0))
        points.append({"horizon": h, "predicted_score": round(pred, 2)})
    return {"current_score": round(float(scores[-1]), 2), "horizons": points}


def tune_lstm(
    scores: np.ndarray,
    horizon: int = 1,
    window: int = DEFAULT_WINDOW,
    param_grid: dict | None = None,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    epochs: int = DEFAULT_EPOCHS,
) -> dict:
    """하이퍼파라미터 격자를 validation MAE로 탐색해 최고 설정 선정."""
    grid = param_grid or LSTM_PARAM_GRID
    keys = list(grid)
    combos = [{}]
    for key in keys:
        combos = [{**c, key: v} for c in combos for v in grid[key]]

    results = []
    for combo in combos:
        res = train_lstm(scores, window=window, horizon=horizon, train_ratio=train_ratio,
                         epochs=epochs, **combo)
        results.append(res)
    results.sort(key=lambda r: r["val_mae"])
    best = results[0]
    return {
        "horizon": horizon,
        "window": window,
        "n_candidates": len(combos),
        "best": best,
        "results": results,
    }


def run_lstm(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    window: int = DEFAULT_WINDOW,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    epochs: int = DEFAULT_EPOCHS,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    tune: bool = True,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores = fomo_scores(candles)
    per_horizon = []
    for h in sorted(set(horizons)):
        if tune:
            t = tune_lstm(scores, horizon=h, window=window, train_ratio=train_ratio, epochs=epochs)
            entry = {"horizon": h, "n_candidates": t["n_candidates"], **t["best"]}
        else:
            entry = train_lstm(scores, window=window, horizon=h, train_ratio=train_ratio, epochs=epochs)
        per_horizon.append(entry)
    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_scored": len(scores),
        "model": "LSTM(50,tanh) + opt Input Dense + Dense(1)",
        "tuned": tune,
        "results": per_horizon,
        "disclaimer": DISCLAIMER,
    }


def format_report_md(report: dict) -> str:
    lines = [
        "# 가벼운 LSTM FOMO 학습 리포트",
        "",
        f"- market: `{report['market']}`  ·  scored: {report['n_scored']}",
        f"- model: {report['model']}  ·  tuned: {report['tuned']}  ·  입력: `{report['csv_path']}`",
        "",
        "| horizon | hidden | in_dense | dropout | params | val MAE | persist MAE | skill |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in report["results"]:
        skill = "-" if r["skill"] is None else f"{r['skill']:+.3f}"
        lines.append(
            f"| {r['horizon']}d | {r['hidden']} | {r['input_dense']} | {r['dropout']} | "
            f"{r['n_params']} | {r['val_mae']} | {r['persist_mae']} | {skill} |"
        )
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description="가벼운 LSTM FOMO Score 학습 + 튜닝 (CSV, 오프라인)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--no-tune", action="store_true", help="하이퍼파라미터 튜닝 생략")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    report = run_lstm(Path(args.csv), args.market, window=args.window,
                      epochs=args.epochs, tune=not args.no_tune)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lstm_training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(report)
    (out_dir / "lstm_training_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'lstm_training_report.json'}\n      {out_dir / 'lstm_training_report.md'}")


if __name__ == "__main__":
    main()
