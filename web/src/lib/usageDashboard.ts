import { API_URL, apiFetch } from "@/lib/access";

export type UsagePeriod = "today" | "7d" | "30d";
export type Coverage = "COLLECTED" | "NOT_INSTRUMENTED";
export type UsagePage = { route: string; service: string; label: string; visits: number; page_views: number; features: number | null; feature_status: Coverage };
export type UsageService = {
  service: string; label: string; visits: number; page_views: number;
  features: number | null; feature_status: Coverage; feature_label: string;
  used_sessions: number | null; feature_rate: number | null; external: number | null;
  errors: number; map_clicks: number | null; project_clicks: number | null; naver: number | null;
  session_funnel: number[] | null;
};
export type UsageDay = { day: string; service: string; visits: number; page_views: number; features: number };
export type UsageSummary = {
  period: UsagePeriod; timezone: string; start_at: string; end_at: string;
  totals: { visits: number; page_views: number; features: number; external: number; errors: number };
  pages: UsagePage[]; services: UsageService[]; daily: UsageDay[];
  recent: { at: string; service_label: string; label: string }[];
};

export async function getUsageSummary(period: UsagePeriod, signal: AbortSignal): Promise<UsageSummary> {
  const response = await apiFetch(`${API_URL}/api/admin/usage?period=${period}`, { signal, timeoutMs: 6000, cache: "no-store" });
  if (!response.ok) {
    // Render only fixed messages. Never show backend exceptions or arbitrary response content.
    let code = "";
    try { code = (await response.json())?.detail?.code ?? ""; } catch {}
    const messages: Record<string, string> = {
      setup_required: "운영현황 집계가 아직 준비되지 않았어요.",
      range_too_large: "조회량이 많아요. 더 짧은 기간을 선택해 주세요.",
      busy: "다른 조회가 진행 중이에요. 잠시 후 다시 확인해 주세요.",
    };
    const error = new Error(response.status === 401 ? "관리자 로그인이 필요해요." : messages[code] ?? "운영현황을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json();
}
