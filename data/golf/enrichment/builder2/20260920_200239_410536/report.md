# Golf Master DB Builder 2 — 10개 검토 보고서

기준일: 2026-09-20 · catalog 555개 · 테스트 10개

catalog는 변경하지 않았습니다. 아래 값은 적용 전 검토 후보입니다.
원문 작성일이 없는 값은 날짜 미상이며, checked_at은 출처 확인일입니다.

| 골프장 | 전체 홀수 후보 | 운영형태 후보 | 변경 후보 수 | KGA 격리 행 |
|---|---:|---|---:|---:|
| 88컨트리클럽 | 36 | 확인필요 | 2 | 0 |
| 라비에벨CC | 36 | 확인필요 | 1 | 0 |
| 레이크사이드CC | 54 | 확인필요 | 1 | 9 |
| 레인보우힐스CC | 확인필요 | 확인필요 | 2 | 0 |
| 블랙스톤 이천 | 27 | 확인필요 | 3 | 0 |
| 블루헤런GC | 18 | 확인필요 | 2 | 0 |
| 사우스스프링스CC | 확인필요 | 확인필요 | 1 | 0 |
| 청주 세레니티 | 확인필요 | 확인필요 | 0 | 0 |
| 클럽72 | 72 | 대중제 | 2 | 11 |
| 클럽디 더플레이어스 | 27 | 확인필요 | 3 | 0 |

