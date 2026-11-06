"use client";

import { useEffect, useRef, type PointerEvent, type ReactNode } from "react";
import { sheetGesture } from "@/lib/sheetGesture";

export type SheetSnap = "peek" | "full";

/**
 * 모바일·태블릿에서 지도 위로 열리는 바텀시트. 두 단계(peek / full)이며 손잡이를 위·아래로 끌거나
 * 버튼으로 전환한다. 지도는 뒤에서 계속 보이고 조작할 수 있어(모달이 아님) 포커스를 가두지 않는다.
 * Esc와 닫기 버튼으로 닫는다. 외부 라이브러리 없이 포인터 이벤트만 쓴다.
 */
export default function MobileSheet({
  label, snap, onSnap, onClose, children,
}: {
  label: string;
  snap: SheetSnap;
  onSnap: (snap: SheetSnap) => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const start = useRef<number | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const down = (event: PointerEvent<HTMLDivElement>) => {
    start.current = event.clientY;
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      // 일부 Android 브라우저는 포인터가 이미 끝났으면 예외를 던진다. 캡처 없이도 끌기 판정은 동작한다.
    }
  };
  const toggle = () => onSnap(snap === "full" ? "peek" : "full");
  const up = (event: PointerEvent<HTMLDivElement>) => {
    if (start.current === null) return;
    const delta = event.clientY - start.current;
    start.current = null;
    // 탭도 여기서 처리한다. 포인터 캡처 때문에 손잡이 안 버튼의 click은 버튼으로 오지 않는다.
    const action = sheetGesture(delta, snap);
    if (action === "toggle") toggle();
    else if (action === "close") onClose();
    else if (action) onSnap(action);
  };

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label={label}
      data-snap={snap}
      // 확장 88%(85~90% 기준), 기본 42%. svh를 모르는 브라우저(구형 Samsung Internet 등)는 vh로 떨어진다.
      className={`fixed inset-x-0 bottom-0 z-40 flex flex-col overflow-hidden rounded-t-2xl border border-b-0 border-border bg-surface shadow-[0_-8px_30px_-12px_rgba(15,23,42,.35)] transition-[height] duration-200 motion-reduce:transition-none ${
        snap === "full" ? "h-[88vh] supports-[height:100svh]:h-[88svh]" : "h-[42vh] supports-[height:100svh]:h-[42svh]"
      }`}
    >
      {/* 끌기 영역: 손가락으로 잡기 쉽게 44px 이상. 위로 끌면 확장, 아래로 끌면 기본·닫기. */}
      <div
        data-sheet-handle
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={() => { start.current = null; }}
        className="relative flex min-h-11 shrink-0 cursor-grab touch-none items-center justify-center"
      >
        <button
          type="button"
          // 키보드로 누른 경우(detail === 0)만 여기서 처리한다. 포인터 탭은 위 up()이 처리해 두 번 전환되지 않는다.
          onClick={(event) => {
            if (event.detail === 0) toggle();
          }}
          aria-label={snap === "full" ? "시트 줄이기" : "시트 펼치기"}
          aria-expanded={snap === "full"}
          className="flex h-11 w-24 items-center justify-center"
        >
          <span aria-hidden className="h-1.5 w-12 rounded-full bg-border" />
        </button>
        <span aria-hidden className="pointer-events-none absolute right-3 text-[11px] font-bold text-subtle">
          {snap === "full" ? "접기 ▾" : "펼치기 ▴"}
        </span>
      </div>
      {/* 내부 스크롤: 높이가 정해진 flex 열이어야 안쪽 overflow-y-auto가 동작한다. */}
      <div data-sheet-body className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
