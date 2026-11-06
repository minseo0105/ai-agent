"use client";

import { DevelopmentBadge } from "../../DevelopmentCard";
import DevelopmentCard from "../../DevelopmentCard";
import StageTimeline from "../../StageTimeline";
import type { DevelopmentProject, ZoneDetail } from "@/lib/realestate";
import { NONE, formatArea, formatCount, formatDate } from "@/lib/zipFormat";
import CheckpointCard from "../CheckpointCard";
import ProcessTimeline from "../ProcessTimeline";
import type { DetailState } from "../useZoneDetail";

function Fact({ label, value, pending = false }: { label: string; value: string | null | undefined; pending?: boolean }) {
  const text = pending ? "불러오는 중…" : value || NONE;
  const empty = pending || !value || value === NONE || value.startsWith(NONE);
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 text-xs">
      <dt className="shrink-0 text-subtle">{label}</dt>
      <dd className={`min-w-0 break-words text-right ${empty ? "text-subtle" : "font-semibold"}`}>{text}</dd>
    </div>
  );
}

/** 데이터 출처와 수집일. 공식 고시일·기준일과 수집일은 서로 다른 날짜라 따로 적는다. */
function ProvenanceStrip({ project, detail, loading }: { project: DevelopmentProject; detail: ZoneDetail | null; loading: boolean }) {
  const source = detail?.sources.items.find((s) => s.official) ?? detail?.sources.items[0] ?? null;
  const sourceName = source?.name ?? project.official_source.name ?? NONE;
  const collected = detail?.provenance.last_collected_at ?? project.last_checked;
  return (
    <section aria-label="데이터 출처와 기준일" className="rounded-xl border border-border bg-surface-muted/60 px-3 py-2">
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <div><dt className="text-subtle">출처</dt><dd className="font-semibold">{sourceName}</dd></div>
        <div><dt className="text-subtle">최종 수집일</dt><dd className="font-semibold">{formatDate(collected)}</dd></div>
        <div><dt className="text-subtle">공식 기준일</dt><dd className="font-semibold">{loading ? "불러오는 중…" : formatDate(detail?.provenance.source_date ?? project.source_date)}</dd></div>
        <div><dt className="text-subtle">최근 고시일</dt><dd className="font-semibold">{loading ? "불러오는 중…" : formatDate(detail?.provenance.notice_date ?? project.notice_date)}</dd></div>
      </dl>
      {project.freshness?.stale && (
        <p role="status" className="mt-1.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
          {project.freshness.label} 현재와 다를 수 있으니 공식 사업정보를 함께 확인해 주세요.
        </p>
      )}
    </section>
  );
}

