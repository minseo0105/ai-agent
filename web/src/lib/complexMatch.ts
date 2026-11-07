/**
 * 재건축 사업 ↔ 실제 아파트 단지 매칭(같은 자치구·같은 법정동의 이미 받은 실거래만 사용, 추가 호출 없음).
 *
 * 확정 조건: 사업 주소의 본번 = 단지 거래의 본번 AND 단지명이 사업명과 맞음(차수 번호 충돌 없음).
 * 둘 중 하나만 맞으면 '후보'로만 보여 주고 확정하지 않는다. 단지는 국토부 단지 일련번호(aptSeq)로 묶는다.
 */
import type { ZoneTradeRow } from "./zoneTrades.ts";

export type TradeRowLike = ZoneTradeRow & {
  id?: string;
  apt_seq?: string | null;
  jibun?: string;
  raw_detail?: Record<string, string>;
};
export type Complex = { key: string; aptSeq: string | null; name: string; bonbun: string | null; buildYear: string | null; rows: TradeRowLike[] };
export type Candidate = { complex: Complex; reasons: string[] };
export type MatchStatus = "CONFIRMED" | "UNCERTAIN" | "NO_TRADES";
export type ComplexMatch = {
  status: MatchStatus;
  lot: { main: string; sub: string | null; mountain: boolean } | null;
  confirmed: Complex[];
  candidates: Candidate[];
  others: TradeRowLike[];
  reason: string | null;
};

const GENERIC = /(서울특별시|주택|재건축|재개발|정비|사업|조합|설립|추진위원회|추진위|추진|구역|지구|아파트|일대)/g;

/** 사업명·단지명 비교용 키: 괄호 내용·일반어·공백·기호를 뺀다. */
export function nameKey(text: string): string {
  return (text ?? "").normalize("NFKC").replace(/\(.*?\)/g, "").replace(GENERIC, "").replace(/[\s·,.\-_/]+/g, "");
}

/** 'N차·N단지' 번호(‘1,2,3차’ 포함). */
export function ordinals(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of (text ?? "").normalize("NFKC").matchAll(/(\d+(?:\s*[,·]\s*\d+)*)\s*(차|단지)/g)) {
    for (const n of m[1].split(/[,·]/)) out.add(n.trim());
  }
  return out;
}

const core = (key: string) => key.replace(/\d+(차|단지)/g, "").replace(/\d+/g, "");
const bigrams = (s: string) => new Set(Array.from({ length: Math.max(0, s.length - 1) }, (_, i) => s.slice(i, i + 2)));
function dice(a: string, b: string): number {
  const A = bigrams(a), B = bigrams(b);
  if (!A.size || !B.size) return 0;
  let n = 0;
  A.forEach((x) => { if (B.has(x)) n++; });
  return (2 * n) / (A.size + B.size);
}

/** 단지명이 사업명과 맞는지. 차수 번호가 어긋나면(상아2차 vs 상아1차) 맞지 않는다. */
export function nameMatches(projectName: string, complexName: string): boolean {
  const po = ordinals(projectName), co = ordinals(complexName);
  if (po.size && co.size && [...co].some((n) => !po.has(n))) return false;
  const p = core(nameKey(projectName)), c = core(nameKey(complexName));
  if (c.length < 2 || p.length < 2) return false;
  return p.includes(c) || c.includes(p) || dice(p, c) >= 0.6;
}

/** 사업 주소 끝의 지번(본번·부번). '산' 지번이나 지번이 없으면 null/mountain. */
export function parseLot(address: string | null | undefined) {
  const m = (address ?? "").normalize("NFKC").trim()
    .match(/(?:^|\s)(산\s*)?(\d+)(?:-(\d+))?(?:\s*번지)?(?:\s*(?:일대|일원|외\s*\d+\s*(?:개\s*)?필지))?\s*$/);
  return m ? { main: String(Number(m[2])), sub: m[3] ? String(Number(m[3])) : null, mountain: !!m[1] } : null;
}

const strip0 = (v: string | undefined | null) => (v && /^\d+$/.test(v) ? String(Number(v)) : null);

/** 거래의 국토부 단지 일련번호. 서버가 apt_seq를 주면 그것을, 아니면 거래 id(유형:지역:단지번호:…)에서 읽는다. */
export function aptSeqOf(r: TradeRowLike): string | null {
  if (r.apt_seq) return r.apt_seq;
  const part = (r.id ?? "").split(":")[2];
  return part && /^\d{5}-\d+$/.test(part) ? part : null;
}

function bonbunOf(r: TradeRowLike): string | null {
  return strip0(r.raw_detail?.["본번"]) ?? strip0((r.jibun ?? "").split("-")[0]);
}

