# 골프 DB 분기 갱신 보고서 · 2026-09-23

- 대상 2곳 · 수집 성공 2곳 · 실패 0곳
- DB 반영 1곳 (dry-run: 저장 안 함) · 확인 필요 1곳
- DB 파일: golf_master_precision_checkpoint_2026-09-23_filled.json
- 모델 claude-opus-5 · 토큰 입력 55,352 / 출력 7,179 · 추정 비용 $0.46
- 수집 원본: official_enrich_2026-09-23_quarterly_1790165015.json

## 반영된 변경
- 88컨트리클럽: caddie_fee

## 확인 필요 (정밀 DB 값과 공식 홈페이지 값이 다름 · 덮어쓰지 않음)
- 블랙스톤 이천 · two_person: DB=미확인 / 홈페이지=False · https://www.blackstoneresort.com/ic/aboutList?section=fare

## 수집 실패
- 없음