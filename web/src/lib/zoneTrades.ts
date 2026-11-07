/**
 * 구역 실거래 표시 상태 판정(순수 함수). 국토부 실거래 API 결과만 다룬다.
 * 네이버부동산 매물·호가는 수집하지 않으며 실거래로 표시하지 않는다.
 *
 * 상태: NOT_CONNECTED(서버 키 미설정) / FORBIDDEN(403, 활용신청 필요) / FAILED(그 밖의 조회 오류)
 *       / EMPTY(조회는 됐지만 거래 없음) / OK(거래 있음)
 */
export type ZoneTradeRow = { date: string; price_text: string; price_100m: number; area: number; area_basis?: string;
  property_type: string; name: string; region: string; detail?: Record<string, string> };

/** 계약 해제(취소) 신고된 거래는 시세 참고에서 뺀다. 국토부 cdealType 값이 있으면 해제 건이다. */
export function withoutCancelled<T extends { detail?: Record<string, string> }>(rows: T[]): T[] {
  return rows.filter((r) => !(r.detail?.["계약해제"] ?? "").trim());
}

/** 화면에 적는 조회 기준: 계약년월(국토부 DEAL_YMD) 범위. */
export function periodText(months: string[]): string {
  const f = (m: string) => `${m.slice(0, 4)}.${m.slice(4)}`;
  return months.length ? `${f(months[months.length - 1])}~${f(months[0])} 계약분` : "";
}
export type ZoneTradeStatus = "NOT_CONNECTED" | "FORBIDDEN" | "TIMEOUT" | "PARSE_ERROR" | "FAILED" | "EMPTY" | "OK";

