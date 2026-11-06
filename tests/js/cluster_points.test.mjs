// 클러스터 계산·마커 계획(설계 §7-1): 정확성, 성능, 1,190건 회귀.
import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { clusterPoints, DEFAULT_MAX_ZOOM, DEFAULT_GRID_SIZE } from "../../web/src/lib/clusterPoints.ts";
import { buildMarkerPlan } from "../../web/src/lib/markerPlan.ts";
import { makeProjects, makePoints, TOTAL, LOCATED } from "./fixtures/zone_fixture.mjs";

const toInputs = (points) => points.filter((p) => p.latitude !== null).map((p) => ({ id: p.project_id, latitude: p.latitude, longitude: p.longitude }));
const all = makePoints(makeProjects());
const located = toInputs(all);

function ids(result) {
  return [...result.singles.map((s) => s.id), ...result.clusters.flatMap((c) => c.memberIds), ...result.skipped];
}

test("모든 점은 정확히 한 그룹에 속한다 (합계 = 전체, 중복·누락 없음)", () => {
  for (const zoom of [6, 9, 11, 12, 13, 14, 16]) {
    const result = clusterPoints(located, { zoom });
    const seen = ids(result);
    assert.equal(seen.length, located.length, `zoom ${zoom}`);
    assert.equal(new Set(seen).size, located.length, `zoom ${zoom}`);
    assert.equal(result.singles.length + result.clusters.reduce((n, c) => n + c.count, 0), located.length);
  }
});

test("클러스터의 count는 구성원 수와 같고 minClusterSize 미만 그룹은 개별 점으로 남는다", () => {
  const result = clusterPoints(located, { zoom: 11, minClusterSize: 3 });
  for (const c of result.clusters) {
    assert.equal(c.count, c.memberIds.length);
    assert.ok(c.count >= 3);
  }
  const two = clusterPoints([{ id: "a", latitude: 37.5, longitude: 127 }, { id: "b", latitude: 37.5, longitude: 127 }], { zoom: 10, minClusterSize: 3 });
  assert.equal(two.clusters.length, 0);
  assert.equal(two.singles.length, 2);
});

test("같은 좌표의 점들은 한 클러스터가 된다", () => {
  const same = Array.from({ length: 16 }, (_, i) => ({ id: `s${i}`, latitude: 37.5, longitude: 127.0 }));
  for (const zoom of [6, 10, 13]) {
    const result = clusterPoints(same, { zoom });
    assert.equal(result.clusters.length, 1, `zoom ${zoom}`);
    assert.equal(result.clusters[0].count, 16);
  }
});

test("줌이 커질수록 그룹 수는 줄지 않는다 (격자가 세분되므로)", () => {
  let previous = 0;
  for (let zoom = 6; zoom <= 16; zoom++) {
    const result = clusterPoints(located, { zoom, maxZoom: 99 });
    const groups = result.singles.length + result.clusters.length;
    assert.ok(groups >= previous, `zoom ${zoom}: ${groups} < ${previous}`);
    previous = groups;
  }
});

test("격자 세분 보장: 줌 z+1에서 한 그룹인 두 점은 줌 z에서도 한 그룹이다", () => {
  // 줌이 1 커지면 픽셀 좌표가 2배가 되어 격자 경계가 정확히 겹쳐야 한다(칸 위치를 반 칸 밀면 깨진다).
  let seed = 12345;
  const rand = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  let together = 0;
  for (let i = 0; i < 4000; i++) {
    const a = { id: "a", latitude: 37.4 + rand() * 0.2, longitude: 126.8 + rand() * 0.3 };
    const spread = rand() * 0.004;
    const b = { id: "b", latitude: a.latitude + spread, longitude: a.longitude + spread };
    for (let zoom = 8; zoom <= 13; zoom++) {
      const finer = clusterPoints([a, b], { zoom: zoom + 1, maxZoom: 99 }).clusters.length === 1;
      const coarser = clusterPoints([a, b], { zoom, maxZoom: 99 }).clusters.length === 1;
      if (finer) { together++; assert.ok(coarser, `pair ${i} zoom ${zoom}`); }
    }
  }
  assert.ok(together > 1000, `검증한 쌍 ${together}`);
});

test("maxZoom 이상에서는 클러스터가 없다", () => {
  for (const zoom of [DEFAULT_MAX_ZOOM, DEFAULT_MAX_ZOOM + 3]) {
    const result = clusterPoints(located, { zoom });
    assert.equal(result.clusters.length, 0);
    assert.equal(result.singles.length, located.length);
  }
  assert.ok(clusterPoints(located, { zoom: DEFAULT_MAX_ZOOM - 1 }).clusters.length > 0);
});

