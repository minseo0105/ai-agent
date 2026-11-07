import test from "node:test";
import assert from "node:assert/strict";
import { STATUS_LABEL, EMPTY_MONEY, dealCondition, formatAmountInput, fundsCondition, fundsFor, loanScenarios, monthlyPayment, priceCeiling, projectKind, rightsCondition, transferNote } from "../../web/src/lib/investDecision.ts";

const M = (o) => ({ ...EMPTY_MONEY, ...o });

test("금액 입력: 천 단위 쉼표, 숫자 외 제거, 빈칸 유지", () => {
  assert.equal(formatAmountInput("75000"), "75,000");
  assert.equal(formatAmountInput("1,2a34,567"), "1,234,567");
  assert.equal(formatAmountInput(""), "");
  assert.equal(formatAmountInput("0"), "0");
  assert.equal(formatAmountInput("3.5"), "3.5");
});

test("원리금균등 월 상환액과 0%·미입력 처리", () => {
  assert.ok(Math.abs(monthlyPayment(12000, 6, 1) - 1032.7972) < 1e-3);
  assert.equal(monthlyPayment(12000, 0, 1), 1000);
  assert.equal(monthlyPayment(12000, null, 30), null);
  assert.equal(monthlyPayment(0, null, null), 0);
});

test("가격 상한: 부대비용 빈칸은 미입력 표시, 0%는 입력으로 처리", () => {
  assert.deepEqual(priceCeiling(M({ cash: 50000, reserve: 5000 }), 40000), { value: 85000, costMissing: true, invalid: false });
  assert.deepEqual(priceCeiling(M({ cash: 50000, reserve: 5000, costRate: 0 }), 40000), { value: 85000, costMissing: false, invalid: false });
  assert.equal(Math.round(priceCeiling(M({ cash: 52000, costRate: 4 }), 0).value), 50000);
  assert.equal(priceCeiling(M({}), 0).value, null);
});

test("대출 시나리오 0·절반·전액, 부담률은 기존+신규 연 상환 ÷ 연소득", () => {
  const s = loanScenarios(M({ cash: 30000, income: 10000, debtAnnual: 500, loan: 20000, rate: 0, years: 10 }));
  assert.deepEqual(s.map((x) => x.loan), [0, 10000, 20000]);
  assert.equal(s[2].monthly, 20000 / 120);
  assert.equal(s[2].burden, (500 + 2000) / 10000);
  assert.equal(s[0].ceiling, 30000);
  assert.deepEqual(loanScenarios(M({ cash: 1 })), []);
});

test("자금 조건: 부족이면 미충족, 비용 미입력·대출 미확인은 추가 확인, 모두 갖추면 충족", () => {
  assert.equal(fundsCondition(M({ cash: 50000 }), null).status, "CHECK");
  assert.equal(fundsCondition(M({ cash: 30000, loan: 10000 }), 50000).status, "NOT_MET");
  assert.equal(fundsCondition(M({ cash: 60000 }), 50000).status, "CHECK"); // 부대비용 빈칸
  assert.equal(fundsCondition(M({ cash: 30000, loan: 30000, costRate: 4 }), 50000).status, "CHECK"); // 대출 미확인
  const ok = fundsCondition(M({ cash: 30000, loan: 30000, costRate: 4, loanConfirmed: true }), 50000);
  assert.equal(ok.status, "MET");
  assert.match(ok.summary, /대출 승인·매수 가능 확정 아님/);
  const f = fundsFor(M({ cash: 30000, reserve: 2000, loan: 20000, costRate: 4 }), 50000);
  assert.deepEqual([f.need, f.available, f.shortfall], [52000, 28000, 4000]);
});

