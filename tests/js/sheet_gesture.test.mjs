// 모바일 시트 손잡이 제스처 판정. 탭은 전환, 위로 끌기는 펼침, 아래로 끌기는 줄임/닫기.
import test from "node:test";
import assert from "node:assert/strict";
import { sheetGesture, SWIPE_DISTANCE, TAP_SLOP } from "../../web/src/lib/sheetGesture.ts";

test("거의 움직이지 않은 손잡이 누름은 탭이라 펼침/줄임을 전환한다", () => {
  for (const delta of [0, 3, -3, TAP_SLOP - 1, -(TAP_SLOP - 1)]) assert.equal(sheetGesture(delta, "peek"), "toggle", String(delta));
  assert.equal(sheetGesture(0, "full"), "toggle");
});

test("위로 충분히 끌면 어느 단계에서든 full", () => {
  assert.equal(sheetGesture(-(SWIPE_DISTANCE + 1), "peek"), "full");
  assert.equal(sheetGesture(-(SWIPE_DISTANCE + 1), "full"), "full");
});

test("아래로 충분히 끌면 full → peek, peek → 닫기", () => {
  assert.equal(sheetGesture(SWIPE_DISTANCE + 1, "full"), "peek");
  assert.equal(sheetGesture(SWIPE_DISTANCE + 1, "peek"), "close");
});

test("탭과 스와이프 사이의 어중간한 움직임은 아무것도 하지 않는다 (실수로 닫히지 않게)", () => {
  for (const delta of [TAP_SLOP, TAP_SLOP + 5, SWIPE_DISTANCE, -TAP_SLOP, -SWIPE_DISTANCE]) {
    assert.equal(sheetGesture(delta, "peek"), null, String(delta));
    assert.equal(sheetGesture(delta, "full"), null, String(delta));
  }
});

test("경계값: 정확히 SWIPE_DISTANCE는 스와이프가 아니다", () => {
  assert.equal(sheetGesture(SWIPE_DISTANCE, "full"), null);
  assert.equal(sheetGesture(-SWIPE_DISTANCE, "peek"), null);
});

test("잘못된 값(NaN·무한대)은 무시한다", () => {
  for (const bad of [NaN, Infinity, -Infinity]) assert.equal(sheetGesture(bad, "peek"), null);
});
