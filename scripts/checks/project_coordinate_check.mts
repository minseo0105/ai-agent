/**
 * 공통 좌표 helper를 실제 운영 좌표 122건으로 돌려 본다. 문자열 비교가 아니라 실행이다.
 *
 *   node --experimental-strip-types scripts/checks/project_coordinate_check.mts
 *
 * 결과를 JSON 한 줄로 찍는다. 테스트가 그 값을 확인한다.
 */
import { readFileSync } from "node:fs";
import { getProjectCoordinate, coordinateProblem } from "../../web/src/lib/projectCoordinate.ts";

const root = new URL("../../", import.meta.url).pathname;
const doc = JSON.parse(
  readFileSync(`${root}data/development/bulk_geocode_result_20260927.json`, "utf8"),
);
const accepted = doc.items.filter((row: { outcome: string }) => row.outcome === "ACCEPTED");

let matched = 0;
const rejected: string[] = [];
const byDistrict: Record<string, { lat: number; lng: number }> = {};
for (const row of accepted) {
  const coordinate = getProjectCoordinate(row);
  if (coordinate && coordinate.lat === row.latitude && coordinate.lng === row.longitude) {
    matched += 1;
    byDistrict[row.district] ??= coordinate;
  } else {
    rejected.push(`${row.project_name}:${coordinateProblem(row)}`);
  }
}

console.log(
  JSON.stringify({
    accepted: accepted.length,
    matched,
    rejected,
    districts: byDistrict,
    // 위도는 37번대, 경도는 126~127번대여야 한다. 뒤집히면 여기서 드러난다.
    latitude_band: Object.values(byDistrict).every((c) => c.lat > 37 && c.lat < 38),
    longitude_band: Object.values(byDistrict).every((c) => c.lng > 126 && c.lng < 128),
    string_input: getProjectCoordinate({ latitude: "37.55", longitude: "127.14" }),
    swapped: getProjectCoordinate({ latitude: 127.14, longitude: 37.55 }),
    swapped_problem: coordinateProblem({ latitude: 127.14, longitude: 37.55 }),
    missing_problem: coordinateProblem({ latitude: null, longitude: null }),
    outside_problem: coordinateProblem({ latitude: 35.1, longitude: 129.0 }),
  }),
);
