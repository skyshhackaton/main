# Contributing

## 기본 원칙

- 작은 단위로 브랜치를 나눕니다.
- PR은 기능, 문서, 실험 단위를 섞지 않습니다.
- 투자 추천처럼 읽히는 문구는 코드와 문서 모두에서 피합니다.
- 사용자 API Key, Secret Key, 개인정보를 저장하지 않습니다.

## 브랜치 이름

```text
feat/backend-fomo-score
feat/frontend-dashboard
feat/historical-mirror
docs/product-brief
fix/compliance-copy
```

## 커밋 메시지

```text
feat: add fomo score specification
fix: revise greedy grade wording
docs: add api design draft
chore: initialize backend structure
```

## PR 체크리스트

- [ ] 실행 방법이 README 또는 관련 문서에 반영되었나요?
- [ ] 공개 API만 사용하나요?
- [ ] 투자 권유/자문/수익 보장으로 읽힐 표현이 없나요?
- [ ] UI에 면책 문구가 노출되나요?
- [ ] 테스트 또는 수동 검증 결과가 적혀 있나요?

## 역할 분담 초안

- 기획/문서: 제품 메시지, 발표 스토리, 규정 문구
- 백엔드: Upbit 공개 API 수집, FOMO Score 계산, API 엔드포인트
- 프론트엔드: 점수 시각화, Historical Mirror, Decision Pause UI
- 데이터/실험: 유사 구간 기준, 백테스트, 가중치 검토
