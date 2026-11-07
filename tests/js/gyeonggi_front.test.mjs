import test from "node:test";
import assert from "node:assert/strict";
import { regionLabel } from "../../web/src/lib/zoneTrades.ts";
import { FILTER_OPTIONS, GYEONGGI_FILTER_OPTIONS, filterProjects, matchesFilter } from "../../web/src/lib/developmentFilter.ts";
import { matchComplexes, parseLot } from "../../web/src/lib/complexMatch.ts";

test("실거래 지역: 서울 자치구는 그대로, 경기 시·구는 경기 코드로, 구를 모르는 구 단위 시는 조회하지 않음", () => {
  assert.equal(regionLabel("강동구"), "서울 > 강동구");
  assert.equal(regionLabel("광명시"), "경기 > 광명시");
  assert.equal(regionLabel("수원시 팔달구"), "경기 > 수원시 팔달구");
  assert.equal(regionLabel("가평군"), "경기 > 가평군");
  assert.equal(regionLabel("수원시"), null);
  assert.equal(regionLabel("부천시"), null);
  assert.equal(regionLabel("인천광역시 중구"), null);
});

test("서울 필터 목록은 그대로, 경기 칩은 별도 목록", () => {
  assert.deepEqual(FILTER_OPTIONS, ["전체", "재개발", "재건축", "신속통합기획", "모아타운", "기타 정비사업"]);
  assert.deepEqual(GYEONGGI_FILTER_OPTIONS, ["소규모정비", "주거환경개선"]);
  const small = { type_label: "소규모주택정비", program_label: "소규모주택정비" };
  const env = { type_label: "주거환경개선", program_label: null };
  assert.equal(matchesFilter(small, "소규모정비"), true);
  assert.equal(matchesFilter(env, "소규모정비"), false);
  assert.equal(matchesFilter(env, "주거환경개선"), true);
  assert.equal(matchesFilter({ type_label: "재건축", program_label: null }, "소규모정비"), false);
});

test("서울·경기 사업이 같은 필터·검색을 통과한다(경기 시군구 지역 선택 포함)", () => {
  const p = (id, district, type_label, name, program_label = null) => ({ project_id: id, name, address: null, dong: null, district, type_label, program_label, stage: { label: "조합설립" } });
  const all = [p("s1", "강동구", "재건축", "둔촌"), p("g1", "수원시 팔달구", "재개발", "매산"), p("g2", "광명시", "소규모주택정비", "철산", "소규모주택정비")];
  const q = (o) => filterProjects(all, { districts: new Set(), filter: "전체", stageFilter: "전체", search: "", ...o }).map((x) => x.project_id);
  assert.deepEqual(q({ districts: new Set(["수원시 팔달구"]) }), ["g1"]);
  assert.deepEqual(q({ filter: "소규모정비" }), ["g2"]);
  assert.deepEqual(q({ search: "매산" }), ["g1"]);
  assert.deepEqual(q({ filter: "재건축" }), ["s1"]);
});

test("경기 주소의 '일원' 지번도 단지 매칭에 쓰고, 확정 규칙(본번+단지명)은 그대로", () => {
  assert.deepEqual(parseLot("수원시 팔달구 매산동 166 일원"), { main: "166", sub: null, mountain: false });
  const rows = [{ property_type: "아파트", name: "매산주공", region: "매산동", area: 59, price_100m: 5, price_text: "", date: "2026-10-01", apt_seq: "41115-1", raw_detail: { 본번: "0166" } },
    { property_type: "아파트", name: "다른단지", region: "매산동", area: 59, price_100m: 6, price_text: "", date: "2026-10-01", apt_seq: "41115-2", raw_detail: { 본번: "0166" } }];
  const m = matchComplexes({ name: "매산주공아파트 재건축", address: "수원시 팔달구 매산동 166 일원" }, rows);
  assert.deepEqual(m.confirmed.map((c) => c.aptSeq), ["41115-1"]);
  assert.equal(m.candidates[0].complex.aptSeq, "41115-2");
});
