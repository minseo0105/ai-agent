// 투자금 계산(설계 §5). 단위는 만원. 권리가액·추가분담금·총투자금·손익의 관계와 중복 계산 방지를 검증한다.
import test from "node:test";
import assert from "node:assert/strict";
import {
  calculate, applyDeltas, compareScenarios, formatManwon, DEFAULT_DELTAS, FORMULA_LINES, REQUIRED_FOR_RIGHTS,
} from "../../web/src/lib/investmentCalc.ts";

const near = (actual, expected, message) =>
  assert.ok(Math.abs(actual - expected) < 1e-9, `${message ?? ""} expected ${expected} got ${actual}`);

// 기준 예시: P=5억, A=3억, 비례율 100%, 분양가 4.5억, 취득비용 2,500만, 대출 2억, 금리 5%, 36개월, 기타 500만, 가정 시세 9억
const BASE = {
  purchasePrice: 50000, appraisedValue: 30000, proportionalRate: 100, memberSalePrice: 45000,
  acquisitionCost: 2500, loanAmount: 20000, interestRate: 5, holdingMonths: 36, otherCost: 500,
  futureMarketValue: 90000,
};
const BLANK = Object.fromEntries(Object.keys(BASE).map((k) => [k, null]));

test("기준 예시의 모든 값이 정의대로 계산된다", () => {
  const r = calculate(BASE);
  near(r.rightsValue, 30000, "권리가액 = A × r");
  near(r.contribution, 15000, "추가분담금 = S − R");
  assert.equal(r.contributionKind, "PAY");
  near(r.additionalPayment, 15000);
  near(r.refund, 0);
  near(r.financeCost, 3000, "금융비용 = L × i × m/12");
  near(r.totalInvestment, 71000, "총투자금 = P + C + X + F + E");
  near(r.equity, 51000, "자기자본 = T − L");
  near(r.profit, 19000, "손익 = V − T");
  near(r.roi, 19000 / 51000);
  assert.deepEqual(r.missingRequired, []);
});

// ---- 중복 계산 방지: 관계 검증식 ----
test("관계식 1: T − (P + C + F + E) = X", () => {
  for (const s of [20000, 30000, 45000, 80000]) {
    const r = calculate({ ...BASE, memberSalePrice: s });
    near(r.totalInvestment - (BASE.purchasePrice + BASE.acquisitionCost + r.financeCost + BASE.otherCost), r.contribution);
  }
});

test("관계식 2: 권리가액이 변해도 총투자금은 오직 추가분담금을 통해서만 변한다 (ΔT = −ΔR)", () => {
  const a = calculate(BASE);
  for (const change of [{ appraisedValue: 36000 }, { proportionalRate: 112.5 }, { appraisedValue: 12345, proportionalRate: 77 }]) {
    const b = calculate({ ...BASE, ...change });
    near(b.totalInvestment - a.totalInvestment, -(b.rightsValue - a.rightsValue), JSON.stringify(change));
  }
});

test("관계식 3: 분양가 = 권리가액이면 분담금 0, 총투자금 = P + C + F + E", () => {
  const r = calculate({ ...BASE, memberSalePrice: 30000 });
  near(r.contribution, 0);
  assert.equal(r.contributionKind, "ZERO");
  near(r.totalInvestment, 50000 + 2500 + 3000 + 500);
});

test("관계식 4: 가정 시세 = 총투자금이면 손익 0", () => {
  const first = calculate(BASE);
  const r = calculate({ ...BASE, futureMarketValue: first.totalInvestment });
  near(r.profit, 0);
  near(r.roi, 0);
});

test("권리가액은 총투자금에 더하지 않는다 (이중 계산 금지)", () => {
  // 권리가액을 더했다면 총투자금이 R만큼 커졌을 것이다. 같은 X(=분양가−R)를 만드는 두 입력은 같은 T를 줘야 한다.
  const a = calculate({ ...BASE, appraisedValue: 30000, proportionalRate: 100, memberSalePrice: 45000 });
  const b = calculate({ ...BASE, appraisedValue: 60000, proportionalRate: 100, memberSalePrice: 75000 });
  near(a.contribution, b.contribution);
  near(a.totalInvestment, b.totalInvestment);
  assert.notEqual(a.rightsValue, b.rightsValue);
});

test("금융비용은 총투자금에 한 번만 들어가고 자기자본은 대출 원금만 뺀다", () => {
  const withLoan = calculate(BASE);
  const noLoan = calculate({ ...BASE, loanAmount: 0 });
  near(noLoan.financeCost, 0);
  near(withLoan.totalInvestment - noLoan.totalInvestment, withLoan.financeCost);
  near(withLoan.equity, withLoan.totalInvestment - BASE.loanAmount);
});

test("가정 시세는 총투자금에 들어가지 않는다", () => {
  near(calculate({ ...BASE, futureMarketValue: 1 }).totalInvestment, calculate({ ...BASE, futureMarketValue: 999999 }).totalInvestment);
});

