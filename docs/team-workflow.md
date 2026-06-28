# Team Workflow

## 현재 팀 논의 요약

- 프로젝트 방향: FOMO Break
- 핵심 문장: "당신이 지금 사려는 이유는 정말 정보 때문인가, 아니면 감정 때문인가?"
- MVP 기능: Emotion Score, Historical Mirror, Decision Pause
- 데이터: 업비트 공개 일봉 캔들 중심
- 보안: API Key/Secret Key 저장 금지
- 문구: 투자 추천이 아닌 시장 상태 관찰 도구로 표현

## GitHub 계정 메모

대화 내역 기준:

- caffeine-fighter
- Akebimdru
- cyanbackpack
- 한지후: TODO

## 작업 보드 추천

1. 기획/문서
   - 제품 한 줄 설명 정리
   - 발표 스토리 구성
   - 규정 문구 검토

2. 백엔드
   - Upbit candles/days 페이지네이션
   - X1~X8 점수 계산
   - `/api/fomo-score`, `/api/fomo-history`

3. 프론트엔드
   - 현재 점수 카드
   - 구성 요소 바 차트
   - 히스토리 차트
   - Decision Pause 질문
   - MVP 시연용 통합 API `/api/mvp-overview` 우선 연결

4. 데이터/실험
   - 유사 구간 기준 정의
   - 200일 히스토리 검증
   - 가중치 조정 후보 기록
   - KNN Mirror 피처/응답 계약은 `docs/knn-integration-contract.md` 기준으로 맞춤

## 오늘의 우선순위

1. 저장소 구조 정리
2. FOMO Score 산식 확정
3. 백엔드 API 최소 구현
4. 프론트엔드 첫 화면 구현
5. 발표용 시나리오 정리
