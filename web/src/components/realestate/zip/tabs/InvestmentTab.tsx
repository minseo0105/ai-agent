"use client";

import InvestmentSimulator from "../InvestmentSimulator";

export default function InvestmentTab({ projectId }: { projectId: string }) {
  return <InvestmentSimulator projectId={projectId} />;
}
