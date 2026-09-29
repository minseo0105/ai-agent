/**
 * 요청 취소·시간제한·cold start 재시도를 실제로 실행해 본다. 문자열 비교가 아니다.
 *
 *   node --experimental-strip-types scripts/checks/request_race_check.mts
 *
 * 확인하는 것
 *   1. 늦게 오는 이전 요청이 최신 요청을 덮어쓰지 않는다(취소가 실제로 동작한다).
 *   2. 응답이 없으면 시간제한으로 끊긴다. 화면이 영영 로딩에 머무르지 않는다.
 *   3. 서버가 깨어나는 중(503/연결실패)이면 다시 시도하고, 진짜 오류는 다시 시도하지 않는다.
 * 결과를 JSON 한 줄로 찍는다. 테스트가 그 값을 확인한다.
 */
import { apiFetch, ConnectionError } from "../../web/src/lib/access.ts";
import { isTransient, withColdStartRetry } from "../../web/src/lib/coldStart.ts";

// localStorage가 없는 환경이므로 토큰 조회는 조용히 실패한다(access.ts가 try/catch로 감싼다).
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 지정한 시간 뒤에 응답하는 가짜 서버. abort 신호를 실제로 존중한다. */
function slowServer(delayMs: number, body: unknown, status = 200) {
  return (_input: string, init?: RequestInit) =>
    new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(
        () => resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
        delayMs,
      );
      init?.signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    });
}

const report: Record<string, unknown> = {};

// --- 1. 최신 요청만 화면을 갱신한다 --------------------------------------
{
  // 컴포넌트가 쓰는 방식 그대로: 세대 번호 + AbortController.
  let screen: string | null = null;
  let generation = 0;
  let inFlight: AbortController | null = null;
  const errors: string[] = [];

  async function search(label: string, delayMs: number) {
    inFlight?.abort();
    const controller = new AbortController();
    inFlight = controller;
    const mine = ++generation;
    try {
      globalThis.fetch = slowServer(delayMs, { label }) as typeof fetch;
      const res = await apiFetch("http://test/search", { signal: controller.signal, timeoutMs: 5000 });
      const body = (await res.json()) as { label: string };
      if (mine !== generation) return; // 더 새로운 검색이 이미 시작됐다
      screen = body.label;
    } catch (error) {
      if (controller.signal.aborted || mine !== generation) return;
      errors.push(`${label}:${(error as Error).name}`);
    }
  }

  // A(느림)를 먼저 시작하고, 곧바로 B(빠름)를 시작한다.
  const a = search("A-old-slow", 400);
  await sleep(20);
  const b = search("B-new-fast", 40);
  await Promise.all([a, b]);
  await sleep(500); // A가 끝날 시간을 충분히 준다

  report.latest_request_wins = screen === "B-new-fast";
  report.screen_after_race = screen;
  report.race_errors = errors;
}

// --- 2. 응답이 없으면 시간제한으로 끊는다 --------------------------------
{
  globalThis.fetch = slowServer(3000, { never: true }) as typeof fetch;
  const started = Date.now();
  let kind = "none";
  try {
    await apiFetch("http://test/hang", { timeoutMs: 120 });
  } catch (error) {
    kind = error instanceof ConnectionError ? error.kind : (error as Error).name;
  }
  report.timeout_kind = kind;
  report.timeout_ms_under_1s = Date.now() - started < 1000;
}

// --- 3. 깨어나는 중이면 다시 시도한다 -------------------------------------
{
  let attempts = 0;
  const value = await withColdStartRetry(
    async () => {
      attempts += 1;
      if (attempts < 3) throw new ConnectionError("offline", "not awake yet");
      return "awake";
    },
    { delays: [1, 1, 1] },
  );
  report.cold_start_retries = attempts;
  report.cold_start_result = value;

  let permanentAttempts = 0;
  let permanentError = "";
  try {
    await withColdStartRetry(
      async () => {
        permanentAttempts += 1;
        const error = new Error("입력값을 확인해 주세요.") as Error & { status?: number };
        error.status = 422;
        throw error;
      },
      { delays: [1, 1] },
    );
  } catch (error) {
    permanentError = (error as Error).message;
  }
  // 진짜 오류는 다시 시도하지 않는다. 같은 잘못된 요청을 세 번 보내지 않는다.
  report.permanent_attempts = permanentAttempts;
  report.permanent_error = permanentError;
  report.transient_classification = {
    connection: isTransient(new ConnectionError("timeout", "x")),
    unavailable: isTransient(Object.assign(new Error("x"), { status: 503 })),
    bad_request: isTransient(Object.assign(new Error("x"), { status: 422 })),
    server_error: isTransient(Object.assign(new Error("x"), { status: 500 })),
  };
}

console.log(JSON.stringify(report));
