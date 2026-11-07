"use client";

import { useMemo, useState } from "react";
import { inputClass } from "@/components/golf/ui";
import { compareListing, dongReview, failedTypes, type ProjectLite } from "@/lib/budgetReview";
import { formatManwon } from "@/lib/investmentCalc";
import { RULES, dealCondition, fundsCondition, fundsFor, parseField, projectKind, rightsCondition, type Money } from "@/lib/investDecision";
import type { DevelopmentProject } from "@/lib/realestate";
import { STATUS_TEXT, classify, partialFailureText, periodText } from "@/lib/zoneTrades";
import { parseNumberInput } from "@/lib/zipFormat";
import DecisionBoard from "./DecisionBoard";
import { AmountInput, CostScope, Term } from "./MoneyForm";
import { TRADE_TYPES, type DistrictTrades } from "./useDistrictTrades";

const SCOPE_NOTE = "모두 같은 법정동의 참고 거래예요. 정비구역 경계 자료가 없어 구역 안 거래인지는 구분하지 않았어요.";
const eok = (v: number | null) => (v === null ? "—" : `${v.toFixed(2)}억`);

/** 거래 조회 상태(키 없음·403·실패·거래 없음)를 실거래 탭과 같은 문구로 알린다. */
function TradeStatus({ t, apiKeyConfigured }: { t: DistrictTrades; apiKeyConfigured: boolean }) {
  if (t.loading) return <p aria-busy="true" className="text-xs text-muted">자치구 실거래를 불러오고 있어요…</p>;
  if (!t.region) return <p className="text-xs text-muted">자치구 정보가 없어 실거래를 조회하지 않았어요.</p>;
  const status = classify({ apiKeyConfigured, rows: t.rows, errors: t.errors });
  if (status !== "OK") return <p role="status" className="text-xs font-semibold text-muted">{STATUS_TEXT[status]}</p>;
  const partial = partialFailureText(t.errors);
  return partial ? <p role="status" className="rounded-lg bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-300">{partial}</p> : null;
}

const KINDS = ["전체", "재개발", "재건축", "신속통합기획"] as const;
type Kind = (typeof KINDS)[number];
const matchKind = (p: ProjectLite, k: Kind) => k === "전체" || p.type_label === k || p.program_label === k;

