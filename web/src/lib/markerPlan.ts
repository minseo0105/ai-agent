/**
 * 지도에 그릴 마커를 한 번에 계산한다(순수 함수). 개별 마커·클러스터·선택 보존·좌표 없음 집계가
 * 여기서 정해지므로, 지도 컴포넌트는 이 결과를 그리기만 한다. 좌표가 없는 사업은 목록에만 남는다.
 */
import { clusterPoints, hasValidCoordinate, type ClusterBounds, type ClusterOptions } from "./clusterPoints.ts";

export type PlanPoint = { project_id: string; latitude: number | null; longitude: number | null };
export type MarkerPlanItem =
  | { kind: "single"; id: string; latitude: number; longitude: number }
  | { kind: "cluster"; key: string; latitude: number; longitude: number; count: number; memberIds: string[]; bounds: ClusterBounds };
export type MarkerPlan = {
  items: MarkerPlanItem[];
  located: number; // 좌표가 있는 사업 수
  coordinateless: number; // 좌표가 없거나 유효하지 않은 사업 수(목록에만 남음)
  singles: number;
  clusters: number;
  clustered: number; // 클러스터에 묶인 사업 수
};

export function buildMarkerPlan(
  points: PlanPoint[],
  options: { zoom: number; selectedId?: string | null; enabled?: boolean } & Pick<ClusterOptions, "gridSize" | "minClusterSize" | "maxZoom">,
): MarkerPlan {
  const located = points.filter((p) => hasValidCoordinate(p));
  const inputs = located.map((p) => ({ id: p.project_id, latitude: p.latitude as number, longitude: p.longitude as number }));
  const { enabled = true, ...clusterOptions } = options;
  const result = enabled
    ? clusterPoints(inputs, clusterOptions)
    : { clusters: [], singles: inputs, skipped: [] as string[] };
  const items: MarkerPlanItem[] = [
    ...result.singles.map((s) => ({ kind: "single" as const, id: s.id, latitude: s.latitude, longitude: s.longitude })),
    ...result.clusters.map((c) => ({ kind: "cluster" as const, ...c })),
  ];
  return {
    items, located: located.length, coordinateless: points.length - located.length,
    singles: result.singles.length, clusters: result.clusters.length,
    clustered: result.clusters.reduce((n, c) => n + c.count, 0),
  };
}
