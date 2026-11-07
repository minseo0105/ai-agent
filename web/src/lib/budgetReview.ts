/**
 * 내 예산으로 매수 검토(가정 기반). 금액 단위: 예산·시뮬레이터는 만원, 실거래 price_100m은 억원.
 * LTV·DSR 같은 규제 한도는 계산하지 않는다(대출금액은 사용자가 입력한 가정값).
 */
import type { SimInputs, SimResult } from "./investmentCalc.ts";
import { sameDong, type ZoneTradeRow } from "./zoneTrades.ts";

export type Homes = "" | "0" | "1" | "2+";
export type Budget = { cash: number | null; income: number | null; debt: number | null; reserve: number | null; homes: Homes };

export type BudgetResult = {
  available: number | null; // 현금 − 예비비
  need: number | null; // 매수 시 필요한 자기자금(입력된 항목만)
  gap: number | null; // available − need (음수면 부족)
  ceiling: number | null; // 같은 가정에서 감당 가능한 최대 매입가격(만원)
  contributionIncluded: boolean;
  missingCosts: string[]; // 비어 있어 0원으로 계산된 비용(직접 0을 입력한 경우는 포함하지 않음)
  debtMultiple: number | null; // (기존 부채 + 입력 대출) ÷ 연소득, 규제 지표 아님
  notes: string[];
};

const n0 = (v: number | null) => v ?? 0;

export function budgetCheck(b: Budget, sim: SimInputs, r: SimResult): BudgetResult {
  const available = b.cash === null ? null : b.cash - n0(b.reserve);
  const contributionIncluded = r.additionalPayment !== null;
  // 환급금은 준공 무렵 받으므로 매수 자금에서 빼지 않는다(추가분담금은 보수적으로 매수 자금에 포함).
  const extra = n0(sim.acquisitionCost) + n0(sim.otherCost) + n0(r.financeCost) + n0(r.additionalPayment);
  const need = sim.purchasePrice === null ? null : sim.purchasePrice + extra - n0(sim.loanAmount);
  const ceiling = available === null ? null : Math.max(0, available + n0(sim.loanAmount) - extra);
  const debtMultiple = b.income && b.income > 0 ? (n0(b.debt) + n0(sim.loanAmount)) / b.income : null;
  // 빈칸(null)과 직접 입력한 0을 구분한다. 빈칸만 "미입력"이다.
  const missingCosts = [sim.acquisitionCost === null && "취득 관련 비용", !contributionIncluded && "추가분담금"].filter((x): x is string => !!x);
  const notes = [
    "대출금액은 입력한 가정값이에요. LTV·DSR 등 규제 한도는 계산하지 않았으니 금융기관에서 확인하세요.",
    "부채 ÷ 연소득은 부채 잔액 기준 단순 배수로, 연간 원리금 상환액 기준인 DSR이 아니에요.",
  ];
  if (!contributionIncluded) notes.push("추가분담금이 빠져 있어요. 감정평가액·비례율·조합원 분양가를 넣으면 반영돼요.");
  if (b.homes === "1" || b.homes === "2+") notes.push("주택을 보유하면 취득세율과 대출 가능 여부가 달라질 수 있어요. 취득 관련 비용과 대출금액을 최신 규정으로 확인해 입력하세요.");
  if (sim.acquisitionCost === null) notes.push("취득 관련 비용(취득세·중개보수·법무비)이 비어 있어 최대 매입가격이 실제보다 크게 나올 수 있어요.");
  return { available, need, gap: available !== null && need !== null ? available - need : null, ceiling, contributionIncluded, missingCosts, debtMultiple, notes };
}

const median = (xs: number[]): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const quantile = (xs: number[], q: number): number => {
  const s = [...xs].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  return s[lo] + (s[Math.ceil(pos)] - s[lo]) * (pos - lo);
};

export type ProjectLite = { name: string; dong: string | null; stage: { label: string }; investor_guide?: { risk_label: string; risk_level: string } };
export type DongRow = {
  dong: string;
  projects: { name: string; stage: string; risk: string | null }[];
  trades: number;
  median: number | null; // 억원
  withinBudget: number | null; // 예산 이하 거래 수(예산 미입력이면 null)
  types: string[];
};

/** 정비사업이 있는 법정동별 최근 거래와 예산 이하 거래 수. 거래는 모두 '동일 법정동 참고 거래'다. */
export function dongReview(rows: ZoneTradeRow[], projects: ProjectLite[], ceilingManwon: number | null): DongRow[] {
  const dongs = [...new Set(projects.map((p) => p.dong).filter((d): d is string => !!d))];
  const limit = ceilingManwon === null ? null : ceilingManwon / 10000;
  return dongs
    .map((dong) => {
      const local = sameDong(rows, dong).filter((r) => r.price_100m > 0);
      return {
        dong,
        projects: projects.filter((p) => p.dong === dong).map((p) => ({ name: p.name, stage: p.stage.label, risk: p.investor_guide?.risk_label ?? null })),
        trades: local.length,
        median: median(local.map((r) => r.price_100m)),
        withinBudget: limit === null ? null : local.filter((r) => r.price_100m <= limit).length,
        types: [...new Set(local.map((r) => r.property_type))],
      };
    })
    .sort((a, b) => n0(b.withinBudget) - n0(a.withinBudget) || b.trades - a.trades || a.dong.localeCompare(b.dong));
}

