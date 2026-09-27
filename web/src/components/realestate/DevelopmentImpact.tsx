"use client";

import type { DevelopmentImpactBlock } from "@/lib/realestate";

function Row({ label, value, strong = false }: { label: string; value: React.ReactNode; strong?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5 text-xs">
      <span className="shrink-0 text-subtle">{label}</span>
      <span className={`min-w-0 break-words text-right ${strong ? "font-extrabold text-estate" : "font-semibold"}`}>{value}</span>
    </div>
  );
}

/** '이 부동산과 개발사업의 관계'를 사용자 언어로 보여준다. 내부 상태값은 쓰지 않는다. */
export default function DevelopmentImpact({
  impact,
  onShowMap,
}: {
  impact: DevelopmentImpactBlock;
  onShowMap?: () => void;
}) {
  const nearest = impact.nearest;
  return (
    <section className="mt-2 rounded-xl bg-surface-muted p-2.5">
      <h4 className="text-[11px] font-extrabold tracking-wide text-muted">개발사업 영향</h4>
      <div className="mt-1 divide-y divide-border/60">
        <Row label="정비구역 내부 여부" value={impact.inside.label} strong={impact.inside.code === "INSIDE"} />
        {nearest && (
          <>
            <Row label="가까운 개발사업" value={nearest.name} />
            {nearest.distance_label && <Row label="거리" value={nearest.distance_m ? `${nearest.distance_label} (약 ${Math.round(nearest.distance_m)}m)` : nearest.distance_label} />}
            <Row label="사업유형" value={nearest.type_label} />
            {nearest.program_label && <Row label="정책" value={nearest.program_label} />}
            <Row label="현재단계" value={`${nearest.stage_label} · ${nearest.stage_basis}`} />
            {nearest.official_source.name && <Row label="공식 확인" value={nearest.official_source.name} />}
          </>
        )}
      </div>
      {impact.inside.notice && <p className="mt-1.5 text-[11px] leading-relaxed text-subtle">{impact.inside.notice}</p>}
      {onShowMap && impact.has_map_point && (
        <button
          type="button"
          onClick={onShowMap}
          className="mt-2 inline-flex min-h-9 items-center rounded-xl border border-border bg-surface px-3 text-xs font-bold text-muted transition hover:text-fg"
        >
          지도에서 보기
        </button>
      )}
    </section>
  );
}