// ---- 특수 상황 ----
test("추가분담금이 음수이면 환급으로 따로 표시하고 총투자금에는 부호 그대로 한 번만 반영한다", () => {
  const r = calculate({ ...BASE, memberSalePrice: 25000 });
  near(r.contribution, -5000);
  assert.equal(r.contributionKind, "REFUND");
  near(r.refund, 5000);
  near(r.additionalPayment, 0);
  near(r.totalInvestment, 50000 + 2500 - 5000 + 3000 + 500);
});

test("자기자본이 0 이하이면 수익률을 계산하지 않고 경고한다", () => {
  const r = calculate({ ...BASE, loanAmount: 80000 });
  assert.ok(r.equity <= 0);
  assert.equal(r.roi, null);
  assert.ok(r.warnings.some((w) => w.code === "EQUITY_NON_POSITIVE"));
});

test("자기자본이 음수여도(대출이 총투자금보다 큼) 수익률을 계산하지 않는다", () => {
  const r = calculate({ ...BASE, loanAmount: 90000 });
  assert.ok(r.equity < 0, `equity ${r.equity}`);
  assert.equal(r.roi, null);
  assert.notEqual(r.profit, null); // 손익 자체는 계산된다
  assert.ok(r.warnings.some((w) => w.code === "EQUITY_NON_POSITIVE"));
});

test("대출금액이 매입가격보다 크면 경고한다", () => {
  assert.ok(calculate({ ...BASE, loanAmount: 60000 }).warnings.some((w) => w.code === "LOAN_EXCEEDS_PRICE"));
  assert.ok(!calculate(BASE).warnings.some((w) => w.code === "LOAN_EXCEEDS_PRICE"));
});

test("비례율이 비정상 범위이면 계산은 하되 경고한다", () => {
  for (const rate of [0, 250]) {
    const r = calculate({ ...BASE, proportionalRate: rate });
    assert.notEqual(r.rightsValue, null);
    assert.ok(r.warnings.some((w) => w.code === "RATE_RANGE"), String(rate));
  }
  assert.ok(!calculate({ ...BASE, proportionalRate: 100 }).warnings.some((w) => w.code === "RATE_RANGE"));
});

// ---- 입력이 없을 때 값을 만들어 내지 않는다 ----
test("아무것도 입력하지 않으면 모든 결과가 null이고 필수 항목을 알려준다", () => {
  const r = calculate(BLANK);
  for (const key of ["rightsValue", "contribution", "totalInvestment", "equity", "profit", "roi", "financeCost"]) {
    assert.equal(r[key], null, key);
  }
  assert.deepEqual(r.missingRequired.sort(), ["appraisedValue", "futureMarketValue", "memberSalePrice", "proportionalRate", "purchasePrice"].sort());
});

test("권리가액·분담금은 감정평가액·비례율·분양가만 있으면 나온다", () => {
  const r = calculate({ ...BLANK, appraisedValue: 30000, proportionalRate: 100, memberSalePrice: 45000 });
  near(r.rightsValue, 30000);
  near(r.contribution, 15000);
  assert.equal(r.totalInvestment, null); // 매입가격이 없다
  assert.deepEqual(REQUIRED_FOR_RIGHTS.slice().sort(), ["appraisedValue", "memberSalePrice", "proportionalRate"]);
});

test("선택 항목이 비면 0으로 계산하되 미입력 항목을 알려준다", () => {
  const r = calculate({ ...BASE, acquisitionCost: null, otherCost: null, loanAmount: null, interestRate: null, holdingMonths: null });
  near(r.totalInvestment, 50000 + 15000);
  assert.deepEqual(r.missingOptional.sort(), ["acquisitionCost", "holdingMonths", "interestRate", "loanAmount", "otherCost"].sort());
});

test("대출이 있는데 금리나 보유기간이 없으면 금융비용을 만들지 않고 총투자금도 내지 않는다", () => {
  for (const missing of ["interestRate", "holdingMonths"]) {
    const r = calculate({ ...BASE, [missing]: null });
    assert.equal(r.financeCost, null, missing);
    assert.equal(r.totalInvestment, null, missing);
    assert.ok(r.missingRequired.includes(missing), missing);
  }
});

test("가정 시세가 없으면 손익과 수익률은 null이지만 총투자금은 나온다", () => {
  const r = calculate({ ...BASE, futureMarketValue: null });
  near(r.totalInvestment, 71000);
  assert.equal(r.profit, null);
  assert.equal(r.roi, null);
});

test("비정상 입력(NaN·무한대·음수·문자열)은 값으로 쓰지 않고 invalid로 알린다", () => {
  for (const bad of [NaN, Infinity, -1, "12", {}]) {
    const r = calculate({ ...BASE, purchasePrice: bad });
    assert.equal(r.totalInvestment, null);
    assert.ok(r.invalid.includes("purchasePrice"), String(bad));
    assert.ok(!JSON.stringify(r).includes("NaN"));
  }
});

