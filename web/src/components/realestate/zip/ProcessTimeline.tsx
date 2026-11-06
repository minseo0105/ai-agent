"use client";

import type { ProcessTimeline as Timeline, TimelineAuxRow, TimelineStatus, TimelineStep } from "@/lib/realestate";
import { stepDateText } from "@/lib/zipFormat";

const STATUS: Record<TimelineStatus, { label: string | null; dot: string; text: string }> = {
  CURRENT: { label: "현재", dot: "border-zip bg-zip text-white", text: "text-zip font-extrabold" },
  REACHED_DATED: { label: null, dot: "border-emerald-600 bg-emerald-600 text-white", text: "text-fg font-bold" },
  REACHED_UNDATED: { label: "일자 미공개", dot: "border-emerald-600 bg-emerald-600/25 text-emerald-700", text: "text-fg font-bold" },
  UPCOMING: { label: null, dot: "border-border bg-surface text-subtle", text: "text-muted" },
  NOT_RECORDED: { label: "기록 없음", dot: "border-dashed border-border bg-surface text-subtle", text: "text-muted" },
  USUALLY_SKIPPED: { label: "일반적으로 거치지 않음", dot: "border-dashed border-border bg-surface text-subtle", text: "text-subtle" },
};
const ICON: Record<TimelineStatus, string> = {
  CURRENT: "●", REACHED_DATED: "✓", REACHED_UNDATED: "✓", UPCOMING: "", NOT_RECORDED: "–", USUALLY_SKIPPED: "–",
};
const SR: Record<TimelineStatus, string> = {
  CURRENT: "현재 단계", REACHED_DATED: "도달, 일자 확인", REACHED_UNDATED: "지나온 단계, 일자 미공개",
  UPCOMING: "예정", NOT_RECORDED: "기록 없음", USUALLY_SKIPPED: "일반적으로 거치지 않는 단계",
};

function Dot({ status }: { status: TimelineStatus }) {
  return (
    <span
      aria-hidden
      className={`flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-extrabold ${STATUS[status].dot}`}
    >
      {ICON[status]}
    </span>
  );
}

