// FastAPI /api/golf 클라이언트 + 검색 상태 보관(sessionStorage)

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Sort = "추천순" | "가까운순" | "가격순";
export type SearchMode = "condition" | "text" | "name";

export type ConditionParams = {
  departure: string;
  day: "주중" | "주말";
  session: "1부" | "2부" | "3부";
  budget: string;
  caddie: "전체" | "캐디" | "노캐디";
  areas: string[];
  subregions: string[];
  players: "전체" | "3인" | "4인";
  night: boolean;
  include_unknown: boolean;
  avg_score_label: string;
  challenge: "편하게" | "적당히" | "도전";
};

export type GolfOptions = {
  areas: string[];
  subregions: Record<string, string[]>;
  budgets: string[];
  avg_scores: string[];
  counts: { all: number; searchable: number; pool: number; by_area: Record<string, number> };
  data_coverage: { night: number; three_person: number; caddie: number; green_fee: number };
  runtime_ok: boolean;
  naver_enabled: boolean;
};

export type ResultCard = {
  id: string;
  name: string;
  location: string;
  status: "confirmed" | "pending";
  badge: string;
  facts: string[];
  badges: string[];
  reasons: string[];
  evidence: string;
};

export type SearchResult = {
  applied: string[];
  departure_status: string | null;
  trace: Record<string, number> & { unknown_reasons?: Record<string, number> };
  include_unknown?: boolean;
  sort: Sort;
  notice: string | null;
  top_ids: string[];
  items: ResultCard[];
  has_departure: boolean;
  parsed?: Record<string, string>;
};

export type ReviewCard = { name: string; verdict: string; sub: string };
export type ReviewLink = { date: string; title: string; url: string; year: number; preview: string };

export type Reviews = {
  naver_search_url: string;
  analysis: { cards: ReviewCard[]; meta: string } | null;
  links: ReviewLink[];
  cutoff_year: number;
  current_year: number;
  can_analyze: boolean;
  notice?: string;
  evidence?: { name: string; verdict: string; quotes: { text: string; date: string; url: string }[] }[];
};

export type ClubDetail = {
  id: string;
  name: string;
  region: string;
  city: string;
  candidate: boolean;
  holes: string;
  overview_bits: string[];
  holes_is_evidence: boolean;
  trait_badges: string[];
  intro: string;
  course_labels: string[];
  verified_fields: string[];
  evidence_fields: string[];
  round: {
    session: string;
    fee: number | null;
    three_person: string;
    caddie_mode: string;
    fee_bits: string[];
    summary: string | null;
    eval_bits: string[];
  };
  objective_summary: string[];
  objective_details: { feature: string; label: string; verification: string; notes: string[] }[];
  kga: { matched: boolean; status?: string; checked_at?: string; combos?: string[]; ratings?: string[]; source_url?: string };
  contact: { phone: string; phone_is_evidence: boolean; official_url: string; kakao_map: string; naver_map: string };
  snapshot: string[];
  route: string | null;
  has_coord: boolean;
  fee_block:
    | {
        verified: true;
        kind: "table";
        weekday: [number, number] | null;
        weekend: [number, number] | null;
        unspecified: [number, number] | null;
        weekday_sessions: Record<string, number>;
        weekend_sessions: Record<string, number>;
        weekday_total: [number, number] | null;
        weekend_total: [number, number] | null;
        cart: number | null;
        caddie: number | null;
        is_current: boolean;
        checked_at: string;
        latest_notice_month: string;
        source_url: string;
        note: string;
      }
    | { verified: true; kind: "legacy"; weekday_total: number | null; weekend_total: number | null; weekday_green: number; weekend_green: number; cart: number; caddie: number; note: string }
    | { verified: false; text: string };
  course_cards: { title: string; specs: string; type: string; source_url: string }[];
  profile: { official_name: string; facts: string[]; source_url: string } | null;
  operations: {
    sessions: { name: string; time: string }[];
    caddie: { mode: string; bits: string[]; source_url: string; checked_at: string };
    cart: { bits: string[]; source_url: string; checked_at: string };
    players: { label: string; status: string; note: string }[];
    players_source_url: string;
  };
  ratings: { course: string; tee: string; gender: string; rating: number | null; slope: number | null; length_yards: number | null }[];
  sources: { items: { label: string; url: string; checked_at: string; fields: string[] }[]; public_status: string; public_checked_at: string };
  completeness: { items: { label: string; status: "complete" | "partial" | "missing" }[]; complete: number; total: number; assessed_at: string } | null;
  hole_rows: { course: string; hole: string; facts: string; strategy: string }[];
  course_overview: string;
  data_checked: string;
  reviews: Reviews;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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

export const golfApi = {
  options: () => request<GolfOptions>("/api/golf/options"),
  find: (q: string) => request<{ items: { id: string; name: string; region: string; city: string }[] }>(`/api/golf/find?q=${encodeURIComponent(q)}`),
  search: (params: ConditionParams, sort: Sort) =>
    request<SearchResult>("/api/golf/search", { method: "POST", body: JSON.stringify({ params, sort }) }),
  searchText: (text: string, sort: Sort, includeUnknown = false) =>
    request<SearchResult>("/api/golf/search/text", {
      method: "POST",
      body: JSON.stringify({ text, sort, include_unknown: includeUnknown }),
    }),
  detail: (id: string, search: LastSearch | null) =>
    request<ClubDetail>(`/api/golf/clubs/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify(search?.mode === "text" ? { text: search.text } : search?.mode === "condition" ? { params: search.params } : {}),
    }),
  refreshReviews: (id: string) =>
    request<Reviews>(`/api/golf/clubs/${encodeURIComponent(id)}/reviews/refresh`, { method: "POST" }),
};

export function won(x: number | null | undefined) {
  return x == null ? "-" : `${Math.round(x).toLocaleString("ko-KR")}원`;
}

export const DEFAULT_PARAMS: ConditionParams = {
  departure: "",
  day: "주중",
  session: "2부",
  budget: "전체",
  caddie: "전체",
  areas: [],
  subregions: [],
  players: "전체",
  night: false,
  include_unknown: false,
  avg_score_label: "미선택",
  challenge: "적당히",
};

// ---- 검색 화면 상태: 상세 → 뒤로가기 시 그대로 복원 ----

export type LastSearch =
  | { mode: "condition"; params: ConditionParams }
  | { mode: "text"; text: string; includeUnknown?: boolean };

export type SavedState = {
  mode: SearchMode;
  params: ConditionParams;
  text: string;
  nameQuery: string;
  sort: Sort;
  filter: "전체" | "조건확인" | "확인필요";
  visible: number;
  result: SearchResult | null;
  last: LastSearch | null;
};

const KEY = "golf-search-state-v2";

export function loadState(): SavedState | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const state = JSON.parse(raw) as SavedState;
    return { ...state, params: { ...DEFAULT_PARAMS, ...state.params } };
  } catch {
    return null;
  }
}

export function saveState(state: SavedState) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {}
}