## 88컨트리클럽

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "경기도 용인시 기흥구 석성로521번길 169" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "031-287-8811" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: 36 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: [{"name": "동코스", "holes": null, "holes_evidence": null}, {"name": "서코스", "holes": null, "holes_evidence": null}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **official_url**: "https://88countryclub.co.kr/" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [88-home](https://88countryclub.co.kr/): 사업자등록 135-83-00798 및 국가보훈부 88골프장 고지, 공공 매칭 주소와 동일
- [88-intro](https://88countryclub.co.kr/About/ClubInfo.aspx): 검토한 공식 홈의 클럽소개 링크; 해당 용인 주소/전화 일치
- [88-course](https://88countryclub.co.kr/Course/CourseInfo.aspx): 공식 홈 코스안내 링크; 해당 지점 유지
- [88cc-public-existing](https://www.data.go.kr/data/15154978/openapi.do): 기존 exact 매칭 공공 레코드. source_date는 레코드 수정일이며 재조회하지 않음.

검토 사항:

- 동/서 명칭은 확인했으나 이번 근거에 코스별 홀수는 명시되지 않아 null.
- 창립연도를 개장연도로 해석하지 않음. 현재 운영형태는 별도 최신 명시 출처 필요.
- 변경 후보 `courses`: [] → [{"name": "동코스", "holes": null, "holes_evidence": null}, {"name": "서코스", "holes": null, "holes_evidence": null}]
- 변경 후보 `official_url`: "https://www.88countryclub.co.kr/" → "https://88countryclub.co.kr/"
- KGA 구조 유효 0행 / 격리 0행. PDF 원문 재검증 전.

## 라비에벨CC

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "강원특별자치도 춘천시 동산면 종자리로 436-0, 1동 1층 1호 (라비에벨컨트리클럽)" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 2026-02-11, 확인일 2026-09-20)
- **phone**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: 36 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **official_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [lavie-operator](https://www.kolon.com/kr/subsidiary/construction-distribution): 그룹 계열사 소개에서 그린나래의 라비에벨 운영을 명시. 골프장 홈페이지 자체 identity는 아직 미확인
- [lavie-public-existing](https://www.data.go.kr/data/15154978/openapi.do): 기존 exact 매칭 공공 레코드. source_date는 레코드 수정일이며 재조회하지 않음.

검토 사항:

- 기존 홈페이지는 HTTP 302, 웹 열기는 412. 공식 홈페이지/예약 URL을 새로 확정하지 않음.
- 운영사 공식 소개의 총36홀만 확인. 올드18+듄스18은 현재 catalog에 있으나 이번 출처에서 개별 홀수 재확인 전.
- 변경 후보 `address`: "강원특별자치도 춘천시 동산면 종자리로 436" → "강원특별자치도 춘천시 동산면 종자리로 436-0, 1동 1층 1호 (라비에벨컨트리클럽)"
- KGA 구조 유효 0행 / 격리 0행. PDF 원문 재검증 전.

## 레이크사이드CC

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "경기도 용인시 처인구 모현읍 능원로 181" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "031-334-2111" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: 54 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **official_url**: "https://www.lakeside.kr/main/mainPage.do" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [lakeside-main](https://www.lakeside.kr/main/mainPage.do): 사업자등록 135-81-02491, 용인 모현읍 주소 및 대표전화가 catalog와 일치; 공식 법인 입회신청서도 존재

검토 사항:

- 루트 응답은 짧은 진입 HTML. 실제 본문 main/mainPage.do를 출처로 사용.
- 동/남/서 각18홀과 현재 회원제/대중제 구성은 이번 dossier에서 재확인 전이며 baseline에 보존.
- 변경 후보 `official_url`: "https://www.lakeside.kr/" → "https://www.lakeside.kr/main/mainPage.do"
- KGA 구조 유효 0행 / 격리 9행. PDF 원문 재검증 전.

## 레인보우힐스CC

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "충청북도 음성군 생극면 차생로 168" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "043-879-7950" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **courses**: [{"name": "동코스", "holes": null, "holes_evidence": null}, {"name": "남코스", "holes": null, "holes_evidence": null}, {"name": "서코스", "holes": null, "holes_evidence": null}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **official_url**: "https://www.rainbowhills.co.kr/index.asp" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [rainbow-main](https://www.rainbowhills.co.kr/index.asp): 사업자번호 303-85-17902, 상호 주식회사 디비월드, 음성 주소/전화 일치
- [rainbow-course](https://www.rainbowhills.co.kr/pagesite/course/intro.asp): 검토한 공식 홈의 코스소개 링크, 동일 법적 고지

검토 사항:

- 코스별 홀수를 KGA 조합에서 추정하지 않음. 대회요강의 본선18홀을 전체 규모로 사용하지 않음.
- 공식 코스 페이지의 레이팅 표는 조합/성별 맥락 부족으로 KGA 레이팅에 병합하지 않음.
- 변경 후보 `courses`: ["서", "남", "동"] → [{"name": "동코스", "holes": null, "holes_evidence": null}, {"name": "남코스", "holes": null, "holes_evidence": null}, {"name": "서코스", "holes": null, "holes_evidence": null}]
- 변경 후보 `official_url`: "https://www.rainbowhills.co.kr/" → "https://www.rainbowhills.co.kr/index.asp"
- KGA 구조 유효 15행 / 격리 0행. PDF 원문 재검증 전.

## 블랙스톤 이천

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "경기도 이천시 장호원읍 장여로 459-160" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **operation_type**: null — 현재 운영형태의 최근 작성일·효력일 확인 필요 (출처일 미상, 확인일 없음)
- **holes**: 27 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: [{"name": "동코스", "holes": 9, "holes_evidence": "동코스(9H)"}, {"name": "북코스", "holes": 9, "holes_evidence": "북코스(9H)"}, {"name": "서코스", "holes": 9, "holes_evidence": "서코스(9H)"}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **official_url**: "https://www.blackstoneresort.com/ic/aboutList?section=course" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [blackstone-course](https://www.blackstoneresort.com/ic/aboutList?section=course): 이천 지점 소개/입회/예약 규정과 주소를 확인. 제주 /jj/ 페이지와 분리; 기존 전화는 대표전화, 630-0700은 예약실

검토 사항:

- 로컬 HTTPS 요청 SSL 오류. TLS 검증을 끄지 않았고 웹 열람 결과와 HTTP 진단을 분리.
- 예약실 번호를 대표전화로 교체하지 않음.
- 혼합을 뒷받침하는 동시 운영 구성이 있어도 작성일 미상이라 current 확정 보류.
- 변경 후보 `address`: "경기도 이천시 장호원읍 풍계리 산52" → "경기도 이천시 장호원읍 장여로 459-160"
- 변경 후보 `courses`: ["북", "동", "서"] → [{"name": "동코스", "holes": 9, "holes_evidence": "동코스(9H)"}, {"name": "북코스", "holes": 9, "holes_evidence": "북코스(9H)"}, {"name": "서코스", "holes": 9, "holes_evidence": "서코스(9H)"}]
- 변경 후보 `official_url`: "https://www.blackstoneresort.com/ic/" → "https://www.blackstoneresort.com/ic/aboutList?section=course"
- 보류 `operation_type`: 현재 운영형태의 최근 작성일·효력일 확인 필요
- KGA 구조 유효 15행 / 격리 0행. PDF 원문 재검증 전.

## 블루헤런GC

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "경기도 여주시 대신면 고달사로 67" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "031-880-0700" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: 18 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: [{"name": "West", "holes": 9, "holes_evidence": "West Course 9 Hole"}, {"name": "East", "holes": 9, "holes_evidence": "East Course 9 Hole"}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **official_url**: "https://blueheron.co.kr/" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [blueheron-main](https://blueheron.co.kr/): 사업자등록번호 126-81-64682, 상호/대표/주소 명시. catalog 주소 일치; 대표전화는 차이 발견
- [blueheron-course](https://blueheron.co.kr/swp/course/outline): 검토한 공식 홈 코스개요 링크; 동일 사업자 고지
- [blueheron-public-existing](https://www.data.go.kr/data/15154978/openapi.do): 기존 exact 매칭 공공 레코드. source_date는 레코드 수정일이며 재조회하지 않음.

검토 사항:

- 공식 대표전화031-880-0700과 기존031-884-0701이 다름. 기존 값은 자동 수정하지 않음.
- 변경 후보 `phone`: "031-884-0701" → "031-880-0700"
- 변경 후보 `courses`: [{"name": "WEST", "holes": 9, "type": "9H"}, {"name": "EAST", "holes": 9, "type": "9H"}] → [{"name": "West", "holes": 9, "holes_evidence": "West Course 9 Hole"}, {"name": "East", "holes": 9, "holes_evidence": "East Course 9 Hole"}]
- KGA 구조 유효 0행 / 격리 0행. PDF 원문 재검증 전.

## 사우스스프링스CC

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "경기 이천시 모가면 공원로 64" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "031-630-7000" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **courses**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **official_url**: "https://www.sscc.co.kr/" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [southsprings-home](https://www.sscc.co.kr/): 사업자등록번호114-86-03810, 골프장 전용 copyright/주소/대표전화 확인. 주소/전화 catalog 일치
- [southsprings-public-existing](https://www.data.go.kr/data/15154978/openapi.do): 기존 exact 매칭 공공 레코드. source_date는 레코드 수정일이며 재조회하지 않음.

검토 사항:

- 이용규정의 라운드 소요시간 18홀/9홀은 전체 홀수 근거로 채택하지 않음.
- 현재 catalog18홀 및 Lake/Mountain 각9홀은 이번 사실 검증값으로 자동 복사하지 않음.
- 변경 후보 `address`: "경기도 이천시 모가면 공원로 64" → "경기 이천시 모가면 공원로 64"
- KGA 구조 유효 7행 / 격리 0행. PDF 원문 재검증 전.

## 청주 세레니티

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: null — 공식 운영주체·지점 identity 근거 부족 (출처일 미상, 확인일 없음)
- **phone**: null — 공식 운영주체·지점 identity 근거 부족 (출처일 미상, 확인일 없음)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: null — 공식 운영주체·지점 identity 근거 부족 (출처일 미상, 확인일 없음)
- **courses**: null — 공식 운영주체·지점 identity 근거 부족 (출처일 미상, 확인일 없음)
- **official_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [serenity-home](https://www.serenitygolfresort.com/cheongju/): 청주 전용 소개에서 동일 주소/전화 확인. 운영 법적 고지의 독립 검증은 아직 미완료

검토 사항:

- 명칭/주소/전화 일치만으로 identity 확정하지 않음. 사업자/운영주체 추가 확인 필요.
- 본문 총27홀 및3코스 표현은 reference로 보존. 각9홀로 나누어 추정하지 않음.
- 보류 `address`: 공식 운영주체·지점 identity 근거 부족
- 보류 `phone`: 공식 운영주체·지점 identity 근거 부족
- 보류 `holes`: 공식 운영주체·지점 identity 근거 부족
- 보류 `courses`: 공식 운영주체·지점 identity 근거 부족
- KGA 구조 유효 0행 / 격리 0행. PDF 원문 재검증 전.

## 클럽72

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **phone**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **operation_type**: "대중제" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 2026-05-12, 확인일 2026-09-20)
- **holes**: 72 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 2026-05-12, 확인일 2026-09-20)
- **courses**: [{"name": "하늘", "holes": null, "holes_evidence": null}, {"name": "오션", "holes": null, "holes_evidence": null}, {"name": "레이크", "holes": null, "holes_evidence": null}, {"name": "클래식", "holes": null, "holes_evidence": null}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 2026-05-12, 확인일 2026-09-20)
- **official_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [club72-operator](https://kxgroup.co.kr/sub/sub04_02.php?boardid=press&category=&idx=41&mode=view&offset=18&sk=&sw=): KX그룹 자사 발표에서 클럽72 운영과 원더클럽 공식 홈페이지 관계를 명시

검토 사항:

- 기존 onetheclub.com/club72/은 실제HTTP404. 운영사 발표의 홈페이지 관계와 개별 URL 가용성은 분리.
- kxleisure.com은 운영 예약망 후보지만 지점의 정확한 진입/예약URL은 추가 검토.
- 72/4로 개별18홀을 추정하지 않음. catalog KGA는 하늘/오션만 있어 전체 구조가 아님.
- 변경 후보 `operation_type`: null → "대중제"
- 변경 후보 `courses`: ["하늘 (Out)", "하늘 (In)", "오션 (Out)", "오션 (In)"] → [{"name": "하늘", "holes": null, "holes_evidence": null}, {"name": "오션", "holes": null, "holes_evidence": null}, {"name": "레이크", "holes": null, "holes_evidence": null}, {"name": "클래식", "holes": null, "holes_evidence": null}]
- KGA 구조 유효 0행 / 격리 11행. PDF 원문 재검증 전.

## 클럽디 더플레이어스

- **name**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **address**: "강원도 춘천시 동산면 새술막길 438" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **phone**: "033-250-5000" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **operation_type**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **holes**: 27 — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **courses**: [{"name": "VALLEY", "holes": null, "holes_evidence": null}, {"name": "LAKE", "holes": null, "holes_evidence": null}, {"name": "MOUNTAIN", "holes": null, "holes_evidence": null}] — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **official_url**: "https://www.clubd.com/theplayers/club/cibi.do" — 출처 검토 근거 있음; 사용자 최종 검토 전 (출처일 미상, 확인일 2026-09-20)
- **booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **external_booking_url**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)
- **description**: null — 필드별 근거 없음 (출처일 미상, 확인일 없음)

출처 및 identity 근거:

- [clubd-intro](https://www.clubd.com/theplayers/club/cibi.do): 상호/사업자등록881-85-02928, 해당 춘천 지점 주소와 전화가 일치. 운영 브랜드 전용 페이지
- [clubd-mobile](https://www.clubd.com/m_clubd/tpintro.do?iCoDiv=06): 같은 운영 사이트의 더플레이어스 모바일 전용 소개; 지점 주소 및 대표전화 일치

검토 사항:

- 기존 playersgc.com은 로컬TLS 오류. 새 후보는 운영사 이도 사이트의 해당 지점 법적 고지를 직접 확인.
- 코스별9홀은 catalog에 있지만 이번 출처에서 명시적 재확인 전이므로 null.
- 변경 후보 `address`: "강원특별자치도 춘천시 동산면 새술막길 438" → "강원도 춘천시 동산면 새술막길 438"
- 변경 후보 `courses`: [{"name": "VALLEY", "holes": 9, "type": "대중형"}, {"name": "LAKE", "holes": 9, "type": "대중형"}, {"name": "MOUNTAIN", "holes": 9, "type": "대중형"}] → [{"name": "VALLEY", "holes": null, "holes_evidence": null}, {"name": "LAKE", "holes": null, "holes_evidence": null}, {"name": "MOUNTAIN", "holes": null, "holes_evidence": null}]
- 변경 후보 `official_url`: "https://www.playersgc.com/" → "https://www.clubd.com/theplayers/club/cibi.do"
- KGA 구조 유효 0행 / 격리 0행. PDF 원문 재검증 전.

## 실제 HTTP 확인 (본문 사실 재검증과 별개)

- blueheron [https://blueheron.co.kr/](https://blueheron.co.kr/): 200 
- blueheron [https://blueheron.co.kr/swp/course/outline](https://blueheron.co.kr/swp/course/outline): 200 
- rainbow [https://www.rainbowhills.co.kr/](https://www.rainbowhills.co.kr/): 302 redirect: http://www.rainbowhills.co.kr/index.asp
- rainbow [https://www.rainbowhills.co.kr/index.asp](https://www.rainbowhills.co.kr/index.asp): 200 
- rainbow [https://www.rainbowhills.co.kr/pagesite/course/intro.asp](https://www.rainbowhills.co.kr/pagesite/course/intro.asp): 200 
- lakeside [https://www.lakeside.kr/](https://www.lakeside.kr/): 200 
- lakeside [https://www.lakeside.kr/main/mainPage.do](https://www.lakeside.kr/main/mainPage.do): 200 
- 88cc [https://www.88countryclub.co.kr/](https://www.88countryclub.co.kr/): 200 
- 88cc [https://88countryclub.co.kr/](https://88countryclub.co.kr/): 200 
- 88cc [https://88countryclub.co.kr/About/ClubInfo.aspx](https://88countryclub.co.kr/About/ClubInfo.aspx): 200 
- 88cc [https://88countryclub.co.kr/Course/CourseInfo.aspx](https://88countryclub.co.kr/Course/CourseInfo.aspx): 200 
- southsprings [https://www.sscc.co.kr/](https://www.sscc.co.kr/): 200 
- blackstone [https://www.blackstoneresort.com/ic/](https://www.blackstoneresort.com/ic/): SSLError 
- blackstone [https://www.blackstoneresort.com/ic/aboutList?section=course](https://www.blackstoneresort.com/ic/aboutList?section=course): SSLError 
- clubd_theplayers [https://www.playersgc.com/](https://www.playersgc.com/): SSLError 
- clubd_theplayers [https://www.clubd.com/theplayers/club/cibi.do](https://www.clubd.com/theplayers/club/cibi.do): 200 
- clubd_theplayers [https://www.clubd.com/m_clubd/tpintro.do?iCoDiv=06](https://www.clubd.com/m_clubd/tpintro.do?iCoDiv=06): 200 
- club72 [https://www.onetheclub.com/club72/](https://www.onetheclub.com/club72/): 404 
- club72 [https://kxgroup.co.kr/sub/sub04_02.php?boardid=press&category=&idx=41&mode=view&offset=18&sk=&sw=](https://kxgroup.co.kr/sub/sub04_02.php?boardid=press&category=&idx=41&mode=view&offset=18&sk=&sw=): 200 
- silkriver [https://www.serenitygolfresort.com/cheongju/](https://www.serenitygolfresort.com/cheongju/): 200 
- lavie [https://www.lavieestbellegolfnresort.com/](https://www.lavieestbellegolfnresort.com/): 302 redirect: http://www.lavieestbellegolfnresort.com/default.asp
- lavie [https://www.kolon.com/kr/subsidiary/construction-distribution](https://www.kolon.com/kr/subsidiary/construction-distribution): 200 

## 무결성

- catalog SHA-256: `7de6dceb16937cabf0741b1d68addc6d5ef3c6b233497f33476e6214d26901af`
- 백업: `data/golf/backups/catalog_before_builder2_20260920_200239_410536.json`
- catalog 반영 코드, NAVER 호출, 외부 LLM 호출 없음.
