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

export type TradeDetail = Record<string, string>;

export type MapConfig = {
  active: string;
  fallback: string;
  providers: {
    id: string;
    label: string;
    kind: string;
    korean_labels: boolean;
    requires_browser_key: boolean;
    configured: boolean;
    note: string;
    url_template: string | null;
    attribution: string;
    max_zoom: number;
  }[];
  tile: { url_template: string | null; attribution: string; max_zoom: number };
  note: string;
};

export type DevelopmentMapPoint = {
  project_id: string;
  name: string | null;
  latitude: number | null;
  longitude: number | null;
  boundary: unknown | null;
  boundary_status: string;
  boundary_status_label: string;
  allows_inside: boolean;
  development_layer: string | null;
  program_layer: string | null;
  address: string | null;
  last_checked: string | null;
  official_url: string | null;
  type_code: string | null;
  type_label: string;
  program_code: string | null;
  program_label: string | null;
  stage_label: string;
  district: string | null;
  dong: string | null;
  accuracy: "OFFICIAL_BOUNDARY" | "REPRESENTATIVE_POINT" | "NO_LOCATION";
  accuracy_label: string;
  confidence: string;
  mappable: boolean;
};

export type DevelopmentMap = {
  status: "ok" | "unavailable";
  reason: string | null;
  points: DevelopmentMapPoint[];
  total: number;
  mappable: number;
  legend: Record<string, { label: string; note: string }>;
  layers: Record<string, { label: string; marker: string; color: string; layer?: string }>;
  bbox_filtered: boolean;
  location_notice: string;
};

export type DevelopmentImpactBlock = {
  inside: { code: string; label: string; project: string | null; notice: string | null };
  nearest: {
    project_id: string;
    name: string;
    type_label: string;
    program_label: string | null;
    stage_label: string;
    stage_basis: string;
    distance_m: number | null;
    distance_label: string | null;
    official_source: { name: string | null; url: string | null };
    trust_label: string;
  } | null;
  count: number;
  has_map_point: boolean;
  available: boolean;
};

export type DevelopmentProject = {
  project_id: string;
  name: string;
  official_id: string | null;
  official_authority: string | null;
  type_label: string;
  program: { code: string; label: string } | null;
  program_label: string | null;
  stage_verified_level: "OFFICIAL_DETAIL_VERIFIED" | "OFFICIAL_LIST_MAPPED";
  stage_timeline: { steps: string[]; current_index: number | null; current_label: string | null; total: number; note: string | null };
  stage_description?: string | null;
  stage_history?: { stage_name: string; stage_date: string | null; stage_order: number; is_current: boolean }[];
  location_accuracy: { code: string; label: string; note: string };
  distance_label: string | null;
  district: string | null;
  dong: string | null;
  address: string | null;
  stage: { label: string; official_text: string | null };
  stage_basis: string;
  status_label: string;
  trust: { code: string; label: string; tone: string; note: string };
  official_source: { name: string | null; url: string | null };
  last_checked: string | null;
  spatial: { code: string; label: string; confirmed_boundary: boolean };
  distance_m: number | null;
  has_location: boolean;
  location_notice: string | null;
};

export type DevelopmentContext = {
  label: string;
  available: boolean;
  projects: DevelopmentProject[];
  notice: string | null;
  reason_label: string | null;
};

export type DevelopmentSummary = {
  status: "ok" | "unavailable";
  reason: string | null;
  total: number;
  districts: { district: string; total: number; verified: number; by_type: Record<string, number>; type_labels: Record<string, number> }[];
};

export type DevelopmentSearch = {
  status: "ok" | "unavailable";
  reason: string | null;
  projects: DevelopmentProject[];
  total: number;
  located: number;
  location_notice: string;
};

export type Trade = {
  id: string;
  property_type: string;
  name: string;
  region: string;
  jibun: string;
  road_name: string;
  area: number;
  area_basis?: string;
  price_100m: number;
  price_text: string;
  date: string;
  floor: string;
  build_year: string;
  region_label: string;
  naver_url: string;
  detail?: TradeDetail;
  raw_detail?: TradeDetail;
  address_road?: string | null;
  address_jibun?: string | null;
  canonical_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  source_label?: string;
  development?: DevelopmentContext | null;
  development_impact?: DevelopmentImpactBlock | null;
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
  developmentSummary: () => request<DevelopmentSummary>("/development/summary"),
  mapConfig: () => request<MapConfig>("/map/config"),
  developmentMap: (sigungu?: string, limit = 200, bbox?: { north: number; south: number; east: number; west: number }) =>
    request<DevelopmentMap>(
      `/development/map?limit=${limit}${sigungu ? `&sigungu=${encodeURIComponent(sigungu)}` : ""}` +
        (bbox ? `&north=${bbox.north}&south=${bbox.south}&east=${bbox.east}&west=${bbox.west}` : ""),
    ),
  developmentNearby: (q: { longitude: number; latitude: number; radius_m?: number; limit?: number }) =>
    post<DevelopmentSearch & { impact: DevelopmentImpactBlock }>("/development/nearby", q),
  development: (q: { sigungu?: string; longitude?: number; latitude?: number; radius_m?: number; limit?: number }) =>
    post<DevelopmentSearch>("/development/search", q),
  trades: async (q: { regions: string[]; property_types: string[]; month: string; max_price_100m?: number; max_area?: number; include_development?: boolean }, onProgress?: (done: number, total: number) => void) => {
    const regions = [...new Set(q.regions)];
    const result = { items: [] as Trade[], errors: [] as string[], counts: {} as Record<string, number>, requests: 0 };
    // 서버의 40개 조합 제한을 유지하고 긴 요청을 줄이기 위해 지역을 5개씩 순차 조회한다.
    for (let start = 0; start < regions.length; start += 5) {
      const batch = regions.slice(start, start + 5);
      try {
        const response = await post<typeof result>("/trades", { ...q, regions: batch });
        result.items.push(...response.items);
        result.errors.push(...response.errors);
        result.requests += response.requests;
      } catch (e) {
        result.errors.push(`${batch.join(", ")}: ${(e as Error).message}`);
      }
      onProgress?.(Math.min(start + batch.length, regions.length), regions.length);
    }
    result.items.sort((a, b) => b.date.localeCompare(a.date));
    for (const item of result.items) result.counts[item.property_type] = (result.counts[item.property_type] ?? 0) + 1;
    return result;
  },
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

export type TradeSort = "최근 거래일 순" | "가격 낮은 순" | "가격 높은 순" | "면적 작은 순" | "면적 큰 순";
export function sortTrades(items: Trade[], order: TradeSort): Trade[] {
  return [...items].sort((a, b) => {
    if (order === "최근 거래일 순") return b.date.localeCompare(a.date);
    const key = order.startsWith("가격") ? "price_100m" : "area";
    const av = a[key], bv = b[key];
    const validA = Number.isFinite(av) && av > 0;
    const validB = Number.isFinite(bv) && bv > 0;
    if (validA !== validB) return validA ? -1 : 1;
    const descending = order === "가격 높은 순" || order === "면적 큰 순";
    const delta = validA && validB ? (av - bv) * (descending ? -1 : 1) : 0;
    return delta || b.date.localeCompare(a.date);
  });
}
