"use client";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import type { DevelopmentProject } from "@/lib/realestate";

const TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  info: "bg-estate-soft text-estate",
  muted: "bg-surface-muted text-muted",
};

/** 신뢰 상태 배지. 내부 enum 대신 사용자 문구만 노출한다. */
export function DevelopmentBadge({ label, tone = "info", title }: { label: string; tone?: string; title?: string }) {
  return (
    <span title={title} className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${TONE[tone] ?? TONE.info}`}>
      {label}
    </span>
  );
}

export default function DevelopmentCard({ project, compact = false }: { project: DevelopmentProject; compact?: boolean }) {
  const place = [project.district, project.dong].filter(Boolean).join(" ");
  return (
    <div className={`rounded-2xl border border-border bg-surface ${compact ? "p-3" : "p-3.5"} shadow-sm`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <DevelopmentBadge label={project.type_label} tone="info" />
        {project.program_label && <DevelopmentBadge label={project.program_label} tone="muted" />}
        <DevelopmentBadge label={project.trust.label} tone={project.trust.tone} title={project.trust.note} />
      </div>
      <div className="mt-1.5 text-[15px] font-extrabold leading-snug">{project.name}</div>
      <p className="mt-0.5 text-xs text-muted">
        {[place, project.address].filter(Boolean).join(" · ") || "주소 확인 필요"}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-bold text-estate">{project.stage.label}</span>
        <span className="text-subtle">{project.stage_basis}</span>
        {project.spatial.code !== "UNKNOWN" && <span className="text-muted">{project.spatial.label}</span>}
        {typeof project.distance_m === "number" && <span className="text-muted">약 {Math.round(project.distance_m)}m</span>}
      </div>
      {!project.has_location && <p className="mt-1 text-[11px] text-subtle">{project.location_notice}</p>}
      <CollapsibleDetails label="상세보기" count={4}>
        <DetailRow label="공식 단계 표기" value={project.stage.official_text} />
        <DetailRow label="사업 상태" value={project.status_label} />
        <DetailRow label="자료 신뢰도" value={project.trust.note} />
        <DetailRow label="마지막 확인" value={project.last_checked?.slice(0, 10)} />
        <DetailRow label="공식 출처" value={project.official_source.name} />
        {project.official_source.url && (
          <a
            href={project.official_source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block text-xs font-bold text-estate hover:underline"
          >
            공식 자료 확인 ↗
          </a>
        )}
      </CollapsibleDetails>
    </div>
  );
}
