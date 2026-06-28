"""모델별 학습 스크립트(train_knn / train_xgb / train_lstm)의 공통 유틸.

CSV 로드, FOMO Score 시계열, 지표, 경로 상수를 한 곳에 모아 모델 코드끼리
중복되지 않게 한다. 모든 학습 대상은 가격이 아니라 시장 심리 상태값(FOMO Score)이다.

MVP rule: 네트워크 호출 없음. 이미 공유된 CSV만 읽는다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from app.fomo_score import score_series

_REPO_ROOT = Path(__file__).parent.parent.parent
# ML 학습은 깊은 히스토리(history)를 우선 사용하고, 없으면 공유 snapshot으로 폴백.
_HISTORY_CSV = _REPO_ROOT / "data" / "upbit_candles_history.csv"
_SNAPSHOT_CSV = _REPO_ROOT / "data" / "upbit_candles_snapshot.csv"
DEFAULT_CSV = _HISTORY_CSV if _HISTORY_CSV.exists() else _SNAPSHOT_CSV
DEFAULT_OUT = _REPO_ROOT / "report"
DEFAULT_MARKET = "KRW-BTC"
DEFAULT_HORIZONS = (1, 3, 7)
DEFAULT_N_SPLITS = 5
DEFAULT_TRAIN_RATIO = 0.7

CSV_NUMERIC = ("open", "high", "low", "close", "volume")

DISCLAIMER = (
    "학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. "
    "모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다."
)


def load_candles_from_csv(csv_path: Path, market: str = DEFAULT_MARKET) -> list[dict]:
    """data-handoff CSV에서 한 마켓 캔들을 공통 인터페이스로 로드(oldest-first)."""
    rows: list[dict] = []
    with Path(csv_path).open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            if raw["market"] != market:
                continue
            rows.append(
                {"date_utc": raw["date_utc"], **{key: float(raw[key]) for key in CSV_NUMERIC}}
            )
    if not rows:
        raise ValueError(f"'{market}' 행이 {csv_path}에 없습니다.")
    rows.sort(key=lambda c: c["date_utc"])
    return rows


def fomo_scores(candles: list[dict], days: int | None = None) -> np.ndarray:
    """전체 구간 FOMO Score 배열 (oldest-first)."""
    days = days if days is not None else len(candles)
    series = score_series(candles, days=days)
    if not series:
        raise ValueError("not enough candles to build score series")
    return np.asarray([s["score"] for s in series], dtype=float)


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """(MAE, RMSE)."""
    err = np.asarray(y_pred) - np.asarray(y_true)
    return float(np.mean(np.abs(err))), float(np.sqrt(np.mean(err**2)))
