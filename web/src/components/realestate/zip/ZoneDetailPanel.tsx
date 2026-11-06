"use client";

import { useRef, type KeyboardEvent } from "react";
import { DevelopmentBadge } from "../DevelopmentCard";
import type { DevelopmentProject, ZoneDetail } from "@/lib/realestate";
import InvestmentTab from "./tabs/InvestmentTab";
import ProjectInfoTab from "./tabs/ProjectInfoTab";
import TradeGuideTab from "./tabs/TradeGuideTab";
import TradesTab from "./tabs/TradesTab";
import type { DetailState } from "./useZoneDetail";

export const ZONE_TABS = [
  { id: "info", label: "사업정보" },
  { id: "trades", label: "실거래" },
  { id: "invest", label: "투자분석" },
  { id: "guide", label: "거래가이드" },
] as const;
export type ZoneTab = (typeof ZONE_TABS)[number]["id"];

/**
 * 선택한 개발구역의 상세 패널. 목록에서 받은 행(row)이 있으면 헤더를 바로 그리고, 상세 조회가 끝나면
 * 같은 화면에 채운다. 목록에 없는 사업(필터·완료사업 숨김)은 상세 응답만으로 그린다.
 */
export default function ZoneDetailPanel({
  projectId, row, detailState, retry, tab, onTab, onBack, onClose, onOpenTradeSearch,
}: {
  projectId: string;
  row: DevelopmentProject | null;
  detailState: DetailState;
  retry: () => void;
  tab: ZoneTab;
  onTab: (tab: ZoneTab) => void;
  onBack: () => void;
  onClose?: () => void;
  onOpenTradeSearch?: () => void;
}) {
  const detail: ZoneDetail | null = detailState.status === "ready" ? detailState.data : null;
  const project = detail?.project ?? row;
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = ZONE_TABS.length - 1;
    const next = event.key === "ArrowRight" ? (index + 1) % ZONE_TABS.length : event.key === "ArrowLeft" ? (index + last) % ZONE_TABS.length
      : event.key === "Home" ? 0 : event.key === "End" ? last : null;
    if (next === null) return;
    event.preventDefault();
    onTab(ZONE_TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="sticky top-0 z-10 border-b border-border bg-surface px-3 pb-0 pt-2.5">
        <div className="flex items-start gap-2">
          <button type="button" onClick={onBack} aria-label="목록으로 돌아가기"
            className="-ml-1 min-h-9 shrink-0 rounded-lg px-2 text-xs font-bold text-muted hover:text-fg">← 목록</button>
          <div className="min-w-0 flex-1">
            {project ? (
              <>
                <h2 className="break-words text-[15px] font-extrabold leading-snug">{project.name}</h2>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full bg-zip-soft px-2 py-0.5 text-[11px] font-bold text-zip">{project.type_label}</span>
                  {project.program_label && <DevelopmentBadge label={project.program_label} tone="muted" />}
                  <DevelopmentBadge label={project.location_accuracy.label} tone="muted" title={project.location_accuracy.note} />
                </div>
                <p className="mt-1 break-words text-[11px] text-subtle">
                  {[project.district, project.dong].filter(Boolean).join(" ") || "위치 정보 없음"}
                </p>
              </>
            ) : detailState.status === "error" ? (
              <p className="text-sm font-bold">사업 정보를 불러오지 못했어요</p>
            ) : (
              <div aria-busy="true"><div className="h-4 w-2/3 animate-pulse rounded bg-surface-muted" /><div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-surface-muted" /></div>
            )}
          </div>
          {onClose && (
            <button type="button" onClick={onClose} aria-label="닫기" className="min-h-9 shrink-0 rounded-lg px-2 text-base text-muted hover:text-fg">✕</button>
          )}
        </div>
        <div role="tablist" aria-label="구역 상세 정보" className="mt-2 flex gap-0.5 overflow-x-auto">
          {ZONE_TABS.map((t, index) => (
            <button
              key={t.id}
              ref={(node) => { tabRefs.current[index] = node; }}
              role="tab"
              id={`zone-tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`zone-panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              onClick={() => onTab(t.id)}
              onKeyDown={(e) => move(e, index)}
              className={`min-h-10 shrink-0 border-b-2 px-3 text-xs font-bold transition ${
                tab === t.id ? "border-zip text-zip" : "border-transparent text-muted hover:text-fg"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div
        role="tabpanel"
        id={`zone-panel-${tab}`}
        aria-labelledby={`zone-tab-${tab}`}
        tabIndex={0}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3"
      >
        {!project ? (
          detailState.status === "error" ? (
            <div role="alert" className="space-y-2">
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">{detailState.message}</p>
              {detailState.code !== 404 && (
                <button type="button" onClick={retry} className="min-h-9 rounded-xl border border-border px-3 text-xs font-bold">다시 시도</button>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted">사업 정보를 불러오고 있어요…</p>
          )
        ) : tab === "info" ? (
          <ProjectInfoTab project={project} detail={detail} detailState={detailState} retry={retry} />
        ) : tab === "trades" ? (
          <TradesTab state={detailState} project={project} onOpenTradeSearch={onOpenTradeSearch} />
        ) : tab === "invest" ? (
          <InvestmentTab projectId={projectId} />
        ) : (
          <TradeGuideTab project={project} timeline={detail?.process_timeline ?? null} state={detailState} />
        )}
      </div>
    </div>
  );
}
