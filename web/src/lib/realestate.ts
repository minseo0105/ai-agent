// FastAPI /api/realestate 클라이언트
import { apiFetch } from "@/lib/access";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type EstateOptions = {
  regions: { 서울: string[]; 경기: string[] };
  property_types: string[];
  supply_types: string[];
  kinds: string[];
  statuses: string[];
  event_types: string[];
  api_key: boolean;
  storage: "supabase" | "local";
};

export type Subscription = {
  id: string;
  name: string;
  type: string;
  region: string;
  address: string;
  announce_date: string;
  apply_date: string;
  apply_begin: string;
  apply_end: string;
  homepage: string;
  supply_type: string;
  subscription_kind: string;
  status: string;
};

export type Trade = {
  id: string;
  property_type: string;
  name: string;
  region: string;
  jibun: string;
  road_name: string;
  area: number;
  price_100m: number;
  price_text: string;
  date: string;
  floor: string;
  build_year: string;
  region_label: string;
  naver_url: string;
};

export type Rule = {
  id: number;
  region: string;
  event_type: string;
  enabled: boolean;
  property_type?: string;
  supply_type?: string;
  max_price_100m: number;
  min_area: number;
  created_at: string;
};

export type MonitorState = {
  auto_enabled: boolean;
  usage: { enabled_rules: number; subscription_calls: number; trade_calls: number; total_calls_per_cycle: number };
  rules: Rule[];
};

export type Notification = {
  id: number;
  title: string;
  category: string;
  message: string;
  created_at: string;
  is_read: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/realestate${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let message = `서버 응답 오류 (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {}
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const estateApi = {
  options: () => request<EstateOptions>("/options"),
  subscriptions: (q: { kind: "apt" | "unsold"; regions: string[]; supply_types: string[]; kinds: string[]; statuses: string[] }) =>
    post<{ total: number; items: Subscription[] }>("/subscriptions", q),
  trades: (q: { regions: string[]; property_types: string[]; month: string }) =>
    post<{ items: Trade[]; errors: string[]; counts: Record<string, number>; requests: number }>("/trades", q),
  monitor: () => request<MonitorState>("/monitor"),
  setAuto: (enabled: boolean) => request<MonitorState>("/monitor/auto", { method: "PUT", body: JSON.stringify({ enabled }) }),
  addRules: (body: {
    regions: string[];
    event_types: string[];
    property_types: string[];
    supply_types: string[];
    max_price_100m: number;
    min_area: number;
  }) => post<MonitorState>("/rules", body),
  toggleRule: (id: number) => post<MonitorState>(`/rules/${id}/toggle`),
  deleteRule: (id: number) => request<MonitorState>(`/rules/${id}`, { method: "DELETE" }),
  runNow: () =>
    post<{ events: number; notifications: number; fetched: { subscriptions?: number; trades?: number }; errors: string[] }>(
      "/monitor/run",
    ),
  notifications: () => request<{ items: Notification[]; unread: number }>("/notifications"),
  markRead: (id: number) => post<{ items: Notification[]; unread: number }>(`/notifications/${id}/read`),
};

export function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}