export const MIN_COMPARABLES = 3;
export type ListingInput = { dong: string; type: string; area: number | null; ask: number | null; complex: string; buildYear?: number | null };
export const YEAR_WINDOW = 5;
export const WIDE_YEAR_SPAN = 10;
export type ListingResult = {
  ok: boolean;
  reason?: string;
  n: number;
  basis: string | null;
  similar?: boolean; // 단지 일치 또는 건축연도 ±5년 안 비교일 때만 true
  caution?: string; // 조건 차이가 커서 범위 해석에 주의할 점
  low?: number; mid?: number; high?: number; // 만원, 입력 면적 기준
  position?: "BELOW" | "WITHIN" | "ABOVE";
  conditions?: { names: string[]; area: [number, number]; floors: string | null; years: string | null; areaBasis: string };
  rows: ZoneTradeRow[];
};

const span = (xs: number[]) => (xs.length ? (Math.min(...xs) === Math.max(...xs) ? `${Math.min(...xs)}` : `${Math.min(...xs)}~${Math.max(...xs)}`) : null);

/** 관심 물건과 비교 가능한 실거래로 참고 거래가격 범위(면적당 가격의 25~75% 구간 × 입력 면적)를 낸다. 표본이 부족하면 내지 않는다. */
export function compareListing(rows: ZoneTradeRow[], q: ListingInput): ListingResult {
  if (!q.area || q.area <= 0) return { ok: false, reason: "면적을 입력해 주세요.", n: 0, basis: null, rows: [] };
  const pool = sameDong(rows, q.dong).filter((r) => r.property_type === q.type && r.price_100m > 0 && r.area > 0 && Math.abs(r.area - q.area!) / q.area! <= 0.15);
  const name = q.complex.trim();
  const byName = name ? pool.filter((r) => r.name.includes(name)) : [];
  const by = q.buildYear ? pool.filter((r) => Math.abs(Number(r.build_year) - q.buildYear!) <= YEAR_WINDOW) : [];
  // 가장 비슷한 조건부터: 같은 단지 → 건축연도 ±5년 → 같은 동·유형·비슷한 면적.
  const [use, basis, similar] =
    byName.length >= MIN_COMPARABLES ? [byName, "같은 단지·비슷한 면적", true]
      : by.length >= MIN_COMPARABLES ? [by, `건축연도 ±${YEAR_WINDOW}년·같은 동·유형·비슷한 면적`, true]
        : [pool, "같은 동·유형·비슷한 면적", false];
  if (use.length < MIN_COMPARABLES) {
    return { ok: false, reason: `비교 가능한 거래가 ${use.length}건이라 참고 거래가격 범위를 낼 수 없어요(최소 ${MIN_COMPARABLES}건).`, n: use.length, basis: null, rows: use };
  }
  const unit = use.map((r) => (r.price_100m * 10000) / r.area);
  const [low, mid, high] = [quantile(unit, 0.25), median(unit)!, quantile(unit, 0.75)].map((u) => Math.round(u * q.area!));
  const position = q.ask === null ? undefined : q.ask < low ? "BELOW" : q.ask > high ? "ABOVE" : "WITHIN";
  const floors = use.map((r) => Number(r.floor)).filter((f) => Number.isFinite(f));
  const years = use.map((r) => Number(r.build_year)).filter((y) => y > 0);
  const yearSpan = years.length ? Math.max(...years) - Math.min(...years) : 0;
  const cautions: string[] = [];
  if (!similar) cautions.push("단지나 건축연도가 일치하는 거래가 부족해 같은 동의 비슷한 면적 거래 전체로 계산했어요");
  if (yearSpan > WIDE_YEAR_SPAN) cautions.push(`건축연도 차이가 ${yearSpan}년이라 범위가 넓어요`);
  return {
    ok: true, n: use.length, basis, similar, caution: cautions.length ? `${cautions.join(". ")}.` : undefined, low, mid, high, position, rows: use,
    conditions: {
      names: [...new Set(use.map((r) => r.name))].slice(0, 5),
      area: [Math.min(...use.map((r) => r.area)), Math.max(...use.map((r) => r.area))],
      floors: span(floors), years: span(years), areaBasis: use[0].area_basis ?? "면적",
    },
  };
}

/** 조회에 실패한 유형: 403(권한 없음)과 그 밖의 실패를 구분한다. 실패한 유형의 '0건'은 거래가 없다는 뜻이 아니다. */
export function failedTypes(errors: string[]): Map<string, "FORBIDDEN" | "FAILED"> {
  const out = new Map<string, "FORBIDDEN" | "FAILED">();
  for (const e of errors) {
    const m = /·\s*([^:]+):/.exec(e);
    if (!m) continue;
    const kind = /\(403\)|403|활용신청|인증 오류|SERVICE_KEY/.test(e) ? "FORBIDDEN" : "FAILED";
    if (out.get(m[1].trim()) !== "FORBIDDEN") out.set(m[1].trim(), kind);
  }
  return out;
}
