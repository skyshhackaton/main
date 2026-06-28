# XGBoost FOMO 학습 리포트

- market: `KRW-BTC`  ·  candles: 2200 (scored: 1835)
- 입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_history.csv`

## 1. 고정 파라미터 학습 (XGBRegressor (per-horizon direct forecast))
lags=5 · TimeSeriesSplit(5)

| horizon | samples | CV MAE | CV RMSE | baseline(유지) MAE |
|---:|---:|---:|---:|---:|
| 1d | 1830 | 3.9711 | 4.9527 | 3.7706 |
| 3d | 1828 | 6.6573 | 8.4577 | 6.9794 |
| 7d | 1824 | 8.8007 | 11.2933 | 9.6897 |

## 2. 하이퍼파라미터 튜닝 (XGBRegressor (grid-tuned), 24 combos)
lags=5 · TimeSeriesSplit(5) · grid CV로 horizon별 최고 설정

| horizon | CV MAE | CV RMSE | baseline MAE | skill | best params |
|---:|---:|---:|---:|---:|---|
| 1d | 3.9122 | 4.8949 | 3.7706 | -0.037 | learning_rate=0.05, max_depth=2, n_estimators=400, subsample=0.8 |
| 3d | 6.5901 | 8.3861 | 6.9794 | +0.056 | learning_rate=0.05, max_depth=2, n_estimators=200, subsample=0.8 |
| 7d | 8.7559 | 11.1914 | 9.6897 | +0.096 | learning_rate=0.05, max_depth=2, n_estimators=200, subsample=0.8 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
