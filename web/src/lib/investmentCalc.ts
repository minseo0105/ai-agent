/**
 * 투자금·추가분담금 계산(설계 §5). 화면과 무관한 순수 함수이며 단위는 만원이다.
 *
 * 입력은 모두 사용자가 넣은 가정값이다. 공식 사업 자료가 아니다. 입력이 없으면 값을 만들지 않고
 * null로 남긴다(선택 항목만 0으로 계산하고 미입력 항목을 알린다).
 *
 * 중복 계산 방지: 권리가액 R은 추가분담금 X를 구하는 데만 쓰고 총투자금에 더하지 않는다.
 * 매입가격 P는 그 권리를 사는 대가이므로, R과 P를 둘 다 더하면 같은 금액을 두 번 세게 된다.
 * 추가분담금은 부호 그대로 한 번만 더한다(환급이면 음수라서 이미 차감된다).
 */

export type SimInputs = {
  purchasePrice: number | null; // 매입가격 P
  appraisedValue: number | null; // 종전자산 감정평가액 A
  proportionalRate: number | null; // 비례율 r(%)
  memberSalePrice: number | null; // 조합원 분양가 S
  acquisitionCost: number | null; // 취득 관련 비용 C (P와 별개 입력)
  loanAmount: number | null; // 대출금액 L
  interestRate: number | null; // 금리 i(연 %)
  holdingMonths: number | null; // 보유기간 m(개월)
  otherCost: number | null; // 기타 비용 E
  futureMarketValue: number | null; // 가정 준공 후 시세 V
};
export type SimKey = keyof SimInputs;

export const INPUT_KEYS: SimKey[] = [
  "purchasePrice", "appraisedValue", "proportionalRate", "memberSalePrice", "acquisitionCost",
  "loanAmount", "interestRate", "holdingMonths", "otherCost", "futureMarketValue",
];
export const REQUIRED_FOR_RIGHTS: SimKey[] = ["appraisedValue", "proportionalRate", "memberSalePrice"];
const OPTIONAL_KEYS: SimKey[] = ["acquisitionCost", "loanAmount", "interestRate", "holdingMonths", "otherCost"];

export type SimDeltas = {
  proportionalRate: number; // %p
  salePricePct: number; // %
  marketValuePct: number; // %
  holdingMonths: number; // 개월
  interestRate: number; // %p
};
/** 예시 가정이며 사실이 아니다. 화면에서 수정·초기화할 수 있다. */
export const DEFAULT_DELTAS: { conservative: SimDeltas; optimistic: SimDeltas } = {
  conservative: { proportionalRate: -5, salePricePct: 5, marketValuePct: -10, holdingMonths: 12, interestRate: 1 },
  optimistic: { proportionalRate: 5, salePricePct: -3, marketValuePct: 10, holdingMonths: -6, interestRate: -0.5 },
};

export type SimWarning = { code: string; message: string };
export type SimResult = {
  rightsValue: number | null; // 권리가액 R
  contribution: number | null; // 추가분담금 X (부호 있음)
  contributionKind: "PAY" | "REFUND" | "ZERO" | null;
  additionalPayment: number | null; // max(X, 0)
  refund: number | null; // max(−X, 0)
  financeCost: number | null; // 금융비용 F (대출을 입력하지 않았으면 null)
  totalInvestment: number | null; // 총투자금 T
  equity: number | null; // 자기자본 투입액 Q
  profit: number | null; // 가정 손익 G
  roi: number | null; // 가정 수익률(가정 기반 추정치)
  missingRequired: SimKey[];
  missingOptional: SimKey[];
  invalid: SimKey[];
  warnings: SimWarning[];
};

export const FORMULA_LINES = [
  "권리가액 = 종전자산 감정평가액 × 비례율 ÷ 100",
  "추가분담금 = 조합원 분양가 − 권리가액 (음수이면 환급 예상)",
  "금융비용 = 대출금액 × 금리 ÷ 100 × 보유기간(개월) ÷ 12 (단순 이자, 분할상환·복리 미반영)",
  "총투자금 = 매입가격 + 취득 관련 비용 + 추가분담금 + 금융비용 + 기타 비용",
  "자기자본 투입액 = 총투자금 − 대출금액",
  "가정 손익 = 가정 준공 후 시세 − 총투자금",
  "가정 수익률 = 가정 손익 ÷ 자기자본 투입액 (자기자본이 0 이하이면 계산하지 않음)",
  "권리가액은 총투자금에 더하지 않습니다. 매입가격이 그 권리를 사는 대가이고, 권리가액은 추가분담금을 구하는 데만 쓰입니다.",
];

const EPS = 1e-9;

function clean(value: unknown): { value: number | null; invalid: boolean } {
  if (value === null || value === undefined) return { value: null, invalid: false };
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return { value: null, invalid: true };
  return { value, invalid: false };
}

