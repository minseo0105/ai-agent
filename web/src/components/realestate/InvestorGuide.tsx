"use client";

import CollapsibleDetails from "./CollapsibleDetails";
import type { InvestorGuideBlock } from "@/lib/realestate";

const RISK_TONE: Record<string, string> = {
  HIGH: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  MEDIUM: "bg-surface-muted text-muted",
  LOW: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  UNKNOWN: "bg-surface-muted text-subtle",
};

/**
 * 이 단계에서 일반적으로 알아둘 점. 이 사업에서 확인된 사실이 아니라 단계별 일반 안내이며
 * 투자 권유가 아니다. 접어 두고, 펼치면 면책 문구를 항상 같이 보여 준다.
 */
export default function InvestorGuide({ guide }: { guide: InvestorGuideBlock | null | undefined }) {
  if (!guide) return null;
  return (
    <CollapsibleDetails label="이 단계에서 알아둘 점" openLabel="알아둘 점 접기">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full border border-border px-2 py-0.5 text-[11px] font-bold text-muted">
          {guide.phase_label}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${RISK_TONE[guide.risk_level] ?? RISK_TONE.UNKNOWN}`}>
          {guide.risk_label}
        </span>
      </div>
      <p className="text-xs leading-relaxed">{guide.risk_note}</p>
      {guide.watch_next.length > 0 && (
        <div>
          <div className="text-[11px] font-bold text-subtle">다음에 지켜볼 것</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">
            {guide.watch_next.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
      {guide.pitfalls.length > 0 && (
        <div>
          <div className="text-[11px] font-bold text-subtle">이 단계에서 흔한 함정</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">
            {guide.pitfalls.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
      <p className="text-[11px] leading-relaxed text-subtle">{guide.disclaimer}</p>
    </CollapsibleDetails>
  );
}