test("선택한 사업은 항상 개별 점으로 남고 클러스터에 들어가지 않는다", () => {
  const same = Array.from({ length: 8 }, (_, i) => ({ id: `s${i}`, latitude: 37.5, longitude: 127.0 }));
  const result = clusterPoints(same, { zoom: 8, selectedId: "s3" });
  assert.deepEqual(result.singles.map((s) => s.id), ["s3"]);
  assert.equal(result.clusters[0].count, 7);
  assert.ok(!result.clusters[0].memberIds.includes("s3"));
  // 선택한 점 하나만 있는 그룹이어도 개별 점
  const alone = clusterPoints([{ id: "x", latitude: 37.5, longitude: 127 }, { id: "y", latitude: 37.5, longitude: 127 }], { zoom: 8, selectedId: "x" });
  assert.equal(alone.clusters.length, 0);
  assert.equal(alone.singles.length, 2);
});

test("결과는 결정적이다 (같은 입력 → 같은 출력, 입력 순서와 무관한 구성)", () => {
  const a = clusterPoints(located, { zoom: 11 });
  const b = clusterPoints(located, { zoom: 11 });
  assert.deepEqual(a, b);
  const shuffled = [...located].reverse();
  const c = clusterPoints(shuffled, { zoom: 11 });
  const members = (r) => r.clusters.map((x) => x.memberIds.slice().sort().join(",")).sort();
  assert.deepEqual(members(c), members(a));
});

test("클러스터 위치는 구성원의 경계 안에 있고 경계 상자는 모든 구성원을 포함한다", () => {
  const byId = new Map(located.map((p) => [p.id, p]));
  for (const c of clusterPoints(located, { zoom: 10 }).clusters) {
    const members = c.memberIds.map((id) => byId.get(id));
    for (const m of members) {
      assert.ok(m.latitude <= c.bounds.north && m.latitude >= c.bounds.south);
      assert.ok(m.longitude <= c.bounds.east && m.longitude >= c.bounds.west);
    }
    assert.ok(c.latitude >= c.bounds.south && c.latitude <= c.bounds.north);
    assert.ok(c.longitude >= c.bounds.west && c.longitude <= c.bounds.east);
  }
});

test("그룹 안의 점은 모두 격자 크기(px) 안에 있다 — 지나치게 넓은 클러스터가 없다", () => {
  const zoom = 11;
  const scale = 256 * 2 ** zoom;
  const px = (lng, lat) => {
    const s = Math.sin((lat * Math.PI) / 180);
    return [((lng + 180) / 360) * scale, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * scale];
  };
  const byId = new Map(located.map((p) => [p.id, p]));
  for (const c of clusterPoints(located, { zoom }).clusters) {
    const pts = c.memberIds.map((id) => px(byId.get(id).longitude, byId.get(id).latitude));
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    assert.ok(Math.max(...xs) - Math.min(...xs) < DEFAULT_GRID_SIZE + 1e-6);
    assert.ok(Math.max(...ys) - Math.min(...ys) < DEFAULT_GRID_SIZE + 1e-6);
  }
});

test("잘못된 좌표는 건너뛰고 skipped에 남긴다 (조용히 사라지지 않는다)", () => {
  const dirty = [{ id: "ok", latitude: 37.5, longitude: 127 }, { id: "nan", latitude: NaN, longitude: 127 },
    { id: "inf", latitude: 37.5, longitude: Infinity }, { id: "range", latitude: 95, longitude: 127 }, { id: "lng", latitude: 37, longitude: 200 }];
  const result = clusterPoints(dirty, { zoom: 10 });
  assert.deepEqual(result.skipped.sort(), ["inf", "lng", "nan", "range"]);
  assert.deepEqual(result.singles.map((s) => s.id), ["ok"]);
});

test("입력을 수정하지 않는다", () => {
  const copy = JSON.stringify(located);
  clusterPoints(located, { zoom: 10, selectedId: located[0].id });
  assert.equal(JSON.stringify(located), copy);
});

test("빈 입력과 한 점", () => {
  assert.deepEqual(clusterPoints([], { zoom: 10 }), { clusters: [], singles: [], skipped: [] });
  const one = clusterPoints([{ id: "a", latitude: 37.5, longitude: 127 }], { zoom: 10 });
  assert.equal(one.singles.length, 1);
  assert.equal(one.clusters.length, 0);
});

// ---- 성능 ----
function fastest(run, times = 7) {
  let best = Infinity;
  for (let i = 0; i < times; i++) {
    const start = performance.now();
    run();
    best = Math.min(best, performance.now() - start);
  }
  return best;
}

