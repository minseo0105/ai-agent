"use client";
import { trackUsage } from "@/lib/analytics";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import StageTimeline from "./StageTimeline";
import ZiponMap, { type MapFocus } from "./ZiponMap";
import type { DevelopmentMapPoint, DevelopmentProject, MapConfig } from "@/lib/realestate";

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
  point = null,
  mapConfig = null,
  selected = false,
}: {
  project: DevelopmentProject;
  compact?: boolean;
  onShowMap?: (focus: MapFocus) => void;
  /**
   * 이 사업의 지도 point. 목록과 같은 응답에서 온 것을 그대로 받는다. 카드가 좌표를
   * 따로 만들거나 복제하지 않기 위해서다. boundary를 함께 들고 오므로, 공식 경계가
   * 확보되면 같은 경로로 Polygon이 그려진다.
   */
  point?: DevelopmentMapPoint | null;
  mapConfig?: MapConfig | null;
  /** 선택된 카드에서만 지도를 그린다. 목록 전체에 지도를 띄우지 않는다. */
  selected?: boolean;
}) {
  const place = [project.district, project.dong].filter(Boolean).join(" ");
  const url = project.official_source.url;
  const canMap = project.location_accuracy.code !== "NO_LOCATION";

  return (
    <div
      className={`rounded-2xl border bg-surface transition ${compact ? "p-3" : "p-3.5"} ${
        // 선택된 카드는 테두리와 배경으로 확실히 구분한다. 어느 카드를 보고 있는지가
        // 목록에서 바로 보여야 지도와 연결이 끊기지 않는다.
        selected ? "border-estate bg-estate-soft/40 shadow-sm" : "border-border"
      }`}
    >
      <div className="break-words text-[15px] font-extrabold leading-snug">{project.name}</div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-estate-soft px-2 py-0.5 text-[11px] font-bold text-estate">{project.type_label}</span>
        {project.program_label && <DevelopmentBadge label={project.program_label} tone="muted" />}
        <DevelopmentBadge label={project.trust.label} tone={project.trust.tone} title={project.trust.note} />
        <DevelopmentBadge label={project.location_accuracy.label} tone="muted" title={project.location_accuracy.note} />
      </div>
      <p className="mt-1 break-words text-xs text-muted">{[place, project.address].filter(Boolean).join(" · ") || "주소 확인 중"}</p>

      {selected && (
        <section className="mt-2.5" aria-label="사업 위치">
          <h4 className="mb-1.5 text-[11px] font-extrabold tracking-wide text-muted">사업 위치</h4>
          {project.mappable && point ? (
            <>
              <ZiponMap
                points={[point]}
                config={mapConfig}
                selectedId={project.project_id}
                height={190}
                compact
              />
              {project.address && (
                <p className="mt-1.5 break-words text-[11px] text-subtle">{project.address}</p>
              )}
              {/* 확인된 공식 경계가 있으면 면이 그려진다. 그때만 구역이라고 말한다. */}
              {point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary ? (
                <p className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-subtle">
                  <span
                    aria-hidden
                    className="inline-block size-2 rounded-sm border border-estate bg-estate/20"
                  />
                  {point.boundary_status_label} · 공식 사업구역
                </p>
              ) : (
                <p className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-subtle">
                  <span aria-hidden className="inline-block size-2 rounded-full bg-estate" />
                  사업 대표위치
                </p>
              )}
            </>
          ) : (
            // 좌표가 없으면 서울 중심 지도를 대신 띄우지 않는다. 가짜 위치를 만들지 않는다.
            <p className="rounded-lg bg-surface-muted px-2.5 py-2 text-[11px] text-muted">
              아직 확인된 사업 위치가 없습니다.
            </p>
          )}
        </section>
      )}

      <div className="mt-2">
        <div className="flex items-baseline justify-between gap-2">
          {/* 행정 용어 대신 사용자가 읽는 말로. 값 자체는 공식 단계 그대로다. */}
          <span className="text-[11px] font-bold text-subtle">현재 사업단계</span>
          <span className="text-xs font-extrabold">{project.stage.label}</span>
        </div>
        <StageTimeline timeline={project.stage_timeline} />
        {project.stage_description && <p className="mt-2 text-xs leading-relaxed text-muted">{project.stage_description}</p>}
      </div>

      {project.stage_guide && (
        <>
          <div className="mt-2 rounded-xl bg-surface-muted px-3 py-2.5">
            <div className="text-[11px] font-bold text-subtle">쉽게 말하면</div>
            <p className="mt-0.5 text-xs leading-relaxed">{project.stage_guide.plain}</p>
          </div>
          <div className="mt-2">
            <div className="text-[11px] font-bold text-subtle">매수 전 체크</div>
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {project.stage_guide.checks.map((check) => (
                <li
                  key={check}
                  className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted"
                >
                  {check}
                </li>
              ))}
            </ul>
            {/* 이 사업에서 확인된 값이 아니라는 것을 화면에서도 분명히 한다. */}
            <p className="mt-1 text-[11px] text-subtle">{project.stage_guide.checks_note}</p>
          </div>
        </>
      )}

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
            onClick={() => trackUsage("external_link_click", "official_source_click")}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted transition hover:text-fg"
          >
            공식 사업정보 ↗
          </a>
        )}
        {/* 주변 매물 탐색. 위치 근거가 없으면 서버가 링크를 만들지 않으므로 여기도 비어 있다. */}
        {project.naver_real_estate && (
          <a
            href={project.naver_real_estate.url}
            onClick={() => trackUsage("external_link_click", "naver_land_click")}
            target="_blank"
            rel="noopener noreferrer"
            title={project.naver_real_estate.note}
            className="inline-flex min-h-9 items-center rounded-xl border border-border px-3 text-xs font-bold text-muted transition hover:text-fg"
          >
            {project.naver_real_estate.label} ↗
          </a>
        )}
      </div>

      {/* 연결이 없으면 왜 없는지 적는다. 버튼이 사라진 이유를 모르는 것이 가장 나쁘다.
          서버가 확인된 링크 형식을 갖출 때까지 이 자리에는 안내만 남는다. */}
      {project.naver_real_estate ? (
        <p className="mt-1 break-words text-[11px] text-subtle">
          연결 위치: {project.naver_real_estate.search_query}
        </p>
      ) : (
        <p className="mt-1 break-words text-[11px] text-subtle">
          네이버부동산 연결은 준비 중입니다. 위 지도에서 이 사업의 위치를 확인할 수 있어요.
        </p>
      )}

      <CollapsibleDetails label="상세보기">
        {!!project.stage_history?.length && (
          <section className="mb-3" aria-label="공식 진행이력">
            <h4 className="mb-2 text-xs font-bold">공식 진행이력</h4>
            <ol className="space-y-1 text-xs">
              {project.stage_history.filter(item => item.stage_date || item.is_current).map(item => (
                <li key={item.stage_order} className="flex justify-between gap-3">
                  <span className={item.is_current ? "font-bold text-estate" : "text-muted"}>
                    {item.is_current ? "● " : ""}{item.stage_name}
                  </span>
                  <span>{item.stage_date?.replace(/-/g, ".") ?? "날짜 미공개"}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
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
