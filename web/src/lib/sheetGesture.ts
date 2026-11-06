/**
 * 모바일 시트 손잡이 제스처 판정(순수 함수). 포인터를 캡처하면 손잡이 안의 버튼 click이 버튼으로 가지 않으므로,
 * 탭도 이 판정(포인터를 뗄 때)으로 처리한다. 키보드로 버튼을 누른 click(detail === 0)만 버튼이 직접 처리한다.
 */
export const TAP_SLOP = 8; // 이보다 덜 움직이면 탭
export const SWIPE_DISTANCE = 40; // 이보다 더 끌면 스와이프. 그 사이는 아무것도 하지 않는다(실수로 닫히지 않게)

export type SheetAction = "toggle" | "full" | "peek" | "close" | null;

export function sheetGesture(delta: number, snap: "peek" | "full"): SheetAction {
  if (!Number.isFinite(delta)) return null;
  if (Math.abs(delta) < TAP_SLOP) return "toggle";
  if (delta < -SWIPE_DISTANCE) return "full";
  if (delta > SWIPE_DISTANCE) return snap === "full" ? "peek" : "close";
  return null;
}