test("성능: 1,190점 20ms 미만, 10,000점 150ms 미만", () => {
  const big = Array.from({ length: 10000 }, (_, i) => ({ id: `p${i}`, latitude: 37.4 + ((i * 7919) % 10000) / 50000, longitude: 126.8 + ((i * 104729) % 10000) / 30000 }));
  const small = fastest(() => clusterPoints(located.concat(located.slice(0, 341)), { zoom: 11 })); // 1,190점
  const large = fastest(() => clusterPoints(big, { zoom: 11 }));
  assert.ok(small < 20, `1,190점 ${small.toFixed(2)}ms`);
  assert.ok(large < 150, `10,000점 ${large.toFixed(2)}ms`);
  console.log(`# 성능 1,190점 ${small.toFixed(2)}ms / 10,000점 ${large.toFixed(2)}ms`);
});

test("성능: 줌 전 구간을 훑어도 선형에 가깝다 (O(n))", () => {
  const make = (n) => Array.from({ length: n }, (_, i) => ({ id: `p${i}`, latitude: 37.4 + ((i * 7919) % 10007) / 50000, longitude: 126.8 + ((i * 104729) % 10007) / 30000 }));
  const t1 = fastest(() => clusterPoints(make(5000), { zoom: 11 }));
  const t2 = fastest(() => clusterPoints(make(20000), { zoom: 11 }));
  assert.ok(t2 < t1 * 12, `5천점 ${t1.toFixed(1)}ms → 2만점 ${t2.toFixed(1)}ms`); // 4배 데이터에 12배 미만
});

// ---- 마커 계획: 1,190건 회귀 ----
test("회귀: 1,190건 중 좌표 849건이 마커가 되고 341건은 목록에만 남는다", () => {
  const plan = buildMarkerPlan(all, { zoom: 16 });
  assert.equal(all.length, TOTAL);
  assert.equal(plan.located, LOCATED);
  assert.equal(plan.coordinateless, TOTAL - LOCATED);
  assert.equal(plan.singles, LOCATED); // 확대하면 전부 개별 마커
  assert.equal(plan.clusters, 0);
  assert.equal(plan.items.length, LOCATED);
});

test("회귀: 어떤 줌에서도 마커에 반영된 사업 수는 좌표 있는 사업 수와 같다", () => {
  for (const zoom of [6, 8, 10, 11, 12, 13, 14, 15, 18]) {
    const plan = buildMarkerPlan(all, { zoom });
    assert.equal(plan.singles + plan.clustered, LOCATED, `zoom ${zoom}`);
    const covered = plan.items.flatMap((item) => (item.kind === "single" ? [item.id] : item.memberIds));
    assert.equal(covered.length, LOCATED);
    assert.equal(new Set(covered).size, LOCATED);
  }
});

test("회귀: 줌 아웃하면 마커 개수가 줄고 줌 인하면 늘어난다", () => {
  const counts = [8, 10, 12, 14].map((zoom) => buildMarkerPlan(all, { zoom }).items.length);
  for (let i = 1; i < counts.length; i++) assert.ok(counts[i] >= counts[i - 1], counts.join(","));
  assert.ok(counts[0] < LOCATED);
});

test("회귀: 클러스터를 끄면(enabled=false) 항상 849개 개별 마커", () => {
  const plan = buildMarkerPlan(all, { zoom: 8, enabled: false });
  assert.equal(plan.items.length, LOCATED);
  assert.equal(plan.clusters, 0);
});

test("회귀: 필터로 줄인 목록은 줄인 만큼만 마커가 된다 (필터 후 개수 일치)", () => {
  const subset = all.slice(0, 300);
  const expected = subset.filter((p) => p.latitude !== null).length;
  const plan = buildMarkerPlan(subset, { zoom: 16 });
  assert.equal(plan.located, expected);
  assert.equal(plan.items.length, expected);
});

test("회귀: 선택한 사업은 어떤 줌에서도 개별 마커로 남는다", () => {
  const target = all.find((p) => p.latitude !== null && p.latitude !== 37.5);
  for (const zoom of [6, 9, 12]) {
    const plan = buildMarkerPlan(all, { zoom, selectedId: target.project_id });
    const single = plan.items.find((item) => item.kind === "single" && item.id === target.project_id);
    assert.ok(single, `zoom ${zoom}`);
    assert.ok(!plan.items.some((item) => item.kind === "cluster" && item.memberIds.includes(target.project_id)));
  }
});

test("마커 계획은 좌표 문자열·NaN을 가진 항목을 좌표 없음으로 센다", () => {
  const plan = buildMarkerPlan([{ project_id: "a", latitude: "37.5", longitude: 127 }, { project_id: "b", latitude: NaN, longitude: 127 },
    { project_id: "c", latitude: 37.5, longitude: 127 }], { zoom: 12 });
  assert.equal(plan.located, 1);
  assert.equal(plan.coordinateless, 2);
});
