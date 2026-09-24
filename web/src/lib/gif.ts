// FastAPI /api/gif 클라이언트 (multipart 업로드 → 이미지 바이너리 응답)
import { apiFetch } from "@/lib/access";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const MAX_UPLOAD_MB = 15;

export type GifOptions = {
  remove_bg: boolean;
  use_background: boolean;
  canvas_color: string;
  use_drive: boolean;
  use_zoom: boolean;
  use_bounce: boolean;
  use_shake: boolean;
  use_tilt: boolean;
  use_pan: boolean;
  direction: "왼쪽 → 오른쪽" | "오른쪽 → 왼쪽";
  travel_strength: number;
  perspective_strength: number;
  speed: number;
  frame_count: number;
  max_width: number;
  loop_style: "일반 반복" | "부메랑";
  brightness: number;
  contrast: number;
};

export type GifMeta = { frames: number; width: number; height: number; duration: number; loop_style: string; bytes: number };

export const DEFAULT_OPTIONS: GifOptions = {
  remove_bg: false,
  use_background: false,
  canvas_color: "#F3F5F8",
  use_drive: true,
  use_zoom: false,
  use_bounce: true,
  use_shake: false,
  use_tilt: false,
  use_pan: false,
  direction: "왼쪽 → 오른쪽",
  travel_strength: 20,
  perspective_strength: 18,
  speed: 3,
  frame_count: 20,
  max_width: 800,
  loop_style: "일반 반복",
  brightness: 100,
  contrast: 100,
};

function formData(image: File, background: File | null, fields: Record<string, string | number | boolean>) {
  const fd = new FormData();
  fd.append("image", image);
  if (background) fd.append("background", background);
  for (const [k, v] of Object.entries(fields)) fd.append(k, String(v));
  return fd;
}

async function post(path: string, fd: FormData, signal?: AbortSignal) {
  const res = await apiFetch(`${API_URL}/api/gif${path}`, { method: "POST", body: fd, signal });
  if (!res.ok) {
    let message = `서버 응답 오류 (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") message = j.detail;
      else if (Array.isArray(j?.detail)) message = "입력값을 확인해 주세요.";
    } catch {}
    throw new Error(message);
  }
  return res;
}

export const gifApi = {
  async preview(image: File, background: File | null, o: Pick<GifOptions, "remove_bg" | "use_background" | "canvas_color">, signal?: AbortSignal) {
    const res = await post("/preview", formData(image, background, o), signal);
    return res.blob();
  },
  async generate(image: File, background: File | null, o: GifOptions, signal?: AbortSignal) {
    const res = await post("/generate", formData(image, background, o), signal);
    const raw = res.headers.get("X-Gif-Meta");
    const meta = raw ? (JSON.parse(decodeURIComponent(raw)) as GifMeta) : null;
    return { blob: await res.blob(), meta };
  },
};
