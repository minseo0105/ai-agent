/** 대시보드 표시 도우미. 값이 없으면 값처럼 보이지 않는 문구('정보 없음')를 돌려준다. */
export const NONE = "정보 없음";

/** 'YYYY-MM-DD'는 그대로, ISO 시각은 한국 날짜로. 읽을 수 없으면 NONE. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return NONE;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.replace(/-/g, ".");
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return NONE;
  return new Date(parsed.getTime() + 9 * 3600_000).toISOString().slice(0, 10).replace(/-/g, ".");
}

/** 단계 날짜. 연도 2자리 원문은 세기를 추정하지 않고 원문 그대로 보여 준다. */
export function stepDateText(item: { date: string | null; date_display: string | null; date_precision: string | null }): string {
  if (item.date) return formatDate(item.date);
  if (item.date_display) return `${item.date_display} (원문)`;
  return "일자 정보 없음";
}

export function formatArea(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return NONE;
  return `${Math.round(value).toLocaleString("ko-KR")}㎡`;
}

export function formatCount(value: number | null | undefined, unit: string): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return NONE;
  return `${Math.round(value).toLocaleString("ko-KR")}${unit}`;
}

/** 입력칸의 문자열 → 숫자. 비었으면 null(값을 만들지 않는다). 쉼표는 지운다. 숫자가 아니면 NaN(검증에서 걸러짐). */
export function parseNumberInput(text: string): number | null {
  const cleaned = text.replace(/[,\s]/g, "");
  if (cleaned === "") return null;
  return Number(cleaned);
}