function Chip({ status }: { status: TimelineStatus }) {
  const label = STATUS[status].label;
  if (!label) return null;
  const strong = status === "CURRENT";
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${strong ? "bg-zip-soft text-zip" : "bg-surface-muted text-subtle"}`}
    >
      {label}
    </span>
  );
}

function StepRow({ step, last }: { step: TimelineStep; last: boolean }) {
  const current = step.status === "CURRENT";
  return (
    <li aria-label={`${step.order}단계 ${step.label}, ${SR[step.status]}`} className="relative flex gap-2.5 pb-3 last:pb-0">
      {!last && <span aria-hidden className="absolute bottom-0 left-3 top-6 w-px bg-border" />}
      <Dot status={step.status} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className={`text-[13px] ${STATUS[step.status].text}`}>
            {step.order}. {step.label}
          </span>
          <Chip status={step.status} />
          <span className="text-[11px] text-subtle">
            {step.sub_items ? null : step.has_date || step.status !== "UPCOMING" ? stepDateText(step) : null}
          </span>
        </div>
        {step.sub_items && (
          <ul className="mt-0.5 space-y-0.5">
            {step.sub_items.map((sub) => (
              <li key={sub.official_name} className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted">
                <span className={sub.status === "CURRENT" ? "font-bold text-zip" : ""}>{sub.official_name}</span>
                <span className="text-subtle">
                  {sub.date || sub.date_display ? stepDateText(sub) : sub.status === "UPCOMING" ? "예정" : "일자 정보 없음"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <details className="mt-1 group" open={current}>
          <summary className="cursor-pointer list-none text-[11px] font-bold text-zip marker:hidden">
            <span className="group-open:hidden">의미·확인 질문 보기 ▾</span>
            <span className="hidden group-open:inline">접기 ▴</span>
          </summary>
          <div className="mt-1 space-y-1.5 rounded-lg bg-surface-muted px-2.5 py-2">
            <p className="text-xs leading-relaxed">{step.meaning}</p>
            {step.next_label && <p className="text-[11px] text-subtle">다음 단계: {step.next_label}</p>}
            <div>
              <div className="text-[11px] font-bold text-subtle">거래 전 확인 질문 (일반 안내)</div>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-xs text-muted">
                {step.questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </div>
            <p className="text-[11px] text-subtle">
              {step.doc.url ? (
                <a href={step.doc.url} target="_blank" rel="noopener noreferrer" className="font-bold text-zip underline-offset-2 hover:underline">
                  공식 사업 상세 페이지
                </a>
              ) : (
                "공식 문서 링크 없음"
              )}
              {" · "}단계별 문서 링크는 제공되지 않습니다.
            </p>
          </div>
        </details>
      </div>
    </li>
  );
}

function AuxRows({ title, rows }: { title: string; rows: TimelineAuxRow[] }) {
  // 기록이 있거나 현재 단계인 줄만 보여 준다. 빈 보조 줄로 화면을 채우지 않는다.
  const shown = rows.filter((r) => r.is_current || r.has_date || r.status === "USUALLY_SKIPPED");
  if (!shown.length) return null;
  return (
    <div className="mt-2 rounded-lg border border-dashed border-border px-2.5 py-2">
      <div className="text-[11px] font-bold text-subtle">{title}</div>
      <ul className="mt-1 space-y-0.5">
        {shown.map((row) => (
          <li key={row.official_name} className="flex flex-wrap items-center gap-x-2 text-xs">
            <span className={row.is_current ? "font-extrabold text-zip" : "text-muted"}>{row.label}</span>
            {row.is_current && <Chip status="CURRENT" />}
            {row.status === "USUALLY_SKIPPED" ? (
              <span className="text-[11px] text-subtle">일반적으로 거치지 않는 단계(공식 기록 없음)</span>
            ) : (
              <span className="text-[11px] text-subtle">{stepDateText(row)}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 공식 14단계를 안내용 8단계로 요약한 타임라인. 공식 정보가 다르면 공식 정보를 우선 표시한다. */
export default function ProcessTimeline({ timeline }: { timeline: Timeline }) {
  const current = timeline.current_official;
  if (!timeline.verified) {
    return (
      <section aria-label="사업 단계 타임라인" className="rounded-xl border border-border bg-surface-muted/60 px-3 py-3">
        <div className="text-[11px] font-extrabold tracking-wide text-muted">사업 단계</div>
        <p className="mt-1 text-sm font-extrabold">{current.name ?? "세부 진행단계 확인 중"}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">{timeline.unverified_note}</p>
        <p className="mt-1 text-[11px] text-subtle">서울시 공식 목록에서 확인한 현재 단계만 표시합니다. 이전·이후 단계는 추정하지 않습니다.</p>
      </section>
    );
  }
  return (
    <section aria-label="사업 단계 타임라인">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-zip-soft px-2 py-0.5 text-[11px] font-bold text-zip">
          {timeline.flow.label} 흐름 · 안내용
        </span>
        {timeline.program_label && (
          <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-bold text-muted">{timeline.program_label}</span>
        )}
      </div>
      {timeline.progress ? (
        <p className="mt-1.5 text-sm font-extrabold">{timeline.progress.phrase}</p>
      ) : (
        timeline.closing_note && <p className="mt-1.5 text-xs font-bold leading-relaxed text-amber-800 dark:text-amber-300">{timeline.closing_note}</p>
      )}
      {!current.in_standard_steps && current.name && (
        <p className="mt-1 text-xs text-muted">
          공식 현재 단계 <span className="font-extrabold text-zip">{current.name}</span>
          {current.recognised ? "는 8단계 밖의 단계라 아래 보조 줄에 표시했어요." : "는 공식 14단계 목록에 없는 이름이라 8단계에 대응시키지 않았어요."}
        </p>
      )}
      <AuxRows title="사전 단계 (8단계 밖)" rows={timeline.pre_steps} />
      <ol className="mt-3" aria-label="8개 주요 단계">
        {timeline.steps.map((step, index) => (
          <StepRow key={step.key} step={step} last={index === timeline.steps.length - 1} />
        ))}
      </ol>
      <AuxRows title="분양·종료 기록 (8단계 밖)" rows={[...timeline.extra_steps, ...timeline.closing_steps]} />
      <p className="mt-2 text-[11px] leading-relaxed text-subtle">{timeline.flow.note}</p>
      <p className="mt-0.5 text-[11px] leading-relaxed text-subtle">{timeline.guide_note}</p>
    </section>
  );
}
