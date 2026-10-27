// 실행: node --test src/lib/interestTicker.test.mjs   (apps/moneyon/web에서, Node 22.6+)
import test from "node:test";
import assert from "node:assert/strict";
import { rawInterest, estimatedRaw, weekProgress, accrued, daysLeft, deltaWon } from "./interestTicker.ts";

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

test("주간 진행률은 0~1로 제한되고 하루 안에서는 시계만큼만 오른다", () => {
  const noon = new Date(2026, 9, 28, 12, 0, 0);
  assert.equal(weekProgress("2026-10-12", "2026-10-12", "2026-10-19", new Date(2026, 9, 28, 0, 0, 0)), 0);
  assert.ok(Math.abs(weekProgress("2026-10-12", "2026-10-12", "2026-10-19", noon) - 0.5 / 7) < 1e-9);
  assert.equal(weekProgress("2026-10-30", "2026-10-12", "2026-10-19", noon), 1);
  assert.equal(weekProgress("2026-10-01", "2026-10-12", "2026-10-19", noon), 0);
  assert.equal(weekProgress("2026-10-12", "2026-10-19", "2026-10-19", noon), 0);
});

test("표시 값은 예상 이자를 넘지 않고 틱마다 0.01원씩 오른다", () => {
  assert.equal(accrued(100, 0, 0), 0);
  assert.ok(Math.abs(accrued(100, 0.5, 3) - 50.03) < 1e-9);
  assert.equal(accrued(100, 0.999, 10_000), 100);
  assert.equal(accrued(0, 0.5, 50), 0);
});

test("정산일까지 남은 날과 이자 변화량", () => {
  assert.equal(daysLeft("2026-10-14", "2026-10-19"), 5);
  assert.equal(daysLeft("2026-10-19", "2026-10-19"), 0);
  assert.equal(daysLeft("2026-10-25", "2026-10-19"), 0);
  assert.equal(deltaWon(2250, 2150), -100);
  assert.equal(deltaWon(100, 100.2), 0);
});
