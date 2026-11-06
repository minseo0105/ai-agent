// 검색·유형·단계·지역 필터 회귀. 기존 DevelopmentTab의 인라인 코드를 그대로 옮긴 기준 구현과 새 모듈을 대조한다.
import test from "node:test";
import assert from "node:assert/strict";
import { filterProjects, typeCounts, distinctStages, visiblePoints, FILTER_OPTIONS, matchesFilter } from "../../web/src/lib/developmentFilter.ts";
import { makeProjects, makePoints, TOTAL, DISTRICTS } from "./fixtures/zone_fixture.mjs";

// ---- 기준 구현: 변경 전 DevelopmentTab.tsx의 코드(동작 변경 없음의 근거) ----
function legacyMatchesFilter(item, filter) {
  if (filter === "전체") return true;
  if (filter === "기타 정비사업") return !["재개발", "재건축", "모아타운"].includes(item.type_label);
  return item.type_label === filter || item.program_label === filter;
}
function legacyVisible(projects, selectedDistricts, filter, stageFilter, search) {
  return projects.filter((p) => {
    if (selectedDistricts.size > 0 && !selectedDistricts.has(p.district ?? "")) return false;
    if (!legacyMatchesFilter(p, filter)) return false;
    if (stageFilter !== "전체" && p.stage.label !== stageFilter) return false;
    if (!search) return true;
    return [p.name, p.address, p.dong, p.district, p.type_label, p.program_label, p.stage.label].filter(Boolean).join(" ").includes(search);
  });
}

const projects = makeProjects();
const points = makePoints(projects);
const ids = (list) => list.map((p) => p.project_id);

test("고정 데이터는 1,190건이다", () => assert.equal(projects.length, TOTAL));

test("필터 선택지는 변경 전과 같다", () => {
  assert.deepEqual(FILTER_OPTIONS, ["전체", "재개발", "재건축", "신속통합기획", "모아타운", "기타 정비사업"]);
});

test("조건이 없으면 1,190건이 모두 보인다", () => {
  const out = filterProjects(projects, { districts: new Set(), filter: "전체", stageFilter: "전체", search: "" });
  assert.equal(out.length, TOTAL);
});

test("유형 필터 전체 조합이 기준 구현과 같은 결과를 낸다", () => {
  for (const filter of FILTER_OPTIONS) {
    const expected = ids(legacyVisible(projects, new Set(), filter, "전체", ""));
    assert.deepEqual(ids(filterProjects(projects, { districts: new Set(), filter, stageFilter: "전체", search: "" })), expected, filter);
  }
});

test("지역·유형·단계·검색어를 섞은 수백 가지 조합이 기준 구현과 같다", () => {
  const stages = ["전체", ...distinctStages(projects)];
  const searches = ["", "천호", "강동구", "재건축", "신속통합기획", "없는검색어", "사업시행", "  ", "1구역", "서울 송파구"];
  const districtSets = [new Set(), new Set(["강동구"]), new Set(["강동구", "송파구", "노원구"]), new Set(DISTRICTS.slice(0, 6)), new Set(["없는구"])];
  let checked = 0;
  for (const districts of districtSets) for (const filter of FILTER_OPTIONS) for (const stageFilter of stages) for (const raw of searches) {
    const search = raw.trim();
    const expected = ids(legacyVisible(projects, districts, filter, stageFilter, search));
    const actual = ids(filterProjects(projects, { districts, filter, stageFilter, search }));
    assert.deepEqual(actual, expected, JSON.stringify([...districts, filter, stageFilter, raw]));
    checked++;
  }
  assert.ok(checked > 1000, `조합 ${checked}개`);
});

test("검색은 사업명·주소·동·자치구·유형·정책·단계 문구를 모두 본다", () => {
  const p = projects.find((x) => x.address && x.dong && x.program_label);
  for (const needle of [p.name.slice(0, 4), p.address.slice(3, 9), p.dong, p.district, p.type_label, p.program_label, p.stage.label]) {
    const out = filterProjects(projects, { districts: new Set(), filter: "전체", stageFilter: "전체", search: needle });
    assert.ok(ids(out).includes(p.project_id), needle);
  }
});

test("null 필드가 있어도 'null' 문자열로 검색되지 않는다", () => {
  assert.equal(filterProjects(projects, { districts: new Set(), filter: "전체", stageFilter: "전체", search: "null" }).length, 0);
  assert.equal(filterProjects(projects, { districts: new Set(), filter: "전체", stageFilter: "전체", search: "undefined" }).length, 0);
});

test("자치구 필터는 district가 비어 있는 사업을 포함하지 않는다", () => {
  const withBlank = [{ ...projects[0], district: null }, ...projects.slice(1, 5)];
  const out = filterProjects(withBlank, { districts: new Set(["강동구"]), filter: "전체", stageFilter: "전체", search: "" });
  assert.ok(!ids(out).includes(withBlank[0].project_id));
});

test("유형별 건수는 지역만 적용한 목록 기준이다 (유형·단계·검색은 분모에 영향 없음)", () => {
  const districts = new Set(["강동구", "송파구"]);
  const inRegion = projects.filter((p) => districts.has(p.district));
  const counts = typeCounts(inRegion, 7);
  assert.equal(counts.total, 7);
  assert.equal(counts.재개발, inRegion.filter((p) => p.type_label === "재개발").length);
  assert.equal(counts.재건축, inRegion.filter((p) => p.type_label === "재건축").length);
  assert.equal(counts.신속통합기획, inRegion.filter((p) => p.program_label === "신속통합기획").length);
  assert.equal(counts.모아타운, inRegion.filter((p) => p.type_label === "모아타운").length);
});

test("단계 선택지는 응답에 실제로 있는 값만, 정렬되어 나온다 (추정 없음)", () => {
  const stages = distinctStages(projects);
  assert.deepEqual(stages, [...new Set(projects.map((p) => p.stage.label))].sort());
});

test("화면에 보이는 사업의 좌표만 마커 대상이 된다", () => {
  const visible = filterProjects(projects, { districts: new Set(["강동구"]), filter: "재건축", stageFilter: "전체", search: "" });
  const shown = visiblePoints(points, visible);
  const idSet = new Set(ids(visible));
  assert.ok(shown.every((p) => idSet.has(p.project_id)));
  assert.equal(shown.length, points.filter((p) => idSet.has(p.project_id)).length);
});

test("matchesFilter는 프로그램 라벨로도 거른다 (신속통합기획·모아타운)", () => {
  assert.ok(matchesFilter({ type_label: "재개발", program_label: "신속통합기획" }, "신속통합기획"));
  assert.ok(!matchesFilter({ type_label: "재개발", program_label: null }, "신속통합기획"));
  assert.ok(matchesFilter({ type_label: "정비사업", program_label: null }, "기타 정비사업"));
  assert.ok(!matchesFilter({ type_label: "모아타운", program_label: null }, "기타 정비사업"));
});

test("입력 배열을 수정하지 않는다", () => {
  const copy = JSON.stringify(projects.slice(0, 50));
  filterProjects(projects.slice(0, 50), { districts: new Set(["강동구"]), filter: "재개발", stageFilter: "전체", search: "천호" });
  assert.equal(JSON.stringify(projects.slice(0, 50)), copy);
});
