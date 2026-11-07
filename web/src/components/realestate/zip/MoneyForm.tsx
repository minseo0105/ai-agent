"use client";

import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { inputClass } from "@/components/golf/ui";
import { clearFinancial, hasConsent, hasLegacy, LEGACY_BUDGET_KEY, MONEY_KEY, readFin, setConsent as setConsentFlag, writeFin } from "@/lib/finStorage";
import { formatManwon } from "@/lib/investmentCalc";
import { COST_SCOPE, EMPTY_MONEY, RULES, TERMS, formatAmountInput, loanScenarios, parseField, priceCeiling, type FieldRule, type Homes, type Money, type Purpose } from "@/lib/investDecision";

type NumKey = "cash" | "income" | "debt" | "reserve" | "debtAnnual" | "costRate" | "loan" | "rate" | "years";
type Raw = Record<NumKey, string> & { homes: Homes; purpose: Purpose; loanConfirmed: boolean };
const EMPTY_RAW: Raw = { cash: "", income: "", debt: "", reserve: "", debtAnnual: "", costRate: "", loan: "", rate: "", years: "", homes: "", purpose: "", loanConfirmed: false };
const FIELDS: Record<NumKey, { label: string; rule: FieldRule }> = {
  cash: { label: "가용현금", rule: RULES.amount }, income: { label: "연소득", rule: RULES.amount }, debt: { label: "기존 대출 잔액", rule: RULES.amount },
  reserve: { label: "예비비", rule: RULES.amount }, debtAnnual: { label: "기존 대출 연 원리금", rule: RULES.amount }, loan: { label: "확인한 대출 가능금액", rule: RULES.amount },
  costRate: { label: "부대비용 가정", rule: RULES.percent }, rate: { label: "예상 대출금리", rule: RULES.percent }, years: { label: "대출기간", rule: RULES.years },
};
// 상세 분석의 예산 점검과 같은 항목. 같은 상태를 쓰므로 두 화면 값이 항상 같다.
const SHARED_BUDGET: (keyof Raw)[] = ["cash", "reserve", "income", "debt", "homes"];

/**
 * 내 자금 입력값 저장소(이 페이지 안에서 하나만 존재). '내 자금'과 상세 분석의 예산 점검이 같은 값을 쓴다.
 * 서버로 보내지 않고, 저장 동의가 있을 때만 이 브라우저에 저장한다(lib/finStorage).
 */
type Snap = { raw: Raw; consent: boolean; legacy: boolean; loaded: boolean; consentAt: number; clearedAt: number };
const INITIAL: Snap = { raw: EMPTY_RAW, consent: false, legacy: false, loaded: false, consentAt: 0, clearedAt: 0 };
let snap = INITIAL;
const listeners = new Set<() => void>();
const emit = (next: Partial<Snap>) => {
  snap = { ...snap, ...next };
  listeners.forEach((l) => l());
};
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** 빈 칸만 채운다(이미 있는 값이 우선). */
function fillBlanks(base: Raw, extra: Partial<Raw> | null | undefined, keys?: (keyof Raw)[]): Raw {
  if (!extra) return base;
  const out = { ...base } as Record<string, unknown>;
  for (const k of keys ?? (Object.keys(EMPTY_RAW) as (keyof Raw)[])) {
    const v = (extra as Record<string, unknown>)[k];
    if ((out[k] === "" || out[k] === false) && v !== undefined && v !== null && v !== "") out[k] = v;
  }
  return out as Raw;
}

/** 동의된 저장값을 합친다: 화면 값 > 저장된 내 자금 > 이전 예산 점검 저장값(빈 칸만). 합친 뒤 이전 키는 지운다. */
function mergeStored(raw: Raw): Raw {
  let next = fillBlanks(raw, readFin<{ values: Partial<Raw> }>(MONEY_KEY)?.values);
  next = fillBlanks(next, readFin<Partial<Raw>>(LEGACY_BUDGET_KEY), SHARED_BUDGET);
  // 이전 저장값은 쉼표 없이 저장돼 있을 수 있어 금액 칸 표시 형식을 맞춘다(값은 같음).
  for (const k of Object.keys(FIELDS) as NumKey[]) if (FIELDS[k].rule === RULES.amount && next[k]) next = { ...next, [k]: formatAmountInput(next[k]) };
  writeFin(MONEY_KEY, { values: next });
  try {
    window.localStorage.removeItem(LEGACY_BUDGET_KEY);
  } catch {
    // 무시
  }
  return next;
}

