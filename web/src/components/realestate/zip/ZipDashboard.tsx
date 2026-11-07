"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { trackUsage } from "@/lib/analytics";
import type { EstateOptions } from "@/lib/realestate";
import ZiponMap, { type MapFocus } from "../ZiponMap";
import DashboardNotices from "./DashboardNotices";
import DashboardToolbar from "./DashboardToolbar";
import MobileSheet, { type SheetSnap } from "./MobileSheet";
import ZoneDetailPanel, { type ZoneTab } from "./ZoneDetailPanel";
import ZoneList from "./ZoneList";
import { useZiponDevelopment } from "./useZiponDevelopment";
import { useZoneDetail } from "./useZoneDetail";

const HASH = /^#zone=([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;
// 데스크톱 기준. 이보다 좁으면 패널이 지도 위로 열리는 바텀시트가 된다.
const DESKTOP = "(min-width: 1024px)";
const PEEK_RATIO = 0.42; // MobileSheet의 peek 높이(42svh)와 같은 값

function useMediaQuery(query: string): boolean {
  // 이 컴포넌트는 옵션을 받은 뒤(클라이언트)에만 마운트되므로 첫 렌더에서 바로 읽어도 하이드레이션 불일치가 없다.
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);
  return matches;
}

function useViewportHeight(): number {
  const [height, setHeight] = useState(() => (typeof window !== "undefined" ? window.innerHeight : 800));
  useEffect(() => {
    const update = () => setHeight(window.innerHeight);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return height;
}

/**
 * ZIP 개발지도 대시보드. 좌측 지도 65% · 우측 상세 패널 35%(1024px 이상), 그보다 좁으면 지도 위 바텀시트.
 * 선택(selectedId)은 하나이고 지도·목록·패널이 모두 이 값을 따른다(양방향 연동). 주소의 #zone=<id>에 저장해
 * 새로고침과 링크 공유 때 복원한다.
 */
export default function ZipDashboard({
  options, property = null, onOpenTradeSearch,
}: {
  options: EstateOptions;
  property?: MapFocus;
  onOpenTradeSearch?: () => void;
}) {
  const data = useZiponDevelopment(options);
  const { selectedId, setSelectedId } = data;
  const desktop = useMediaQuery(DESKTOP);
  const viewport = useViewportHeight();
  const [tab, setTab] = useState<ZoneTab>("info");
  const [snap, setSnap] = useState<SheetSnap>("peek");
  const [listOpen, setListOpen] = useState(false);
  const [hashLoaded, setHashLoaded] = useState(false);
  const [bottomInset, setBottomInset] = useState(0);
  const mapBox = useRef<HTMLDivElement>(null);
  const { state: detailState, retry } = useZoneDetail(selectedId);

  // 주소 해시 → 선택. 첫 렌더에서 해시를 지우지 않도록, 읽은 뒤에만 쓰기 시작한다.
  useEffect(() => {
    const read = () => {
      const match = HASH.exec(window.location.hash);
      setSelectedId(match ? match[1].toLowerCase() : null);
    };
    read();
    setHashLoaded(true);
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [setSelectedId]);
  useEffect(() => {
    if (!hashLoaded) return;
    const target = selectedId ? `#zone=${selectedId}` : "";
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${target}`);
    }
  }, [selectedId, hashLoaded]);

  const select = useCallback(
    (id: string | null, source: "map" | "list") => {
      if (id && id !== selectedId) setTab("info");
      setSelectedId(id);
      if (!id) return;
      trackUsage(source === "map" ? "map_click" : "project_click");
      if (!desktop) {
        setSnap("peek");
        setListOpen(false);
      }
    },
    [selectedId, setSelectedId, desktop],
  );

  // 데스크톱에서는 Esc로 상세를 닫고 목록으로 돌아간다(모바일 시트는 자체 Esc 처리).
  useEffect(() => {
    if (!desktop || !selectedId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLSelectElement)) {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [desktop, selectedId, setSelectedId]);

  const panel = selectedId ? (
    <ZoneDetailPanel
      projectId={selectedId}
      row={data.selectedRow}
      detailState={detailState}
      retry={retry}
      tab={tab}
      onTab={setTab}
      onBack={() => {
        setSelectedId(null);
        if (!desktop) setListOpen(true);
      }}
      onClose={desktop ? undefined : () => setSelectedId(null)}
      onOpenTradeSearch={onOpenTradeSearch}
    />
  ) : (
    <ZoneList data={data} onSelect={(id) => select(id, "list")} />
  );
  const sheetOpen = !desktop && (selectedId !== null || listOpen);

  // 시트(peek)가 지도 아래를 덮는 높이. 시트 높이가 아니라 지도 영역과 겹치는 만큼만 보정한다.
  // (지도 영역은 뷰포트보다 작아서 시트의 일부만 지도와 겹친다.)
  useEffect(() => {
    if (desktop || !selectedId || snap !== "peek" || !mapBox.current) {
      setBottomInset(0);
      return;
    }
    const rect = mapBox.current.getBoundingClientRect();
    setBottomInset(Math.max(0, Math.round(rect.bottom - viewport * (1 - PEEK_RATIO))));
  }, [desktop, selectedId, snap, viewport]);

  return (
    <div data-zip-dashboard className="space-y-3">
      <DashboardToolbar data={data} />
      <DashboardNotices data={data} />

      <div className="grid gap-3 lg:grid-cols-[65fr_35fr]">
        <div ref={mapBox} className="relative h-[calc(100svh-19rem)] min-h-[420px] lg:h-[calc(100svh-21rem)] lg:min-h-[520px]">
          {/* 조회 상태와 무관하게 지도는 한 번 만들고 유지한다. 지역을 바꾸거나 조회가 실패할 때마다
              인스턴스가 파괴되고 SDK 초기화가 다시 도는 것을 막는다. */}
          {data.config ? (
            <ZiponMap
              points={data.visiblePoints}
              property={property}
              config={data.config}
              selectedId={selectedId}
              fill
              bottomInset={bottomInset}
              onSelect={(id) => select(id, "map")}
            />
          ) : (
            <div className="flex h-full items-center justify-center rounded-2xl border border-border bg-surface-muted text-xs text-muted">지도를 준비하고 있어요…</div>
          )}
          {!desktop && !sheetOpen && data.ready && (
            <button
              type="button"
              onClick={() => { setSnap("peek"); setListOpen(true); }}
              aria-label={`개발구역 목록 보기 (${data.visible.length.toLocaleString("ko-KR")}건)`}
              // 지도 가운데를 덮지 않게 화면 왼쪽 아래에 고정한 작은 버튼(지도가 화면보다 길어도 바로 보이게). 오른쪽 아래 NAVER 표시·오른쪽 위 줌과 겹치지 않고,
              // Android 제스처 바·브라우저 하단 메뉴를 피하도록 safe-area만큼 띄운다.
              className="fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-3 z-30 min-h-10 rounded-full bg-zip px-3.5 text-xs font-bold text-white shadow-lg"
            >
              ☰ 목록 {data.visible.length.toLocaleString("ko-KR")}건
            </button>
          )}
        </div>

        {desktop && (
          <aside aria-label="개발구역 상세" className="h-[calc(100svh-21rem)] min-h-[520px] overflow-hidden rounded-2xl border border-border bg-surface">
            {panel}
          </aside>
        )}
      </div>

      {sheetOpen && (
        <MobileSheet
          label={selectedId ? "개발구역 상세" : "개발구역 목록"}
          snap={snap}
          onSnap={setSnap}
          onClose={() => { setSelectedId(null); setListOpen(false); }}
        >
          {panel}
        </MobileSheet>
      )}
    </div>
  );
}
