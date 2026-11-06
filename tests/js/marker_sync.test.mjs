// 마커 동기화(가짜 naver.maps). 실제 지도 렌더링은 샌드박스에서 SDK에 접속할 수 없어 배포 후 확인이 필요하다.
import test from "node:test";
import assert from "node:assert/strict";
import { syncMarkers, createSyncState, clearMarkers } from "../../web/src/lib/markerSync.ts";
import { buildMarkerPlan } from "../../web/src/lib/markerPlan.ts";
import { makeProjects, makePoints, LOCATED } from "./fixtures/zone_fixture.mjs";

function fakeNaver() {
  const created = [];
  const listeners = new Map(); // token -> { target, event, handler }
  let next = 1;
  class Marker {
    constructor(options) {
      this.options = options; this.map = options.map ?? null; this.position = options.position; this.icon = options.icon;
      this.zIndex = options.zIndex; this.id = created.length; created.push(this);
    }
    setMap(map) { this.map = map; }
    setIcon(icon) { this.icon = icon; }
    setZIndex(z) { this.zIndex = z; }
    setPosition(p) { this.position = p; }
    getPosition() { return this.position; }
  }
  const api = {
    Marker,
    LatLng: class { constructor(lat, lng) { this.latitude = lat; this.longitude = lng; } lat() { return this.latitude; } lng() { return this.longitude; } },
    Size: class { constructor(w, h) { this.w = w; this.h = h; } },
    Point: class { constructor(x, y) { this.x = x; this.y = y; } },
    Event: {
      addListener(target, event, handler) { const token = next++; listeners.set(token, { target, event, handler }); return token; },
      removeListener(token) { listeners.delete(token); },
    },
  };
  const click = (marker) => { for (const l of [...listeners.values()]) if (l.target === marker && l.event === "click") l.handler(); };
  const onMap = () => created.filter((m) => m.map !== null);
  return { api, created, listeners, click, onMap };
}

const map = { name: "map" };
const projects = makeProjects();
const points = makePoints(projects);
const byId = new Map(projects.map((p) => [p.project_id, p]));

function context(fake, extra = {}) {
  return {
    api: fake.api, map, selectedId: null,
    singleIcon: (id, selected) => ({ kind: "single", id, selected }),
    singleTitle: (id) => byId.get(id)?.name,
    clusterIcon: (count) => ({ kind: "cluster", count }),
    ...extra,
  };
}

test("처음 동기화: 개별 마커와 클러스터 마커가 계획대로 만들어진다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  const plan = buildMarkerPlan(points, { zoom: 10 });
  syncMarkers(plan, context(fake), state);
  assert.equal(fake.onMap().length, plan.items.length);
  assert.equal(state.singles.size, plan.singles);
  assert.equal(state.clusters.size, plan.clusters);
  assert.ok(plan.clusters > 0);
});

test("확대(줌 16)에서는 좌표 있는 849건이 모두 개별 마커다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  syncMarkers(buildMarkerPlan(points, { zoom: 16 }), context(fake), state);
  assert.equal(fake.onMap().length, LOCATED);
  assert.equal(state.clusters.size, 0);
});

test("같은 계획을 다시 동기화해도 개별 마커를 새로 만들지 않는다 (제자리 갱신)", () => {
  const fake = fakeNaver(); const state = createSyncState();
  const plan = buildMarkerPlan(points, { zoom: 16 });
  syncMarkers(plan, context(fake), state);
  const before = fake.created.length;
  syncMarkers(plan, context(fake), state);
  assert.equal(fake.created.length, before);
});

test("줌을 줄이면 클러스터에 묶인 개별 마커는 지도에서 내려가고 개수가 계획과 일치한다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  syncMarkers(buildMarkerPlan(points, { zoom: 16 }), context(fake), state);
  const plan = buildMarkerPlan(points, { zoom: 9 });
  syncMarkers(plan, context(fake), state);
  assert.equal(fake.onMap().length, plan.items.length);
  assert.equal(state.singles.size, plan.singles);
  assert.ok(plan.items.length < LOCATED);
  // 다시 확대하면 복원된다
  syncMarkers(buildMarkerPlan(points, { zoom: 16 }), context(fake), state);
  assert.equal(fake.onMap().length, LOCATED);
});

