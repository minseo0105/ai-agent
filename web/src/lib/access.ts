// 공개 범위 · 로그인 토큰 · 관리자 API
//
// 모든 서비스 API 호출은 apiFetch를 거쳐 로그인 토큰(Authorization 헤더)을 붙인다.
// 권한 오류(401/403)가 오면 화면 게이트가 다시 상태를 확인하도록 이벤트를 보낸다.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
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

/** fetch + 로그인 토큰. 권한 오류의 {detail:{code,message}}는 다른 코드가 읽기 쉽게 {detail:message}로 바꿔 돌려준다. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(input, { ...init, headers });
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

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!res.ok) {
    let message = `서버 응답 오류 (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") message = j.detail;
      else if (Array.isArray(j?.detail)) message = "입력값을 확인해 주세요.";
    } catch {}
    const err = new Error(message) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
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