/** 최근 n개월(이번 달 포함) YYYYMM, 최신순. 국토부 신고는 늦게 올라오므로 이번 달은 비어 있을 수 있다. */
export function recentMonths(now: Date, n = 3): string[] {
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

/** 서울 자치구 이름 → 실거래 조회 지역 라벨. 자치구를 모르면 조회하지 않는다. */
export function regionLabel(district: string | null | undefined): string | null {
  const name = (district ?? "").trim();
  return /^[가-힣]{1,4}구$/.test(name) ? `서울 > ${name}` : null;
}

/** 같은 법정동 거래만 남긴다(구역 안 여부가 아니라 같은 동). 동을 모르면 자치구 전체를 그대로 둔다. */
export function sameDong<T extends { region: string }>(rows: T[], dong: string | null | undefined): T[] {
  const target = (dong ?? "").replace(/\s/g, "");
  if (!target) return rows;
  return rows.filter((r) => (r.region ?? "").replace(/\s/g, "") === target);
}

export function classify(input: { apiKeyConfigured: boolean; rows: unknown[]; errors: string[] }): ZoneTradeStatus {
  if (!input.apiKeyConfigured) return "NOT_CONNECTED";
  if (input.rows.length > 0) return "OK";
  if (input.errors.some((e) => /\(403\)|403|활용신청|인증 오류|SERVICE_KEY/.test(e))) return "FORBIDDEN";
  if (input.errors.some((e) => /PUBLIC_DATA_API_KEY/.test(e))) return "NOT_CONNECTED";
  if (input.errors.some((e) => /timed? ?out|Timeout|시간 초과|ReadTimeout/i.test(e))) return "TIMEOUT";
  if (input.errors.some((e) => /XML로 해석하지 못했습니다|ParseError/.test(e))) return "PARSE_ERROR";
  if (input.errors.length > 0) return "FAILED";
  return "EMPTY";
}

export const STATUS_TEXT: Record<ZoneTradeStatus, string> = {
  NOT_CONNECTED: "실거래 API가 연결되지 않았어요(서버에 국토교통부 실거래 API 키가 설정되지 않음).",
  FORBIDDEN: "국토교통부 실거래 API가 요청을 거부했어요(403 또는 인증 오류). 공공데이터포털 활용신청·서비스키 상태 확인이 필요해요.",
  TIMEOUT: "국토교통부 실거래 API 응답이 늦어 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.",
  PARSE_ERROR: "국토교통부 실거래 응답 형식을 읽지 못했어요. 잠시 후 다시 시도해 주세요.",
  FAILED: "실거래를 지금 불러오지 못했어요. 잠시 후 다시 시도해 주세요.",
  EMPTY: "조회 기간에 이 동의 신고된 실거래가 없어요.",
  OK: "",
};

/** 일부 유형만 실패한 경우 안내 문구(정상 유형 결과는 그대로 보여 준다). 실패가 없으면 null. */
export function partialFailureText(errors: string[]): string | null {
  const types = new Set<string>();
  let forbidden = false;
  for (const e of errors) {
    const m = /·\s*([^:]+):/.exec(e);
    if (m) types.add(m[1].trim());
    if (/\(403\)|활용신청|인증 오류|SERVICE_KEY/.test(e)) forbidden = true;
  }
  if (!types.size) return null;
  const list = [...types].join("·");
  return forbidden
    ? `${list} 유형은 국토교통부 API 권한(활용신청)이 없어 조회하지 못했어요(403). 아래는 조회된 유형만의 거래입니다.`
    : `${list} 유형은 조회하지 못했어요. 아래는 조회된 유형만의 거래입니다.`;
}

/** 아파트 매매 월별 요약(이미 받은 3개월 거래만 사용, 추가 호출 없음). 가격 단위는 억원. */
export type AptMonth = { month: string; count: number; median: number | null; perPyeong: number | null };
export type AptAnalysis = { months: AptMonth[]; total: number; summary: string };

const median = (xs: number[]): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const PYEONG = 3.3058;

export function aptAnalysis(rows: ZoneTradeRow[], months: string[]): AptAnalysis {
  const apt = rows.filter((r) => r.property_type === "아파트" && r.price_100m > 0);
  const ordered = [...months].sort(); // 오래된 달부터
  const list: AptMonth[] = ordered.map((ym) => {
    const inMonth = apt.filter((r) => r.date.replace(/-/g, "").slice(0, 6) === ym);
    const unit = inMonth.filter((r) => r.area > 0 && (r.area_basis ?? "전용면적") === "전용면적").map((r) => (r.price_100m / r.area) * PYEONG);
    return { month: ym, count: inMonth.length, median: median(inMonth.map((r) => r.price_100m)), perPyeong: median(unit) };
  });
  const total = list.reduce((n, m) => n + m.count, 0);
  return { months: list, total, summary: interpret(list, total) };
}

function interpret(list: AptMonth[], total: number): string {
  if (total === 0) return "조회 기간에 이 동의 아파트 매매 거래가 없어요.";
  if (total < 5) return `아파트 거래가 ${total}건뿐이라 가격 흐름을 해석하기 어려워요(개별 거래 참고).`;
  // 가장 최근 달은 신고 기한(계약 후 30일)이 지나지 않아 건수가 적게 잡힐 수 있다. 앞의 두 달을 비교한다.
  const [a, b] = list.length >= 3 ? [list[0], list[1]] : [list[0], list[list.length - 1]];
  const parts: string[] = [];
  if (a.median && b.median && a.count >= 3 && b.count >= 3) {
    const pct = ((b.median - a.median) / a.median) * 100;
    parts.push(Math.abs(pct) < 3 ? "중위가격은 큰 변화가 없어요" : `중위가격이 ${fmtMonth(a.month)} 대비 ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%예요`);
  } else {
    parts.push("월별 거래가 적어 중위가격 비교는 참고만 해 주세요");
  }
  if (a.count && b.count) {
    const v = ((b.count - a.count) / a.count) * 100;
    parts.push(Math.abs(v) < 20 ? "거래량은 비슷해요" : `거래량은 ${v > 0 ? "늘었어요" : "줄었어요"}(${a.count}→${b.count}건)`);
  }
  return `${fmtMonth(b.month)} 기준 ${parts.join(", ")}. 최근 달은 신고가 덜 들어왔을 수 있어요. 단순 통계이며 가격 예측이 아닙니다.`;
}

export const fmtMonth = (ym: string) => `${Number(ym.slice(4))}월`;

/** 전용면적 3.3㎡(1평)당 표기. 화면 문구는 여기서만 가져다 쓴다. */
export const PER_PYEONG_LABEL = "3.3㎡당";
