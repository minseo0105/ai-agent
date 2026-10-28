// STOCK:ON 화면 데이터. 서버가 모아 둔 스냅샷만 받는다(외부 시세 API를 브라우저가 부르지 않음).
import { API_URL, apiFetch, toApiError, type ApiInit } from "@/lib/access";

export type Source = { name: string; url: string };
export type Stock = { code: string; name: string; market: string; close: number; change: number | null; rate: number | null; volume?: number | null; value: number | null; cap: number | null };
export type IndexCard = { name: string; status?: string; as_of?: string; close?: number | null; change?: number | null; rate?: number | null; series?: { d: string; c: number | null }[]; source?: Source };
export type FlowRow = { code: string; name: string; amount: number };
export type Session = "pre" | "open" | "closing_auction" | "closed" | "holiday";
export type Market = {
  kind?: "kiwoom";
  session?: Session;
  session_label?: string;
  flows?: Record<"foreign_buy" | "foreign_sell" | "inst_buy" | "inst_sell", FlowRow[]>;
  as_of: string;
  source: Source;
  indices: IndexCard[];
  heatmap: Record<"KOSPI" | "KOSDAQ", Stock[]>;
  movers: { up: Stock[]; down: Stock[]; value: Stock[] };
  breadth: { up: number; down: number; flat: number; total: number };
  mover_min_value: number;
  fetched_ts: number;
};
export type Fx = { status: "ok" | "not_configured" | "error"; name?: string; as_of?: string; close?: number; change?: number | null; rate?: number | null; source: Source; fetched_ts?: number };
export type Sentence = { text: string; sources: number[] };
export type Briefing = { sentences: Sentence[]; sources: Source[]; ai: boolean; as_of: string; fetched_ts: number };
export type NewsItem = { title: string; url: string; press: string; pub: string | null; snippet?: string; summary?: string };
export type News = { status: "ok" | "not_configured"; categories?: { id: string; label: string; items: NewsItem[] }[]; source?: Source; fetched_ts: number };
export type Disclosure = { title: string; date: string; url: string };
export type WatchItem = { code: string; name: string; price: Omit<Stock, "code" | "volume"> | null; news: NewsItem[]; disclosures: Disclosure[] };
export type EventItem = { date: string; title: string; kind: string; note?: string; source: Source };
export type Overview = {
  enabled: boolean;
  disclaimer: string;
  oracle_url: string;
  refreshing?: boolean;
  market?: Market | null;
  price_source?: "kiwoom" | "public";
  public_as_of?: string | null;
  fx?: Fx | null;
  briefing?: Briefing | null;
  news?: News | null;
  watch?: { items: WatchItem[]; fetched_ts: number } | null;
  events?: { from: string; to: string; events: EventItem[] };
  errors?: Record<string, string>;
};
export type Why = {
  ready: boolean;
  code: string; name: string; as_of: string; rate: number | null; close: number | null;
  sentences: Sentence[]; note: string; sources: (Source & { kind?: string })[]; ai: boolean;
  news: NewsItem[]; disclosures: Disclosure[];
};

async function get<T>(path: string, init: ApiInit = {}): Promise<T> {
  const res = await apiFetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init.headers || {}) } });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}

export const stockApi = {
  overview: () => get<Overview>("/api/stock/overview"),
  why: (code: string) => get<Why>(`/api/stock/why/${encodeURIComponent(code)}`),
};

// 뉴스 속 숨은 종목 — 서버가 미리 만든 것(또는 직접 입력을 대기열로 만든 것)만 받는다.
// item = 뉴스(대표 기사 + 관련 기사) · AI 해석 · 관련 회사 지도(영향 경로 × 회사) · 실제 반응(등락률).
export type LifeCompany = {
  code: string; name: string; relevance: "강" | "중" | "약"; reason: string;
  direction?: "pos" | "neg"; // AI 해석: 긍정 영향 가능 / 부정 영향 가능
  market?: string; close?: number | null; rate?: number | null; cap?: number | null; value?: number | null;
  moved?: boolean; // 실제 반응이 큼(±5% 이상)
};
export type LifeStage = { key: string; label: string; detail: string; companies: LifeCompany[] }; // 영향 경로
export type LifeArticle = { title: string; url: string; press: string; pub: string | null; rep?: boolean };
export type LifeMap = {
  word: string; stages: LifeStage[]; interpretation?: string[]; ai: boolean; example?: boolean; model?: string; created_ts?: number;
  basis_label?: string; reaction_label?: string;
};
export type LifeItem = {
  name: string; title: string; summary: string; sector: string; articles: LifeArticle[]; map: LifeMap;
  basis_label?: string; carried?: boolean; example?: boolean;
};
export type LifeBasis = { key?: string; source?: "public" | "kiwoom"; as_of?: string; label?: string };
export type LifeOverview = {
  day: string | null; basis: LifeBasis; topics: LifeItem[]; hot: string[]; sectors: string[]; sector_items: Record<string, LifeItem>;
  live: { enabled: boolean; per_session: number; window_min: number };
};
export type LifeWordStatus = "ready" | "queued" | "running" | "failed" | "busy" | "limited" | "daily_limit" | "unavailable" | "invalid" | "none";
export type LifeWordResult = { status: LifeWordStatus; word: string; position?: number; message?: string; item?: LifeItem };

