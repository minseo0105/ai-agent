# 추천 대상 243개 레코드 정밀화 — 1차 조사

## 결과와 범위

2026-09-24 현재 조건 추천 대상 243개 ID를 고정하여 누락 항목 감사와 후기 원문 검색을 수행했다. 243곳 모두 사실 확인이 끝났거나 빈칸이 채워졌다는 의미가 아니다. 이번에는 원장 요금·인원 조건을 변경하지 않았다.

- 243개 대상 각 Tavily basic 검색 1회 완료. 사전 점검 6회 포함 총 249회 요청.
- 짧은 검색어 사용. 최초 긴 검색어 3회는 결과 0건이었으며 단순화 후 재수집.
- 보관된 이름 일치 후보 출처 177곳, 649건. SNS/공식 홈페이지는 후기에서 제외하고 URL 중복 정리.
- 특징 표현 후보 92곳, 235건. 게시일 확인된 출처 76건(오래된 자료 포함). 날짜가 없으면 최신 평가에 사용하지 않는다.
- 원문 문맥 직접 검토 3건: 남여주 좁다는 개별 후기, 드림파크 파크코스 넓다는 개별 후기, 사우스스프링스 6번 홀 벙커가 많다는 개별 후기. 남여주 '넓지는 않습니다'의 wide 자동 추출은 명시적으로 기각.
- 독립 후기 2명 이상으로 검증된 새 전체 골프장 경향은 아직 없다. 단일 후기와 특정 홀/코스 표현을 전체 속성이나 검색 필터로 승격하지 않았다.

## 비용

이번에 호출한 별도 유료 서비스는 Tavily 검색이다. GPT/Claude 분석 API는 호출하지 않았다.
공식 공시 기준 basic 요청당 1크레딧, 종량제 $0.008/credit이므로 249회는 $1.992 상당. 실제 청구는 계정 플랜/무료 잔여량에 따라 다르며 청구 내역은 확인하지 않았다. Codex 대화 사용량은 별도다.
공식 출처: https://www.tavily.com/pricing 및 https://docs.tavily.com/documentation/api-credits
추가 분석은 저장한 자료로 로컬 수행했다. 같은 날 같은 검색어의 성공 응답은 재사용한다.

## 저장 구조와 표시

- data/golf/review_evidence.json: 243개 ID별 source/evidence/confidence, 게시일, 관찰일, 작성자 식별, 후보/검토/기각, 코스 범위를 보관하는 별도 후기 근거 DB.
- data/golf/enrichment_review/refinement_243_audit.json: 243개별 연락처/공식URL/주소/홀수/요금 누락과 후기 확보 현황.
- data/golf/enrichment_review/review_curation_2026-09-24.json: 직접 문맥을 검토한 3건의 기록.
- data/golf/runtime/refinement_2026-09-24/: 검색 원응답. Git에서 제외되는 로컬 재분석 자료. 검색된 내용은 신뢰할 수 없는 입력으로 취급하며 코드/지시로 실행하지 않는다.
- 기존 review_seed/review_runtime 및 원장 DB는 그대로 유지한다.
- 상세 API의 reviews에 evidence_review를 추가. 기존 웹 상세 리뷰 카드/원문 링크 구조를 재사용해 단일 후기, 특정 코스/홀 표시, 후보 확보 상태를 보여준다. 미검토 후보를 새로운 평가로 표시하지 않는다.
- 기존 Streamlit 후기 화면은 별도 경로라 새 evidence_review 연동을 이번에 수정하지 않았다. Next.js 상세는 같은 API를 사용하므로 서버 재시작 후 확인한다.

## 반복 업데이트 기준

후기는 공식 사실이 아니며 검색 snippets만으로 판단하지 않는다. 자동 추출은 전부 needs_review로 시작한다. 사람이 확인한 동일 내용만 검토 상태를 유지한다. 문서가 변경되면 pending_revision에 새 후보를 보존하고 기존 검토본을 자동 덮어쓰지 않는다. 수집 실패/누락도 기존 근거를 삭제하지 않는다.
후기 집계는 동일 블로그 작성자를 1명으로 계산하며 동일 원문 해시도 중복 제외한다. 전체 경향은 전체 범위로 검토된 독립 작성자 2명 이상이 필요하다. 반대 의견이 있으면 엇갈림으로 표시한다. 관리/그린/시설은 최근 365일, 페어웨이/벙커는 730일을 사용하고 조회 때 다시 계산한다. 1명은 추가 확인 필요로 표시한다.
작성자 identity는 블로그 계정/도메인 기반이므로 다른 계정으로 재게시한 사람까지 식별하지 못한다. 지역명이 같은 지점/개명/동일 골프장 중복 ID는 후보 검토가 필요하다. 이 단계에서 confidence는 검증 확률이 아니라 근거 상태다.
수집기 기본 실행은 감사만 하며 --collect를 명시해야 검색 API를 호출한다. 무제한 자동 반복/새 예약 작업은 만들지 않았다. 기존 공식 정보 1·7월, 요금 4·10월 갱신 일정은 유지했다. 후기 반기 갱신은 아래 명령을 실행할 수 있으나 원격 예약에 연결하지 않았다.

```powershell
.\venv\Scripts\python.exe -B scripts\golf_refine_243.py
# 유료 검색 실행: 같은 날 성공 결과는 재사용, 다른 날은 새 요청
.\venv\Scripts\python.exe -B scripts\golf_refine_243.py --collect
# 원장/후기 DB에 곧바로 쓰지 않는 후보 파일 생성
.\venv\Scripts\python.exe -B scripts\build_golf_review_evidence.py --output data\golf\runtime\review_proposal
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_golf_review_evidence.py -v
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_golf_import_policy.py -v
```

다음 작업은 새 유료 전수 검색보다 기존 649개 후보의 날짜/본문 확보, 대상 지점/코스 식별, 미검토 표현 검증을 우선한다. 243개별 부족 필드를 감사 파일에서 확인해 공식 조사 대상을 좁힌다. 검토된 여러 후기의 합의가 확보되기 전에는 '넓은 페어웨이' 복합 필터를 활성화하지 않는다.
