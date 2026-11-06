"use client";

import { useEffect, useRef } from "react";
import type { ZiponDevelopment } from "./useZiponDevelopment";

// 카드 렌더 상한. 넘으면 조용히 자르지 않고 몇 건을 보여주는지 화면에 적는다.
export const MAX_LIST_ITEMS = 200;

/** 패널의 목록 모드. 지도와 같은 응답의 사업을 보여 주고, 선택은 지도와 양방향으로 연결된다. */
export default function ZoneList({ data, onSelect }: { data: ZiponDevelopment; onSelect: (id: string) => void }) {
  const { visible, selectedId, ready, includeCompleted, hiddenCompleted, noDataForRegion, emptyDistricts, coveredDistricts } = data;
  const itemRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // 지도에서 고른 사업이 목록에 있으면 그 줄이 보이게 한다(화면 전체를 스크롤하지 않고 목록 안에서만).
  useEffect(() => {
    if (selectedId) itemRefs.current[selectedId]?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-3 py-2.5">
        <h2 className="text-sm font-extrabold">개발구역 {ready ? `${visible.length.toLocaleString("ko-KR")}건` : ""}</h2>
        <p className="mt-0.5 text-[11px] text-subtle">지도에서 구역을 누르거나 아래에서 골라 보세요.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-2">
        {ready && visible.length === 0 &&
          (noDataForRegion ? (
            <div role="status" data-state="region-no-data" className="rounded-xl border border-border bg-surface-muted px-3 py-3 text-sm">
              <p className="font-extrabold">현재 {emptyDistricts.length > 0 ? emptyDistricts.join("·") : "이 지역"}의 개발정보를 준비 중입니다.</p>
              <p className="mt-1 text-xs text-muted">
                조회는 정상으로 끝났고, 이 지역에 등록된 사업이 아직 0건이에요.
                {coveredDistricts.size > 0 && ` 지금은 ${[...coveredDistricts].sort().join("·")}의 개발정보를 보실 수 있어요.`}
              </p>
              {!includeCompleted && hiddenCompleted > 0 && (
                <p className="mt-1 text-xs text-subtle">완료된 사업까지 포함해 보려면 ‘완료사업 보기’를 켜 주세요.</p>
              )}
            </div>
          ) : (
            <p data-state="filtered-empty" className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">
              조건에 맞는 개발사업이 없어요. 유형·진행단계·검색어를 바꿔 보세요.
            </p>
          ))}
        <ul className="space-y-1.5">
          {visible.slice(0, MAX_LIST_ITEMS).map((p) => {
            const active = selectedId === p.project_id;
            return (
              <li key={p.project_id}>
                <button
                  type="button"
                  ref={(node) => { itemRefs.current[p.project_id] = node; }}
                  onClick={() => onSelect(p.project_id)}
                  aria-current={active ? "true" : undefined}
                  data-project-id={p.project_id}
                  className={`block w-full rounded-xl border px-3 py-2 text-left transition ${
                    active ? "border-zip bg-zip-soft/60" : "border-border bg-surface hover:border-zip/50"
                  }`}
                >
                  <span className="block break-words text-[13px] font-extrabold leading-snug">{p.name}</span>
                  <span className="mt-0.5 block text-[11px] text-muted">
                    {[p.type_label, p.program_label].filter(Boolean).join(" · ")} · {p.stage.label}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-subtle">
                    <span>{[p.district, p.dong].filter(Boolean).join(" ") || "위치 정보 없음"}</span>
                    {!p.mappable && <span className="rounded-full bg-surface-muted px-1.5 py-0.5 font-bold">지도 좌표 없음</span>}
                    {p.freshness?.stale && (
                      <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 font-bold text-amber-800 dark:text-amber-300">
                        {p.freshness.age_days}일 전 확인
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {visible.length > MAX_LIST_ITEMS && (
          <p className="mt-2 rounded-xl bg-surface-muted px-3 py-2.5 text-xs text-muted">
            {visible.length.toLocaleString("ko-KR")}건 중 {MAX_LIST_ITEMS}건을 보여드리고 있어요. 지역이나 유형을 좁혀 주세요.
          </p>
        )}
      </div>
    </div>
  );
}
