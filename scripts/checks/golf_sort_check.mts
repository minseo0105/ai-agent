/**
 * 출발지 입력에 따른 정렬 전이를 실제로 실행해 본다.
 *
 *   node --experimental-strip-types scripts/checks/golf_sort_check.mts
 *
 * 화면 컴포넌트가 쓰는 규칙(decideSort/settleSort)과 요청 취소 장치를 그대로 써서,
 * 사용자가 겪는 순서대로 굴려 본다. 결과를 JSON 한 줄로 찍는다.
 */
import { apiFetch } from "../../web/src/lib/access.ts";
import { decideSort, settleSort, type GolfSort } from "../../web/src/lib/golfSort.ts";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 검색 화면의 정렬 상태만 떼어 낸 모형. run()이 하는 일과 같은 순서로 움직인다. */
class Screen {
  sort: GolfSort = "추천순";
  userChose = false;
  searchedOrigin: string | null = null;
  result: { sort: GolfSort; origin: string; order: string[] } | null = null;
  loading = false;
  private generation = 0;
  private inFlight: AbortController | null = null;

  /** 출발지 입력 뒤 '찾기'를 누른 것과 같다. */
  submit(origin: string, serverDelayMs = 10, geocodes = true) {
    const decision = decideSort({
      origin,
      previousOrigin: this.searchedOrigin,
      currentSort: this.sort,
      userChose: this.userChose,
    });
    this.userChose = decision.keepUserChoice;
    return this.run(origin, decision.sort, serverDelayMs, geocodes);
  }

  /** 정렬 버튼을 직접 누른 것과 같다. */
  chooseSort(next: GolfSort, origin: string, serverDelayMs = 10) {
    this.userChose = true;
    return this.run(origin, next, serverDelayMs, true);
  }

  private async run(origin: string, nextSort: GolfSort, delayMs: number, geocodes: boolean) {
    this.inFlight?.abort();
    const controller = new AbortController();
    this.inFlight = controller;
    const mine = ++this.generation;
    const current = () => mine === this.generation;

    this.loading = true;
    this.result = null;
    this.sort = nextSort;
    this.searchedOrigin = origin.trim();

    // 서버는 요청받은 정렬과 출발지로 실제 거리 순서를 돌려준다.
    globalThis.fetch = ((_input: string, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        const timer = setTimeout(() => {
          const hasDeparture = geocodes && origin.trim().length > 0;
          resolve(
            new Response(
              JSON.stringify({
                sort: settleSort(nextSort, hasDeparture),
                has_departure: hasDeparture,
                origin: origin.trim(),
                order: orderFor(origin.trim(), settleSort(nextSort, hasDeparture)),
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }, delayMs);
        init?.signal?.addEventListener("abort", () => {
          clearTimeout(timer);
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      })) as typeof fetch;

    try {
      const res = await apiFetch("http://test/api/golf/search", {
        method: "POST",
        signal: controller.signal,
        timeoutMs: 5000,
      });
      const body = (await res.json()) as { sort: GolfSort; has_departure: boolean; origin: string; order: string[] };
      if (!current()) return;
      this.result = { sort: body.sort, origin: body.origin, order: body.order };
      this.sort = settleSort(nextSort, body.has_departure);
    } catch {
      if (controller.signal.aborted || !current()) return;
    } finally {
      if (current()) this.loading = false;
    }
  }
}

/** 출발지마다 다른 거리 순서. 출발지가 바뀌면 순서도 반드시 달라져야 한다. */
const DISTANCE: Record<string, string[]> = {
  서울시청: ["A-가까움", "B-중간", "C-멂"],
  판교역: ["C-멂", "B-중간", "A-가까움"],
};
function orderFor(origin: string, sort: GolfSort): string[] {
  if (sort !== "가까운순") return ["추천1", "추천2", "추천3"];
  return DISTANCE[origin] ?? ["A-가까움", "B-중간", "C-멂"];
}

const report: Record<string, unknown> = {};

// A. 출발지 없음 → 기본 정렬
{
  const screen = new Screen();
  await screen.submit("");
  report.a_no_origin_sort = screen.sort;
  report.a_no_origin_result_sort = screen.result?.sort;
}

// B. 출발지 입력 → 버튼을 누르지 않아도 가까운 순
{
  const screen = new Screen();
  await screen.submit("서울시청");
  report.b_origin_entered_sort = screen.sort;
  report.b_origin_entered_order = screen.result?.order;
}

// C/D. 출발지 A → B 변경 → B 기준으로 다시 계산
{
  const screen = new Screen();
  await screen.submit("서울시청");
  const first = screen.result?.order;
  await screen.submit("판교역");
  report.c_first_origin_order = first;
  report.d_second_origin_sort = screen.sort;
  report.d_second_origin_order = screen.result?.order;
  report.d_order_changed = JSON.stringify(first) !== JSON.stringify(screen.result?.order);
  report.d_result_origin = screen.result?.origin;
}

// E. 출발지 삭제 → 거리순 해제
{
  const screen = new Screen();
  await screen.submit("서울시청");
  await screen.submit("");
  report.e_cleared_sort = screen.sort;
  report.e_cleared_order = screen.result?.order;
}

// 5. 같은 출발지에서 사용자가 고른 정렬은 유지, 출발지를 바꾸면 다시 거리순
{
  const screen = new Screen();
  await screen.submit("서울시청");
  await screen.chooseSort("추천순", "서울시청");
  const kept = screen.sort;
  await screen.submit("서울시청");
  const stillKept = screen.sort;
  await screen.submit("판교역");
  report.rule5_after_choice = kept;
  report.rule5_same_origin_resubmit = stillKept;
  report.rule5_origin_changed = screen.sort;
}

// F/G. 출발지를 빠르게 바꿔 입력 → 최신 출발지 결과만 남는다
{
  const screen = new Screen();
  const slow = screen.submit("서울시청", 400);
  await sleep(20);
  const fast = screen.submit("판교역", 30);
  await Promise.all([slow, fast]);
  await sleep(500);
  report.fg_final_origin = screen.result?.origin;
  report.fg_final_order = screen.result?.order;
  report.fg_final_sort = screen.sort;
  report.fg_loading = screen.loading;
}

// geocoding 실패 → 가까운 순이라고 말하지 않는다
{
  const screen = new Screen();
  await screen.submit("알 수 없는 곳", 10, false);
  report.geocode_failed_sort = screen.sort;
}

console.log(JSON.stringify(report));
