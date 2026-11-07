"use client";

import { useMemo, useState } from "react";
import { inputClass } from "@/components/golf/ui";
import { compareListing, dongReview, failedTypes, type ProjectLite } from "@/lib/budgetReview";
import { formatManwon } from "@/lib/investmentCalc";
import type { DevelopmentProject } from "@/lib/realestate";
import { STATUS_TEXT, classify, partialFailureText, periodText } from "@/lib/zoneTrades";
import { parseNumberInput } from "@/lib/zipFormat";
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

/** 같은 자치구에서 정비사업이 있는 법정동별 최근 거래·예산 이하 거래 수·사업 단계와 위험. */
export function RegionReview({ project, projects, trades, apiKeyConfigured, ceiling }: {
  project: DevelopmentProject; projects: ProjectLite[]; trades: DistrictTrades; apiKeyConfigured: boolean; ceiling: number | null;
}) {
  const rows = useMemo(() => dongReview(trades.rows, projects, ceiling), [trades.rows, projects, ceiling]);
  const guide = project.investor_guide;
  const failed = [...failedTypes(trades.errors).keys()];
  return (
    <section data-region-review aria-label="지역별 매수 검토" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">지역별 매수 검토 · {project.district} <span className="font-semibold text-subtle">동일 법정동 참고 실거래</span></h3>
      <p className="text-[11px] text-subtle">{periodText(trades.months)} · {SCOPE_NOTE} {ceiling === null ? "예산(보유 현금)을 입력하면 예산 이하 거래 수를 보여 줘요." : `예산 기준 최대 매입가격 ${formatManwon(ceiling)} 이하 거래를 셉니다.`}</p>
      <TradeStatus t={trades} apiKeyConfigured={apiKeyConfigured} />
      {!trades.loading && trades.rows.length > 0 && rows.length > 0 && (
        <div className="max-h-72 overflow-auto rounded-lg border border-border">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-surface-muted text-subtle">
              <tr><th className="px-2 py-1">법정동</th><th className="px-2 py-1">정비사업 (단계 · 위험)</th><th className="px-2 py-1 text-right">거래</th><th className="px-2 py-1 text-right">중위가</th><th className="px-2 py-1 text-right">예산 이하</th></tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.dong} className={`border-t border-border/60 align-top ${d.dong === project.dong ? "bg-zip/5" : ""}`}>
                  <td className="whitespace-nowrap px-2 py-1 font-bold">{d.dong}</td>
                  <td className="px-2 py-1 text-muted">
                    {d.projects.slice(0, 3).map((p) => <div key={p.name} className="line-clamp-2">{p.name} · {p.stage}{p.risk ? ` · ${p.risk}` : ""}</div>)}
                    {d.projects.length > 3 && <div>외 {d.projects.length - 3}건</div>}
                  </td>
                  <td className="px-2 py-1 text-right">{d.trades === 0 ? (failed.length ? "0 (조회된 유형 기준)" : "0") : d.trades}{d.types.length > 0 && <div className="text-subtle">{d.types.join("·")}</div>}</td>
                  <td className="whitespace-nowrap px-2 py-1 text-right">{eok(d.median)}</td>
                  <td className="px-2 py-1 text-right font-bold">{d.withinBudget === null ? "—" : d.withinBudget}</td>
                </tr>
              ))}
            </tbody>
          </table>
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

/** 관심 물건 비교: 같은 동·유형·비슷한 면적의 최근 실거래가 충분할 때만 가격 범위를 낸다. */
export function ListingCompare({ project, trades }: { project: DevelopmentProject; trades: DistrictTrades }) {
  const dongs = useMemo(() => [...new Set([project.dong, ...trades.rows.map((r) => r.region)].filter((d): d is string => !!d))].sort(), [project.dong, trades.rows]);
  const [f, setF] = useState({ dong: project.dong ?? "", type: "아파트", area: "", ask: "", complex: "", address: "", year: "" });
  const area = parseNumberInput(f.area);
  const ask = parseNumberInput(f.ask);
  const buildYear = parseNumberInput(f.year);
  const r = useMemo(() => compareListing(trades.rows, { dong: f.dong, type: f.type, area, ask, complex: f.complex, buildYear }), [trades.rows, f.dong, f.type, area, ask, f.complex, buildYear]);
  // 403·조회 실패 유형은 '거래 0건'이 아니라 '데이터 없음'이다.
  const blocked = failedTypes(trades.errors).get(f.type);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((v) => ({ ...v, [k]: e.target.value }));
  return (
    <section data-listing-compare aria-label="관심 물건 비교" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">관심 물건 비교 <span className="font-semibold text-subtle">최근 3개월 동일 법정동 실거래 기준</span></h3>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <label className="col-span-2 block"><span className="mb-0.5 block font-bold">주소 (메모)</span><input value={f.address} onChange={set("address")} placeholder="예: 문정동 ○○번지" className={`${inputClass} w-full`} /></label>
        <label className="block"><span className="mb-0.5 block font-bold">법정동</span>
          <select value={f.dong} onChange={set("dong")} className={`${inputClass} w-full`}>{dongs.map((d) => <option key={d}>{d}</option>)}</select></label>
        <label className="block"><span className="mb-0.5 block font-bold">유형</span>
          <select value={f.type} onChange={set("type")} className={`${inputClass} w-full`}>{TRADE_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <label className="block"><span className="mb-0.5 block font-bold">면적 (㎡)</span><input inputMode="decimal" value={f.area} onChange={set("area")} placeholder={f.type === "단독·다가구" ? "연면적" : "전용면적"} className={`${inputClass} w-full`} /></label>
        <label className="block"><span className="mb-0.5 block font-bold">매도가 (만원)</span><input inputMode="decimal" value={f.ask} onChange={set("ask")} placeholder="입력" className={`${inputClass} w-full`} /></label>
        <label className="block"><span className="mb-0.5 block font-bold">단지·건물명 (선택)</span><input value={f.complex} onChange={set("complex")} placeholder="같은 단지 우선" className={`${inputClass} w-full`} /></label>
        <label className="block"><span className="mb-0.5 block font-bold">건축연도 (선택)</span><input inputMode="numeric" value={f.year} onChange={set("year")} placeholder="±5년 우선" className={`${inputClass} w-full`} /></label>
      </div>
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
      <p role="note" className="rounded-lg bg-amber-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-amber-800 dark:text-amber-300">
        권리가액·추가분담금·조합원 자격(입주권 승계, 재당첨 제한 등)은 확인되지 않았어요. 정비사업 물건은 거래가와 별도로 조합·관할 구청에서 반드시 확인하세요.
      </p>
    </section>
  );
}