test("클러스터는 매번 다시 만들어도 이전 클러스터 마커가 지도에 남지 않는다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  for (const zoom of [8, 9, 10, 11, 12, 9, 8]) {
    const plan = buildMarkerPlan(points, { zoom });
    syncMarkers(plan, context(fake), state);
    assert.equal(fake.onMap().length, plan.items.length, `zoom ${zoom}`);
    assert.equal(fake.onMap().filter((m) => m.icon.kind === "cluster").length, plan.clusters, `zoom ${zoom}`);
  }
});

test("선택한 사업은 클러스터에 묶이지 않고 강조(zIndex·아이콘)된다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  const target = points.find((p) => p.latitude !== null && p.latitude !== 37.5).project_id;
  const plan = buildMarkerPlan(points, { zoom: 9, selectedId: target });
  syncMarkers(plan, context(fake, { selectedId: target }), state);
  const marker = state.singles.get(target);
  assert.ok(marker && marker.map === map);
  assert.equal(marker.zIndex, 1000);
  assert.deepEqual(marker.icon, { kind: "single", id: target, selected: true });
  assert.ok(fake.onMap().filter((m) => m !== marker && m.icon.kind === "single").every((m) => m.zIndex === 1));
});

test("선택이 바뀌면 이전 선택의 강조가 풀린다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  const [a, b] = points.filter((p) => p.latitude !== null).slice(0, 2).map((p) => p.project_id);
  syncMarkers(buildMarkerPlan(points, { zoom: 16, selectedId: a }), context(fake, { selectedId: a }), state);
  syncMarkers(buildMarkerPlan(points, { zoom: 16, selectedId: b }), context(fake, { selectedId: b }), state);
  assert.equal(state.singles.get(a).zIndex, 1);
  assert.equal(state.singles.get(b).zIndex, 1000);
});

test("마커 클릭은 그 사업의 project_id로 onSelect를 부른다", () => {
  const fake = fakeNaver(); const state = createSyncState(); const selected = [];
  syncMarkers(buildMarkerPlan(points, { zoom: 16 }), context(fake, { onSelect: (id) => selected.push(id) }), state);
  const id = [...state.singles.keys()][5];
  fake.click(state.singles.get(id));
  assert.deepEqual(selected, [id]);
});

test("클러스터 클릭은 구성원 목록과 경계를 onClusterClick으로 넘긴다", () => {
  const fake = fakeNaver(); const state = createSyncState(); const clicked = [];
  const plan = buildMarkerPlan(points, { zoom: 9 });
  syncMarkers(plan, context(fake, { onClusterClick: (c) => clicked.push(c) }), state);
  const [key, marker] = [...state.clusters.entries()][0];
  fake.click(marker);
  assert.equal(clicked.length, 1);
  assert.equal(clicked[0].key, key);
  assert.equal(clicked[0].memberIds.length, clicked[0].count);
  assert.ok(clicked[0].bounds.north >= clicked[0].bounds.south);
});

test("목록에서 사라진 사업(필터)의 마커와 리스너가 함께 정리된다 (누수 없음)", () => {
  const fake = fakeNaver(); const state = createSyncState();
  syncMarkers(buildMarkerPlan(points, { zoom: 16 }), context(fake, { onSelect: () => {} }), state);
  const subset = points.slice(0, 200);
  const plan = buildMarkerPlan(subset, { zoom: 16 });
  syncMarkers(plan, context(fake, { onSelect: () => {} }), state);
  assert.equal(fake.onMap().length, plan.items.length);
  assert.equal(state.singles.size, plan.singles);
  assert.equal(fake.listeners.size, plan.singles); // 마커마다 리스너 하나, 그 이상 남지 않는다
});

test("clearMarkers는 모든 마커를 내리고 리스너를 지운다", () => {
  const fake = fakeNaver(); const state = createSyncState();
  syncMarkers(buildMarkerPlan(points, { zoom: 10 }), context(fake, { onSelect: () => {}, onClusterClick: () => {} }), state);
  clearMarkers(state, fake.api);
  assert.equal(fake.onMap().length, 0);
  assert.equal(fake.listeners.size, 0);
  assert.equal(state.singles.size + state.clusters.size, 0);
});

test("좌표가 없는 사업은 마커가 만들어지지 않는다 (가짜 좌표 금지)", () => {
  const fake = fakeNaver(); const state = createSyncState();
  const plan = buildMarkerPlan(points, { zoom: 16 });
  syncMarkers(plan, context(fake), state);
  const noCoord = new Set(points.filter((p) => p.latitude === null).map((p) => p.project_id));
  assert.ok([...state.singles.keys()].every((id) => !noCoord.has(id)));
  assert.equal(noCoord.size, projects.length - LOCATED);
});
