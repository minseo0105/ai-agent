// 실행: node --test src/lib/interestTicker.test.mjs   (apps/moneyon/web에서, Node 22.6+)
import test from "node:test";
import assert from "node:assert/strict";
import { rawInterest, estimatedRaw, weekDay, accrued, daysLeft, deltaWon } from "./interestTicker.ts";

const item = (over = {}) => ({ status: "estimated", base: 22500, rate_bps: 1000, cap: null, ...over });

test("서버 reward()와 같은 식: 기준 × 이율, 상한 적용, 버리기 전 값", () => {
  assert.equal(rawInterest(item()), 2250);
  assert.equal(rawInterest(item({ base: 1234, rate_bps: 200, cap: 2000 })), 24.68);
  assert.equal(rawInterest(item({ base: 1_000_000, rate_bps: 200, cap: 2000 })), 2000);
  assert.equal(rawInterest(item({ base: -5 })), 0);
});

test("예상 이자 합계는 estimated 항목만 더한다", () => {
  assert.equal(estimatedRaw([item(), item({ status: "paid", base: 99999 }), item({ base: 5000, rate_bps: 200, cap: 2000 })]), 2250 + 100);
  assert.equal(estimatedRaw(undefined), 0);
});

test("이번 주 며칠째인지는 1~7로 제한된다", () => {
  assert.deepEqual(weekDay("2026-10-12", "2026-10-12", "2026-10-19"), { n: 1, total: 7 });
  assert.deepEqual(weekDay("2026-10-15", "2026-10-12", "2026-10-19"), { n: 4, total: 7 });
  assert.deepEqual(weekDay("2026-10-18", "2026-10-12", "2026-10-19"), { n: 7, total: 7 });
  assert.deepEqual(weekDay("2026-10-19", "2026-10-12", "2026-10-19"), { n: 7, total: 7 });
  assert.deepEqual(weekDay("2026-10-01", "2026-10-12", "2026-10-19"), { n: 1, total: 7 });
  assert.deepEqual(weekDay("2026-10-12", "2026-10-19", "2026-10-19"), { n: 1, total: 1 });
});

test("표시 값은 원 단위 정수이고 예상 이자를 넘지 않으며 시간이 지나도 저절로 오르지 않는다", () => {
  assert.equal(accrued(2250, 1, 7), 321);
  assert.equal(accrued(2250, 7, 7), 2250);
  assert.equal(accrued(2250, 9, 7), 2250);
  assert.equal(accrued(100.7, 7, 7), 100);
  assert.equal(accrued(-5, 3, 7), 0);
  assert.equal(accrued(100, 3, 0), 0);
  assert.ok(Number.isInteger(accrued(1234.56, 3, 7)));
  assert.equal(accrued(2250, 4, 7), accrued(2250, 4, 7));
});

test("정산일까지 남은 날과 이자 변화량", () => {
  assert.equal(daysLeft("2026-10-14", "2026-10-19"), 5);
  assert.equal(daysLeft("2026-10-19", "2026-10-19"), 0);
  assert.equal(daysLeft("2026-10-25", "2026-10-19"), 0);
  assert.equal(deltaWon(2250, 2150), -100);
  assert.equal(deltaWon(100, 100.2), 0);
});
