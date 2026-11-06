/**
 * 마커 계획(markerPlan)을 지도의 마커로 동기화한다. 지도 SDK 호출은 여기에만 있고, 계획 계산은
 * markerPlan/clusterPoints가 한다. 가짜 naver.maps로 단위 검증할 수 있게 React와 분리했다.
 *
 * - 개별 마커는 project_id로 키를 잡아 지우고 다시 만들지 않고 위치·아이콘·zIndex만 바꾼다.
 * - 클러스터 마커는 줌이 바뀔 때마다 다시 만든다(개수가 적다). 이전 클러스터 마커는 지도에서 내린다.
 * - 마커마다 리스너를 하나만 둔다. 마커를 내리거나 목록에서 빠지면 리스너도 함께 해제한다.
 * - 실거래 등 다른 레이어는 이 모듈에 레이어 함수를 추가하는 방식으로 붙인다(하위 프로젝트 3).
 */
import type { NaverMapInstance, NaverMarker, NaverMaps } from "./naverMaps.ts";
import type { MarkerPlan, MarkerPlanItem } from "./markerPlan.ts";

export type ClusterItem = Extract<MarkerPlanItem, { kind: "cluster" }>;
export type SyncContext = {
  api: NaverMaps;
  map: NaverMapInstance;
  selectedId: string | null;
  singleIcon: (projectId: string, selected: boolean) => unknown;
  singleTitle?: (projectId: string) => string | undefined;
  clusterIcon: (count: number) => unknown;
  onSelect?: (projectId: string) => void;
  onClusterClick?: (cluster: ClusterItem) => void;
};
export type SyncState = {
  singles: Map<string, NaverMarker>;
  clusters: Map<string, NaverMarker>;
  listeners: Map<NaverMarker, unknown>;
};

export function createSyncState(): SyncState {
  return { singles: new Map(), clusters: new Map(), listeners: new Map() };
}

function release(api: NaverMaps, state: SyncState, marker: NaverMarker) {
  const token = state.listeners.get(marker);
  if (token !== undefined) api.Event.removeListener(token);
  state.listeners.delete(marker);
  marker.setMap(null);
}

export function syncMarkers(plan: MarkerPlan, ctx: SyncContext, state: SyncState): void {
  const { api, map } = ctx;
  const wantedSingles = new Set<string>();
  const clusters: ClusterItem[] = [];
  for (const item of plan.items) {
    if (item.kind === "single") wantedSingles.add(item.id);
    else clusters.push(item);
  }

  for (const [id, marker] of state.singles) {
    if (!wantedSingles.has(id)) {
      release(api, state, marker);
      state.singles.delete(id);
    }
  }
  for (const [key, marker] of state.clusters) {
    release(api, state, marker);
    state.clusters.delete(key);
  }

  for (const item of plan.items) {
    if (item.kind === "single") {
      const selected = ctx.selectedId === item.id;
      const position = new api.LatLng(item.latitude, item.longitude);
      const existing = state.singles.get(item.id);
      if (existing) {
        existing.setPosition(position);
        existing.setIcon(ctx.singleIcon(item.id, selected));
        existing.setZIndex(selected ? 1000 : 1);
        existing.setMap(map);
        continue;
      }
      const marker = new api.Marker({
        map, position, title: ctx.singleTitle?.(item.id),
        icon: ctx.singleIcon(item.id, selected), zIndex: selected ? 1000 : 1,
      });
      if (ctx.onSelect) {
        state.listeners.set(marker, api.Event.addListener(marker, "click", () => ctx.onSelect?.(item.id)));
      }
      state.singles.set(item.id, marker);
    }
  }
  for (const cluster of clusters) {
    const marker = new api.Marker({
      map, position: new api.LatLng(cluster.latitude, cluster.longitude),
      icon: ctx.clusterIcon(cluster.count), zIndex: 500,
      title: `${cluster.count}개 사업`,
    });
    if (ctx.onClusterClick) {
      state.listeners.set(marker, api.Event.addListener(marker, "click", () => ctx.onClusterClick?.(cluster)));
    }
    state.clusters.set(cluster.key, marker);
  }
}

export function clearMarkers(state: SyncState, api: NaverMaps): void {
  for (const marker of [...state.singles.values(), ...state.clusters.values()]) release(api, state, marker);
  state.singles.clear();
  state.clusters.clear();
}
