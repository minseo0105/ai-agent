"use client";

import type { DevelopmentProject } from "@/lib/realestate";

/** 공식 자료로 확인된 단계만 표시한다. 없으면 진행 막대를 그리지 않는다. */
export default function StageTimeline({ timeline }: { timeline: DevelopmentProject["stage_timeline"] }) {
  const { steps, current_index: index, note } = timeline;
  if (index === null) {
    return <p className="text-[11px] text-subtle">{note ?? "공식 자료로 확인된 진행 단계가 아직 없습니다."}</p>;
  }
  const percent = steps.length > 1 ? (index / (steps.length - 1)) * 100 : 0;
  return (
    <div className="mt-1.5">
      <ol aria-label="공식 사업 진행단계" className="space-y-1 border-l-2 border-border pl-3 sm:hidden">
        {steps.map((step, i) => (Math.abs(i - index) <= 1) && (
          <li key={`${i}-${step}`} aria-current={i === index ? "step" : undefined}
            className={`text-[11px] ${i === index ? "font-bold text-estate" : "text-subtle"}`}>
            {i === index ? "● " : ""}{step}
          </li>
        ))}
      </ol>
      <div className="relative hidden h-1.5 rounded-full bg-surface-muted sm:block" aria-label={`현재 단계: ${steps[index]}`}>
        <div className="absolute inset-y-0 left-0 rounded-full bg-estate" style={{ width: `${percent}%` }} />
        <span
          aria-hidden
          className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-estate bg-surface"
          style={{ left: `${percent}%` }}
        />
      </div>
      <div className="mt-1 hidden justify-between text-[10px] text-subtle sm:flex">
        <span>{steps[0]}</span>
        <span className="font-bold text-estate">{steps[index]}</span>
        <span>{steps[steps.length - 1]}</span>
      </div>
    </div>
  );
}
