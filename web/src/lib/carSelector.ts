// FastAPI /api/car-selector 클라이언트
import { apiFetch } from "@/lib/access";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const media = (path: string | null | undefined) => (path ? `${API_URL}${path}` : "");

/** art는 서버에 고정된 모션 SVG 마크업(사용자 입력 아님) */
export type CarQuestion = { title: string; desc: string; options: { label: string; desc: string; art: string }[] };
export type CarColor = { color: string; price: number; image: string | null; monthly: Record<string, number> };
export type CarRecommendation = {
  persona: { name: string; sub: string; copy: string; quote: string; art: string };
  model: string;
  match: number;
  reasons: string[];
  colors: CarColor[];
  terms: number[];
};

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/car-selector${path}`, {
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

export const carApi = {
  questions: () => request<{ questions: CarQuestion[] }>("/questions"),
  recommend: (answers: number[]) => request<CarRecommendation>("/recommend", { answers }),
};
