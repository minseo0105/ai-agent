// FastAPI /api/saju 클라이언트
import { apiFetch } from "@/lib/access";
import { postSSE } from "@/lib/sse";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type BirthInput = {
  birth: string; // YYYY-MM-DD (음력이면 음력 날짜)
  calendar_type: "양력" | "음력";
  time_text: string; // "모름" | "HH:MM"
  gender: "여성" | "남성";
  lunar_leap: boolean;
};

export type SajuOptions = { genders: string[]; calendars: string[]; times: string[]; topics: string[]; available: boolean };

export type Pillar = { label: string; ganji: string; hangul: string; gan_el?: string; zhi_el?: string };
export type FlowDetail = {
  gan: string;
  zhi: string;
  gan_hangul: string;
  zhi_hangul: string;
  gan_el: string;
  zhi_el: string;
  gan_god: string;
  gan_group: string;
  zhi_group: string;
  headline: string;
  work: string;
  money: string;
  relation: string;
  action: string;
};
export type YearFlow = FlowDetail & { year: number; ganji: string; hangul: string };
export type Cycle = {
  ganji: string;
  hangul: string;
  start_year: number;
  end_year: number;
  start_age: number;
  end_age: number;
  current: boolean;
  detail: FlowDetail;
  years: YearFlow[];
};
export type Domain = { title: string; icon: string; headline: string; main: string; strength: string; risk: string; cycle: string; basis: string };

export type SajuResult = {
  input: BirthInput;
  solar_ymd: string;
  unknown_time: boolean;
  pillars: Pillar[];
  elements: { element: string; symbol: string; count: number; desc: string }[];
  strong_elements: string[];
  weak_elements: string[];
  max_count: number;
  min_count: number;
  profile: { title: string; one_line: string; month: string; work: string; shadow: string; money: string; relation: string; cycle: string };
  top_gods: { god: string; count: number; sentence: string; group_title: string; group_work: string }[];
  basis_gods: { god: string; count: number; desc: string }[];
  domains: Domain[];
  daewoon: { direction: string; start_phrase: string; start_solar: string; current_index: number; cycles: Cycle[] };
  this_year: number;
};

export type AiRequest = BirthInput & {
  kind: "full" | "cycle" | "year" | "question";
  cycle_index?: number;
  year?: number;
  topic?: string;
  question?: string;
};

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/saju${path}`, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let message = `서버 응답 오류 (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") message = j.detail;
    } catch {}
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const sajuApi = {
  options: () => request<SajuOptions>("/options"),
  analyze: (input: BirthInput) => request<SajuResult>("/analyze", input),
  /** GPT 해석을 스트리밍으로 받는다. onDelta로 본문 조각이 오고, 끝나면 {truncated}를 돌려준다. */
  async ai(req: AiRequest, onDelta: (text: string) => void, signal?: AbortSignal) {
    let truncated = false;
    let error = "";
    await postSSE(
      `${API_URL}/api/saju/ai`,
      req,
      (event, data) => {
        const d = data as { text?: string; truncated?: boolean; message?: string };
        if (event === "delta" && d.text) onDelta(d.text);
        else if (event === "end") truncated = !!d.truncated;
        else if (event === "error") error = d.message || "AI 해석을 불러오지 못했습니다.";
      },
      signal,
    );
    if (error) throw new Error(error);
    return { truncated };
  },
};