test("거래·허가와 권리 조건은 근거가 없으므로 항상 추가 확인 필요", () => {
  for (const m of [M({}), M({ purpose: "invest", homes: "2+" })]) assert.equal(dealCondition(m).status, "CHECK");
  assert.ok(dealCondition(M({ purpose: "invest" })).items.some((i) => /실거주 의무/.test(i)));
  const r = rightsCondition({ business: "재건축", plan: null }, "MANAGEMENT_DISPOSITION", false);
  assert.equal(r.status, "CHECK");
  assert.match(r.items[0], /구역 안인지 확인되지 않았어요/);
  for (const i of r.items) assert.doesNotMatch(i, /승계할 수 있어요|입주권이 나와요|매수 가능/);
});

test("사업 유형과 양도 제한 시점 안내", () => {
  assert.deepEqual(projectKind({ type_label: "정비사업", program_label: "신속통합기획" }), { business: null, plan: "신속통합기획" });
  assert.match(transferNote({ business: "재건축", plan: null }, "ASSOCIATION_APPROVED"), /그 단계 이후로 표시/);
  assert.match(transferNote({ business: "재개발", plan: null }, "ASSOCIATION_APPROVED"), /아직 그 단계 전/);
  assert.match(transferNote({ business: null, plan: "신속통합기획" }, "COMMITTEE"), /유형.*확인되지 않아/);
  assert.match(transferNote({ business: "재개발", plan: null }, "UNKNOWN"), /현재 단계가 확인되지 않아요/);
});

import { calculate } from "../../web/src/lib/investmentCalc.ts";
import { budgetCheck } from "../../web/src/lib/budgetReview.ts";

test("충족 문구는 가정 기준이며 승인·매수 가능 표현이 없다", () => {
  assert.equal(STATUS_LABEL.MET, "입력한 자금 가정상 충족");
  for (const v of Object.values(STATUS_LABEL)) assert.doesNotMatch(v, /승인|매수 가능/);
});

test("같은 입력이면 기존 시뮬레이터·예산 점검과 새 자금 계산이 일치", () => {
  // 매입 10억, 부대비용 4%(=4,000만원), 대출 5억, 현금 6억, 예비비 5,000만원, 추가분담금 0, 이자 0(새 자금 계산은 이자를 포함하지 않음)
  const price = 100000, loan = 50000;
  const m = { ...EMPTY_MONEY, cash: 60000, reserve: 5000, loan, costRate: 4, loanConfirmed: true };
  const f = fundsFor(m, price);
  const simIn = { purchasePrice: price, appraisedValue: 60000, proportionalRate: 100, memberSalePrice: 60000, acquisitionCost: 4000, loanAmount: loan, interestRate: 0, holdingMonths: 12, otherCost: null, futureMarketValue: null };
  const sim = calculate(simIn);
  assert.equal(sim.equity, f.need - loan); // 시뮬레이터 자기자본 = 필요자금 − 대출
  const b = budgetCheck({ cash: 60000, reserve: 5000, income: null, debt: null, homes: "" }, simIn, sim);
  assert.equal(b.need, f.need - loan);
  assert.equal(b.gap, -f.shortfall);
  // 상한 가격에서는 두 방식(정액 부대비용·비율 부대비용)이 같은 값을 낸다.
  const cap = priceCeiling(m, loan).value;
  const capIn = { ...simIn, purchasePrice: cap, acquisitionCost: cap * 0.04 };
  assert.ok(Math.abs(budgetCheck({ cash: 60000, reserve: 5000, income: null, debt: null, homes: "" }, capIn, calculate(capIn)).gap) < 1e-6);
});

test("정비구역 경계가 없으면 매물을 구역 안 물건으로 확정하지 않는다", () => {
  const r = rightsCondition({ business: "재개발", plan: null }, "MANAGEMENT_DISPOSITION", false);
  assert.equal(r.status, "CHECK");
  assert.ok(r.items.some((i) => /구역 안인지 확인되지 않았어요/.test(i)));
  for (const i of [r.summary, ...r.items]) assert.doesNotMatch(i, /구역 안(의| 물건)이에요|구역에 포함돼요|조합원이 될 수 있어요/);
});