function load() {
  if (snap.loaded || typeof window === "undefined") return;
  const consent = hasConsent();
  emit({ loaded: true, consent, legacy: hasLegacy(), raw: consent ? mergeStored(snap.raw) : snap.raw, consentAt: consent ? Date.now() : 0 });
}

export function setMoneyRaw(update: (r: Raw) => Raw) {
  const raw = update(snap.raw);
  if (snap.consent) writeFin(MONEY_KEY, { values: raw });
  emit({ raw });
}

/** 저장 동의 켜기: 이전 저장값도 이때 불러온다. 끄기: 이 기기의 금융 저장값을 모두 지우고(화면 값은 유지) 이후 저장하지 않는다. */
export function setMoneyConsent(on: boolean) {
  setConsentFlag(on);
  if (on) emit({ consent: true, legacy: false, raw: mergeStored(snap.raw), consentAt: Date.now() });
  else emit({ consent: false, legacy: false });
}

/** 이 기기의 금융 저장값(내 자금·예산 점검·사업별 시뮬레이터)을 모두 지우고 화면 입력도 비운다. */
export function clearMoney() {
  clearFinancial();
  emit({ raw: EMPTY_RAW, consent: false, legacy: false, clearedAt: Date.now() });
}

export function useMoney() {
  const s = useSyncExternalStore(subscribe, () => snap, () => INITIAL);
  useEffect(load, []);
  const { money, errors } = useMemo(() => {
    const errs = {} as Record<NumKey, string | null>;
    const val = {} as Record<NumKey, number | null>;
    const invalid: string[] = [];
    for (const k of Object.keys(FIELDS) as NumKey[]) {
      const r = parseField(s.raw[k], FIELDS[k].rule);
      errs[k] = r.error;
      val[k] = r.value;
      if (r.error) invalid.push(FIELDS[k].label);
    }
    const m: Money = { ...EMPTY_MONEY, ...val, homes: s.raw.homes, purpose: s.raw.purpose, loanConfirmed: s.raw.loanConfirmed, invalid };
    return { money: m, errors: errs };
  }, [s.raw]);
  return { raw: s.raw, money, errors, consent: s.consent, legacy: s.legacy, consentAt: s.consentAt, clearedAt: s.clearedAt, setRaw: setMoneyRaw, setConsent: setMoneyConsent, clear: clearMoney };
}
export type MoneyState = ReturnType<typeof useMoney>;
export type { NumKey };

/** 용어 도움말. 눌러서 펼친다. */
export function Term({ name, children }: { name: keyof typeof TERMS | string; children?: ReactNode }) {
  return (
    <details className="inline-block align-baseline [&_summary::-webkit-details-marker]:hidden">
      <summary className="cursor-pointer list-none underline decoration-dotted underline-offset-2">{children ?? name}<span aria-hidden className="ml-0.5 text-subtle">ⓘ</span></summary>
      <span role="note" className="mt-1 block max-w-xs rounded-lg bg-surface-muted px-2 py-1.5 text-[11px] font-normal leading-relaxed text-muted">{TERMS[name] ?? ""}</span>
    </details>
  );
}

/** 금액·비율 입력: 천 단위 쉼표, 억·만원 변환, 형식·범위 오류를 바로 보여 준다. 빈칸(미입력)과 0을 구분한다. */
export function AmountInput({ label, unit = "만원", value, onChange, hint, help, rule }: { label: string; unit?: string; value: string; onChange: (v: string) => void; hint?: string; help?: string; rule?: FieldRule }) {
  const r = parseField(value, rule ?? (unit === "만원" ? RULES.amount : RULES.percent));
  const note = r.error ? r.error : r.value === null ? hint ?? "비어 있음(미입력)" : unit === "만원" ? `= ${formatManwon(r.value)}` : `${r.value}${unit}`;
  return (
    <label className="block text-xs">
      <span className="mb-0.5 flex items-baseline justify-between gap-2 font-bold">
        <span>{help ? <Term name={help}>{label}</Term> : label}</span>
        <span className="font-semibold text-subtle">{unit}</span>
      </span>
      <input inputMode="decimal" value={value} onChange={(e) => onChange(unit === "만원" ? formatAmountInput(e.target.value) : e.target.value.replace(/[^\d.]/g, ""))} placeholder="미입력" aria-label={`${label} (${unit})`} aria-invalid={!!r.error} className={`${inputClass} w-full ${r.error ? "border-red-500" : ""}`} />
      <span data-field-note className={`mt-0.5 block text-[11px] ${r.error ? "font-semibold text-red-600 dark:text-red-400" : "text-subtle"}`}>{note}</span>
    </label>
  );
}

