// FastAPI /api/dreamcar 클라이언트 + 할부 계산
import { apiFetch } from "@/lib/access";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const media = (path: string | null | undefined) => (path ? `${API_URL}${path}` : "");

export type Question = { title: string; desc: string; options: { label: string; desc: string; art: string }[] };
export type DreamConfig = { questions: Question[]; apr: number; terms: number[]; deposit_rates: number[] };
export type OwnedCar = {
  model: string;
  year: number;
  mileage: number;
  market: number;
  range_low: number;
  range_high: number;
  grade: string;
  plate: string;
};
export type ColorOption = { color: string; price: number; image: string | null };
export type TopCar = {
  model: string;
  match: number;
  tagline: string;
  reasons: string[];
  price: number;
  segment: string;
  seats: string;
  colors: ColorOption[];
};
export type Recommendation = {
  persona: { name: string; sub: string; copy: string; quote: string; art: string };
  total_models: number;
  top: TopCar[];
};

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(`${API_URL}/api/dreamcar${path}`, {
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

export const dreamApi = {
  config: () => request<DreamConfig>("/config"),
  lookup: (plate: string) => request<OwnedCar>("/lookup", { plate }),
  recommend: (answers: number[]) => request<Recommendation>("/recommend", { answers }),
};

/** 원리금균등 월 납입금(만원)과 총 이자(만원). services/dreamcar.py monthly_installment와 같은 공식. */
export function monthlyInstallment(principalManwon: number, months: number, annualRate: number) {
  if (principalManwon <= 0) return { monthly: 0, interest: 0 };
  const principal = principalManwon * 10000;
  const r = annualRate / 100 / 12;
  const monthly = r === 0 ? principal / months : (principal * r * (1 + r) ** months) / ((1 + r) ** months - 1);
  return { monthly: monthly / 10000, interest: (monthly * months - principal) / 10000 };
}
