import test from "node:test";
import assert from "node:assert/strict";
import { budgetCheck, compareListing, dongReview, failedTypes } from "../../web/src/lib/budgetReview.ts";
import { calculate } from "../../web/src/lib/investmentCalc.ts";

const sim = (o) => ({ purchasePrice: null, appraisedValue: null, proportionalRate: null, memberSalePrice: null, acquisitionCost: null, loanAmount: null, interestRate: null, holdingMonths: null, otherCost: null, futureMarketValue: null, ...o });
const tr = (region, price, area, type = "아파트", name = "A단지", floor = "5", build_year = "1990") =>
  ({ date: "2026-10-01", price_100m: price, area, area_basis: "전용면적", property_type: type, name, region, price_text: "", floor, build_year });

test("예산: 필요 자기자금·여유/부족·최대 매입가격, 대출은 입력값 그대로", () => {
  const s = sim({ purchasePrice: 100000, acquisitionCost: 4000, loanAmount: 50000 });
  const r = budgetCheck({ cash: 60000, reserve: 5000, income: 10000, debt: 2000, homes: "1" }, s, calculate(s));
  assert.equal(r.available, 55000);
  assert.equal(r.need, 54000); // 100000 + 4000 − 50000
  assert.equal(r.gap, 1000);
  assert.equal(r.ceiling, 101000); // 55000 + 50000 − 4000
  assert.equal(r.debtMultiple, 5.2);
  assert.equal(r.contributionIncluded, false);
  assert.ok(r.notes.some((n) => /LTV·DSR/.test(n)));
  assert.ok(r.notes.some((n) => /DSR이 아니에요/.test(n)));
  assert.ok(r.notes.some((n) => /추가분담금이 빠져/.test(n)));
  assert.ok(r.notes.some((n) => /주택을 보유하면/.test(n)));
});

test("예산: 추가분담금이 있으면 필요 자기자금에 포함, 현금 미입력이면 최대가 없음", () => {
  const s = sim({ purchasePrice: 80000, appraisedValue: 50000, proportionalRate: 100, memberSalePrice: 70000 });
  const r = budgetCheck({ cash: null, reserve: null, income: null, debt: null, homes: "" }, s, calculate(s));
  assert.equal(r.need, 100000); // 80000 + 분담금 20000
  assert.equal(r.ceiling, null);
  assert.equal(r.contributionIncluded, true);
});

test("지역: 정비사업이 있는 동만, 예산 이하 거래 수 순", () => {
  const rows = [tr("문정동", 10, 84), tr("문정동", 14, 84), tr("가락동", 8, 59), tr("가락동", 9, 59), tr("잠실동", 30, 84)];
  const projects = [{ name: "P1", dong: "문정동", stage: { label: "사업시행인가" }, investor_guide: { risk_label: "중간", risk_level: "MEDIUM" } }, { name: "P2", dong: "가락동", stage: { label: "조합설립" } }];
  const d = dongReview(rows, projects, 95000);
  assert.deepEqual(d.map((x) => [x.dong, x.trades, x.withinBudget]), [["가락동", 2, 2], ["문정동", 2, 0]]);
  assert.equal(d[1].median, 12);
  assert.equal(dongReview(rows, projects, null)[0].withinBudget, null);
});

test("비교: 표본 3건 미만이면 가격 범위를 내지 않는다", () => {
  const r = compareListing([tr("문정동", 10, 84), tr("문정동", 11, 84)], { dong: "문정동", type: "아파트", area: 84, ask: 100000, complex: "" });
  assert.equal(r.ok, false);
  assert.match(r.reason, /2건이라 참고 거래가격 범위를 낼 수 없어요/);
});

test("비교: 같은 동·유형·±15% 면적으로 범위와 조건, 다른 유형·면적 제외", () => {
  const rows = [tr("문정동", 10, 84, "아파트", "A", "3", "1988"), tr("문정동", 11, 84, "아파트", "A", "7", "1988"), tr("문정동", 12, 84, "아파트", "B", "10", "1995"),
    tr("문정동", 30, 150), tr("문정동", 5, 84, "연립·다세대"), tr("가락동", 20, 84)];
  const r = compareListing(rows, { dong: "문정동", type: "아파트", area: 84, ask: 130000, complex: "" });
  assert.equal(r.ok, true);
  assert.equal(r.n, 3);
  assert.deepEqual([r.low, r.mid, r.high], [105000, 110000, 115000]);
  assert.equal(r.position, "ABOVE");
  assert.equal(r.conditions.floors, "3~10");
  assert.equal(r.conditions.years, "1988~1995");
  assert.equal(r.basis, "같은 동·유형·비슷한 면적");
  assert.equal(r.similar, false);
  assert.match(r.caution, /일치하는 거래가 부족/);
});

test("비교: 건축연도 ±5년 거래가 3건 이상이면 그 거래만, 연식 차이가 크면 주의", () => {
  const old = [tr("문정동", 10, 84, "아파트", "A", "3", "1986"), tr("문정동", 10.4, 84, "아파트", "B", "5", "1988"), tr("문정동", 10.2, 84, "아파트", "C", "9", "1990")];
  const rows = [...old, tr("문정동", 20, 84, "아파트", "D", "4", "2020")];
  const r = compareListing(rows, { dong: "문정동", type: "아파트", area: 84, ask: null, complex: "", buildYear: 1988 });
  assert.equal(r.n, 3);
  assert.equal(r.similar, true);
  assert.equal(r.caution, undefined);
  const wide = compareListing(rows, { dong: "문정동", type: "아파트", area: 84, ask: null, complex: "" });
  assert.equal(wide.n, 4);
  assert.match(wide.caution, /건축연도 차이가 34년/);
});

test("조회 실패 유형: 403과 기타 실패를 구분", () => {
  const m = failedTypes(["서울 > 송파구 · 연립·다세대: 공공데이터포털 활용신청이 필요한 API입니다 (403)", "서울 > 송파구 · 오피스텔: 시간 초과"]);
  assert.equal(m.get("연립·다세대"), "FORBIDDEN");
  assert.equal(m.get("오피스텔"), "FAILED");
  assert.equal(m.get("아파트"), undefined);
});
