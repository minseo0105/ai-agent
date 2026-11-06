/**
 * 마커 클러스터 계산(순수 함수). 지도 SDK와 무관하다.
 *
 * NAVER 공식 MarkerClustering.js를 쓰지 않고 자체 구현한 이유와 조사 결과는
 * docs/superpowers/specs/2026-11-06-zip-dashboard-phase1-design.md §7-1에 있다.
 * 공식 옵션 이름(gridSize·minClusterSize·maxZoom)을 그대로 따른다.
 *
 * 방식: 웹 메르카토르 픽셀 좌표를 줌 수준에서 계산해 gridSize(px) 격자 칸에 해싱하는 O(n) 방식이다.
 * 줌이 1 커지면 픽셀 좌표가 2배가 되어 격자가 정확히 세분되므로, 줌이 커질수록 그룹 수는 줄지 않는다.
 * 칸 경계에서 이웃한 점이 서로 다른 그룹이 될 수 있다(격자 방식의 알려진 한계, 표시 용도에는 무방).
 *
 * 선택한 사업은 항상 개별 점으로 남는다. 잘못된 좌표는 skipped에 남기고 조용히 버리지 않는다.
 */
export type ClusterInput = { id: string; latitude: number; longitude: number };
export type ClusterBounds = { north: number; south: number; east: number; west: number };
export type ClusterGroup = {
  key: string;
  latitude: number; // 구성원 평균 위치
  longitude: number;
  count: number;
  memberIds: string[];
  bounds: ClusterBounds;
};
export type ClusterOptions = {
  zoom: number;
  gridSize?: number;
  minClusterSize?: number;
  /** 이 줌 이상에서는 클러스터링하지 않는다. */
  maxZoom?: number;
  selectedId?: string | null;
};
export type ClusterResult = { clusters: ClusterGroup[]; singles: ClusterInput[]; skipped: string[] };

export const DEFAULT_GRID_SIZE = 64;
export const DEFAULT_MIN_CLUSTER = 2;
export const DEFAULT_MAX_ZOOM = 14;

export function hasValidCoordinate(point: { latitude: unknown; longitude: unknown }): boolean {
  const { latitude, longitude } = point;
  return (
    typeof latitude === "number" && typeof longitude === "number" &&
    Number.isFinite(latitude) && Number.isFinite(longitude) &&
    Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
  );
}

function worldPixel(latitude: number, longitude: number, zoom: number): [number, number] {
  const scale = 256 * 2 ** zoom;
  const s = Math.max(-0.9999, Math.min(0.9999, Math.sin((latitude * Math.PI) / 180)));
  return [((longitude + 180) / 360) * scale, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * scale];
}

export function clusterPoints(points: ClusterInput[], options: ClusterOptions): ClusterResult {
  const gridSize = options.gridSize ?? DEFAULT_GRID_SIZE;
  const minSize = Math.max(2, options.minClusterSize ?? DEFAULT_MIN_CLUSTER);
  const maxZoom = options.maxZoom ?? DEFAULT_MAX_ZOOM;
  const skipped: string[] = [];
  const valid: ClusterInput[] = [];
  for (const point of points) {
    if (hasValidCoordinate(point)) valid.push(point);
    else skipped.push(point.id);
  }
  if (options.zoom >= maxZoom) return { clusters: [], singles: valid, skipped };

  // 선택한 사업은 격자에 넣지 않는다. 항상 개별 점이다.
  const cells = new Map<string, ClusterInput[]>();
  const singleIds = new Set<string>();
  for (const point of valid) {
    if (point.id === options.selectedId) {
      singleIds.add(point.id);
      continue;
    }
    const [x, y] = worldPixel(point.latitude, point.longitude, options.zoom);
    const key = `${Math.floor(x / gridSize)}:${Math.floor(y / gridSize)}`;
    const cell = cells.get(key);
    if (cell) cell.push(point);
    else cells.set(key, [point]);
  }

  const clusters: ClusterGroup[] = [];
  for (const [cell, members] of cells) {
    if (members.length < minSize) {
      for (const member of members) singleIds.add(member.id);
      continue;
    }
    let lat = 0, lng = 0, north = -Infinity, south = Infinity, east = -Infinity, west = Infinity;
    for (const m of members) {
      lat += m.latitude; lng += m.longitude;
      north = Math.max(north, m.latitude); south = Math.min(south, m.latitude);
      east = Math.max(east, m.longitude); west = Math.min(west, m.longitude);
    }
    clusters.push({
      key: `${options.zoom}:${cell}`, count: members.length, memberIds: members.map((m) => m.id),
      latitude: Math.min(north, Math.max(south, lat / members.length)),
      longitude: Math.min(east, Math.max(west, lng / members.length)),
      bounds: { north, south, east, west },
    });
  }
  clusters.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return { clusters, singles: valid.filter((p) => singleIds.has(p.id)), skipped };
}