test("결과에 NaN·Infinity가 절대 들어가지 않는다", () => {
  const cases = [BLANK, BASE, { ...BASE, loanAmount: 0, holdingMonths: 0 }, { ...BASE, appraisedValue: 0 },
    { ...BASE, memberSalePrice: 0 }, { ...BASE, proportionalRate: 0 }];
  for (const input of cases) {
    for (const value of Object.values(calculate(input))) {
      if (typeof value === "number") assert.ok(Number.isFinite(value));
    }
  }
});

test("입력 객체를 수정하지 않는다", () => {
  const input = { ...BASE };
  const copy = JSON.stringify(input);
  calculate(input);
  applyDeltas(input, DEFAULT_DELTAS.conservative);
  assert.equal(JSON.stringify(input), copy);
});

// ---- 시나리오 ----
test("조정폭 적용: 비례율 %p, 분양가·시세 %, 보유기간·금리 가산, 나머지는 고정", () => {
  const out = applyDeltas(BASE, { proportionalRate: -5, salePricePct: 5, marketValuePct: -10, holdingMonths: 12, interestRate: 1 });
  near(out.proportionalRate, 95);
  near(out.memberSalePrice, 47250);
  near(out.futureMarketValue, 81000);
  near(out.holdingMonths, 48);
  near(out.interestRate, 6);
  for (const key of ["purchasePrice", "appraisedValue", "acquisitionCost", "loanAmount", "otherCost"]) {
    assert.equal(out[key], BASE[key], key);
  }
});

test("조정 결과는 0 아래로 내려가지 않고, 비어 있던 입력을 값으로 만들지 않는다", () => {
  const out = applyDeltas({ ...BASE, holdingMonths: 3, interestRate: 0.5 }, { proportionalRate: 0, salePricePct: 0, marketValuePct: 0, holdingMonths: -6, interestRate: -1 });
  assert.equal(out.holdingMonths, 0);
  assert.equal(out.interestRate, 0);
  const blank = applyDeltas(BLANK, DEFAULT_DELTAS.conservative);
  for (const value of Object.values(blank)) assert.equal(value, null);
});

test("세 시나리오는 같은 계산식을 쓴다 (시나리오별 별도 식 없음)", () => {
  const out = compareScenarios(BASE, DEFAULT_DELTAS);
  assert.deepEqual(out.base.result, calculate(BASE));
  assert.deepEqual(out.conservative.result, calculate(applyDeltas(BASE, DEFAULT_DELTAS.conservative)));
  assert.deepEqual(out.optimistic.result, calculate(applyDeltas(BASE, DEFAULT_DELTAS.optimistic)));
});

test("기본 조정폭에서 손익은 보수 < 기준 < 낙관 순서다", () => {
  const out = compareScenarios(BASE, DEFAULT_DELTAS);
  assert.ok(out.conservative.result.profit < out.base.result.profit);
  assert.ok(out.base.result.profit < out.optimistic.result.profit);
});

test("조정폭을 바꾸면 결과가 따라 바뀐다 (수정 가능)", () => {
  const custom = { ...DEFAULT_DELTAS, conservative: { ...DEFAULT_DELTAS.conservative, marketValuePct: -30 } };
  assert.ok(compareScenarios(BASE, custom).conservative.result.profit < compareScenarios(BASE, DEFAULT_DELTAS).conservative.result.profit);
});

test("조정폭 기본값이 설계 문서의 값과 같다", () => {
  assert.deepEqual(DEFAULT_DELTAS.conservative, { proportionalRate: -5, salePricePct: 5, marketValuePct: -10, holdingMonths: 12, interestRate: 1 });
  assert.deepEqual(DEFAULT_DELTAS.optimistic, { proportionalRate: 5, salePricePct: -3, marketValuePct: 10, holdingMonths: -6, interestRate: -0.5 });
});

// ---- 표시 ----
test("계산식 안내문은 화면과 같은 식을 담는다", () => {
  const text = FORMULA_LINES.join("\n");
  for (const token of ["권리가액", "추가분담금", "금융비용", "총투자금", "자기자본", "손익", "수익률"]) {
    assert.ok(text.includes(token), token);
  }
  assert.ok(text.includes("권리가액은 총투자금에 더하지 않"));
});

test("금액 표시: 만원 단위를 억·만원으로, 없으면 대시", () => {
  assert.equal(formatManwon(71000), "7억 1,000만원");
  assert.equal(formatManwon(2500), "2,500만원");
  assert.equal(formatManwon(100000), "10억원");
  assert.equal(formatManwon(0), "0원");
  assert.equal(formatManwon(-5000), "-5,000만원");
  assert.equal(formatManwon(-12500), "-1억 2,500만원");
  assert.equal(formatManwon(null), "—");
  assert.equal(formatManwon(NaN), "—");
});
