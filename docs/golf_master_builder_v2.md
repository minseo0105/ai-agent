# Golf Master DB Builder 2

## 저장소 분석 및 유지/변경/폐기 결정

2026-09-20 catalog는 555개다. VWorld 좌표 477개, 공공데이터 이름 293개,
KGA 객체 213개, operation_type 95개가 있다. 필드 존재 수이며 정확도 인증 수는 아니다.
courses는 문자열과 객체 목록이 혼재한다. KGA 조합에서 유래한 문자열은 물리적 코스의
홀수 증거가 아니다. KGA 레이팅 중 course가 빈 행도 발견됐다.

- 유지: pages/6_골프장_추천.py, golf_catalog의 Pool/검색/요금 처리, 지도,
  NAVER/Tavily/GPT 후기 경로, golf_kga_ui/ratings/enrichment, 기존 catalog 필드.
- 추가: 독립적인 Builder 2 검증 모듈, 고정 10개 실행기, 검토 출처 dossier, 테스트 및 보고서.
- 재사용하지 않음: 이름+주소 토큰 점수로 공식사이트 확정, 도메인 블랙리스트,
  루트 URL로 축약, 페이지에 등장한 단일 홀수를 전체 홀수로 승격,
  회원제/대중제 단어 동시 존재로 혼합 처리, 다른 도메인을 곧 독립 출처로 간주.
- 이전 golf_master_db_builder_test10.py와 2B_* 산출물은 실제 저장소에 존재했다.
  과거 오탐 진단에만 참고했고 실행/수정/삭제하지 않았다.

## 데이터 흐름과 검토 경계

원본 catalog 읽기 → 바이트 단위 백업 → 기존 값/공공정보/KGA 분리 →
검토된 출처 dossier의 필드별 assertion 검증 → 충돌/과거/미확인 격리 →
10개 JSON 및 Markdown 보고서. catalog 쓰기나 apply 옵션은 없다.

`data/golf/builder2/test10_sources.json`은 검색 결과 자동 입력이 아닌 **검토자 편집 입력**이다.
이번 입력은 Codex가 실제 웹 출처를 검토해 작성했다. 사용자 승인은 아직 아니다.
`reviewed_by`를 자동 검색으로 채워 넣어서는 안 된다. 알려지지 않은 공식사이트는
authority의 연결 또는 운영주체/법적 고지/해당 지점의 연락처를 직접 확인한 뒤 등록한다.
제3자 사이트에 이름/주소/전화가 모두 있어도 자동 통과하지 않는다.

각 source는 publisher/branch/identity 판단 근거/원문 URL을 가지며, 각 claim은
field/value/quote/locator/review_note/scope/temporal을 가진다.
source_supported는 검토 출처로 뒷받침된 후보라는 뜻이며 점수나 사용자 승인 상태가 아니다.
사실의 source_date와 checked_at은 분리한다. 미상의 작성일을 수집일로 채우지 않는다.
일반 소개 페이지의 현재성은 보장하지 않으며 운영형태는 최근 730일 이내 명시적 현재
운영 출처일이 있어야 한다. 이는 보수적 검증 정책이며 오래된 출처는 reference로 남긴다.

우선순위는 공식 → 정부 → 협회 → 독립성이 검토된 복수 보조출처다.
동일 우선순위 충돌은 보류한다. 날짜가 확인된 운영형태만 최신 명시 진술을 우선한다.
후기 데이터는 수집하지 않고 별도 review_information 경계로 표시한다.

## 홀수/코스/KGA

- 전체 홀수는 검토자가 문맥을 확인한 explicit_club_total만 허용한다.
- physical_courses에 완전한 코스 목록 표시와 각 코스의 holes_evidence가 있을 때만 합산한다.
- 전체 합계와 명시적 전체 홀수가 다르면 보류한다. 일부 코스만 존재하면 합산하지 않는다.
- 확인한 이름만 있는 코스의 holes는 null이다. 27홀/3코스라는 이유로 9홀씩 채우지 않는다.
- KGA 조합과 물리 코스는 분리한다. 레이팅은 조합/티/성별/값 범위를 검사한다.
  course 누락은 추정 배정하지 않는다. 기존 PDF 데이터는 구조 유효 여부만 검사하며,
  원본 PDF 재검증 전까지 legacy_requires_source_review 상태다.
- 공식 예약 URL은 운영주체가 지정한 정확한 링크만 허용한다. 외부 플랫폼은
  external_booking_url로 별도 기록하며 공식 홈페이지로 승격하지 않는다.

## 실행

```powershell
.venv/Scripts/python.exe -X utf8 scripts/build_golf_master_v2_test10.py
.venv/Scripts/python.exe -X utf8 scripts/build_golf_master_v2_test10.py --fetch
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_golf_master_builder_v2.py -v
```

기본 실행은 네트워크 없이 dossier의 검토를 재현한다. --fetch는 기존 후보와 출처 URL의
실제 HTTP 상태만 확인한다. 상태 200은 사실 정확도/identity 재검증 성공이 아니다.
리디렉션을 자동 추종하지 않고 TLS 검증을 해제하지 않는다. 키나 Secrets를 읽지 않는다.
각 실행은 새로운 시간별 폴더로 출력하므로 기존 보고서를 덮어쓰지 않는다.
기존 requirements만 사용하며 앱에서 Builder를 import하지 않는다.
`--reuse-http-report <이전 result.json>`으로 기존 HTTP 확인 시각을 보존하면서
네트워크 없이 보고서만 다시 생성할 수 있다. 본문 재검증으로 표현하지 않는다.

## catalog 반영 전 해야 할 일

보고서의 변경 후보, identity, 미상 날짜, 운영형태 보류, KGA 격리 행을 사람이 확인한다.
특히 기존 대표전화와 공식 안내 전화의 용도가 같은지, 지점별 URL인지 확인한다.
독립적인 정답표 없이 정확도 백분율을 만들지 않는다. 정확도가 확인된 이후 별도 작업으로
필드별 승인/백업/충돌 검사/rollback을 포함한 catalog 반영 로직을 구현한다.
