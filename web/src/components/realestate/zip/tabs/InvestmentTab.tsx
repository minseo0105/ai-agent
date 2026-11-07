"use client";

import { useMemo, useState } from "react";
import type { DevelopmentProject } from "@/lib/realestate";
import { ListingCompare, RegionReview } from "../BuyReview";
import InvestmentSimulator from "../InvestmentSimulator";
import { useDistrictTrades } from "../useDistrictTrades";
import type { DetailState } from "../useZoneDetail";

export default function InvestmentTab({ projectId, project, state, allProjects = [] }: {
  projectId: string; project?: DevelopmentProject | null; state?: DetailState; allProjects?: DevelopmentProject[];
}) {
  const [ceiling, setCeiling] = useState<number | null>(null);
  const apiKeyConfigured = state?.status === "ready" ? state.data.connections.trades.api_key_configured : false;
  // 실거래 탭과 같은 자치구 3개월 조회를 공유한다(추가 호출 없음).
  const trades = useDistrictTrades(project?.district, apiKeyConfigured);
  const districtProjects = useMemo(
    () => (project ? allProjects.filter((p) => p.district === project.district) : []),
    [allProjects, project],
  );
  return (
    <div className="space-y-3">
      <InvestmentSimulator projectId={projectId} onCeiling={setCeiling} />
      {project && (
        <>
          <RegionReview project={project} projects={districtProjects.length ? districtProjects : [project]} trades={trades} apiKeyConfigured={apiKeyConfigured} ceiling={ceiling} />
          <ListingCompare key={project.project_id} project={project} trades={trades} />
        </>
      )}
    </div>
  );
}
