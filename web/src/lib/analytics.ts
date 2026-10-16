// Optional telemetry: no imports from service clients, no tokens, no retries.
const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const SESSION_KEY = "ailab-usage-session-v1";
const ROUTES: Record<string, string> = {
  "/": "home", "/realestate": "realestate", "/golf": "golf", "/golf/club": "golf",
  "/dreamcar": "dreamcar", "/report": "report", "/saju": "saju",
  "/car-selector": "car-selector", "/gif": "gif", "/moneyon": "moneyon", "/other": "other",
};
export type UsageEvent = "page_view" | "search" | "project_click" | "map_click" | "external_link_click";
export type UsageAction = "address_search" | "golf_search" | "trade_search" | "subscription_search" | "naver_land_click" | "official_source_click" | "moneyon_card_click";
type Event = { session_id: string; service: string; route: string; event_type: UsageEvent; metadata: { action?: UsageAction } };
let session: string | undefined;
let lastPath: string | undefined;
const queue: Event[] = [];
let scheduled = false;
let sending = false;

function sessionId(): string {
  if (session) return session;
  try {
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(saved)) session = saved;
  } catch { /* Memory-only session if storage is unavailable. */ }
  if (!session) {
    session = crypto.randomUUID();
    try { sessionStorage.setItem(SESSION_KEY, session); } catch {}
  }
  return session;
}

function schedule() {
  if (scheduled || sending || !queue.length) return;
  scheduled = true;
  // Let initial service requests start and paint first; nothing awaits this timer.
  setTimeout(() => {
    const run = () => { scheduled = false; void flush(); };
    if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(run, { timeout: 2000 });
    else run();
  }, 1500);
}

async function flush() {
  if (sending || !queue.length) return;
  sending = true;
  const batch = queue.splice(0, 20);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), 1500);
    await fetch(`${API}/api/analytics/events`, {
      method: "POST", headers: { "Content-Type": "text/plain;charset=UTF-8" },
      body: JSON.stringify({ events: batch }), credentials: "omit", referrerPolicy: "no-referrer",
      signal: controller.signal,
    });
  } catch { /* Telemetry is lossy by design. Never surface an error or retry. */ }
  finally {
    if (timer) clearTimeout(timer);
    sending = false;
    schedule();
  }
}

export function trackUsage(event_type: UsageEvent, action?: UsageAction, pathname?: string): void {
  try {
    if (typeof window === "undefined" || queue.length >= 64) return;
    const path = (pathname ?? window.location.pathname).split(/[?#]/)[0].replace(/\/$/, "") || "/";
    if (path === "/admin" || path.startsWith("/admin/")) return;
    const route = Object.hasOwn(ROUTES, path) ? path : "/other";
    queue.push({ session_id: sessionId(), service: ROUTES[route], route, event_type,
      metadata: action ? { action } : {} });
    schedule();
  } catch { /* Unsupported crypto/storage/browser APIs must not affect the UI. */ }
}

// Module lifetime survives StrictMode effect replay and component remounts.
// A -> B -> A records three visits. Reload starts a new visit with the same tab session.
export function recordPageView(pathname: string): void {
  if (lastPath === pathname) return;
  lastPath = pathname;
  trackUsage("page_view", undefined, pathname);
}

// MONEY:ON은 외부 앱이라 이 사이트에서는 방문이 아닌 "홈 카드 클릭"만 알 수 있다.
// 기록 실패는 조용히 무시한다. 카드 이동(링크)은 이 함수와 무관하게 동작한다.
export function trackMoneyCardClick(): void {
  try {
    if (typeof window === "undefined" || queue.length >= 64) return;
    queue.push({ session_id: sessionId(), service: "moneyon", route: "/moneyon", event_type: "external_link_click",
      metadata: { action: "moneyon_card_click" } });
    schedule();
  } catch { /* Telemetry must never affect navigation. */ }
}
