import test from "node:test";
import assert from "node:assert/strict";
import { classify, recentMonths, regionLabel, sameDong } from "../../web/src/lib/zoneTrades.ts";

test("403, 미연동, 거래 없음, 실패를 서로 구분한다", () => {
  assert.equal(classify({ apiKeyConfigured: false, rows: [], errors: [] }), "NOT_CONNECTED");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["서울 > 강동구 · 아파트: 공공데이터포털 활용신청이 필요한 API입니다 (403)"] }), "FORBIDDEN");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["x: PUBLIC_DATA_API_KEY가 없습니다."] }), "NOT_CONNECTED");
  assert.equal(classify({ apiKeyConfigured: true, rows: [], errors: ["x: timeout"] }), "FAILED");
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
