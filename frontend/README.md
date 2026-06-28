# Frontend

FOMO Break MVP 웹 클라이언트입니다. 별도 빌드 없이 정적 HTML/CSS/JS로 실행합니다.

## 화면 구성

1. 현재 FOMO Score 카드
2. 구성 요소별 점수 바
3. 판단 준비도 패널
4. 시장 레이더: KRW-BTC, KRW-ETH, KRW-XRP 심리 상태 비교
5. 최근 FOMO Score 흐름 차트
6. Historical Mirror 과거 참고 구간
7. FOMO Score 흐름 참고와 오차 범위 밴드
8. Decision Pause 체크리스트와 질문
9. 면책 문구

## 실행

백엔드 하나만 실행해도 API와 화면을 함께 확인할 수 있습니다.

```powershell
cd C:\Coding\2026SKYSH\main\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8000
```

프론트엔드만 따로 띄우고 싶다면 다른 터미널에서 정적 서버를 실행합니다.

```powershell
cd C:\Coding\2026SKYSH\main\frontend
python -m http.server 5173
```

이 경우에도 프론트는 기본적으로 `http://127.0.0.1:8000` API를 호출합니다.

```text
http://127.0.0.1:5173
```

## MVP 차별화

이 UI는 점수만 크게 보여주는 대시보드가 아니라, `시장 레이더`, `오차 범위`, `과거 유사 구간`, `Decision Pause 체크리스트`를 한 화면에 묶어 사용자가 감정적 판단 전에 근거를 점검하도록 설계했습니다.

- 시장 레이더는 세 마켓의 심리 쏠림이 동조인지 분산인지 보여줍니다.
- 오차 범위 밴드는 FOMO Score 참고값을 방향으로 단정하지 않도록 돕습니다.
- Decision Pause 체크리스트는 사용자의 선택을 저장하지 않고 현재 화면의 판단 준비도에만 반영합니다.
