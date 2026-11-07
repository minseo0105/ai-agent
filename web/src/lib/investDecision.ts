/**
 * 투자 의사결정 보조(가정 기반). 금액 단위는 만원. 서버로 보내지 않는다.
 * 규제(LTV·DSR·스트레스 DSR) 한도는 최신 기준과 시행일을 검증하지 못해 계산하지 않는다.
 * 권리·거래허가 조건은 근거 자료가 없으므로 '추가 확인 필요'로만 표시하고 확정하지 않는다.
 */

export type Homes = "" | "0" | "1" | "2+";
export type Purpose = "" | "live" | "invest";
export type Money = {
  cash: number | null; // 가용현금
  income: number | null; // 연소득
  debt: number | null; // 기존 대출 잔액
  homes: Homes;
  purpose: Purpose;
  reserve: number | null; // 예비비
  debtAnnual: number | null; // 기존 대출 연간 원리금 상환액
  rate: number | null; // 예상 대출금리(연 %)
  years: number | null; // 예상 대출기간(년)
  loan: number | null; // 사용자가 확인한 대출 가능금액(가정)
  loanConfirmed: boolean; // 금융기관 상담으로 확인한 금액인지(사용자 표시)
  costRate: number | null; // 취득세·중개보수 등 부대비용 가정(매입가격 대비 %)
  invalid: string[]; // 형식·범위가 잘못된 입력 항목 이름. 하나라도 있으면 계산 결과를 내지 않는다.
};
export const EMPTY_MONEY: Money = {
  cash: null, income: null, debt: null, homes: "", purpose: "", reserve: null,
  debtAnnual: null, rate: null, years: null, loan: null, loanConfirmed: false, costRate: null, invalid: [],
};

/** 입력 규칙. 빈칸은 미입력(null), 0은 값, 형식·범위 오류는 error. */
export type FieldRule = { min: number; max: number; minExclusive?: boolean; integer?: boolean };
export const RULES = {
  amount: { min: 0, max: 10_000_000 }, // 만원(최대 1,000억)
  price: { min: 0, max: 10_000_000, minExclusive: true },
  percent: { min: 0, max: 30 },
  years: { min: 1, max: 50, integer: true },
} satisfies Record<string, FieldRule>;

export function parseField(text: string, rule: FieldRule): { value: number | null; error: string | null } {
  const t = text.replace(/[,\s]/g, "");
  if (t === "") return { value: null, error: null };
  if (!/^\d+(\.\d+)?$/.test(t)) return { value: null, error: "숫자 형식이 올바르지 않아요" };
  const v = Number(t);
  if (!Number.isFinite(v)) return { value: null, error: "숫자 형식이 올바르지 않아요" };
  if (rule.integer && !Number.isInteger(v)) return { value: null, error: "정수로 입력해 주세요" };
  if (v < rule.min || (rule.minExclusive && v === rule.min)) return { value: null, error: rule.minExclusive ? `${rule.min}보다 커야 해요` : `${rule.min} 이상이어야 해요` };
  if (v > rule.max) return { value: null, error: `${rule.max.toLocaleString("ko-KR")} 이하로 입력해 주세요` };
  return { value: v, error: null };
}

/** 계산 직전 방어: 숫자 필드가 유한한 0 이상 값인지(입력 검증을 거치지 않은 값도 막는다). */
export function moneyInvalid(m: Money): string[] {
  const bad = [...m.invalid];
  const fields: [keyof Money, string][] = [["cash", "가용현금"], ["income", "연소득"], ["debt", "기존 대출 잔액"], ["reserve", "예비비"], ["debtAnnual", "기존 대출 연 원리금"], ["rate", "예상 대출금리"], ["years", "대출기간"], ["loan", "확인한 대출 가능금액"], ["costRate", "부대비용 가정"]];
  for (const [k, label] of fields) {
    const v = m[k] as number | null;
    if (v !== null && (!Number.isFinite(v) || v < 0) && !bad.includes(label)) bad.push(label);
  }
  return bad;
}
const priceBad = (price: number | null) => price !== null && (!Number.isFinite(price) || price <= 0);

