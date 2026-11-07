"use client";

import { useState } from "react";
import type { ZiponDevelopment } from "./useZiponDevelopment";

/**
 * 작은 상태 표시줄. 모바일은 화면 하단에 고정하되 왼쪽 목록 버튼 오른쪽에, PC는 지도 하단 가운데에 둔다(NAVER 로고와 겹치지 않음).
 * 최신성 경고는 줄여서 보여 주고, 누르면 원래 문구를 펼친다.
 */
export default function MapStatusBar({ data }: { data: ZiponDevelopment }) {
  const [open, setOpen] = useState(false);
  const { visible, mappable, coordinateless, freshness } = data;
  const stale = !!freshness && freshness.state !== "fresh";
  return (
    <div data-map-status className="pointer-events-none fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-[8.25rem] right-2 z-30 flex flex-col items-start gap-1 lg:absolute lg:inset-x-0 lg:bottom-8 lg:z-10 lg:items-center lg:px-28">
      {open && stale && (
        <p role="status" className="pointer-events-auto max-w-sm rounded-lg bg-surface/95 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted shadow">
          {freshness.label} 지도의 단계와 일정은 현재와 다를 수 있으니 공식 사업정보를 함께 확인해 주세요.
        </p>
      )}
      <div
        aria-live="polite"
        title={coordinateless > 0 ? `좌표 없는 ${coordinateless.toLocaleString("ko-KR")}건은 목록에만 표시` : undefined}
        className="pointer-events-auto flex max-w-full flex-wrap items-center gap-x-1.5 rounded-2xl bg-surface/90 px-2.5 py-1 text-[11px] text-muted shadow"
      >
        <span>
          {visible.length === 0
            ? "표시할 사업이 없어요"
            : `사업 ${visible.length.toLocaleString("ko-KR")}건 · 지도 ${mappable.toLocaleString("ko-KR")}건`}
        </span>
        {stale && (
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="font-bold text-amber-700 dark:text-amber-300">
            ⚠ 최신성 확인
          </button>
        )}
      </div>
    </div>
  );
}
