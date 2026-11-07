import test from "node:test";
import assert from "node:assert/strict";
import { aptSeqOf, areaGroups, groupComplexes, matchComplexes, nameMatches, parseLot, rebuildView } from "../../web/src/lib/complexMatch.ts";

// 송파구 오금동 실제 거래(2026.09~11)에서 가져온 단지명·단지번호·본번
const t = (name, seq, bon, { area = 84.9, price = 15, date = "2026-10-01", floor = "5", type = "아파트", viaId = false, cancel = "" } = {}) => ({
  property_type: type, name, region: "오금동", area, area_basis: "전용면적", price_100m: price, price_text: `${price}억원`, date, floor,
  build_year: "1988", raw_detail: { 본번: String(bon).padStart(4, "0") }, detail: cancel ? { 계약해제: cancel } : {},
  ...(viaId ? { id: `${type}:11710:${seq}:${name}:${date}` } : { apt_seq: seq }),
});
const OGEUM = [t("상아2차아파트", "11710-124", 165), t("우창", "11710-129", 164), t("삼성", "11710-123", 160), t("현대백조", "11710-131", 11), t("송파두산위브", "11710-8878", 135)];
const SANGA1 = { name: "가락상아1차아파트 재건축사업 조합", address: "서울특별시 송파구 오금동 166" };

test("보고된 오류: 가락상아1차에 상아2차·삼성·현대백조 거래를 붙이지 않는다", () => {
  const m = matchComplexes(SANGA1, OGEUM);
  assert.equal(m.status, "NO_TRADES");
  assert.deepEqual(m.confirmed, []);
  assert.equal(m.others.length, OGEUM.length); // 전부 '주변 비교 시세'로
  assert.match(m.reason, /확인된 거래가 없어요/);
});

test("단지명과 본번이 함께 맞는 단지만 확정하고 나머지는 주변 비교로 분리", () => {
  const own = [t("상아1차", "11710-125", 166, { price: 16 }), t("상아1차", "11710-125", 166, { price: 17, area: 117.5 })];
  const m = matchComplexes(SANGA1, [...OGEUM, ...own]);
  assert.equal(m.status, "CONFIRMED");
  assert.equal(m.confirmed.length, 1);
  assert.equal(m.confirmed[0].aptSeq, "11710-125");
  assert.equal(m.confirmed[0].rows.length, 2);
  assert.equal(m.others.length, OGEUM.length);
});

test("단지명 오매칭: 지번만 같고 이름이 다르면 확정하지 않는다(장미 vs 더샵스타파크)", () => {
  const m = matchComplexes({ name: "장미1,2,3차아파트 주택재건축정비사업 조합", address: "서울특별시 송파구 신천동 7" }, [t("잠실더샵스타파크", "11710-999", 7)]);
  assert.equal(m.status, "UNCERTAIN");
  assert.deepEqual(m.candidates[0].reasons, ["지번(본번) 일치", "단지명 불일치"]);
  assert.equal(m.confirmed.length, 0);
});

test("주소 불일치: 이름이 맞아도 본번이 다르면 후보로만", () => {
  const m = matchComplexes({ name: "가락극동아파트 재건축사업 조합", address: "서울특별시 송파구 가락동 192" }, [t("극동", "11710-200", 190)]);
  assert.equal(m.status, "UNCERTAIN");
  assert.deepEqual(m.candidates[0].reasons, ["단지명 유사", "지번 불일치"]);
});

test("사업 주소에 지번이 없거나 산 지번이면 확정하지 않는다", () => {
  assert.match(matchComplexes({ name: "가락극동아파트", address: "서울특별시 송파구 가락동" }, [t("극동", "11710-200", 192)]).reason, /지번이 없어/);
  assert.equal(matchComplexes({ name: "가락극동아파트", address: "가락동 산 192" }, [t("극동", "11710-200", 192)]).status, "UNCERTAIN");
});

test("이름 규칙: 차수 불일치는 불일치, 어순이 달라도 같은 이름은 일치", () => {
  assert.equal(nameMatches("가락상아1차아파트", "상아2차아파트"), false);
  assert.equal(nameMatches("가락1차현대아파트 재건축정비사업 조합", "문정가락현대1차"), true);
  assert.equal(nameMatches("가락극동아파트 재건축사업 조합", "극동"), true);
  assert.equal(nameMatches("장미1,2,3차아파트", "장미1차"), true);
  assert.equal(nameMatches("가락상아1차아파트", "삼성"), false);
});

test("한 사업에 여러 단지(같은 본번·이름)면 단지번호별로 따로 확정", () => {
  const rows = [t("올림픽선수기자촌1단지", "11710-1", 89), t("올림픽선수기자촌2단지", "11710-2", 89)];
  const m = matchComplexes({ name: "올림픽선수기자촌아파트 재건축정비사업", address: "방이동 89" }, rows);
  assert.deepEqual(m.confirmed.map((c) => c.aptSeq), ["11710-1", "11710-2"]);
});

test("단지번호: 서버 apt_seq 우선, 없으면 거래 id에서 읽고, 같은 이름도 번호가 다르면 다른 단지", () => {
  assert.equal(aptSeqOf(t("현대", "11710-50", 1, { viaId: true })), "11710-50");
  assert.equal(aptSeqOf({ id: "단독·다가구:11710:11710:단독:2026" }), null);
  assert.equal(groupComplexes([t("현대", "11710-50", 1), t("현대", "11710-51", 2)]).length, 2);
  assert.deepEqual(parseLot("서울특별시 송파구 송파동 100번지 일대"), { main: "100", sub: null, mountain: false });
  assert.deepEqual(parseLot("오금동 166-3"), { main: "166", sub: "3", mountain: false });
});

test("면적별 묶음: 0.5㎡ 이내만 합치고 해제 거래는 제외", () => {
  const g = areaGroups([t("A", "1", 1, { area: 84.95, price: 10 }), t("A", "1", 1, { area: 84.98, price: 12, date: "2026-10-09" }),
    t("A", "1", 1, { area: 59.9, price: 8 }), t("A", "1", 1, { area: 84.97, price: 99, cancel: "O" })]);
  assert.deepEqual(g.map((x) => [x.label, x.count, x.median]), [["59.9", 1, 8], ["84.95~84.98", 2, 11]]);
  assert.equal(g[1].latest.date, "2026-10-09");
});

test("API 오류는 '거래 없음'과 구분한다", () => {
  assert.deepEqual(rebuildView("FORBIDDEN", [], SANGA1, []), { kind: "API_ERROR", status: "FORBIDDEN" });
  assert.deepEqual(rebuildView("TIMEOUT", [], SANGA1, []), { kind: "API_ERROR", status: "TIMEOUT" });
  assert.equal(rebuildView("OK", ["서울 > 송파구 · 아파트: 시간 초과"], SANGA1, OGEUM).status, "APT_FAILED");
  const empty = rebuildView("EMPTY", [], SANGA1, []);
  assert.equal(empty.kind, "NEED_CHECK");
  assert.equal(empty.match.status, "NO_TRADES");
  assert.equal(rebuildView("OK", ["서울 > 송파구 · 연립·다세대: (403)"], SANGA1, OGEUM).kind, "NEED_CHECK");
});
