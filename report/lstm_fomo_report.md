# 가벼운 LSTM FOMO 학습 리포트

- market: `KRW-BTC`  ·  scored: 1835
- model: LSTM(hidden=32, 1-layer, window=20)  ·  입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_history.csv`

| horizon | train | val | LSTM val MAE | persist MAE | skill |
|---:|---:|---:|---:|---:|---:|
| 1d | 1270 | 545 | 4.4943 | 3.8074 | -0.180 |
| 7d | 1266 | 543 | 9.0668 | 9.8099 | +0.076 |
| 30d | 1250 | 536 | 10.3381 | 13.0654 | +0.209 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천을 제공하지 않습니다.