/** 필요자금·추정 상한 바로 옆에 항상 보이는 포함·미포함 안내. */
export function CostScope({ costMissing }: { costMissing?: boolean }) {
  return (
    <span data-cost-scope className="block text-[11px] text-subtle">
      포함: {COST_SCOPE.included}{costMissing ? " — 부대비용 미입력(0%로 계산)" : ""} · <b className="font-semibold text-amber-800 dark:text-amber-300">미포함: {COST_SCOPE.excluded}</b>
    </span>
  );
}

/** 저장 동의·삭제 영역. 내 자금과 상세 분석에서 같은 동작을 한다. */
export function StorageControls({ state }: { state: MoneyState }) {
  const { consent, legacy, setConsent, clear } = state;
  return (
    <div data-storage-controls className="space-y-1.5 border-t border-border pt-2 text-[11px] text-subtle">
      {legacy && (
        <div role="status" data-legacy-notice className="rounded-lg bg-amber-500/10 px-2 py-1.5 text-amber-800 dark:text-amber-300">
          이전 버전에서 이 기기에 자동 저장된 금융 입력값이 있어요. 동의 전에는 불러오지 않아요.
          <span className="mt-1 flex gap-1.5">
            <button type="button" onClick={() => setConsent(true)} className="min-h-8 rounded-lg border border-current px-2 font-bold">저장 유지(동의)</button>
            <button type="button" onClick={clear} className="min-h-8 rounded-lg border border-current px-2 font-bold">삭제</button>
          </span>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />금융 입력값을 이 브라우저에 저장</label>
        <button type="button" onClick={clear} className="min-h-8 rounded-lg border border-border px-2 font-bold text-muted hover:text-fg">이 기기 저장값 지우기</button>
      </div>
      <p>
        입력값은 서버로 보내지 않아요. 저장은 동의했을 때만 하며 범위는 이 기기 브라우저의 내 자금·예산 점검·사업별 상세 분석 입력값이에요.
        저장을 끄거나 &apos;지우기&apos;를 누르면 이 세 가지가 모두 삭제돼요(끄기는 화면 값은 유지, 지우기는 화면 값도 비움).
      </p>
    </div>
  );
}

const SELECT = `${inputClass} w-full`;

export default function MoneyForm({ state }: { state: MoneyState }) {
  const { raw, setRaw } = state;
  const set = (k: NumKey) => (v: string) => setRaw((r) => ({ ...r, [k]: v }));
  const ceiling = priceCeiling(state.money, state.money.loan ?? 0);
  return (
    <section data-money-form aria-label="내 자금" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">내 자금 <span className="font-semibold text-subtle">필수 1개(가용현금) · 나머지는 선택</span></h3>
      <div className="grid grid-cols-2 gap-2">
        <AmountInput label="가용현금" value={raw.cash} onChange={set("cash")} hint="지금 쓸 수 있는 현금" />
        <AmountInput label="연소득" value={raw.income} onChange={set("income")} />
        <AmountInput label="기존 대출 잔액" value={raw.debt} onChange={set("debt")} />
        <label className="block text-xs"><span className="mb-0.5 block font-bold">주택 보유</span>
          <select value={raw.homes} onChange={(e) => setRaw((r) => ({ ...r, homes: e.target.value as Homes }))} className={SELECT}>
            <option value="">선택 안 함</option><option value="0">무주택</option><option value="1">1주택</option><option value="2+">2주택 이상</option>
          </select></label>
        <label className="col-span-2 block text-xs"><span className="mb-0.5 block font-bold">목적</span>
          <select value={raw.purpose} onChange={(e) => setRaw((r) => ({ ...r, purpose: e.target.value as Purpose }))} className={SELECT}>
            <option value="">선택 안 함</option><option value="live">실거주</option><option value="invest">투자</option>
          </select></label>
      </div>
      <details className="rounded-lg bg-surface-muted/60 px-2.5 py-2">
        <summary className="cursor-pointer text-xs font-bold">추가 입력 (예비비 · 대출 가정 · 부대비용)</summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <AmountInput label="예비비" value={raw.reserve} onChange={set("reserve")} hint="매수 후에도 남길 돈" />
          <AmountInput label="기존 대출 연 원리금" value={raw.debtAnnual} onChange={set("debtAnnual")} hint="1년 동안 갚는 원금+이자" />
          <AmountInput label="부대비용 가정" unit="%" value={raw.costRate} onChange={set("costRate")} hint="취득세·중개보수·법무비 (매입가격 대비)" rule={RULES.percent} />
          <AmountInput label="확인한 대출 가능금액" value={raw.loan} onChange={set("loan")} hint="금융기관에서 들은 금액(가정)" />
          <AmountInput label="예상 대출금리" unit="%" value={raw.rate} onChange={set("rate")} rule={RULES.percent} />
          <AmountInput label="대출기간" unit="년" value={raw.years} onChange={set("years")} rule={RULES.years} hint="1~50년" />
          <label className="col-span-2 flex items-center gap-2 text-xs">
            <input type="checkbox" checked={raw.loanConfirmed} onChange={(e) => setRaw((r) => ({ ...r, loanConfirmed: e.target.checked }))} />
            대출 가능금액을 금융기관 상담으로 확인했어요
          </label>
        </div>
      </details>
      <div data-ceiling className="text-xs">
        <b>입력 조건상 추정 상한</b>{" "}
        {ceiling.invalid
          ? <span className="font-bold text-red-600 dark:text-red-400">입력 오류·추가 확인 필요 ({state.money.invalid.join(", ") || "입력값"} 확인)</span>
          : ceiling.value === null ? "가용현금을 입력해 주세요" : formatManwon(ceiling.value)}
        <span className="block text-[11px] text-subtle">
          = (가용현금 − 예비비 + 대출 가정) ÷ (1 + 부대비용률).{ceiling.costMissing && " 부대비용 미입력이라 입력된 비용 기준 가정 한도예요."} 매수 가능 금액·대출 승인액이 아니에요.
        </span>
        <CostScope costMissing={ceiling.costMissing} />
      </div>
      <StorageControls state={state} />
    </section>
  );
}

const FIN_CHECKS = ["실제 대출 가능금액과 적용 LTV·DSR(스트레스 DSR 포함)", "적용 금리(고정·변동)와 상환 방식·기간", "주택 보유 수·실거주 요건에 따른 대출 제한", "정비사업 물건(입주권·멸실 예정 주택)의 담보 인정 여부", "이주비·중도금 대출 가능 여부"];

/** 대출 시나리오 비교. 규제 한도는 계산하지 않고, 입력한 금액을 0·절반·전액으로 나눠 비교한다. */
export function LoanPanel({ money }: { money: Money }) {
  const rows = useMemo(() => loanScenarios(money), [money]);
  return (
    <section data-loan-panel aria-label="대출 시나리오" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">대출 시나리오 <span className="font-semibold text-subtle">입력한 금액 기준 · 승인액 아님</span></h3>
      <p data-loan-disclaimer className="rounded-lg bg-amber-500/10 px-2 py-1.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
        사용자가 입력한 대출금액에 따른 가정별 비교이며, 금융기관의 실제 대출 가능 한도를 산정한 결과가 아니에요.
      </p>
      <p className="text-[11px] text-subtle">최신 LTV·DSR·스트레스 DSR 기준과 시행일을 확인하지 못해 자동 대출 한도는 계산하지 않아요.</p>
      {money.invalid.length > 0 ? (
        <p role="status" className="text-xs font-bold text-red-600 dark:text-red-400">입력 오류·추가 확인 필요: {money.invalid.join(", ")} 값을 확인해 주세요.</p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted">&apos;추가 입력&apos;에 확인한 대출 가능금액을 넣으면 금액별로 비교해요.</p>
      ) : (
        <table className="w-full text-left text-[11px]">
          <thead className="text-subtle"><tr><th className="py-1">대출</th><th className="py-1 text-right">추정 상한</th><th className="py-1 text-right">월 상환(가정)</th><th className="py-1 text-right">상환부담률*</th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.loan} className="border-t border-border/60">
                <td className="py-1">{formatManwon(s.loan)}</td>
                <td className="py-1 text-right font-bold">{formatManwon(s.ceiling)}</td>
                <td className="py-1 text-right">{s.monthly === null ? "금리·기간 필요" : formatManwon(s.monthly)}</td>
                <td className="py-1 text-right">{s.burden === null ? "—" : `${(s.burden * 100).toFixed(0)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-[11px] text-subtle">* (기존 연 원리금 + 새 대출 연 원리금) ÷ 연소득. 원리금균등 가정이며 <Term name="DSR">규제 DSR</Term>이 아니에요.</p>
      <CostScope costMissing={money.costRate === null} />
      <details className="text-[11px] text-muted">
        <summary className="cursor-pointer font-bold">금융기관에서 확인할 항목</summary>
        <ul className="mt-1 list-disc pl-4">{FIN_CHECKS.map((c) => <li key={c}>{c}</li>)}</ul>
      </details>
    </section>
  );
}
