# KNN k 최적화 & XGBoost FOMO 학습 리포트

- market: `KRW-BTC`
- candles: 2200 (scored: 1835)
- 입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_history.csv`

## 1. KNN k 최적화 (horizon=1d, FOMO Score 예측)
피처: fomo_score, change_rate_1d, volume_ratio_5_20, rsi_14 · StandardScaler · TimeSeriesSplit(5)
표본: 1834 · **최적 k = 11** (CV MAE=4.424)

| k | CV MAE | CV RMSE |
|---:|---:|---:|
| 3 | 4.7037 | 5.9353 |
| 5 | 4.512 | 5.7095 |
| 7 | 4.4591 | 5.6078 |
| 9 | 4.4281 | 5.5738 |
| 11 (best) | 4.424 | 5.5751 |
| 13 | 4.4272 | 5.5788 |
| 15 | 4.4587 | 5.6036 |
| 17 | 4.4696 | 5.6157 |
| 19 | 4.5028 | 5.6529 |

## 2. XGBoost FOMO 학습 (XGBRegressor (per-horizon direct forecast))
lags=5 · TimeSeriesSplit(5)

| horizon | samples | CV MAE | CV RMSE | baseline(유지) MAE |
|---:|---:|---:|---:|---:|
| 1d | 1830 | 3.9711 | 4.9527 | 3.7706 |
| 3d | 1828 | 6.6573 | 8.4577 | 6.9794 |
| 7d | 1824 | 8.8007 | 11.2933 | 9.6897 |

## 3. XGBoost 하이퍼파라미터 튜닝 (XGBRegressor (grid-tuned), 24 combos)
lags=5 · TimeSeriesSplit(5) · grid CV로 horizon별 최고 설정

| horizon | CV MAE | CV RMSE | baseline MAE | skill | best params |
|---:|---:|---:|---:|---:|---|
| 1d | 3.9122 | 4.8949 | 3.7706 | -0.037 | learning_rate=0.05, max_depth=2, n_estimators=400, subsample=0.8 |
| 3d | 6.5901 | 8.3861 | 6.9794 | +0.056 | learning_rate=0.05, max_depth=2, n_estimators=200, subsample=0.8 |
| 7d | 8.7559 | 11.1914 | 9.6897 | +0.096 | learning_rate=0.05, max_depth=2, n_estimators=200, subsample=0.8 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
