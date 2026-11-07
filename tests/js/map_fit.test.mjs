import test from "node:test";
import assert from "node:assert/strict";
import { fitTarget, SINGLE_RESULT_ZOOM } from "../../web/src/lib/mapFit.ts";

test("0건은 이동하지 않는다", () => assert.equal(fitTarget([]), null));
test("1건은 중심 이동(과도한 확대 금지, 선택과 같은 확대)", () => {
  assert.deepEqual(fitTarget([{ lat: 37.49, lng: 127.14 }]), { kind: "single", lat: 37.49, lng: 127.14 });
  assert.equal(SINGLE_RESULT_ZOOM, 15);
});
test("같은 좌표 여러 건도 1건처럼", () => assert.equal(fitTarget([{ lat: 1, lng: 2 }, { lat: 1, lng: 2 }]).kind, "single"));
test("여러 건은 전체가 보이게 fitBounds", () => assert.equal(fitTarget([{ lat: 1, lng: 2 }, { lat: 1.1, lng: 2 }]).kind, "bounds"));