export default function ProjectInfoTab({
  project,
  detail,
  detailState,
  retry,
}: {
  project: DevelopmentProject;
  detail: ZoneDetail | null;
  detailState: DetailState;
  retry: () => void;
}) {
  const loading = detailState.status === "loading" || detailState.status === "idle";
  const facts = detail?.project.facts ?? null;
  const boundary = detail?.project.boundary ?? null;
  const place = [project.district, project.dong].filter(Boolean).join(" ");
  const naver = project.naver_real_estate;
  const officialUrl = project.official_source.url;

  return (
    <div className="space-y-3">
      <ProvenanceStrip project={project} detail={detail} loading={loading} />

      <section aria-label="현재 사업 단계">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-bold text-subtle">현재 사업단계</span>
          <span className="text-sm font-extrabold">{project.stage.label}</span>
          <DevelopmentBadge label={project.trust.label} tone={project.trust.tone} title={project.trust.note} />
        </div>
        <p className="mt-0.5 text-[11px] text-subtle">{project.stage_basis}</p>
        {project.stage_display && project.stage_display.label && !project.stage_display.legal_stage_confirmed && (
          <p data-stage-display className="mt-1 rounded-lg bg-surface-muted px-2 py-1.5 text-[11px] leading-relaxed text-muted">
            <span className="font-bold text-fg">표시 단계: {project.stage_display.label}</span>
            {" · "}공식 원문 “{project.stage_display.raw}”
            {project.stage_display.needs_official_check
              ? " · 공식 단계표에 없는 표기라 확인이 필요합니다."
              : " · 이해를 돕는 표시용 분류이며 공식 법적 단계가 아닙니다."}
          </p>
        )}
        {project.stage_description && <p className="mt-1 text-xs leading-relaxed text-muted">{project.stage_description}</p>}
      </section>

      {detailState.status === "ready" ? (
        <ProcessTimeline timeline={detailState.data.process_timeline} />
      ) : loading ? (
        <div aria-busy="true" className="space-y-2 rounded-xl border border-border px-3 py-3">
          <div className="h-3 w-2/3 animate-pulse rounded bg-surface-muted" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-surface-muted" />
          <div className="h-3 w-3/5 animate-pulse rounded bg-surface-muted" />
          <p className="text-[11px] text-subtle">사업 단계 타임라인을 불러오고 있어요…</p>
        </div>
      ) : (
        <div role="alert" className="space-y-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-3">
          <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
            {detailState.status === "error" ? detailState.message : "상세 정보를 불러오지 못했어요."} 목록에서 받은 정보만 표시합니다.
          </p>
          <button type="button" onClick={retry} className="min-h-9 rounded-xl border border-border bg-surface px-3 text-xs font-bold text-fg">
            다시 시도
          </button>
          <StageTimeline timeline={project.stage_timeline} />
        </div>
      )}

      <CheckpointCard project={project} timeline={detail?.process_timeline ?? null} />

      <section aria-label="핵심 사실">
        <h3 className="text-[11px] font-extrabold tracking-wide text-muted">사업 개요</h3>
        <dl className="mt-1 divide-y divide-border/60">
          <Fact label="사업유형" value={[project.type_label, project.program_label].filter(Boolean).join(" · ")} />
          <Fact label="위치" value={[place, project.address].filter(Boolean).join(" · ")} />
          <Fact label="사업 구역 면적" value={facts ? formatArea(facts.area_m2) : undefined} pending={loading} />
          <Fact label="예정 세대수" value={facts ? formatCount(facts.planned_units, "세대") : undefined} pending={loading} />
          <Fact label="최초 지정일" value={facts ? formatDate(facts.selected_date) : undefined} pending={loading} />
          <Fact label="추진 주체" value="정보 없음 (공식 데이터에 연결되지 않음)" />
          <Fact label="담당기관" value={facts?.official_authority} pending={loading} />
          <Fact label="공식 사업 ID" value={facts?.external_id ?? project.official_id} pending={loading} />
          <Fact label="위치 정확도" value={project.location_accuracy.label} />
          <Fact
            label="사업구역 경계"
            value={boundary ? (boundary.verified ? "공식 경계 확인" : "대표 위치만 있음(공식 경계 미확인)") : undefined}
            pending={loading}
          />
        </dl>
      </section>

      <div className="flex flex-wrap gap-2">
        {officialUrl && (
          <a href={officialUrl} target="_blank" rel="noopener noreferrer"
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted hover:text-fg">
            공식 사업 정보 보기
          </a>
        )}
        {naver && (
          <a href={naver.url} target="_blank" rel="noopener noreferrer"
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted hover:text-fg">
            {naver.label}
          </a>
        )}
      </div>

      <details className="rounded-xl border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-bold text-zip">변경 이력 · 출처 목록</summary>
        {detailState.status !== "ready" ? (
          <p className="mt-1.5 text-xs text-subtle">{loading ? "불러오고 있어요…" : "상세 정보를 불러오지 못해 표시할 수 없어요."}</p>
        ) : (
          <div className="mt-2 space-y-3">
            <div>
              <div className="text-[11px] font-bold text-subtle">최근 변경 이력</div>
              {detailState.data.recent_updates.state === "unavailable" ? (
                <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">변경 이력을 불러오지 못했어요.</p>
              ) : detailState.data.recent_updates.items.length === 0 ? (
                <p className="mt-1 text-xs text-subtle">기록된 변경 이력이 없어요.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-xs">
                  {detailState.data.recent_updates.items.map((u) => (
                    <li key={`${u.recorded_at}-${u.update_kind}`} className="flex flex-wrap gap-x-2">
                      <span className="font-bold">{u.kind_label}</span>
                      {(u.previous_stage || u.new_stage) && <span className="text-muted">{u.previous_stage ?? NONE} → {u.new_stage ?? NONE}</span>}
                      <span className="text-subtle">{formatDate(u.recorded_at)} 기록</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <div className="text-[11px] font-bold text-subtle">출처</div>
              {detailState.data.sources.state === "unavailable" ? (
                <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">출처 목록을 불러오지 못했어요.</p>
              ) : detailState.data.sources.items.length === 0 ? (
                <p className="mt-1 text-xs text-subtle">연결된 출처가 없어요.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-xs">
                  {detailState.data.sources.items.map((s, i) => (
                    <li key={`${s.url ?? s.name}-${i}`} className="flex flex-wrap gap-x-2">
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-bold text-zip hover:underline">{s.name ?? "출처"}</a>
                      ) : (
                        <span className="font-bold">{s.name ?? "출처"}</span>
                      )}
                      <span className="text-subtle">{s.official ? "공식 사이트" : "공식 여부 미확인"} · 수집 {formatDate(s.collected_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </details>
      {detailState.status === "error" && <DevelopmentCard project={project} compact />}
    </div>
  );
}
