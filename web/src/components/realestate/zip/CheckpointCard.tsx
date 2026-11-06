"use client";

import type { DevelopmentProject, ProcessTimeline } from "@/lib/realestate";

/**
 * 거래 전 체크포인트. 이 단계에서 일반적으로 확인하는 질문을 보여 준다.
 * 이 사업에서 확인된 사실이 아니며, 법적 거래 가능 여부를 판정하지 않는다(질문형 안내).
 */
export default function CheckpointCard({
  project,
  timeline,
}: {
  project: Pick<DevelopmentProject, "stage_guide" | "investor_guide">;
  timeline: ProcessTimeline | null;
}) {
  const guide = project.stage_guide;
  const investor = project.investor_guide;
  const steps = timeline?.verified ? timeline.steps : [];
  const currentIndex = steps.findIndex((s) => s.status === "CURRENT");
  const currentStep = currentIndex >= 0 ? steps[currentIndex] : null;
  const nextStep = currentIndex >= 0 ? steps[currentIndex + 1] ?? null : null;

  // 같은 뜻의 질문이 겹치지 않게 합친다. 단계 안내(stage_guide)를 먼저, 타임라인 질문을 뒤에.
  const questions: string[] = [];
  for (const q of [...(guide?.checks ?? []), ...(currentStep?.questions ?? []), ...(investor?.watch_next ?? [])]) {
    if (!questions.includes(q)) questions.push(q);
  }
  if (!guide && !currentStep && !investor) return null;

  return (
    <section aria-label="거래 전 체크포인트" className="rounded-xl border border-zip/30 bg-zip-soft/50 px-3 py-3">
      <h3 className="text-[11px] font-extrabold tracking-wide text-zip">거래 전 체크포인트</h3>
      {guide && <p className="mt-1 text-xs leading-relaxed">{guide.plain}</p>}
      {investor?.interpreted && (
        <p className="mt-1.5 text-xs leading-relaxed text-muted">
          <span className="font-bold text-fg">{investor.phase_label} · {investor.risk_label}</span> — {investor.risk_note}
        </p>
      )}
      {questions.length > 0 && (
        <ul className="mt-2 space-y-1">
          {questions.map((q) => (
            <li key={q} className="flex gap-1.5 text-xs leading-relaxed">
              <span aria-hidden className="mt-0.5 text-zip">☐</span>
              <span>{q}</span>
            </li>
          ))}
        </ul>
      )}
      {nextStep && (
        <p className="mt-2 rounded-lg bg-surface/70 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted">
          <span className="font-bold text-fg">다음 단계({nextStep.label})</span>: {nextStep.meaning}
        </p>
      )}
      {investor?.pitfalls && investor.pitfalls.length > 0 && (
        <details className="mt-2 group">
          <summary className="cursor-pointer list-none text-[11px] font-bold text-zip marker:hidden">
            <span className="group-open:hidden">이 단계에서 흔한 함정 보기 ▾</span>
            <span className="hidden group-open:inline">접기 ▴</span>
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">
            {investor.pitfalls.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </details>
      )}
      <p className="mt-2 text-[11px] leading-relaxed text-subtle">
        {guide?.checks_note ?? "이 사업에서 확인된 값이 아니라, 이 단계에서 일반적으로 확인하는 항목이에요."}
        {" "}
        {investor?.disclaimer ??
          "법적 거래 가능 여부를 판정하지 않습니다. 거래 전에 관할 구청, 조합, 전문가에게 확인하세요."}
      </p>
    </section>
  );
}
