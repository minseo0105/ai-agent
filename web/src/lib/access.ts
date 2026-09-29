// 공개 범위 · 로그인 토큰 · 관리자 API
//
// 모든 서비스 API 호출은 apiFetch를 거쳐 로그인 토큰(Authorization 헤더)을 붙인다.
// 권한 오류(401/403)가 오면 화면 게이트가 다시 상태를 확인하도록 이벤트를 보낸다.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "ailab-access-token";
export const ACCESS_EVENT = "ailab:access-changed";

export type Level = "public" | "members" | "admin" | "hidden";
export type Me = { role: "admin" | "member"; name: string; id?: string } | null;
export type AccessStatus = {
  site_mode: "public" | "members" | "closed";
  site_allowed: boolean;
  notice: { enabled: boolean; text: string } | null;
  services: Record<string, { level: Level; visible: boolean; allowed: boolean }>;
  me: Me;
};

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
  if (typeof window !== "undefined") window.dispatchEvent(new Event(ACCESS_EVENT));
}

/** 응답을 기다리는 기본 한계(ms). 이보다 오래 걸리면 화면이 영영 로딩에 머무르지 않게 끊는다. */
export const DEFAULT_TIMEOUT_MS = 20000;

/** 서버가 아직 깨어나지 않았거나 네트워크가 끊겼을 때의 오류. 화면이 구분해서 말할 수 있게 표시한다. */
export class ConnectionError extends Error {
  readonly kind: "timeout" | "offline";
  constructor(kind: "timeout" | "offline", message: string) {
    super(message);
    this.name = "ConnectionError";
    this.kind = kind;
  }
}

export type ApiInit = RequestInit & { timeoutMs?: number };

/**
 * fetch + 로그인 토큰 + 시간제한 + 취소.
 *
 * 시간제한이 없으면 서버가 응답하지 않을 때 화면이 영영 로딩 상태로 남고, 취소가 없으면
 * 지난 검색의 응답이 최신 결과를 덮어쓴다. 호출자가 준 signal과 시간제한을 함께 건다.
 * 권한 오류의 {detail:{code,message}}는 다른 코드가 읽기 쉽게 {detail:message}로 바꿔 돌려준다.
 */
export async function apiFetch(input: string, init: ApiInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = init;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", abort, { once: true });
  }
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let res: Response;
  try {
    res = await fetch(input, { ...rest, headers, signal: controller.signal });
  } catch (error) {
    // 호출자가 취소한 것은 그대로 올려 보낸다. 최신 요청만 화면을 갱신하게 하는 장치다.
    if (signal?.aborted) throw error;
    if ((error as Error)?.name === "AbortError") {
      throw new ConnectionError("timeout", "서버 응답이 늦어지고 있어요. 잠시 후 다시 시도해 주세요.");
    }
    throw new ConnectionError("offline", "서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.");
  } finally {
    if (timer) clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
  if (res.status === 401 || res.status === 403) {
    try {
      const j = await res.clone().json();
      if (j?.detail && typeof j.detail === "object" && typeof j.detail.message === "string") {
        if (["login_required", "closed", "hidden"].includes(j.detail.code)) window.dispatchEvent(new Event(ACCESS_EVENT));
        return new Response(JSON.stringify({ detail: j.detail.message, code: j.detail.code }), {
          status: res.status,
          headers: { "Content-Type": "application/json" },
        });
      }
    } catch {}
  }
  return res;
}

export type ApiError = Error & { status?: number; requestId?: string };

/** 서버 오류를 화면이 쓸 수 있는 문장으로 바꾼다. request_id는 문의할 때 쓰도록 남긴다. */
export async function toApiError(res: Response): Promise<ApiError> {
  let message = `서버 응답 오류 (${res.status})`;
  let requestId = res.headers.get("X-Request-Id") ?? undefined;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") message = body.detail;
    else if (Array.isArray(body?.detail)) message = "입력값을 확인해 주세요.";
    if (typeof body?.request_id === "string") requestId = body.request_id;
  } catch {}
  if (res.status >= 500) message = message || "잠시 문제가 발생했어요. 잠시 후 다시 시도해 주세요.";
  const err = new Error(message) as ApiError;
  err.status = res.status;
  err.requestId = requestId;
  return err;
}

async function json<T>(path: string, init: ApiInit = {}): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

type LoginResult = { token: string; expires_at: number; name: string; role: "admin" | "member" };

export const accessApi = {
  status: () => json<AccessStatus>("/api/access/status"),
  login: (code: string) => json<LoginResult>("/api/access/login", { method: "POST", body: JSON.stringify({ code }) }),
};

// ---------------------------------------------------------
// 관리자
// ---------------------------------------------------------

export type SiteMode = AccessStatus["site_mode"];
export type ServiceMode = "inherit" | "public" | "members" | "hidden";
export type Member = { id: string; name: string; note: string; code_hint: string; active: boolean; created_at: number; last_login_at: number | null };
export type AdminSettings = {
  site_mode: SiteMode;
  notice: { enabled: boolean; text: string };
  services: Record<string, ServiceMode>;
  member_token_days: number;
  members: Member[];
  catalog: { id: string; icon: string; title: string; page: string }[];
  updated_at: number;
};

export const adminApi = {
  info: () => json<{ configured: boolean }>("/api/admin/info"),
  login: (password: string) => json<LoginResult>("/api/admin/login", { method: "POST", body: JSON.stringify({ password }) }),
  settings: () => json<AdminSettings>("/api/admin/settings"),
  save: (s: Pick<AdminSettings, "site_mode" | "notice" | "services" | "member_token_days">) =>
    json<AdminSettings>("/api/admin/settings", { method: "PUT", body: JSON.stringify(s) }),
  addMember: (name: string, note: string) => json<{ member: Member; code: string }>("/api/admin/members", { method: "POST", body: JSON.stringify({ name, note }) }),
  updateMember: (id: string, patch: Partial<Pick<Member, "name" | "note" | "active">>) =>
    json<Member>(`/api/admin/members/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  reissue: (id: string) => json<{ member: Member; code: string }>(`/api/admin/members/${id}/reissue`, { method: "POST" }),
  removeMember: (id: string) => json<{ ok: boolean }>(`/api/admin/members/${id}`, { method: "DELETE" }),
};

/** 화면 경로 → 서비스 id (접근 게이트용). 홈("/")과 /admin은 null */
export function serviceForPath(pathname: string): string | null {
  const map: [string, string][] = [
    ["/golf", "golf"],
    ["/dreamcar", "dreamcar"],
    ["/realestate", "realestate"],
    ["/report", "report"],
    ["/saju", "saju"],
    ["/car-selector", "car-selector"],
    ["/gif", "gif"],
  ];
  const hit = map.find(([p]) => pathname === p || pathname.startsWith(p + "/"));
  return hit ? hit[1] : null;
}
