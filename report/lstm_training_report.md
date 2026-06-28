# 가벼운 LSTM FOMO 학습 리포트

- market: `KRW-BTC`  ·  scored: 1835
- model: LSTM(50,tanh) + opt Input Dense + Dense(1)  ·  tuned: True  ·  입력: `C:\Users\juwon\Desktop\skysh-2026-hackaton\data\upbit_candles_history.csv`

| horizon | hidden | in_dense | dropout | params | val MAE | persist MAE | skill |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1d | 50 | 32 | 0.0 | 16915 | 3.7365 | 3.8074 | +0.019 |
| 7d | 50 | 32 | 0.2 | 16915 | 8.7609 | 9.8099 | +0.107 |
| 30d | 50 | 0 | 0.2 | 10651 | 10.2267 | 13.0654 | +0.217 |

> 학습/예측 대상은 시장 심리 상태값(FOMO Score)이며 가격·수익률 예측이 아닙니다. 모델 성능 참고치일 뿐 투자 추천, 투자 자문, 수익 보장을 제공하지 않습니다.
