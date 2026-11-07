"use client";

import { useState, type ReactNode } from "react";
import { areaGroups, rebuildView, type Complex, type TradeRowLike } from "@/lib/complexMatch";
import { STATUS_TEXT, type ZoneTradeStatus } from "@/lib/zoneTrades";

const eok = (v: number | null) => (v === null ? "—" : `${v.toFixed(2)}억`);

function ComplexDetail({ complex }: { complex: Complex }) {
  const groups = areaGroups(complex.rows);
  const rows = [...complex.rows].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <div data-complex={complex.aptSeq ?? complex.key} className="space-y-2">
      <p className="text-[11px] text-subtle">
        확인 근거: 단지명·지번(본번 {complex.bonbun ?? "?"}) 일치{complex.aptSeq ? ` · 국토부 단지번호 ${complex.aptSeq}` : ""}{complex.buildYear ? ` · ${complex.buildYear}년 준공` : ""}
      </p>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table data-area-groups className="w-full text-left text-[11px]">
          <thead className="bg-surface-muted text-subtle"><tr><th className="px-2 py-1">전용면적(㎡)</th><th className="px-2 py-1 text-right">건수</th><th className="px-2 py-1 text-right">중위가</th><th className="px-2 py-1 text-right">최저~최고</th><th className="px-2 py-1 text-right">최근 거래</th></tr></thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.label} className="border-t border-border/60">
                <td className="px-2 py-1 font-bold">{g.label}</td>
                <td className="px-2 py-1 text-right">{g.count}</td>
                <td className="px-2 py-1 text-right">{eok(g.median)}{g.count < 3 && <span className="block text-[10px] text-subtle">표본 부족</span>}</td>
                <td className="whitespace-nowrap px-2 py-1 text-right">{eok(g.low)}~{eok(g.high)}</td>
                <td className="whitespace-nowrap px-2 py-1 text-right">{g.latest.price_text} · {g.latest.date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-subtle">면적이 0.5㎡ 넘게 다르면 합치지 않아요. 계약 해제 거래는 뺐어요(정정 여부는 국토부 자료에 표시되지 않아요).</p>
      <div className="max-h-64 overflow-auto rounded-lg border border-border">
        <table data-complex-trades className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface-muted text-[11px] text-subtle"><tr><th className="px-2 py-1.5">계약일</th><th className="px-2 py-1.5">거래금액</th><th className="px-2 py-1.5">전용면적</th><th className="px-2 py-1.5">층</th></tr></thead>
          <tbody>
            {rows.map((r: TradeRowLike, i) => (
              <tr key={`${r.date}-${i}`} className="border-t border-border/60">
                <td className="whitespace-nowrap px-2 py-1.5">{r.date}</td>
                <td className="whitespace-nowrap px-2 py-1.5 font-bold">{r.price_text}</td>
                <td className="whitespace-nowrap px-2 py-1.5">{r.area}㎡</td>
                <td className="px-2 py-1.5">{r.floor ? `${r.floor}층` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * 재건축 사업: 단지명·지번이 함께 일치하는 단지의 거래만 이 사업의 실거래로 보여 준다.
 * 확정되지 않으면 '해당 단지 실거래가 확인 필요'만 표시하고, 같은 동 다른 거래는 '주변 비교 시세'로 분리한다.
 */
export default function ComplexTrades({ project, status, errors, rows, renderNearby }: {
  project: { name: string; address?: string | null };
  status: ZoneTradeStatus;
  errors: string[];
  rows: TradeRowLike[];
  renderNearby: (rows: TradeRowLike[]) => ReactNode;
}) {
  const view = rebuildView(status, errors, project, rows);
  const [pick, setPick] = useState(0);
  if (view.kind === "API_ERROR") {
    return (
      <p role="status" data-complex-status="API_ERROR" className="rounded-xl border border-border px-3 py-2.5 text-xs font-semibold text-muted">
        {view.status === "APT_FAILED" ? "아파트 실거래 조회에 실패해 해당 단지 거래를 확인할 수 없어요. 잠시 후 다시 시도해 주세요." : STATUS_TEXT[view.status as ZoneTradeStatus] ?? "실거래를 조회하지 못했어요."}
      </p>
    );
  }
  const { match } = view;
  const chosen = match.confirmed[Math.min(pick, match.confirmed.length - 1)];
  return (
    <div className="space-y-3">
      <section data-complex-status={match.status} aria-label="해당 단지 실거래" className="space-y-2">
        <h3 className="text-sm font-extrabold">해당 단지 실거래{chosen ? ` · ${chosen.name}` : ""}</h3>
        {chosen ? (
          <>
            {match.confirmed.length > 1 && (
              <div role="group" aria-label="단지 선택" className="flex flex-wrap gap-1.5">
                {match.confirmed.map((c, i) => (
                  <button key={c.key} type="button" aria-pressed={i === pick} onClick={() => setPick(i)}
                    className={`min-h-8 rounded-full px-2.5 text-[11px] font-bold ${i === pick ? "bg-zip text-white" : "border border-border text-muted"}`}>{c.name}</button>
                ))}
              </div>
            )}
            <ComplexDetail complex={chosen} />
          </>
        ) : (
          <div role="status" className="rounded-lg bg-amber-500/10 px-2.5 py-2 text-xs text-amber-800 dark:text-amber-300">
            <p className="font-bold">해당 단지 실거래가 확인 필요</p>
            <p className="mt-0.5">{match.reason} 다른 단지 거래를 이 사업의 시세로 보여 주지 않아요.</p>
            {match.candidates.length > 0 && (
              <ul data-candidates className="mt-1 list-disc pl-4 text-[11px]">
                {match.candidates.map((c) => <li key={c.complex.key}>{c.complex.name} — {c.reasons.join(", ")} (확정 아님)</li>)}
              </ul>
            )}
          </div>
        )}
      </section>
      <details data-nearby className="rounded-xl border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-bold">주변 비교 시세 · 같은 법정동 다른 거래 {match.others.length}건</summary>
        <div className="mt-2">{renderNearby(match.others)}</div>
      </details>
    </div>
  );
}