/** 필요자금·추정 상한에 포함·미포함되는 비용(항상 결과 옆에 표시). */
export const COST_SCOPE = {
  included: "매입가격 + 부대비용(취득세·중개보수·법무비 등, 입력한 %)",
  excluded: "대출 이자, 추가분담금, 이주비, 보유세(재산세·종부세), 양도세",
};

const n0 = (v: number | null | undefined) => v ?? 0;

/** 입력칸 표시용: 숫자와 소수점만 남기고 정수부에 천 단위 쉼표를 넣는다. */
export function formatAmountInput(text: string): string {
  const cleaned = text.replace(/[^\d.]/g, "");
  if (!cleaned) return "";
  const [int, ...rest] = cleaned.split(".");
  const grouped = (int.replace(/^0+(?=\d)/, "") || (rest.length ? "0" : "")).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  // 소수점이 여러 개면 합치지 않고 그대로 둬서 검증에서 오류로 잡히게 한다.
  return rest.length ? `${grouped}.${rest.join(".")}` : grouped;
}

/** 원리금균등상환 가정의 월 상환액(만원). 금리·기간이 없으면 null. */
export function monthlyPayment(loan: number, ratePct: number | null, years: number | null): number | null {
  if (loan <= 0) return 0;
  if (ratePct === null || years === null || years <= 0) return null;
  const n = years * 12;
  const i = ratePct / 100 / 12;
  return i === 0 ? loan / n : (loan * i) / (1 - Math.pow(1 + i, -n));
}

/** 같은 가정에서 감당 가능한 매입가격 상한: (가용현금 − 예비비 + 대출) ÷ (1 + 부대비용률). */
export function priceCeiling(m: Money, loan: number): { value: number | null; costMissing: boolean; invalid: boolean } {
  if (moneyInvalid(m).length || !Number.isFinite(loan) || loan < 0) return { value: null, costMissing: m.costRate === null, invalid: true };
  if (m.cash === null) return { value: null, costMissing: m.costRate === null, invalid: false };
  const funds = m.cash - n0(m.reserve) + loan;
  return { value: Math.max(0, funds / (1 + n0(m.costRate) / 100)), costMissing: m.costRate === null, invalid: false };
}

export type Scenario = { loan: number; ceiling: number | null; monthly: number | null; burden: number | null };

/** 대출금액별 비교(0 · 절반 · 입력액). 부담률 = (기존 연 상환액 + 신규 연 상환액) ÷ 연소득. 규제 DSR 아님. */
export function loanScenarios(m: Money): Scenario[] {
  if (!m.loan || m.loan <= 0 || moneyInvalid(m).length) return [];
  const amounts = [...new Set([0, Math.round(m.loan / 2), m.loan])];
  return amounts.map((loan) => {
    const monthly = monthlyPayment(loan, m.rate, m.years);
    const burden = monthly !== null && m.income && m.income > 0 ? (n0(m.debtAnnual) + monthly * 12) / m.income : null;
    return { loan, ceiling: priceCeiling(m, loan).value, monthly, burden };
  });
}

export type Status = "MET" | "NOT_MET" | "CHECK";
// 충족(MET)은 자금 조건에만 나오며, 실제 매수 가능·대출 승인으로 읽히지 않게 가정 기준임을 붙인다.
export const STATUS_LABEL: Record<Status, string> = { MET: "입력한 자금 가정상 충족", NOT_MET: "조건 미충족", CHECK: "추가 확인 필요" };
export type Condition = { key: "funds" | "deal" | "rights"; title: string; status: Status; summary: string; items: string[] };

export type FundsResult = { need: number | null; available: number | null; shortfall: number | null; cost: number | null };

/** 관심 매물 필요자금: 매입가격 + 부대비용(가정). 추가분담금·이주비·보유비용은 포함하지 않는다. */
export function fundsFor(m: Money, price: number | null): FundsResult {
  if (moneyInvalid(m).length || priceBad(price)) return { need: null, available: null, shortfall: null, cost: null };
  const cost = price === null || m.costRate === null ? null : (price * m.costRate) / 100;
  const need = price === null ? null : price + n0(cost);
  const available = m.cash === null ? null : m.cash - n0(m.reserve);
  const shortfall = need !== null && available !== null ? need - available - n0(m.loan) : null;
  return { need, available, shortfall, cost };
}

