"use client";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import StageTimeline from "./StageTimeline";
import type { MapFocus } from "./ZiponMap";
import type { DevelopmentProject } from "@/lib/realestate";

const TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  info: "bg-surface-muted text-muted",
  muted: "bg-surface-muted text-muted",
};

export function DevelopmentBadge({ label, tone = "info", title }: { label: string; tone?: string; title?: string }) {
  return (
    <span title={title} className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${TONE[tone] ?? TONE.info}`}>
      {label}
    </span>
  );
}

export default function DevelopmentCard({
  project,
  compact = false,
  onShowMap,
}: {
  project: DevelopmentProject;
  compact?: boolean;
  onShowMap?: (focus: MapFocus) => void;
}) {
  const place = [project.district, project.dong].filter(Boolean).join(" ");
  const url = project.official_source.url;
  const canMap = project.location_accuracy.code !== "NO_LOCATION";

  return (
    <div className={`rounded-2xl border border-border bg-surface ${compact ? "p-3" : "p-3.5"}`}>
      <div className="break-words text-[15px] font-extrabold leading-snug">{project.name}</div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-estate-soft px-2 py-0.5 text-[11px] font-bold text-estate">{project.type_label}</span>
        {project.program_label && <DevelopmentBadge label={project.program_label} tone="muted" />}
        <DevelopmentBadge label={project.trust.label} tone={project.trust.tone} title={project.trust.note} />
        <DevelopmentBadge label={project.location_accuracy.label} tone="muted" title={project.location_accuracy.note} />
      </div>
      <p className="mt-1 break-words text-xs text-muted">{[place, project.address].filter(Boolean).join(" · ") || "주소 확인 중"}</p>

      <div className="mt-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[11px] font-bold text-subtle">현재 단계</span>
          <span className="text-xs font-extrabold">{project.stage.label}</span>
        </div>
        <StageTimeline timeline={project.stage_timeline} />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-subtle">
        <span>{project.stage_basis}</span>
        {project.last_checked && <span>최근 확인 {project.last_checked.slice(0, 10).replace(/-/g, ".")}</span>}
        {project.distance_label && <span className="font-bold text-muted">{project.distance_label}</span>}
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {onShowMap && canMap && (
          <button
            type="button"
            onClick={() => onShowMap(null)}
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted transition hover:text-fg"
          >
            지도에서 보기
          </button>
        )}
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted transition hover:text-fg"
          >
            서울시 공식자료 ↗
          </a>
        )}
      </div>

      <CollapsibleDetails label="상세보기">
        <DetailRow label="공식 사업명" value={project.name} />
        <DetailRow label="공식 사업 ID" value={project.official_id} />
        <DetailRow label="담당기관" value={project.official_authority} />
        <DetailRow label="대표주소" value={project.address} />
        <DetailRow label="사업유형" value={project.type_label} />
        <DetailRow label="정책 프로그램" value={project.program_label} />
        <DetailRow label="현재단계" value={`${project.stage.label} · ${project.stage_basis}`} />
        <DetailRow label="공식 단계 표기" value={project.stage.official_text} />
        <DetailRow label="공식 출처" value={project.official_source.name} />
        <DetailRow label="최근 확인일" value={project.last_checked?.slice(0, 10)} />
        <DetailRow label="자료 신뢰수준" value={project.trust.note} />
        <DetailRow label="위치 정확도" value={project.location_accuracy.note} />
      </CollapsibleDetails>
    </div>
  );
}