/** 내 예산으로 투자 가능 지역 찾기: 선택한 자치구에서 정비사업이 있는 법정동별 과거 실거래·예산 이하 거래 사례·사업 단계와 위험. */
export function RegionReview({ project, projects, trades, apiKeyConfigured, ceiling, district, districts, onDistrict }: {
  project: DevelopmentProject; projects: ProjectLite[]; trades: DistrictTrades; apiKeyConfigured: boolean; ceiling: number | null;
  district?: string | null; districts?: string[]; onDistrict?: (d: string) => void;
}) {
  const [kind, setKind] = useState<Kind>("전체");
  const shown = useMemo(() => projects.filter((p) => matchKind(p, kind)), [projects, kind]);
  const rows = useMemo(() => dongReview(trades.rows, shown, ceiling), [trades.rows, shown, ceiling]);
  const noDong = shown.filter((p) => !p.dong);
  const here = (district ?? project.district) === project.district;
  const guide = here ? project.investor_guide : undefined;
  const failed = [...failedTypes(trades.errors).keys()];
  return (
    <section data-region-review aria-label="내 예산으로 투자 가능 지역 찾기" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">내 예산으로 투자 가능 지역 찾기 <span className="font-semibold text-subtle">과거 실거래 기반 지역 후보</span></h3>
      <p className="rounded-lg bg-surface-muted px-2 py-1.5 text-[11px] text-muted">실제 판매 중인 매물이 아니라, 최근 3개월에 신고된 거래 가격으로 가격대가 맞을 수 있는 동을 찾아요.</p>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {districts && onDistrict && (
          <select aria-label="자치구" value={district ?? project.district ?? ""} onChange={(e) => onDistrict(e.target.value)} className={`${inputClass} min-w-28`}>
            {districts.map((d) => <option key={d}>{d}</option>)}
          </select>
        )}
        {KINDS.map((k) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
            className={`min-h-8 rounded-full px-2.5 text-[11px] font-bold ${kind === k ? "bg-zip text-white" : "border border-border text-muted"}`}>{k}</button>
        ))}
      </div>
      <p className="text-[11px] text-subtle">재개발·재건축은 실제 사업 유형, 신속통합기획은 정책·계획 유형이에요(신속통합기획 중 실제 유형이 확인되지 않은 곳은 &apos;유형 확인 필요&apos;). 모아타운·소규모정비사업 자료는 아직 연결되지 않았어요.</p>
      <p className="text-[11px] text-subtle">{periodText(trades.months)} · {SCOPE_NOTE} {ceiling === null ? "내 자금(가용현금)을 입력하면 예산 이하 거래 수를 보여 줘요(입력 오류가 있으면 세지 않아요)." : `입력 조건상 추정 상한 ${formatManwon(ceiling)} 이하 거래 사례를 셉니다.`}</p>
      {ceiling !== null && <CostScope />}
      <TradeStatus t={trades} apiKeyConfigured={apiKeyConfigured} />
      {!trades.loading && trades.rows.length > 0 && rows.length === 0 && <p className="text-xs text-muted">이 조건에 맞는 정비사업이 있는 동이 없어요.</p>}
      {noDong.length > 0 && (
        <p data-no-dong className="text-[11px] text-subtle">
          법정동 정보가 없는 사업 {noDong.length}건({noDong.slice(0, 3).map((p) => p.name).join(", ")}{noDong.length > 3 ? " 등" : ""})은 실거래와 연결하지 못해 표에서 빠졌어요.
        </p>
      )}
      {!trades.loading && trades.rows.length > 0 && rows.length > 0 && (
        <div className="max-h-72 overflow-auto rounded-lg border border-border">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-surface-muted text-subtle">
              <tr><th className="px-2 py-1">법정동</th><th className="px-2 py-1">정비사업 (유형 · 단계 · 위험)</th><th className="px-2 py-1 text-right">거래</th><th className="px-2 py-1 text-right">중위가</th><th className="px-2 py-1 text-right">예산 이하 거래 사례{failed.length > 0 && "*"}</th></tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.dong} className={`border-t border-border/60 align-top ${d.dong === project.dong ? "bg-zip/5" : ""}`}>
                  <td className="whitespace-nowrap px-2 py-1 font-bold">{d.dong}</td>
                  <td className="px-2 py-1 text-muted">
                    {d.projects.slice(0, 3).map((p) => <div key={p.name} className="line-clamp-2">{p.name} · {p.business ?? "유형 확인 필요"}{p.plan ? `(${p.plan})` : ""} · {p.stage}{p.risk ? ` · ${p.risk}` : ""}</div>)}
                    {d.projects.length > 3 && <div>외 {d.projects.length - 3}건</div>}
                  </td>
                  <td className="px-2 py-1 text-right">{d.trades === 0 ? (failed.length ? "0 (조회된 유형 기준)" : "0") : d.trades}{d.types.length > 0 && <div className="text-subtle">{d.types.join("·")}</div>}</td>
                  <td className="whitespace-nowrap px-2 py-1 text-right">{eok(d.median)}</td>
                  <td className="px-2 py-1 text-right font-bold">{d.withinBudget === null ? "—" : d.withinBudget === 0 && failed.length ? "0 (조회된 유형 기준)" : d.withinBudget}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {failed.length > 0 && (
            <p data-scope-note className="border-t border-border px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-300">
              * 거래·예산 이하 건수는 조회에 성공한 유형만 센 거래 사례 수예요. {failed.join("·")} 유형은 조회하지 못해(403·실패) 빠져 있으며, 거래가 0건이라는 뜻이 아니에요.
            </p>
          )}
        </div>
      )}
      {guide && (
        <div className="rounded-lg bg-surface-muted px-2.5 py-2 text-[11px] leading-relaxed">
          <p className="font-bold">{project.name} · {project.stage.label} 단계 위험: {guide.risk_label}</p>
          {guide.risk_note && <p className="text-muted">{guide.risk_note}</p>}
          {[...guide.watch_next.slice(0, 2), ...guide.pitfalls.slice(0, 2)].length > 0 && (
            <ul className="mt-1 list-disc pl-4 text-muted">
              {guide.watch_next.slice(0, 2).map((w) => <li key={w}>확인: {w}</li>)}
              {guide.pitfalls.slice(0, 2).map((w) => <li key={w}>주의: {w}</li>)}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

const POSITION = { BELOW: "입력 매도가가 참고 범위보다 낮아요", WITHIN: "입력 매도가가 참고 범위 안에 있어요", ABOVE: "입력 매도가가 참고 범위보다 높아요" } as const;

const safeUrl = (u: string) => (/^https?:\/\/[^\s]+$/i.test(u.trim()) ? u.trim() : null);

/** 관심 매물 분석: 사용자가 입력한 매물 정보로 필요자금·유사 실거래 비교·정비사업 권리 확인 항목을 보여 준다. URL은 원문 이동용(자동 수집 없음). */
export function ListingCompare({ project, trades, money }: { project: DevelopmentProject; trades: DistrictTrades; money?: Money }) {
  const dongs = useMemo(() => [...new Set([project.dong, ...trades.rows.map((r) => r.region)].filter((d): d is string => !!d))].sort(), [project.dong, trades.rows]);
  const [f, setF] = useState({ dong: project.dong ?? "", type: "아파트", area: "", ask: "", complex: "", address: "", year: "", url: "" });
  const area = parseNumberInput(f.area);
  // 매도 희망가격은 형식·범위를 검증한다. 잘못된 값은 NaN으로 넘겨 자금 조건이 '입력 오류'가 되게 한다.
  const askParsed = parseField(f.ask, RULES.price);
  const ask = askParsed.value;
  const askForFunds = askParsed.error ? Number.NaN : ask;
  const buildYear = parseNumberInput(f.year);
  const r = useMemo(() => compareListing(trades.rows, { dong: f.dong, type: f.type, area, ask, complex: f.complex, buildYear }), [trades.rows, f.dong, f.type, area, ask, f.complex, buildYear]);
  // 403·조회 실패 유형은 '거래 0건'이 아니라 '데이터 없음'이다.
  const blocked = failedTypes(trades.errors).get(f.type);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((v) => ({ ...v, [k]: e.target.value }));
  const sameDong = !!f.dong && f.dong === project.dong;
  const kind = sameDong ? projectKind(project) : { business: null, plan: null };
  // 경기 사업은 stage_guide가 없어 경기 목록의 표준 단계를 쓴다(목록 표기 기준, 공식 고시 확인 아님).
  const stage = sameDong ? project.stage_guide?.stage ?? project.gyeonggi?.stage_std ?? null : null;
  const m = money;
  const funds = m ? fundsFor(m, askForFunds) : null;
  const fundsBad = !!m && (m.invalid.length > 0 || !!askParsed.error);
  const conditions = m ? [fundsCondition(m, askForFunds), dealCondition(m), rightsCondition(kind, stage, false)] : [];
  const url = safeUrl(f.url);
  return (
    <section data-listing-compare aria-label="관심 매물 분석" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">관심 매물 분석 <span className="font-semibold text-subtle">직접 입력한 매물 · 최근 3개월 동일 법정동 실거래 비교</span></h3>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <label className="col-span-2 block"><span className="mb-0.5 block font-bold">주소 (메모)</span><input value={f.address} onChange={set("address")} placeholder="예: 문정동 ○○번지" className={`${inputClass} w-full`} /></label>
        <label className="col-span-2 block"><span className="mb-0.5 block font-bold">매물 URL (선택)</span><input value={f.url} onChange={set("url")} inputMode="url" placeholder="네이버 부동산 등 매물 주소" className={`${inputClass} w-full`} />
          <span className="mt-0.5 block text-[11px] text-subtle">원문으로 이동하는 데만 써요. 매물 정보를 자동으로 가져오지 않아요.{url && <> <a href={url} target="_blank" rel="noopener noreferrer" className="font-bold text-zip underline">원문 열기 ↗</a></>}</span></label>
        <label className="block"><span className="mb-0.5 block font-bold">법정동</span>
          <select value={f.dong} onChange={set("dong")} className={`${inputClass} w-full`}>{dongs.map((d) => <option key={d}>{d}</option>)}</select></label>
        <label className="block"><span className="mb-0.5 block font-bold">유형</span>
          <select value={f.type} onChange={set("type")} className={`${inputClass} w-full`}>{TRADE_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <label className="block"><span className="mb-0.5 block font-bold">{f.type === "단독·다가구" ? "연면적" : "전용면적"} (㎡)</span><input inputMode="decimal" value={f.area} onChange={set("area")} placeholder={f.type === "단독·다가구" ? "연면적" : "전용면적"} className={`${inputClass} w-full`} /></label>
        <AmountInput label="매도 희망가격" value={f.ask} onChange={(v) => setF((o) => ({ ...o, ask: v }))} rule={RULES.price} />
        <label className="block"><span className="mb-0.5 block font-bold">단지·건물명 (선택)</span><input value={f.complex} onChange={set("complex")} placeholder="같은 단지 우선" className={`${inputClass} w-full`} /></label>
        <label className="block"><span className="mb-0.5 block font-bold">건축연도 (선택)</span><input inputMode="numeric" value={f.year} onChange={set("year")} placeholder="±5년 우선" className={`${inputClass} w-full`} /></label>
      </div>
      {funds && fundsBad && (
        <p role="status" data-listing-funds className="rounded-lg bg-red-500/10 px-2.5 py-2 text-xs font-bold text-red-700 dark:text-red-300">
          입력 오류·추가 확인 필요: {[...(m?.invalid ?? []), ...(askParsed.error ? ["매도 희망가격"] : [])].join(", ")} 값을 확인해 주세요. 계산 결과를 표시하지 않아요.
        </p>
      )}
      {funds && !fundsBad && (
        <dl data-listing-funds className="grid grid-cols-2 gap-x-3 gap-y-1 rounded-lg bg-surface-muted px-2.5 py-2 text-xs">
          <dt className="text-muted">필요자금 (매입가 + 부대비용)</dt><dd className="text-right font-bold">{funds.need === null ? "매도 희망가격 필요" : formatManwon(funds.need)}{funds.need !== null && funds.cost === null && <span className="block text-[11px] font-normal text-subtle">부대비용 미입력(0%로 계산)</span>}</dd>
          <dt className="text-muted">가용현금 − 예비비 + 대출 가정</dt><dd className="text-right">{funds.available === null ? "가용현금 필요" : formatManwon(funds.available + (m?.loan ?? 0))}</dd>
          <dt className="text-muted">부족 / 여유</dt><dd className={`text-right font-extrabold ${funds.shortfall !== null && funds.shortfall > 0 ? "text-red-600 dark:text-red-400" : ""}`}>{funds.shortfall === null ? "—" : funds.shortfall > 0 ? `부족 ${formatManwon(funds.shortfall)}` : `여유 ${formatManwon(-funds.shortfall)}`}</dd>
          <dd className="col-span-2"><CostScope costMissing={funds.need !== null && funds.cost === null} /></dd>
        </dl>
      )}
      {trades.loading ? (
        <p className="text-xs text-muted">실거래를 불러오고 있어요…</p>
      ) : blocked ? (
        <p role="status" data-blocked className="rounded-lg bg-amber-500/10 px-2.5 py-2 text-xs font-semibold text-amber-800 dark:text-amber-300">
          {f.type} 거래는 {blocked === "FORBIDDEN" ? "국토교통부 API 권한(활용신청)이 없어(403)" : "조회에 실패해"} 데이터가 없어요. 거래가 0건이라는 뜻이 아니므로 비교할 수 없어요.
        </p>
      ) : !r.ok ? (
        <p role="status" className="rounded-lg bg-surface-muted px-2.5 py-2 text-xs font-semibold text-muted">{r.reason}</p>
      ) : (
        <div className="space-y-1 text-xs">
          <p><b>참고 거래가격 범위</b> {formatManwon(r.low!)} ~ {formatManwon(r.high!)} <span className="text-subtle">(중위 {formatManwon(r.mid!)}, 면적당 가격 25~75% 구간 × 입력 면적)</span></p>
          {r.position && <p className="font-bold">{POSITION[r.position]}.</p>}
          <p className="text-[11px] text-muted">
            비교 기준: {r.basis} · {r.n}건 · {r.conditions!.areaBasis} {r.conditions!.area[0]}~{r.conditions!.area[1]}㎡
            {r.conditions!.floors && ` · ${r.conditions!.floors}층`}{r.conditions!.years && ` · 건축 ${r.conditions!.years}년`} · {r.conditions!.names.join(", ")}
          </p>
          {r.caution && <p className="text-[11px] font-semibold text-amber-800 dark:text-amber-300">{r.caution}</p>}
          <p className="text-[11px] text-subtle">층·향·수리 상태·대지지분은 반영하지 않은 최근 거래 통계예요. 적정가격이 아닙니다.</p>
        </div>
      )}
      <div data-listing-project className="rounded-lg border border-border px-2.5 py-2 text-[11px] leading-relaxed">
        <p className="font-bold">정비사업 연결: <span className="text-amber-800 dark:text-amber-300">추가 확인 필요</span></p>
        <p className="text-muted">
          {sameDong
            ? <>같은 법정동에 <b className="text-fg">{project.name}</b>({kind.business ?? "유형 확인 필요"}{kind.plan ? ` · ${kind.plan}` : ""} · {project.stage.label})이 있어요. 구역 경계 자료가 없어 이 매물이 구역 안인지는 확정하지 않았어요.</>
            : "선택한 동은 지금 보고 있는 사업과 다른 법정동이에요. 그 동의 정비사업은 지도에서 해당 구역을 선택해 확인하세요."}
        </p>
      </div>
      <p role="note" className="rounded-lg bg-amber-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-amber-800 dark:text-amber-300">
        <Term name="권리가액" />·<Term name="추가분담금" />·조합원 자격(<Term name="입주권" />, <Term name="현금청산" />, 재당첨 제한 등)은 확인되지 않았어요. 정비사업 물건은 거래가와 별도로 조합·관할 구청에서 반드시 확인하세요.
      </p>
      {conditions.length > 0 && <DecisionBoard conditions={conditions} />}
    </section>
  );
}
