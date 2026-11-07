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
