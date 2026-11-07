"use client";

import { useEffect, useMemo } from "react";
import { inputClass } from "@/components/golf/ui";
import { budgetCheck, type Budget, type Homes } from "@/lib/budgetReview";
import { formatManwon, type SimInputs, type SimResult } from "@/lib/investmentCalc";
import { AmountInput, useMoney } from "./MoneyForm";

const SHARED = [
  { key: "cash", label: "가용현금" },
  { key: "reserve", label: "예비비", hint: "매수 후에도 남겨 둘 돈" },
  { key: "income", label: "연소득" },
  { key: "debt", label: "기존 대출 잔액", hint: "대출 잔액 합계" },
] as const;
const LABELS = SHARED.map((f) => f.label) as string[];

/**
 * 상세 분석의 예산 점검. 현금·예비비·소득·부채·주택 보유는 '내 자금'과 같은 상태를 쓴다(따로 저장하지 않음).
 * 매입가격·취득비용·대출·추가분담금은 아래 시뮬레이터 가정을 그대로 쓴다.
 */
export default function BudgetPanel({ sim, result, onCeiling }: { sim: SimInputs; result: SimResult; onCeiling?: (manwon: number | null) => void }) {
  const { raw, money, setRaw } = useMoney();
  const sharedBad = money.invalid.filter((l) => LABELS.includes(l));
  const simBad = result.invalid.length > 0;
  const budget: Budget = useMemo(() => ({ cash: money.cash, reserve: money.reserve, income: money.income, debt: money.debt, homes: money.homes as Homes }), [money]);
  const r = useMemo(() => budgetCheck(budget, sim, result), [budget, sim, result]);
  const blocked = sharedBad.length > 0 || simBad;
  const ceiling = blocked ? null : r.ceiling;
  useEffect(() => onCeiling?.(ceiling), [ceiling, onCeiling]);

  return (
    <section data-budget aria-label="내 예산 점검" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">내 예산 점검 <span className="font-semibold text-subtle">(만원 · 가정값 · &apos;내 자금&apos;과 같은 값)</span></h3>
      <div className="grid grid-cols-2 gap-2">
        {SHARED.map((f) => (
          <AmountInput key={f.key} label={f.label} value={raw[f.key]} onChange={(v) => setRaw((o) => ({ ...o, [f.key]: v }))} hint={"hint" in f ? f.hint : undefined} />
        ))}
        <label className="col-span-2 block text-xs">
          <span className="mb-0.5 block font-bold">주택 보유</span>
          <select value={raw.homes} onChange={(e) => setRaw((o) => ({ ...o, homes: e.target.value as Homes }))} className={`${inputClass} w-full`}>
            <option value="">선택 안 함</option>
            <option value="0">무주택</option>
            <option value="1">1주택</option>
            <option value="2+">2주택 이상</option>
          </select>
        </label>
      </div>
      {blocked ? (
        <p role="status" className="text-xs font-bold text-red-600 dark:text-red-400">
          입력 오류·추가 확인 필요: {[...sharedBad, ...(simBad ? ["시뮬레이터 입력"] : [])].join(", ")} 값을 확인해 주세요.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <dt className="text-muted">쓸 수 있는 현금</dt><dd className="text-right font-bold">{r.available === null ? "현금 입력 필요" : formatManwon(r.available)}</dd>
          <dt className="text-muted">매수 시 필요한 자기자금</dt><dd className="text-right font-bold">{r.need === null ? "매입가격 입력 필요" : formatManwon(r.need)}</dd>
          <dt className="text-muted">여유 / 부족</dt>
          <dd className={`text-right font-extrabold ${r.gap !== null && r.gap < 0 ? "text-red-600 dark:text-red-400" : ""}`}>{r.gap === null ? "—" : r.gap < 0 ? `부족 ${formatManwon(-r.gap)}` : `여유 ${formatManwon(r.gap)}`}</dd>
          <dt className="text-muted">{r.missingCosts.length ? "입력된 비용 기준 가정 한도" : "입력 조건상 추정 상한"}</dt><dd className="text-right font-bold">{r.ceiling === null ? "—" : formatManwon(r.ceiling)}</dd>
          {r.ceiling !== null && r.missingCosts.length > 0 && (
            <dd data-missing-costs className="col-span-2 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
              미입력: {r.missingCosts.join("·")}(0원으로 계산). 실제 매수 가능 한도가 아니며, 비용을 넣으면 낮아질 수 있어요.
            </dd>
          )}
          <dt className="text-muted">(기존 부채 + 입력 대출) ÷ 연소득 · DSR 아님</dt><dd className="text-right">{r.debtMultiple === null ? "—" : `${r.debtMultiple.toFixed(1)}배`}</dd>
        </dl>
      )}
      <p className="text-[11px] text-subtle">이 점검은 아래 시뮬레이터의 취득 관련 비용·추가분담금·금융비용(이자)·기타 비용을 포함해요. 보유세·양도세는 포함하지 않아요.</p>
      <ul className="list-disc space-y-0.5 pl-4 text-[11px] leading-relaxed text-muted">
        {r.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </section>
  );
}

