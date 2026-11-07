"use client";

import { useMemo, useState } from "react";
import { priceCeiling } from "@/lib/investDecision";
import type { DevelopmentProject } from "@/lib/realestate";
import { ListingCompare, RegionReview } from "../BuyReview";
import InvestmentSimulator from "../InvestmentSimulator";
import MoneyForm, { LoanPanel, useMoney } from "../MoneyForm";
import { useDistrictTrades } from "../useDistrictTrades";
import type { DetailState } from "../useZoneDetail";

type Mode = "region" | "listing";
const MODES: { id: Mode; title: string; desc: string }[] = [
  { id: "region", title: "내 예산으로 투자 가능 지역 찾기", desc: "내 자금으로 가격대가 맞을 수 있는 정비사업 동을 과거 실거래로 찾아요" },
  { id: "listing", title: "관심 매물 분석하기", desc: "네이버 부동산 등에서 본 매물을 직접 입력해 가격·자금·권리 위험을 점검해요" },
];

export default function InvestmentTab({ projectId, project, state, allProjects = [] }: {
  projectId: string; project?: DevelopmentProject | null; state?: DetailState; allProjects?: DevelopmentProject[];
}) {
  const [mode, setMode] = useState<Mode | null>(null);
  const money = useMoney();
  const apiKeyConfigured = state?.status === "ready" ? state.data.connections.trades.api_key_configured : false;
  const [district, setDistrict] = useState<string | null>(null);
  const regionDistrict = district ?? project?.district ?? null;
  // 실거래 탭과 같은 자치구 3개월 조회를 공유한다(같은 자치구면 추가 호출 없음). 다른 자치구는 선택했을 때만 조회한다.
  const homeTrades = useDistrictTrades(project?.district, apiKeyConfigured && mode === "listing");
  const regionTrades = useDistrictTrades(regionDistrict, apiKeyConfigured && mode === "region");
  const districts = useMemo(() => [...new Set(allProjects.map((p) => p.district).filter((d): d is string => !!d))].sort(), [allProjects]);
  const districtProjects = useMemo(() => allProjects.filter((p) => p.district === regionDistrict), [allProjects, regionDistrict]);
  const ceiling = priceCeiling(money.money, money.money.loan ?? 0).value;

  return (
    <div className="space-y-3">
      <div role="group" aria-label="분석 방식 선택" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {MODES.map((m) => (
          <button key={m.id} type="button" aria-pressed={mode === m.id} data-mode={m.id} onClick={() => setMode(m.id)}
            className={`rounded-xl border px-3 py-2.5 text-left transition ${mode === m.id ? "border-zip bg-zip/5" : "border-border hover:border-zip/50"}`}>
            <span className="block text-sm font-extrabold">{m.title}</span>
            <span className="mt-0.5 block text-[11px] text-muted">{m.desc}</span>
          </button>
        ))}
      </div>

      {mode && project && (
        <>
          <MoneyForm state={money} />
          <details className="rounded-xl border border-border px-3 py-2">
            <summary className="cursor-pointer text-xs font-bold">대출 시나리오 비교</summary>
            <div className="mt-2"><LoanPanel money={money.money} /></div>
          </details>
          {mode === "region" ? (
            <RegionReview project={project} projects={districtProjects.length ? districtProjects : [project]} trades={regionTrades}
              apiKeyConfigured={apiKeyConfigured} ceiling={ceiling} district={regionDistrict} districts={districts} onDistrict={setDistrict} />
          ) : (
            <ListingCompare key={project.project_id} project={project} trades={homeTrades} money={money.money} />
          )}
        </>
      )}

      <details data-detailed-analysis className="rounded-xl border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-bold">상세 분석 · 추가분담금·투자금·수익 계산식</summary>
        <div className="mt-2"><InvestmentSimulator projectId={projectId} /></div>
      </details>
    </div>
  );
}
