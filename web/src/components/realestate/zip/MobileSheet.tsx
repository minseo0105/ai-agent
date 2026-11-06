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
    event.currentTarget.setPointerCapture?.(event.pointerId);
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
      className={`fixed inset-x-0 bottom-0 z-40 flex flex-col rounded-t-2xl border border-b-0 border-border bg-surface shadow-[0_-8px_30px_-12px_rgba(15,23,42,.35)] transition-[height] duration-200 motion-reduce:transition-none ${
        snap === "full" ? "h-[92svh]" : "h-[42svh]"
      }`}
    >
      <div
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={() => { start.current = null; }}
        className="flex shrink-0 cursor-grab touch-none items-center justify-center py-2"
      >
        <button
          type="button"
          // 키보드로 누른 경우(detail === 0)만 여기서 처리한다. 포인터 탭은 위 up()이 처리해 두 번 전환되지 않는다.
          onClick={(event) => {
            if (event.detail === 0) toggle();
          }}
          aria-label={snap === "full" ? "시트 줄이기" : "시트 펼치기"}
          className="h-1.5 w-12 rounded-full bg-border"
        />
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
