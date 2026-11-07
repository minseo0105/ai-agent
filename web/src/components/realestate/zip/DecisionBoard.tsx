"use client";

import { STATUS_LABEL, VERIFY_STEPS, type Condition, type Status } from "@/lib/investDecision";

const TONE: Record<Status, string> = {
  MET: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  NOT_MET: "bg-red-500/15 text-red-700 dark:text-red-300",
  CHECK: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
};

/** 매수 가능 여부를 세 조건으로 따로 보여 준다. 셋 다 충족이어도 '매수 가능'이라고 단정하지 않는다. */
export default function DecisionBoard({ conditions }: { conditions: Condition[] }) {
  return (
    <section data-decision-board aria-label="매수 검토 결과" className="space-y-2">
      <h4 className="text-xs font-extrabold">매수 검토 결과 <span className="font-semibold text-subtle">조건별로 따로 판단해요</span></h4>
      {conditions.map((c) => (
        <details key={c.key} data-condition={c.key} data-status={c.status} className="rounded-lg border border-border px-2.5 py-2" open={c.status !== "MET"}>
          <summary className="flex cursor-pointer items-center justify-between gap-2 text-xs">
            <span className="font-bold">{c.title}</span>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-extrabold ${TONE[c.status]}`}>{STATUS_LABEL[c.status]}</span>
          </summary>
          <p className="mt-1 text-xs">{c.summary}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-relaxed text-muted">{c.items.map((i) => <li key={i}>{i}</li>)}</ul>
        </details>
      ))}
      <p className="text-[11px] text-subtle">가격이 예산 안이어도 거래허가·조합원 자격이 확인되기 전에는 매수 가능하다고 판단하지 않아요.</p>
      <details className="rounded-lg bg-surface-muted px-2.5 py-2 text-[11px] text-muted">
        <summary className="cursor-pointer font-bold">확인되지 않은 정보와 확인 방법</summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">{VERIFY_STEPS.map((v) => <li key={v}>{v}</li>)}</ul>
      </details>
    </section>
  );
}
