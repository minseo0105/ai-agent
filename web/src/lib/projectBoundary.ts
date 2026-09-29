/**
 * 사업구역 경계를 한 곳에서만 해석한다.
 *
 * 경계는 공식적으로 확인된 것만 면으로 그린다. 확인되지 않은 값을 구역처럼 그리면
 * 화면은 정상처럼 보이는데 사업 범위가 틀린 상태가 된다. 그래서 여기서 막는다.
 *
 * Polygon과 MultiPolygon을 모두 받는다. MultiPolygon을 Polygon으로 착각해 첫 번째
 * 구역만 그리거나, 떨어져 있는 두 구역을 '구멍 뚫린 한 구역'으로 그리지 않기 위해
 * 중첩 깊이를 보고 나눈다. 좌표를 만들어내거나 고쳐 그리지 않는다.
 */
export type BoundaryRing = Array<[number, number]>;

type BoundarySource = {
  boundary?: unknown;
  boundary_status?: string | null;
} | null | undefined;

const OFFICIAL = "OFFICIAL_VERIFIED";

function pair(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const [lng, lat] = value;
  if (typeof lng !== "number" || typeof lat !== "number") return null;
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return [lng, lat];
}

/** ring 하나. 한 점이라도 읽을 수 없으면 ring 전체를 버린다(모양을 일그러뜨리지 않는다). */
function ring(value: unknown): BoundaryRing | null {
  if (!Array.isArray(value) || value.length < 4) return null;
  const points: BoundaryRing = [];
  for (const entry of value) {
    const point = pair(entry);
    if (point === null) return null;
    points.push(point);
  }
  return points;
}

function rings(value: unknown): BoundaryRing[] {
  if (!Array.isArray(value)) return [];
  return value.map(ring).filter((entry): entry is BoundaryRing => entry !== null);
}

/**
 * 확인된 공식 경계를 구역별 ring 묶음으로 돌려준다. 첫 ring이 외곽, 나머지가 구멍이다.
 * 확인되지 않았거나 읽을 수 없으면 빈 배열이다. 그때 지도는 면을 그리지 않는다.
 */
export function verifiedBoundaryPolygons(source: BoundarySource): BoundaryRing[][] {
  if (!source || source.boundary_status !== OFFICIAL || !source.boundary) return [];
  const geometry = source.boundary as { type?: unknown; coordinates?: unknown };
  const coordinates = geometry?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length === 0) return [];
  // type을 믿기 전에 중첩 깊이로 확인한다. type이 없거나 어긋난 원천도 있다.
  const multi = geometry.type === "MultiPolygon"
    ? true
    : geometry.type === "Polygon"
      ? false
      : Array.isArray(coordinates[0]) && Array.isArray((coordinates[0] as unknown[])[0])
        && Array.isArray(((coordinates[0] as unknown[])[0] as unknown[])[0]);
  const parts = multi
    ? coordinates.map(rings)
    : [rings(coordinates)];
  return parts.filter((part) => part.length > 0);
}

/** 화면을 맞추기 위한 모든 점. 외곽·구멍을 구분하지 않는다. */
export function boundaryPoints(polygons: BoundaryRing[][]): BoundaryRing {
  return polygons.flat().flat();
}
