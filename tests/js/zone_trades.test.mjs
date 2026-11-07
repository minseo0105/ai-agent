import test from "node:test";
import assert from "node:assert/strict";
import { classify, recentMonths, regionLabel, sameDong } from "../../web/src/lib/zoneTrades.ts";

test("403, 미연동, 거래 없음, 실패를 서로 구분한다", () => {
  assert.equal(classify({ apiKeyConfigured: false, rows: [], errors: [] }), "NOT_CONNECTED");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["서울 > 강동구 · 아파트: 공공데이터포털 활용신청이 필요한 API입니다 (403)"] }), "FORBIDDEN");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["x: PUBLIC_DATA_API_KEY가 없습니다."] }), "NOT_CONNECTED");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["x: connection reset"] }), "FAILED");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: [] }), "EMPTY");
  assert.equal(classify({ apiKeyConfigured: true, rows: [{}], errors: ["일부 유형 403"] }), "OK");
});

test("최근 3개월, 연도 경계 포함", () => {
  assert.deepEqual(recentMonths(new Date(2026, 0, 15)), ["202601", "202512", "202511"]);
});

test("자치구가 아니면 조회 지역을 만들지 않는다", () => {
  assert.equal(regionLabel("강동구"), "서울 > 강동구");
  assert.equal(regionLabel(null), null);
  assert.equal(regionLabel("천호동"), null);
});

test("같은 법정동만 남기고, 동을 모르면 그대로 둔다", () => {
  const rows = [{ region: "천호동" }, { region: "성내동" }, { region: "천호 동" }];
  assert.equal(sameDong(rows, "천호동").length, 2);
  assert.equal(sameDong(rows, null).length, 3);
});

import { withoutCancelled, periodText } from "../../web/src/lib/zoneTrades.ts";

test("계약 해제 건은 빼고, 해제 표시가 없으면 남긴다", () => {
  const rows = [{ detail: { 계약해제: "O" } }, { detail: { 계약해제: " " } }, { detail: {} }, {}];
  assert.equal(withoutCancelled(rows).length, 3);
});

test("HTTP 200 인증 오류는 거래 없음이 아니라 거부로 분류", () => {
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["아파트 공공데이터포털 인증 오류 30: SERVICE_KEY_IS_NOT_REGISTERED_ERROR"] }), "FORBIDDEN");
});

test("조회 기준 문구는 계약년월 범위", () => {
  assert.equal(periodText(["202611", "202610", "202609"]), "2026.09~2026.11 계약분");
});

test("시간 초과·파싱 오류를 따로 구분", () => {
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["서울 > 송파구 · 아파트: HTTPSConnectionPool Read timed out."] }), "TIMEOUT");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["아파트 API 응답을 XML로 해석하지 못했습니다."] }), "PARSE_ERROR");
});

import { partialFailureText } from "../../web/src/lib/zoneTrades.ts";
test("일부 유형 403은 따로 안내, 실패 없으면 null", () => {
  const t = partialFailureText(["서울 > 송파구 · 연립·다세대: 공공데이터포털 활용신청이 필요한 API입니다 (403)", "서울 > 송파구 · 오피스텔: 공공데이터포털 활용신청이 필요한 API입니다 (403)"]);
  assert.match(t, /연립·다세대·오피스텔 유형은 국토교통부 API 권한/);
  assert.equal(partialFailureText([]), null);
});

import { aptAnalysis } from "../../web/src/lib/zoneTrades.ts";
const tr = (date, price, area = 84, type = "아파트") => ({ date, price_100m: price, area, area_basis: "전용면적", property_type: type, price_text: "", name: "", region: "" });
test("아파트 월별 중위가격·거래량·3.3㎡당, 다른 유형 제외", () => {
  const rows = [tr("2026-09-02", 9), tr("2026-09-10", 11), tr("2026-09-20", 10), tr("2026-10-01", 12), tr("2026-10-05", 12), tr("2026-10-07", 13), tr("2026-11-01", 14), tr("2026-10-01", 3, 50, "오피스텔")];
  const a = aptAnalysis(rows, ["202611", "202610", "202609"]);
  assert.deepEqual(a.months.map((m) => [m.month, m.count, m.median]), [["202609", 3, 10], ["202610", 3, 12], ["202611", 1, 14]]);
  assert.equal(a.total, 7);
  assert.ok(Math.abs(a.months[0].perPyeong - (10 / 84) * 3.3058) < 1e-9);
  assert.match(a.summary, /10월 기준 중위가격이 9월 대비 \+20\.0%/);
  assert.match(a.summary, /가격 예측이 아닙니다/);
});
test("거래 부족·없음은 해석하지 않는다", () => {
  assert.match(aptAnalysis([tr("2026-10-01", 9)], ["202610"]).summary, /1건뿐/);
  assert.match(aptAnalysis([], ["202610"]).summary, /거래가 없어요/);
});
