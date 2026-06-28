"""가벼운 LSTM 기반 FOMO Score 시계열 학습 (실험).

최근 W일 FOMO Score 시퀀스로 horizon 시점의 FOMO Score를 직접 예측하는 1-layer
LSTM. XGBoost/패턴매칭과 같은 타깃(시장 심리 상태값 FOMO Score)·같은 holdout
방식으로 비교한다. 가격·수익률 예측이 아니다(compliance).

가벼움/재현성:
- 1-layer LSTM, hidden=32, 단변량 입력(점수/100 스케일).
- time-based train/val 분할(셔플 없음) → look-ahead 없음.
- torch.manual_seed로 고정, CPU 단일 스레드 권장.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

from app.knn_pattern import (
    DEFAULT_CSV,
    DEFAULT_MARKET,
    DEFAULT_OUT,
    DEFAULT_TRAIN_RATIO,
    fomo_score_series,
    load_candles_from_csv,
)

SEED = 42
DEFAULT_WINDOW = 20
DEFAULT_HORIZONS = (1, 7, 30)
DEFAULT_HIDDEN = 32
DEFAULT_EPOCHS = 150
DEFAULT_LR = 0.01
SCALE = 100.0  # FOMO Score 0~100 → 0~1


class LSTMRegressor(nn.Module):
    def __init__(self, hidden: int = DEFAULT_HIDDEN):
        super().__init__()
        self.lstm = nn.LSTM(input_size=1, hidden_size=hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (B, W, 1)
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)  # (B,)


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
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
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

    Xs = X / SCALE
    ys = y / SCALE
    Xtr = torch.tensor(Xs[:split], dtype=torch.float32).unsqueeze(-1)
    ytr = torch.tensor(ys[:split], dtype=torch.float32)
    Xval = torch.tensor(Xs[split:], dtype=torch.float32).unsqueeze(-1)

    model = LSTMRegressor(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(model(Xtr), ytr)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        pred = model(Xval).numpy() * SCALE
    pred = np.clip(pred, 0.0, 100.0)

    actual = y[split:]
    current = scores[ends[split:]]  # persistence = 입력 시퀀스 마지막(현재) 값
    lstm_mae = float(np.mean(np.abs(pred - actual)))
    persist_mae = float(np.mean(np.abs(current - actual)))
    skill = 1.0 - lstm_mae / persist_mae if persist_mae > 0 else None

    return {
        "horizon": horizon,
        "window": window,
        "hidden": hidden,
        "epochs": epochs,
        "lr": lr,
        "train_samples": split,
        "val_samples": n - split,
        "val_mae": round(lstm_mae, 4),
        "persist_mae": round(persist_mae, 4),
        "skill": round(skill, 4) if skill is not None else None,
    }


def run_lstm(
    csv_path: Path = DEFAULT_CSV,
    market: str = DEFAULT_MARKET,
    window: int = DEFAULT_WINDOW,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    hidden: int = DEFAULT_HIDDEN,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> dict:
    candles = load_candles_from_csv(csv_path, market)
    scores, _ = fomo_score_series(candles)
    results = [
        train_lstm(scores, window=window, horizon=h, train_ratio=train_ratio,
                   hidden=hidden, epochs=epochs, lr=lr)
        for h in sorted(set(horizons))
    ]
    return {
        "market": market,
        "csv_path": str(csv_path),
        "n_scored": len(scores),
        "model": f"LSTM(hidden={hidden}, 1-layer, window={window})",
        "results": results,
        "disclaimer": (
            "학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. "
            "모델 성능 참고치일 뿐 투자 추천을 제공하지 않습니다."
        ),
    }


def format_report_md(report: dict) -> str:
    lines = [
        "# 가벼운 LSTM FOMO 학습 리포트",
        "",
        f"- market: `{report['market']}`  ·  scored: {report['n_scored']}",
        f"- model: {report['model']}  ·  입력: `{report['csv_path']}`",
        "",
        "| horizon | train | val | LSTM val MAE | persist MAE | skill |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in report["results"]:
        skill = "-" if r["skill"] is None else f"{r['skill']:+.3f}"
        lines.append(
            f"| {r['horizon']}d | {r['train_samples']} | {r['val_samples']} | "
            f"{r['val_mae']} | {r['persist_mae']} | {skill} |"
        )
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import argparse
    import json

    torch.set_num_threads(1)
    parser = argparse.ArgumentParser(description="가벼운 LSTM FOMO Score 학습 (CSV, 오프라인)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--hidden", type=int, default=DEFAULT_HIDDEN)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    report = run_lstm(Path(args.csv), args.market, window=args.window,
                      hidden=args.hidden, epochs=args.epochs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lstm_fomo_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = format_report_md(report)
    (out_dir / "lstm_fomo_report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\n저장: {out_dir / 'lstm_fomo_report.json'}\n      {out_dir / 'lstm_fomo_report.md'}")


if __name__ == "__main__":
    main()
