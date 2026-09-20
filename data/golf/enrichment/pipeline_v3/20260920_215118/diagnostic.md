# Golf Master Pipeline v3 진단

- 전체 catalog: 553개
- 현재 주요 필드 완비: 0개
- 웹 조사 대상: 553개
- 기존 웹 결과 재사용 가능: 50개
- 신규 웹 검색 예상 대상: 503개
- 신규 Tavily 최소 예상: 503회
- 신규 Tavily 최대 예상: 1004회

## 필드별 부족

- operation_type: 459개
- holes: 537개
- courses: 344개
- official_url: 534개
- booking_url: 550개
- phone: 475개

## 원칙

- catalog.json 수정 없음
- 기존 1~100 웹 결과 재사용
- 부족 필드만 검색
- 필드별 A_CANDIDATE / B_CANDIDATE / HOLD
- 후보값은 자동 반영하지 않음
- 중단 후 checkpoint에서 재개
