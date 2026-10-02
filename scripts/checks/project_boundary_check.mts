/**
 * 경계 helper를 실제로 실행해 본다. 문자열 비교가 아니라 실행이다.
 *
 *   node --experimental-strip-types scripts/checks/project_boundary_check.mts
 *
 * 확인된 EXACT 폴리곤 검토 산출물이 있으면 그것도 통과시켜 본다. 없으면 건너뛴다.
 * 결과를 JSON 한 줄로 찍는다. 테스트가 그 값을 확인한다.
 */
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { boundaryPoints, verifiedBoundaryPolygons } from "../../web/src/lib/projectBoundary.ts";

const square = (lng: number, lat: number, size: number): Array<[number, number]> => [
  [lng, lat], [lng, lat + size], [lng + size, lat + size], [lng + size, lat], [lng, lat],
];
const verified = (boundary: unknown) => ({ boundary, boundary_status: "OFFICIAL_VERIFIED" });

const polygon = { type: "Polygon", coordinates: [square(127.13, 37.55, 0.002)] };
const withHole = {
  type: "Polygon",
  coordinates: [square(127.13, 37.55, 0.004), square(127.131, 37.551, 0.001)],
};
const multi = {
  type: "MultiPolygon",
  coordinates: [[square(127.13, 37.55, 0.002)], [square(127.14, 37.56, 0.002)]],
};
const untyped = { coordinates: [[square(127.13, 37.55, 0.002)], [square(127.14, 37.56, 0.002)]] };

const root = fileURLToPath(new URL("../../", import.meta.url));
const reviewPath = `${root}data/development/polygon_match_exact_20260928.geojson`;
let reviewFeatures: number | null = null;
let reviewParsed: number | null = null;
if (existsSync(reviewPath)) {
  const document = JSON.parse(readFileSync(reviewPath, "utf8"));
  reviewFeatures = document.features.length;
  reviewParsed = document.features
    .map((feature: { geometry: unknown }) => verifiedBoundaryPolygons(verified(feature.geometry)))
    .filter((parts: unknown[]) => parts.length > 0).length;
}

console.log(
  JSON.stringify({
    polygon_parts: verifiedBoundaryPolygons(verified(polygon)).length,
    polygon_rings: verifiedBoundaryPolygons(verified(polygon))[0].length,
    hole_rings: verifiedBoundaryPolygons(verified(withHole))[0].length,
    multipolygon_parts: verifiedBoundaryPolygons(verified(multi)).length,
    // type이 없어도 중첩 깊이로 MultiPolygon을 알아본다.
    untyped_parts: verifiedBoundaryPolygons(verified(untyped)).length,
    // 확인되지 않은 경계는 절대 그리지 않는다.
    unverified: verifiedBoundaryPolygons({ boundary: polygon, boundary_status: "UNVERIFIED" }).length,
    no_status: verifiedBoundaryPolygons({ boundary: polygon }).length,
    no_boundary: verifiedBoundaryPolygons(verified(null)).length,
    empty: verifiedBoundaryPolygons(verified({ type: "Polygon", coordinates: [] })).length,
    // 점이 3개면 면이 아니다. 숫자가 아닌 좌표가 섞이면 ring 전체를 버린다.
    too_few: verifiedBoundaryPolygons(
      verified({ type: "Polygon", coordinates: [[[127.1, 37.5], [127.2, 37.5], [127.1, 37.5]]] }),
    ).length,
    not_numbers: verifiedBoundaryPolygons(
      verified({ type: "Polygon", coordinates: [[["a", "b"], [1, 2], [3, 4], ["a", "b"]]] }),
    ).length,
    out_of_range: verifiedBoundaryPolygons(
      verified({ type: "Polygon", coordinates: [[[1000, 37.5], [127.2, 37.5], [127.2, 37.6], [1000, 37.5]]] }),
    ).length,
    // 화면 맞추기에 쓰는 점 수. MultiPolygon의 두 구역이 모두 들어간다.
    points: boundaryPoints(verifiedBoundaryPolygons(verified(multi))).length,
    review_features: reviewFeatures,
    review_parsed: reviewParsed,
  }),
);
