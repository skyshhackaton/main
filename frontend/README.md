# Frontend

FOMO Break MVP 웹 클라이언트입니다. 별도 빌드 없이 정적 HTML/CSS/JS로 실행합니다.

## 화면 구성

1. 현재 FOMO Score 카드
2. 구성 요소별 점수 바
3. 판단 준비도 패널
4. 최근 FOMO Score 흐름 차트
5. Historical Mirror 과거 참고 구간
6. FOMO Score 흐름 참고와 오차 범위
7. Decision Pause 질문
8. 면책 문구

## 실행

백엔드를 먼저 실행합니다.

```powershell
cd C:\Coding\2026SKYSH\main\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서 정적 서버를 실행합니다.

```powershell
cd C:\Coding\2026SKYSH\main\frontend
python -m http.server 5173
```

브라우저에서 엽니다.

```text
http://127.0.0.1:5173
```

## MVP 차별화

이 UI는 점수만 크게 보여주는 대시보드가 아니라, `오차 범위`, `과거 유사 구간`, `Decision Pause`를 한 화면에 묶어 사용자가 감정적 판단 전에 근거를 점검하도록 설계했습니다.
