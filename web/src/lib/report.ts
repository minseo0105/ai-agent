// FastAPI /api/report 클라이언트
import { apiFetch } from "@/lib/access";
import { postSSE } from "./sse";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type ReportOptions = {
  styles: string[];
  depths: string[];
  modes: string[];
  style_help: Record<string, string>;
  depth_help: Record<string, string>;
};

export type ReportChart = { company: string; labels: string[]; values: number[]; dates: string[] } | null;
export type ToolStep = { name: string; label: string; input: Record<string, unknown> };
export type ReportResult = { text: string; chart: ReportChart };

export const reportApi = {
  options: async (): Promise<ReportOptions> => {
    const res = await apiFetch(`${API_URL}/api/report/options`);
    if (!res.ok) throw new Error(`서버 응답 오류 (${res.status})`);
    return res.json();
  },

  generate: async (
    body: { topic: string; style: string; depth: string; mode: string },
    onTool: (t: ToolStep) => void,
    signal?: AbortSignal,
  ): Promise<ReportResult> => {
    let result: ReportResult | null = null;
    let error = "";
    await postSSE(
      `${API_URL}/api/report/generate`,
      body,
      (event, data) => {
        if (event === "tool") onTool(data as ToolStep);
        else if (event === "answer") result = data as ReportResult;
        else if (event === "error") error = (data as { message: string }).message;
      },
      signal,
    );
    if (error) throw new Error(error);
    if (!result) throw new Error("보고서를 받지 못했어요.");
    return result;
  },

  pdf: async (text: string, chart: ReportChart): Promise<Blob> => {
    const res = await apiFetch(`${API_URL}/api/report/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, chart: chart ? { company: chart.company, dates: chart.dates } : null }),
    });
    if (!res.ok) throw new Error(`PDF 생성 실패 (${res.status})`);
    return res.blob();
  },
};