export function calculate(inputs: SimInputs): SimResult {
  const v = {} as Record<SimKey, number | null>;
  const invalid: SimKey[] = [];
  for (const key of INPUT_KEYS) {
    const cleaned = clean((inputs as Record<string, unknown>)[key]);
    v[key] = cleaned.value;
    if (cleaned.invalid) invalid.push(key);
  }
  const loan = v.loanAmount ?? 0;
  const needsFinanceInputs = loan > 0;

  const missingRequired: SimKey[] = [
    ...REQUIRED_FOR_RIGHTS.filter((k) => v[k] === null),
    ...(v.purchasePrice === null ? (["purchasePrice"] as SimKey[]) : []),
    ...(v.futureMarketValue === null ? (["futureMarketValue"] as SimKey[]) : []),
    ...(needsFinanceInputs ? (["interestRate", "holdingMonths"] as SimKey[]).filter((k) => v[k] === null) : []),
  ];
  const missingOptional = OPTIONAL_KEYS.filter((k) => v[k] === null && !missingRequired.includes(k));

  const rightsValue = v.appraisedValue !== null && v.proportionalRate !== null ? (v.appraisedValue * v.proportionalRate) / 100 : null;
  const contribution = rightsValue !== null && v.memberSalePrice !== null ? v.memberSalePrice - rightsValue : null;
  const kind = contribution === null ? null : Math.abs(contribution) < EPS ? "ZERO" : contribution > 0 ? "PAY" : "REFUND";

  // 금융비용: 대출을 입력하지 않았으면 표시값은 null, 총투자금 계산에는 0으로 쓴다.
  let financeCost: number | null = null;
  let financeForTotal: number | null = 0;
  if (v.loanAmount !== null) {
    if (loan === 0) {
      financeCost = 0;
    } else if (v.interestRate !== null && v.holdingMonths !== null) {
      financeCost = (loan * v.interestRate) / 100 * (v.holdingMonths / 12);
    }
    financeForTotal = financeCost;
  } else {
    financeForTotal = 0;
  }

  const totalInvestment =
    v.purchasePrice !== null && contribution !== null && financeForTotal !== null
      ? v.purchasePrice + (v.acquisitionCost ?? 0) + contribution + financeForTotal + (v.otherCost ?? 0)
      : null;
  const equity = totalInvestment !== null ? totalInvestment - loan : null;
  const profit = totalInvestment !== null && v.futureMarketValue !== null ? v.futureMarketValue - totalInvestment : null;
  const roi = profit !== null && equity !== null && equity > EPS ? profit / equity : null;

  const warnings: SimWarning[] = [];
  if (v.proportionalRate !== null && (v.proportionalRate <= 0 || v.proportionalRate > 200)) {
    warnings.push({ code: "RATE_RANGE", message: "비례율이 일반적인 범위(0 초과 200% 이하)를 벗어났어요. 입력값을 확인하세요." });
  }
  if (v.purchasePrice !== null && loan > v.purchasePrice) {
    warnings.push({ code: "LOAN_EXCEEDS_PRICE", message: "대출금액이 매입가격보다 커요. 입력값을 확인하세요." });
  }
  if (equity !== null && equity <= EPS) {
    warnings.push({ code: "EQUITY_NON_POSITIVE", message: "자기자본 투입액이 0 이하라 수익률을 계산하지 않았어요." });
  }

  return {
    rightsValue, contribution, contributionKind: kind,
    additionalPayment: contribution === null ? null : Math.max(contribution, 0),
    refund: contribution === null ? null : Math.max(-contribution, 0),
    financeCost, totalInvestment, equity, profit, roi,
    missingRequired, missingOptional, invalid, warnings,
  };
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** 기준 입력에 조정폭을 적용한다. 입력을 수정하지 않고, 비어 있던 입력을 값으로 만들지 않는다. */
export function applyDeltas(base: SimInputs, d: SimDeltas): SimInputs {
  const out: SimInputs = { ...base };
  const r = num(base.proportionalRate);
  const s = num(base.memberSalePrice);
  const v = num(base.futureMarketValue);
  const m = num(base.holdingMonths);
  const i = num(base.interestRate);
  if (r !== null) out.proportionalRate = Math.max(0, r + d.proportionalRate);
  if (s !== null) out.memberSalePrice = Math.max(0, s * (1 + d.salePricePct / 100));
  if (v !== null) out.futureMarketValue = Math.max(0, v * (1 + d.marketValuePct / 100));
  if (m !== null) out.holdingMonths = Math.max(0, m + d.holdingMonths);
  if (i !== null) out.interestRate = Math.max(0, i + d.interestRate);
  return out;
}

export type ScenarioName = "conservative" | "base" | "optimistic";
export type ScenarioSet = Record<ScenarioName, { inputs: SimInputs; result: SimResult }>;

/** 세 시나리오 모두 같은 calculate()를 쓴다. 시나리오별로 다른 식은 없다. */
export function compareScenarios(base: SimInputs, deltas: { conservative: SimDeltas; optimistic: SimDeltas }): ScenarioSet {
  const conservative = applyDeltas(base, deltas.conservative);
  const optimistic = applyDeltas(base, deltas.optimistic);
  return {
    conservative: { inputs: conservative, result: calculate(conservative) },
    base: { inputs: base, result: calculate(base) },
    optimistic: { inputs: optimistic, result: calculate(optimistic) },
  };
}

/** 만원 단위를 '7억 1,000만원'처럼. 값이 없거나 유효하지 않으면 대시. */
export function formatManwon(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const total = Math.round(Math.abs(value));
  if (total === 0) return "0원";
  const eok = Math.floor(total / 10000);
  const man = total % 10000;
  const grouped = String(man).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = eok > 0 ? (man === 0 ? `${eok}억원` : `${eok}억 ${grouped}만원`) : `${grouped}만원`;
  return value < 0 ? `-${body}` : body;
}
