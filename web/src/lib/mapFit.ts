/** 검색·필터 결과에 맞춰 지도 화면을 정하는 규칙(순수 함수). 지도 SDK와 무관하다. */
/** 결과 1건이거나 사업을 고를 때의 확대 수준. 두 경우가 같은 화면을 보여야 한다. */
export const SINGLE_RESULT_ZOOM = 15;

/** 결과 좌표로 화면 맞추기 방식을 정한다(순수 함수). 0건이면 null(이동하지 않음). */
export function fitTarget(coords: { lat: number; lng: number }[]):
  | { kind: "single"; lat: number; lng: number }
  | { kind: "bounds" }
  | null {
  if (!coords.length) return null;
  const first = coords[0];
  // 좌표가 모두 같으면 1건과 같다(같은 위치의 여러 사업).
  if (coords.every((c) => c.lat === first.lat && c.lng === first.lng)) return { kind: "single", lat: first.lat, lng: first.lng };
  return { kind: "bounds" };
}