/** 같은 동의 아파트 거래를 단지 단위로 묶는다(단지번호 우선, 없으면 단지명+본번). */
export function groupComplexes(rows: TradeRowLike[]): Complex[] {
  const map = new Map<string, Complex>();
  for (const r of rows) {
    if (r.property_type !== "아파트") continue;
    const seq = aptSeqOf(r);
    const bon = bonbunOf(r);
    const key = seq ?? `${r.name}|${bon ?? "?"}`;
    const c = map.get(key) ?? { key, aptSeq: seq, name: r.name, bonbun: bon, buildYear: (r as { build_year?: string }).build_year ?? null, rows: [] };
    c.rows.push(r);
    map.set(key, c);
  }
  return [...map.values()];
}

/** 재건축 사업과 같은 동 거래의 단지 매칭. 확정되지 않으면 다른 단지 거래를 대신 보여 주지 않는다. */
export function matchComplexes(project: { name: string; address?: string | null }, dongRows: TradeRowLike[]): ComplexMatch {
  const lot = parseLot(project.address);
  const complexes = groupComplexes(dongRows);
  const confirmed: Complex[] = [];
  const candidates: Candidate[] = [];
  for (const c of complexes) {
    const lotOk = !!lot && !lot.mountain && !!c.bonbun && c.bonbun === lot.main;
    const nameOk = nameMatches(project.name, c.name);
    if (lotOk && nameOk) confirmed.push(c);
    else if (lotOk) candidates.push({ complex: c, reasons: ["지번(본번) 일치", "단지명 불일치"] });
    else if (nameOk) candidates.push({ complex: c, reasons: ["단지명 유사", lot ? "지번 불일치" : "사업 주소에 지번 없음"] });
  }
  const keys = new Set(confirmed.map((c) => c.key));
  const others = dongRows.filter((r) => !(r.property_type === "아파트" && keys.has(aptSeqOf(r) ?? `${r.name}|${bonbunOf(r) ?? "?"}`)));
  const status: MatchStatus = confirmed.length ? "CONFIRMED" : candidates.length ? "UNCERTAIN" : "NO_TRADES";
  const reason = confirmed.length ? null
    : !lot ? "사업 주소에 지번이 없어 단지를 확정할 수 없어요."
      : lot.mountain ? "사업 주소가 산 지번이라 단지를 확정할 수 없어요."
        : candidates.length ? "단지명과 지번이 함께 일치하는 단지가 없어 확정하지 않았어요."
          : "조회 기간에 이 단지로 확인된 거래가 없어요.";
  return { status, lot, confirmed, candidates, others, reason };
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : null;
};

export type AreaGroup = { label: string; min: number; max: number; count: number; median: number | null; low: number; high: number; latest: TradeRowLike };

/** 전용면적별 묶음. 0.5㎡ 이내 차이만 같은 면적으로 보고, 그보다 다른 면적은 합치지 않는다. 해제 거래는 넣지 않는다. */
export function areaGroups(rows: TradeRowLike[]): AreaGroup[] {
  const valid = rows.filter((r) => r.area > 0 && r.price_100m > 0 && !(r.detail?.["계약해제"] ?? "").trim()).sort((a, b) => a.area - b.area);
  const groups: TradeRowLike[][] = [];
  for (const r of valid) {
    const g = groups[groups.length - 1];
    if (g && r.area - g[0].area <= 0.5) g.push(r);
    else groups.push([r]);
  }
  return groups.map((g) => {
    const prices = g.map((r) => r.price_100m);
    const min = g[0].area, max = g[g.length - 1].area;
    const latest = [...g].sort((a, b) => b.date.localeCompare(a.date))[0];
    return { label: min === max ? `${min}` : `${min}~${max}`, min, max, count: g.length, median: median(prices), low: Math.min(...prices), high: Math.max(...prices), latest };
  });
}

export type RebuildView =
  | { kind: "API_ERROR"; status: string }
  | { kind: "CONFIRMED" | "NEED_CHECK"; match: ComplexMatch };

/**
 * 재건축 화면 상태. 아파트 조회 자체가 실패했으면(403·시간 초과 등) '거래 없음'이 아니라 API 오류로 둔다.
 * apiStatus는 동 단위 조회 결과(classify)이고, errors는 유형별 실패 문구다.
 */
export function rebuildView(apiStatus: string, errors: string[], project: { name: string; address?: string | null }, dongRows: TradeRowLike[]): RebuildView {
  const aptFailed = errors.some((e) => /·\s*아파트\s*:/.test(e));
  if ((apiStatus !== "OK" && apiStatus !== "EMPTY") || aptFailed) return { kind: "API_ERROR", status: aptFailed && apiStatus === "OK" ? "APT_FAILED" : apiStatus };
  const match = matchComplexes(project, apiStatus === "OK" ? dongRows : []);
  return { kind: match.status === "CONFIRMED" ? "CONFIRMED" : "NEED_CHECK", match };
}