export function fundsCondition(m: Money, price: number | null): Condition {
  const f = fundsFor(m, price);
  const items = [`포함: ${COST_SCOPE.included}. 미포함: ${COST_SCOPE.excluded}(추가분담금·이자는 상세 분석에서 가정 입력).`];
  const base = { key: "funds" as const, title: "자금 조건" };
  const bad = moneyInvalid(m);
  if (bad.length || priceBad(price)) {
    const names = [...bad, ...(priceBad(price) ? ["매도 희망가격"] : [])];
    return { ...base, status: "CHECK", summary: `입력 오류·추가 확인 필요: ${names.join(", ")} 값을 확인해 주세요.`, items };
  }
  if (price === null || f.available === null) {
    return { ...base, status: "CHECK", summary: price === null ? "매도 희망가격을 입력해 주세요." : "가용현금을 입력해 주세요.", items };
  }
  if (f.shortfall! > 0) {
    // 미입력 비용은 필요자금을 늘리기만 하므로, 지금도 부족하면 미충족이 확실하다.
    return { ...base, status: "NOT_MET", summary: `입력한 현금·대출 가정으로 약 ${Math.round(f.shortfall!).toLocaleString("ko-KR")}만원 부족해요.`, items };
  }
  if (m.costRate === null) {
    return { ...base, status: "CHECK", summary: "부대비용(취득세·중개보수 등)이 빠져 있어 판단할 수 없어요.", items };
  }
  if (n0(m.loan) > 0 && !m.loanConfirmed) {
    return { ...base, status: "CHECK", summary: "입력한 대출금액이 금융기관에서 확인한 금액인지 표시되지 않았어요.", items: ["대출 가능금액은 금융기관 심사로 정해져요. 상담 후 '확인한 금액' 표시를 해 주세요.", ...items] };
  }
  return { ...base, status: "MET", summary: "입력 조건상 필요자금이 현금·대출 가정 안에 있어요(대출 승인·매수 가능 확정 아님).", items };
}

/** 거래·허가 조건: 토지거래허가·규제지역 자료가 없어 항상 추가 확인 필요. 목적·보유 주택 수에 맞춘 확인 항목만 안내한다. */
export function dealCondition(m: Money): Condition {
  const items = [
    "토지거래허가구역인지: 토지이음(eum.go.kr)에서 주소로 확인하고, 허가 대상이면 계약 전 허가가 필요해요.",
    "투기과열지구·조정대상지역 여부와 그에 따른 대출·세금 조건을 확인하세요.",
  ];
  if (m.purpose === "invest") items.push("투자 목적이라면 토지거래허가구역에서는 실거주 의무 때문에 전세를 낀 매수가 제한될 수 있어요.");
  if (m.purpose === "live") items.push("실거주 목적이라도 허가구역이면 입주 시점·실거주 기간 요건을 지켜야 해요.");
  if (m.homes === "1" || m.homes === "2+") items.push("이미 주택이 있으면 취득세 중과·대출 제한·처분 조건이 붙을 수 있어요.");
  return { key: "deal", title: "거래·허가 조건", status: "CHECK", summary: "허가구역·규제지역 자료를 연결하지 않아 확정할 수 없어요.", items };
}

// 서버 stage_guide.stage 코드의 일반적 진행 순서.
const STAGE_ORDER = [
  "CANDIDATE", "SAFETY_DIAGNOSIS", "PLANNING", "PLAN_DELIBERATION", "PLAN_NOTICED", "DESIGNATED", "COMMITTEE",
  "ASSOCIATION_APPROVED", "IMPLEMENTER_DESIGNATED", "IMPLEMENTATION_APPROVED", "MANAGEMENT_DISPOSITION",
  "DEMOLITION", "CONSTRUCTION", "SALES", "PARTIAL_COMPLETION",
];
const reached = (stage: string | null | undefined, target: string) => {
  const a = STAGE_ORDER.indexOf(stage ?? "");
  return a < 0 ? null : a >= STAGE_ORDER.indexOf(target);
};

export type ProjectKind = { business: "재개발" | "재건축" | null; plan: string | null };
/** 실제 사업 유형(재개발·재건축)과 정책·계획 유형(신속통합기획 등)을 나눈다. 모르면 null. */
export function projectKind(p: { type_label?: string | null; program_label?: string | null }): ProjectKind {
  const t = p.type_label ?? "";
  return { business: t === "재개발" || t === "재건축" ? t : null, plan: p.program_label || null };
}

