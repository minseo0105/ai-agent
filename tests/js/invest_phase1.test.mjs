import test from "node:test";
import assert from "node:assert/strict";
import { COST_SCOPE, EMPTY_MONEY, RULES, formatAmountInput, fundsCondition, fundsFor, loanScenarios, moneyInvalid, parseField, priceCeiling } from "../../web/src/lib/investDecision.ts";
import { CONSENT_KEY, LEGACY_BUDGET_KEY, MONEY_KEY, SIM_PREFIX, clearFinancial, finKeys, hasConsent, hasLegacy, readFin, setConsent, writeFin } from "../../web/src/lib/finStorage.ts";
import { budgetCheck } from "../../web/src/lib/budgetReview.ts";
import { calculate } from "../../web/src/lib/investmentCalc.ts";

const M = (o) => ({ ...EMPTY_MONEY, ...o });

test("입력 검증: 빈칸·0·형식 오류·범위 오류를 구분", () => {
  assert.deepEqual(parseField("", RULES.amount), { value: null, error: null });
  assert.deepEqual(parseField("0", RULES.amount), { value: 0, error: null });
  assert.equal(parseField("70,000", RULES.amount).value, 70000);
  for (const bad of [".", "1.2.3", "0.", "-1", "1e5", "Infinity", "NaN", "abc", "1..2"]) {
    assert.ok(parseField(bad, RULES.amount).error, `"${bad}" 는 오류여야 함`);
  }
  assert.ok(parseField("31", RULES.percent).error);
  assert.equal(parseField("30", RULES.percent).value, 30);
  assert.ok(parseField("0", RULES.years).error);
  assert.ok(parseField("2.5", RULES.years).error);
  assert.ok(parseField("0", RULES.price).error);
  assert.ok(parseField("10000001", RULES.amount).error);
});

test("소수점이 여러 개면 합치지 않고 남겨 오류로 잡는다", () => {
  assert.equal(formatAmountInput("1.2.3"), "1.2.3");
  assert.ok(parseField(formatAmountInput("1.2.3"), RULES.amount).error);
  assert.equal(formatAmountInput("1234.5"), "1,234.5");
});

test("잘못된 입력은 계산을 무효화하고 '충족'이 나오지 않는다", () => {
  const ok = { cash: 90000, costRate: 4, loanConfirmed: true };
  assert.equal(fundsCondition(M(ok), 50000).status, "MET");
  const cases = [
    M({ ...ok, invalid: ["부대비용 가정"] }),
    M({ ...ok, costRate: Number.NaN }),
    M({ ...ok, rate: Number.POSITIVE_INFINITY }),
    M({ ...ok, cash: -1 }),
  ];
  for (const m of cases) {
    const c = fundsCondition(m, 50000);
    assert.equal(c.status, "CHECK");
    assert.match(c.summary, /입력 오류·추가 확인 필요/);
    assert.equal(priceCeiling(m, 0).value, null);
    assert.equal(priceCeiling(m, 0).invalid, true);
    assert.deepEqual(fundsFor(m, 50000).need, null);
  }
  for (const p of [Number.NaN, 0, -5, Number.POSITIVE_INFINITY]) assert.equal(fundsCondition(M(ok), p).status, "CHECK");
  assert.deepEqual(loanScenarios(M({ cash: 1, loan: 100, rate: 4, years: 10, invalid: ["대출기간"] })), []);
  assert.deepEqual(moneyInvalid(M({ costRate: Number.NaN })), ["부대비용 가정"]);
});

test("포함·미포함 비용 안내: 취득세는 포함, 보유세·양도세·이자·추가분담금은 미포함", () => {
  assert.match(COST_SCOPE.included, /취득세/);
  for (const w of ["대출 이자", "추가분담금", "보유세", "양도세"]) assert.ok(COST_SCOPE.excluded.includes(w));
  assert.doesNotMatch(COST_SCOPE.excluded, /취득세/);
  const c = fundsCondition(M({ cash: 1 }), 50000);
  for (const i of c.items) assert.doesNotMatch(i, /세금은 포함하지/);
  assert.doesNotMatch(fundsCondition(M({ cash: 90000, costRate: 4, loanConfirmed: true }), 50000).summary, /매수 가능해요|감당할 수 있어요/);
});

function fakeStorage(init = {}) {
  const m = new Map(Object.entries(init));
  return { get length() { return m.size; }, key: (i) => [...m.keys()][i] ?? null, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), _m: m };
}

test("저장: 동의 전에는 읽지도 쓰지도 않는다", () => {
  const s = fakeStorage();
  assert.equal(hasConsent(s), false);
  assert.equal(writeFin(MONEY_KEY, { values: { cash: "1" } }, s), false);
  assert.equal(s.getItem(MONEY_KEY), null);
  setConsent(true, s);
  assert.equal(writeFin(MONEY_KEY, { values: { cash: "1" } }, s), true);
  assert.deepEqual(readFin(MONEY_KEY, s), { values: { cash: "1" } });
});

test("이전 버전 자동 저장값은 '이전 저장값'으로 감지, 동의 전에는 읽지 않음", () => {
  const s = fakeStorage({ [LEGACY_BUDGET_KEY]: '{"cash":"5"}', [`${SIM_PREFIX}abc`]: '{"values":{}}', "other:key": "x" });
  assert.equal(hasLegacy(s), true);
  assert.equal(readFin(LEGACY_BUDGET_KEY, s), null);
  assert.deepEqual(finKeys(s).sort(), [`${SIM_PREFIX}abc`, LEGACY_BUDGET_KEY].sort());
});

test("지우기·저장 끄기: 금융 키(내 자금·예산 점검·사업별 시뮬레이터)와 동의를 모두 지우고 다른 키는 남긴다", () => {
  const init = { [CONSENT_KEY]: "1", [MONEY_KEY]: "{}", [LEGACY_BUDGET_KEY]: "{}", [`${SIM_PREFIX}p1`]: "{}", [`${SIM_PREFIX}p2`]: "{}", "golf:state": "keep" };
  const s = fakeStorage(init);
  assert.equal(clearFinancial(s), 4);
  assert.deepEqual([...s._m.keys()], ["golf:state"]);
  const s2 = fakeStorage(init);
  setConsent(false, s2);
  assert.deepEqual([...s2._m.keys()], ["golf:state"]);
  assert.equal(writeFin(`${SIM_PREFIX}p1`, {}, s2), false);
});

test("같은 현금·예비비·대출이면 예산 점검과 새 자금 계산의 가용 자금이 같다", () => {
  const m = M({ cash: 60000, reserve: 5000, loan: 50000, costRate: 4 });
  const simIn = { purchasePrice: 100000, appraisedValue: 60000, proportionalRate: 100, memberSalePrice: 60000, acquisitionCost: 4000, loanAmount: 50000, interestRate: 0, holdingMonths: 12, otherCost: null, futureMarketValue: null };
  const b = budgetCheck({ cash: m.cash, reserve: m.reserve, income: m.income, debt: m.debt, homes: m.homes }, simIn, calculate(simIn));
  const f = fundsFor(m, 100000);
  assert.equal(b.available, f.available);
  assert.equal(b.gap, -f.shortfall);
});
