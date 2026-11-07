import type { DevelopmentMapPoint, DevelopmentProject } from "./realestate.ts";

/**
 * 경기 사업 → 지도 점. 검증된 주소 좌표(mappable)가 있는 사업만 점이 된다. 좌표가 없으면 점을 만들지 않는다(임의 위치 금지).
 * 서울 지도 점과 같은 모양으로 맞춘다.
 */
export function gyeonggiPoints(projects: DevelopmentProject[]): DevelopmentMapPoint[] {
  return projects
    .filter((p) => p.mappable && p.latitude != null && p.longitude != null)
    .map((p): DevelopmentMapPoint => ({
      project_id: p.project_id, name: p.name, latitude: p.latitude, longitude: p.longitude,
      boundary: null, boundary_status: "NO_BOUNDARY", boundary_status_label: "구역 경계 없음", allows_inside: false,
      development_layer: null, program_layer: p.program_label, address: p.address, last_checked: p.last_checked,
      official_url: p.official_source.url, type_code: null, type_label: p.type_label, program_code: null,
      program_label: p.program_label, stage_label: p.stage.label, district: p.district, dong: p.dong,
      accuracy: "REPRESENTATIVE_POINT", accuracy_label: "검증된 주소 좌표", confidence: "VERIFIED_ADDRESS", mappable: true,
      lifecycle: p.completed ? "COMPLETED" : "ACTIVE", lifecycle_label: p.completed ? "완료·청산" : "추진 중",
      lifecycle_basis: "경기데이터드림 단계", in_default_map: !p.completed,
    }));
}
