"use client";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import type { DevelopmentProject } from "@/lib/realestate";

const TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  info: "bg-surface-muted text-muted",
  muted: "bg-surface-muted text-muted",
};

/** 신뢰 상태 배지. 내부 enum 대신 사용자 문구만 노출한다. */
export function DevelopmentBadge({ label, tone = "info", title }: { label: string; tone?: string; title?: string }) {
  return (
    <span title={title} className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${TONE[tone] ?? TONE.info}`}>
      {label}
    </span>
  );
}

export default function DevelopmentCard({ project, compact = false }: { project: DevelopmentProject; compact?: boolean }) {
  const place = [project.district, project.dong].filter(Boolean).join(" ");
  const url = project.official_source.url;

  return (
    <div className={`rounded-2xl border border-border bg-surface ${compact ? "p-3" : "p-3.5"}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-estate-soft px-2 py-0.5 text-[11px] font-bold text-estate">{project.type_label}</span>
        {project.program_label && <DevelopmentBadge label={project.program_label} tone="muted" />}
        <DevelopmentBadge label={project.trust.label} tone={project.trust.tone} title={project.trust.note} />
      </div>
      <div className="mt-1.5 break-words text-[15px] font-extrabold leading-snug">{project.name}</div>
      <p className="mt-0.5 break-words text-xs text-muted">
        {[place, project.address].filter(Boolean).join(" · ") || "주소 확인 필요"}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-bold">{project.stage.label}</span>
        <span className="text-subtle">{project.stage_basis}</span>
        {project.last_checked && <span className="text-subtle">확인 {project.last_checked.slice(0, 10)}</span>}
        {project.spatial.code !== "UNKNOWN" && <span className="text-muted">{project.spatial.label}</span>}
        {typeof project.distance_m === "number" && <span className="text-muted">약 {Math.round(project.distance_m)}m</span>}
      </div>
      {!project.has_location && <p className="mt-1 text-[11px] text-subtle">{project.location_notice}</p>}

      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted transition hover:text-fg"
        >
          공식자료 ↗
        </a>
      )}

      <CollapsibleDetails label="상세보기">
        <DetailRow label="원문 사업명" value={project.name} />
        <DetailRow label="사업유형" value={project.type_label} />
        <DetailRow label="추진 프로그램" value={project.program_label} />
        <DetailRow label="주소" value={project.address} />
        <DetailRow label="공식 ID" value={project.official_id} />
        <DetailRow label="공식 기관" value={project.official_authority} />
        <DetailRow label="확인 단계" value={`${project.stage.label} · ${project.stage_basis}`} />
        <DetailRow label="공식 단계 표기" value={project.stage.official_text} />
        <DetailRow label="사업 상태" value={project.status_label} />
        <DetailRow label="검증 상태" value={`${project.trust.label} · ${project.trust.note}`} />
        <DetailRow label="공식 출처" value={project.official_source.name} />
        <DetailRow label="최근 확인" value={project.last_checked?.slice(0, 10)} />
      </CollapsibleDetails>
    </div>
  );
}