/** 조합원 지위 양도 제한 검토 문구. 투기과열지구 여부·예외 요건은 확인하지 못하므로 확정하지 않는다. */
export function transferNote(kind: ProjectKind, stage: string | null | undefined): string {
  if (!kind.business) return "실제 사업 유형(재개발·재건축)이 확인되지 않아 양도 제한 시점을 판단할 수 없어요.";
  const [target, label] = kind.business === "재건축" ? ["ASSOCIATION_APPROVED", "조합설립인가"] : ["MANAGEMENT_DISPOSITION", "관리처분계획인가"];
  const r = reached(stage, target);
  const law = `${kind.business}은 투기과열지구에서 ${label} 이후 매수하면 조합원 지위를 승계하지 못할 수 있어요(예외 요건 있음).`;
  if (r === null) return `${law} 현재 단계가 확인되지 않아요.`;
  return r ? `${law} 이 사업은 그 단계 이후로 표시돼 있어 매도인의 예외 요건 충족 여부 확인이 꼭 필요해요.` : `${law} 이 사업은 아직 그 단계 전으로 표시돼 있지만, 단계는 바뀔 수 있어요.`;
}

export function rightsCondition(kind: ProjectKind, stage: string | null | undefined, linked: boolean): Condition {
  const items = [
    transferNote(kind, stage),
    "권리산정기준일 이후 지분 쪼개기·신축으로 생긴 물건은 입주권 없이 현금청산될 수 있어요.",
    "한 세대가 여러 물건을 가지면 입주권이 하나만 나올 수 있어요(다물권자).",
    "분양신청 기간에 신청하지 않으면 현금청산 대상이 돼요.",
    "투기과열지구에서 이미 정비사업 분양을 받은 세대는 일정 기간 재당첨이 제한될 수 있어요.",
    "권리가액·추가분담금은 감정평가와 관리처분계획으로 정해져요. 조합에 예상 권리가액을 확인하세요.",
  ];
  if (!linked) items.unshift("이 매물이 정비구역 안인지 확인되지 않았어요(구역 경계 자료 없음). 조합·구청에서 구역 포함 여부부터 확인하세요.");
  return { key: "rights", title: "조합원 지위·입주권 조건", status: "CHECK", summary: "조합원 자격·입주권은 등기·조합 자료로만 확정할 수 있어요.", items };
}

export const VERIFY_STEPS = [
  "등기부등본(인터넷등기소): 소유자·근저당·취득일",
  "건축물대장·토지대장(정부24): 면적·용도·사용승인일·위반건축물 여부",
  "토지이음: 토지거래허가구역·용도지역",
  "조합(추진위) 사무실: 조합원 여부·예상 권리가액·분담금·분양신청 일정",
  "관할 구청 정비사업 담당: 구역 포함 여부·권리산정기준일·사업 단계",
  "금융기관: 대출 가능금액·금리·상환 조건(이 화면의 금액은 승인액이 아님)",
];

export const TERMS: Record<string, string> = {
  권리가액: "기존 집·땅의 감정평가액에 비례율을 곱한 값. 새 아파트 분양가에서 이 금액을 뺀 만큼을 추가로 내요.",
  추가분담금: "조합원 분양가에서 권리가액을 뺀 금액. 사업비가 늘면 커질 수 있어요.",
  입주권: "정비사업 조합원이 새 아파트를 분양받을 수 있는 권리.",
  현금청산: "입주권을 받지 못하고 감정평가 금액 등을 현금으로 받고 나가는 것.",
  "조합원 지위 양도 제한": "특정 단계 이후 매수한 사람은 조합원이 되지 못하게 하는 규정(예외 있음).",
  토지거래허가구역: "계약 전에 구청 허가가 필요하고, 허가 후 실거주 등 의무가 붙는 지역.",
  권리산정기준일: "이 날짜 이후 쪼개거나 새로 지은 물건은 입주권을 받지 못할 수 있는 기준 날짜.",
  DSR: "모든 대출의 연간 원리금 상환액 ÷ 연소득. 규제 DSR은 금리·만기 산정 방식이 따로 정해져 있어 이 화면의 부담률과 달라요.",
};