const SESSION_KEY = "stockon-session";
/** 새 단어 1인 횟수 제한용 무작위 ID(개인정보 없음). 저장이 막힌 브라우저면 이번 화면에서만 쓴다. */
function sessionId(): string {
  const make = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`);
  try {
    const v = localStorage.getItem(SESSION_KEY) || make();
    localStorage.setItem(SESSION_KEY, v);
    return v;
  } catch {
    return (sessionId as unknown as { v?: string }).v ??= make();
  }
}

export const lifeApi = {
  overview: () => get<LifeOverview>("/api/stock/lifemap"),
  request: (word: string) => get<LifeWordResult>("/api/stock/lifemap/word", { method: "POST", body: JSON.stringify({ word }), headers: { "X-Stockon-Session": sessionId() } }),
  status: (word: string) => get<LifeWordResult>(`/api/stock/lifemap/word?w=${encodeURIComponent(word)}`),
};

// 관리자
export type AiTaskStatus = {
  ok_ts: number | null; error_ts: number | null; last_error: string | null; consecutive: number;
  fails_today: number; fallbacks_today: number; fails_total: number; fallbacks_total: number;
};
export type AdminStatus = {
  enabled: boolean;
  refreshing: boolean;
  configured: Record<"public_data" | "naver_search" | "dart" | "exim_fx" | "ai", boolean>;
  tasks: Record<string, { ok_ts: number | null; error: string | null; error_ts: number | null; fails: number | null }>;
  as_of: string | null;
  why_today: { as_of: string | null; count: number; limit: number };
  ai: Record<"briefing" | "why" | "news_summary", AiTaskStatus>;
  models: Record<"briefing" | "why" | "news_summary", string>;
  watchlist: { code: string; name: string }[];
  kiwoom: {
    connected: boolean; mode?: string; price_source?: string; showing?: "kiwoom" | "public"; mock_key_expires?: string | null;
    days_left?: number | null; last_ok?: string | null; fails?: number; last_error?: string | null; session?: string | null; updated?: string | null;
  };
};
// 뉴스 속 숨은 종목 시연 안전장치(관리자)
export type CurationItem = {
  key: string; name: string; title: string; sector: string; rep_title: string; rep_press: string; rep_url: string;
  source: "topic" | "reserve" | "sector" | "example"; position: number | null; hidden: boolean; excluded_by: string; fin_incident: boolean;
};
export type Curation = {
  day: string; basis: LifeBasis; items: CurationItem[]; hidden_other: { key: string; name: string; title: string }[];
  words: string[]; fin_first: boolean; order: string[]; min: number; max: number;
};
type CurationAction = { action: "hide" | "show"; key: string } | { action: "order"; keys: string[] } | { action: "words"; words: string[] } | { action: "fin_first"; on: boolean };
export const stockAdminApi = {
  curation: () => get<Curation>("/api/stock/admin/lifemap"),
  setCuration: (body: CurationAction) => get<Curation>("/api/stock/admin/lifemap", { method: "POST", body: JSON.stringify(body) }),
  status: () => get<AdminStatus>("/api/stock/admin/status"),
  search: (q: string) => get<{ items: { code: string; name: string; market: string; cap: number | null }[] }>(`/api/stock/admin/search?q=${encodeURIComponent(q)}`),
  saveWatchlist: (codes: string[]) => get<{ watchlist: { code: string; name: string }[] }>("/api/stock/admin/watchlist", { method: "PUT", body: JSON.stringify({ codes }) }),
  refresh: (tasks: string[]) => get<{ started: boolean; refreshing: boolean }>("/api/stock/admin/refresh", { method: "POST", body: JSON.stringify({ tasks }) }),
};

// 표시 도우미 — 상승 빨강·하락 파랑(국내 관례), 색과 함께 ▲▼ 기호를 써서 색에만 의존하지 않는다.
export const dateLabel = (ymd?: string | null) => (ymd && ymd.length >= 8 ? `${Number(ymd.slice(4, 6))}/${Number(ymd.slice(6, 8))}` : "");
export const tone = (v?: number | null) => (!v ? "text-muted" : v > 0 ? "text-rose-600 dark:text-rose-400" : "text-blue-600 dark:text-blue-400");
export const arrow = (v?: number | null) => (!v ? "–" : v > 0 ? "▲" : "▼");
export const pct = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
export const won = (v?: number | null) => (v == null ? "—" : v.toLocaleString("ko-KR"));
export function eok(v?: number | null): string {
  if (v == null) return "—";
  const jo = v / 1e12;
  if (jo >= 1) return `${jo >= 10 ? jo.toFixed(0) : jo.toFixed(1)}조`;
  return `${Math.round(v / 1e8).toLocaleString("ko-KR")}억`;
}
export const hhmm = (ts?: number | null) =>
  ts ? new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) : "";

/** 시세 기준 배지 문구. 키움: 장중·마감 동시호가·마감 기준, 공공데이터: 전일 기준. */
export function basisLabel(m?: Market | null): { text: string; tone: "live" | "auction" | "closed" | "prev" } | null {
  if (!m) return null;
  if (m.kind === "kiwoom") {
    if (m.session === "open") return { text: `장중 · ${hhmm(m.fetched_ts)} 반영`, tone: "live" };
    if (m.session === "closing_auction") return { text: `마감 동시호가 · ${hhmm(m.fetched_ts)} (체결 전 가격)`, tone: "auction" };
    return { text: `마감 기준 · ${dateLabel(m.as_of)} 15:30`, tone: "closed" };
  }
  return { text: `전일 기준 · ${dateLabel(m.as_of)} 종가`, tone: "prev" };
}

export const timeLabel = (ts?: number | null) =>
  ts ? new Date(ts * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
