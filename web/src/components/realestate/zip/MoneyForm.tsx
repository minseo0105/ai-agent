"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { inputClass } from "@/components/golf/ui";
import { formatManwon } from "@/lib/investmentCalc";
import { EMPTY_MONEY, TERMS, formatAmountInput, loanScenarios, priceCeiling, type Homes, type Money, type Purpose } from "@/lib/investDecision";
import { parseNumberInput } from "@/lib/zipFormat";

const KEY = "zip:money:v1";
const OLD_KEYS = ["zip:budget:v1"]; // 상세 분석의 예산 점검이 쓰던 저장값도 함께 지운다.
type NumKey = "cash" | "income" | "debt" | "reserve" | "debtAnnual" | "costRate" | "loan" | "rate" | "years";
type Raw = Record<NumKey, string> & { homes: Homes; purpose: Purpose; loanConfirmed: boolean };
const EMPTY_RAW: Raw = { cash: "", income: "", debt: "", reserve: "", debtAnnual: "", costRate: "", loan: "", rate: "", years: "", homes: "", purpose: "", loanConfirmed: false };

/** 내 자금 입력값. 기본은 저장하지 않고, 사용자가 켜면 이 브라우저(localStorage)에만 저장한다. 서버로 보내지 않는다. */
export function useMoney() {
  const [raw, setRaw] = useState<Raw>(EMPTY_RAW);
  const [persist, setPersist] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(KEY) ?? "null");
      if (saved?.values) {
        setRaw({ ...EMPTY_RAW, ...saved.values });
        setPersist(true);
      }
    } catch {
      // 저장소를 못 쓰면 저장 없이 동작한다.
    }
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return; // 불러오기 전에는 저장값을 지우지 않는다.
    try {
      if (persist) window.localStorage.setItem(KEY, JSON.stringify({ values: raw }));
      else window.localStorage.removeItem(KEY);
    } catch {
      // 무시
    }
  }, [raw, persist, loaded]);
  const money: Money = useMemo(() => {
    const num = (k: NumKey) => parseNumberInput(raw[k]);
    return { ...EMPTY_MONEY, cash: num("cash"), income: num("income"), debt: num("debt"), reserve: num("reserve"), debtAnnual: num("debtAnnual"), costRate: num("costRate"), loan: num("loan"), rate: num("rate"), years: num("years"), homes: raw.homes, purpose: raw.purpose, loanConfirmed: raw.loanConfirmed };
  }, [raw]);
  const clear = () => {
    setRaw(EMPTY_RAW);
    setPersist(false);
    try {
      [KEY, ...OLD_KEYS].forEach((k) => window.localStorage.removeItem(k));
    } catch {
      // 무시
    }
  };
  return { raw, setRaw, money, persist, setPersist, clear };
}
export type MoneyState = ReturnType<typeof useMoney>;

/** 용어 도움말. 눌러서 펼친다. */
export function Term({ name, children }: { name: keyof typeof TERMS | string; children?: ReactNode }) {
  return (
    <details className="inline-block align-baseline [&_summary::-webkit-details-marker]:hidden">
      <summary className="cursor-pointer list-none underline decoration-dotted underline-offset-2">{children ?? name}<span aria-hidden className="ml-0.5 text-subtle">ⓘ</span></summary>
      <span role="note" className="mt-1 block max-w-xs rounded-lg bg-surface-muted px-2 py-1.5 text-[11px] font-normal leading-relaxed text-muted">{TERMS[name] ?? ""}</span>
    </details>
  );
}

