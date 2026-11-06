import test from "node:test";
import assert from "node:assert/strict";
import { NONE, formatDate, stepDateText, formatArea, formatCount, parseNumberInput } from "../../web/src/lib/zipFormat.ts";

test("날짜: 순수 날짜는 그대로, 시각은 한국 날짜로, 없거나 잘못되면 정보 없음", () => {
  assert.equal(formatDate("2020-01-02"), "2020.01.02");
  assert.equal(formatDate("2026-11-01T16:30:00+00:00"), "2026.11.02"); // UTC 16:30 = KST 다음 날 01:30
  assert.equal(formatDate("2026-11-01T14:00:00+00:00"), "2026.11.01");
  for (const bad of [null, undefined, "", "어제", "2026-13-45xx"]) assert.equal(formatDate(bad), NONE);
});

test("단계 날짜: ISO는 날짜로, 연도 2자리 원문은 원문 그대로(세기 추정 없음), 없으면 안내", () => {
  assert.equal(stepDateText({ date: "2021-03-04", date_display: "2021-03-04", date_precision: "ISO_DATE" }), "2021.03.04");
  assert.equal(stepDateText({ date: null, date_display: "14.12.15", date_precision: "SOURCE_SHORT_YEAR" }), "14.12.15 (원문)");
  assert.equal(stepDateText({ date: null, date_display: null, date_precision: null }), "일자 정보 없음");
  assert.ok(!stepDateText({ date: null, date_display: "14.12.15", date_precision: "SOURCE_SHORT_YEAR" }).includes("2014"));
});

test("면적·개수: 값이 없거나 0 이하면 정보 없음 (0을 값처럼 보이지 않는다)", () => {
  assert.equal(formatArea(12345.6), "12,346㎡");
  assert.equal(formatCount(1200, "세대"), "1,200세대");
  for (const bad of [null, undefined, 0, -1, NaN]) {
    assert.equal(formatArea(bad), NONE);
    assert.equal(formatCount(bad, "세대"), NONE);
  }
});

test("입력 문자열 파싱: 빈 입력은 null, 쉼표 제거, 숫자가 아니면 NaN", () => {
  assert.equal(parseNumberInput(""), null);
  assert.equal(parseNumberInput("   "), null);
  assert.equal(parseNumberInput("50,000"), 50000);
  assert.equal(parseNumberInput("3.5"), 3.5);
  assert.ok(Number.isNaN(parseNumberInput("abc")));
});
