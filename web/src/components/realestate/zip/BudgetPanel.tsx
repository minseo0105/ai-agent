"use client";

import { useEffect, useMemo, useState } from "react";
import { inputClass } from "@/components/golf/ui";
import { budgetCheck, type Budget, type Homes } from "@/lib/budgetReview";
import { formatManwon, type SimInputs, type SimResult } from "@/lib/investmentCalc";
import { parseNumberInput } from "@/lib/zipFormat";

const KEY = "zip:budget:v1"; // 사업과 무관한 내 예산이라 하나만 저장한다(이 브라우저에만).
const FIELDS = [
  { key: "cash", label: "보유 현금" },
  { key: "reserve", label: "예비비", hint: "매수 후에도 남겨 둘 돈" },
  { key: "income", label: "연소득" },
  { key: "debt", label: "기존 부채", hint: "대출 잔액 합계" },
] as const;
type Values = Record<(typeof FIELDS)[number]["key"], string> & { homes: Homes };
const EMPTY: Values = { cash: "", reserve: "", income: "", debt: "", homes: "" };

/** 내 예산 점검. 아래 시뮬레이터의 매입가격·취득비용·대출·추가분담금 가정을 그대로 쓴다. */
export default function BudgetPanel({ sim, result, onCeiling }: { sim: SimInputs; result: SimResult; onCeiling?: (manwon: number | null) => void }) {
  const [v, setV] = useState<Values>(EMPTY);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) setV({ ...EMPTY, ...JSON.parse(raw) });
    } catch {
      // 저장소를 못 써도 계산은 된다.
    }
  }, []);
  const update = (patch: Partial<Values>) =>
    setV((prev) => {
      const next = { ...prev, ...patch };
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // 무시
      }
      return next;
    });
  const budget: Budget = useMemo(
    () => ({ cash: parseNumberInput(v.cash), reserve: parseNumberInput(v.reserve), income: parseNumberInput(v.income), debt: parseNumberInput(v.debt), homes: v.homes }),
    [v],
  );
  const r = useMemo(() => budgetCheck(budget, sim, result), [budget, sim, result]);
  useEffect(() => onCeiling?.(r.ceiling), [r.ceiling, onCeiling]);

  return (
    <section data-budget aria-label="내 예산 점검" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">내 예산 점검 <span className="font-semibold text-subtle">(만원 · 가정값)</span></h3>
      <div className="grid grid-cols-2 gap-2">
        {FIELDS.map((f) => (
          <label key={f.key} className="block text-xs">
            <span className="mb-0.5 block font-bold">{f.label}</span>
            <input inputMode="decimal" value={v[f.key]} onChange={(e) => update({ [f.key]: e.target.value })} placeholder="입력" aria-label={`${f.label} (만원)`} className={`${inputClass} w-full`} />
            {"hint" in f && <span className="mt-0.5 block text-[11px] text-subtle">{f.hint}</span>}
          </label>
        ))}
        <label className="col-span-2 block text-xs">
          <span className="mb-0.5 block font-bold">주택 보유</span>
          <select value={v.homes} onChange={(e) => update({ homes: e.target.value as Homes })} className={`${inputClass} w-full`}>
            <option value="">선택 안 함</option>
            <option value="0">무주택</option>
            <option value="1">1주택</option>
            <option value="2+">2주택 이상</option>
          </select>
        </label>
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">쓸 수 있는 현금</dt><dd className="text-right font-bold">{r.available === null ? "현금 입력 필요" : formatManwon(r.available)}</dd>
        <dt className="text-muted">매수 시 필요한 자기자금</dt><dd className="text-right font-bold">{r.need === null ? "매입가격 입력 필요" : formatManwon(r.need)}</dd>
        <dt className="text-muted">여유 / 부족</dt>
        <dd className={`text-right font-extrabold ${r.gap !== null && r.gap < 0 ? "text-red-600 dark:text-red-400" : ""}`}>{r.gap === null ? "—" : r.gap < 0 ? `부족 ${formatManwon(-r.gap)}` : `여유 ${formatManwon(r.gap)}`}</dd>
        <dt className="text-muted">{r.missingCosts.length ? "입력된 비용 기준 가정 한도" : "같은 가정의 최대 매입가격"}</dt><dd className="text-right font-bold">{r.ceiling === null ? "—" : formatManwon(r.ceiling)}</dd>
        {r.ceiling !== null && r.missingCosts.length > 0 && (
          <dd data-missing-costs className="col-span-2 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
            미입력: {r.missingCosts.join("·")}(0원으로 계산). 실제 매수 가능 한도가 아니며, 비용을 넣으면 낮아질 수 있어요.
          </dd>
        )}
        <dt className="text-muted">(기존 부채 + 입력 대출) ÷ 연소득 · DSR 아님</dt><dd className="text-right">{r.debtMultiple === null ? "—" : `${r.debtMultiple.toFixed(1)}배`}</dd>
      </dl>
      <ul className="list-disc space-y-0.5 pl-4 text-[11px] leading-relaxed text-muted">
        {r.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </section>
  );
}