/** 금액 입력: 천 단위 쉼표와 억·만원 변환 결과를 보여 준다. 빈칸과 0은 다르게 표시한다. */
export function AmountInput({ label, unit = "만원", value, onChange, hint, help }: { label: string; unit?: string; value: string; onChange: (v: string) => void; hint?: string; help?: string }) {
  const n = parseNumberInput(value);
  const converted = unit === "만원" && n !== null && Number.isFinite(n) ? formatManwon(n) : null;
  return (
    <label className="block text-xs">
      <span className="mb-0.5 flex items-baseline justify-between gap-2 font-bold">
        <span>{help ? <Term name={help}>{label}</Term> : label}</span>
        <span className="font-semibold text-subtle">{unit}</span>
      </span>
      <input inputMode="decimal" value={value} onChange={(e) => onChange(unit === "만원" ? formatAmountInput(e.target.value) : e.target.value.replace(/[^\d.]/g, ""))} placeholder="미입력" aria-label={`${label} (${unit})`} className={`${inputClass} w-full`} />
      <span className="mt-0.5 block text-[11px] text-subtle">{n === null ? hint ?? "비어 있음(미입력)" : converted ? `= ${converted}` : `${value}${unit}`}</span>
    </label>
  );
}

const SELECT = `${inputClass} w-full`;

export default function MoneyForm({ state }: { state: MoneyState }) {
  const { raw, setRaw, money, persist, setPersist, clear } = state;
  const set = (k: NumKey) => (v: string) => setRaw((r) => ({ ...r, [k]: v }));
  const ceiling = priceCeiling(money, money.loan ?? 0);
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
          <AmountInput label="부대비용 가정" unit="%" value={raw.costRate} onChange={set("costRate")} hint="취득세·중개보수 등 (매입가격 대비)" />
          <AmountInput label="확인한 대출 가능금액" value={raw.loan} onChange={set("loan")} hint="금융기관에서 들은 금액(가정)" />
          <AmountInput label="예상 대출금리" unit="%" value={raw.rate} onChange={set("rate")} />
          <AmountInput label="대출기간" unit="년" value={raw.years} onChange={set("years")} />
          <label className="col-span-2 flex items-center gap-2 text-xs">
            <input type="checkbox" checked={raw.loanConfirmed} onChange={(e) => setRaw((r) => ({ ...r, loanConfirmed: e.target.checked }))} />
            대출 가능금액을 금융기관 상담으로 확인했어요
          </label>
        </div>
      </details>
      <p className="text-xs">
        <b>매수 가격 상한(가정)</b> {ceiling.value === null ? "가용현금을 입력해 주세요" : formatManwon(ceiling.value)}
        <span className="block text-[11px] text-subtle">
          = (가용현금 − 예비비 + 대출 가정) ÷ (1 + 부대비용률).{ceiling.costMissing && " 부대비용이 미입력이라 0%로 계산한 입력된 비용 기준 가정 한도예요."} 대출 승인액이 아니에요.
        </span>
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2 text-[11px] text-subtle">
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />이 브라우저에 저장</label>
        <button type="button" onClick={clear} className="min-h-8 rounded-lg border border-border px-2 font-bold text-muted hover:text-fg">이 기기 저장값 지우기</button>
        <p className="w-full">입력값은 서버로 보내지 않아요. 저장을 켜면 이 기기 브라우저에만 남고, 끄거나 '지우기'를 누르면 삭제돼요.</p>
      </div>
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
      {rows.length === 0 ? (
        <p className="text-xs text-muted">'추가 입력'에 확인한 대출 가능금액을 넣으면 금액별로 비교해요.</p>
      ) : (
        <table className="w-full text-left text-[11px]">
          <thead className="text-subtle"><tr><th className="py-1">대출</th><th className="py-1 text-right">매수 가격 상한</th><th className="py-1 text-right">월 상환(가정)</th><th className="py-1 text-right">상환부담률*</th></tr></thead>
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
      <details className="text-[11px] text-muted">
        <summary className="cursor-pointer font-bold">금융기관에서 확인할 항목</summary>
        <ul className="mt-1 list-disc pl-4">{FIN_CHECKS.map((c) => <li key={c}>{c}</li>)}</ul>
      </details>
    </section>
  );
}
