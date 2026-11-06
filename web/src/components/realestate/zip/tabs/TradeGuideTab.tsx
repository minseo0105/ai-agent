"use client";

import type { DevelopmentProject, ProcessTimeline } from "@/lib/realestate";
import FeatureStatusCard from "../FeatureStatusCard";
import type { DetailState } from "../useZoneDetail";

/**
 * 거래가이드 탭. 단계별 거래·권리 확인 질문(일반 안내)만 제공한다.
 * 거래 가능 여부와 조합원 지위 취득 가능 여부를 판정하는 사전진단 엔진은 연결되어 있지 않으며,
 * 그 상태는 서버가 알려준 connections.rights_engine 값을 따른다.
 */
export default function TradeGuideTab({
  project,
  timeline,
  state,
}: {
  project: DevelopmentProject;
  timeline: ProcessTimeline | null;
  state: DetailState;
}) {
  const steps = timeline?.verified ? timeline.steps : [];
  const engine = state.status === "ready" ? state.data.connections.rights_engine.state : null;
  return (
    <div className="space-y-3">
      <section aria-label="단계별 거래·권리 확인 질문">
        <h3 className="text-[11px] font-extrabold tracking-wide text-muted">단계별 거래·권리 확인 질문</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          각 단계에서 일반적으로 확인하는 질문이에요. 이 사업에서 확인된 사실이 아니며 법적 거래 가능 여부를 판정하지 않습니다.
        </p>
        {steps.length > 0 ? (
          <ol className="mt-2 space-y-1.5">
            {steps.map((step) => (
              <li key={step.key}>
                <details open={step.status === "CURRENT"} className="rounded-lg border border-border px-2.5 py-1.5">
                  <summary className="cursor-pointer text-xs font-bold">
                    {step.order}. {step.label}
                    {step.status === "CURRENT" && <span className="ml-1.5 rounded-full bg-zip-soft px-1.5 py-0.5 text-[10px] text-zip">현재</span>}
                  </summary>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-muted">
                    {step.questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ol>
        ) : (
          <div className="mt-2 rounded-lg border border-border px-2.5 py-2">
            <p className="text-xs font-bold">{project.stage.label}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">
              {(project.stage_guide?.checks ?? ["공식 사업정보를 먼저 확인"]).map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-subtle">공식 상세 단계가 확인되면 8단계별 질문을 보여 드려요.</p>
          </div>
        )}
      </section>

      <FeatureStatusCard
        title="거래·권리 사전진단"
        badge={engine === "CONNECTED" ? "연결됨" : "연결되지 않음"}
        badgeTone={engine === "CONNECTED" ? "ok" : "off"}
        notice="지금은 거래 가능 여부나 조합원 지위 취득 가능 여부를 판정하지 않아요. 정보가 부족한 경우에도 '거래 가능'이나 '안전한 매물'이라고 표시하지 않습니다."
        rows={[
          { label: "규칙 기반 판정 엔진", value: engine === "CONNECTED" ? "연결됨" : "연결되지 않음", tone: engine === "CONNECTED" ? "ok" : "off" },
          { label: "현행 법령·시행일 데이터", value: "연결되지 않음", tone: "off" },
          { label: "규제지역·토지거래허가구역 데이터", value: "연결되지 않음", tone: "off" },
          { label: "지금 제공하는 것", value: "단계별 확인 질문(일반 안내)", tone: "ok" },
        ]}
        planned={[
          "매매계약 가능 여부와 조합원 지위·분양대상자 지위 취득 가능 여부를 구분한 사전진단",
          "판단 근거·적용 법령·기준일·추가로 확인할 정보 표시",
          "결과 3단계: 검토 결과 제한사항 미확인 / 추가 확인 필요 / 법적 제한 또는 위험요소 확인",
          "검증된 규칙 기반 판정과 AI 설명 계층을 분리(법률 판단을 AI 생성 답변에만 의존하지 않음)",
        ]}
      />
      <p className="text-[11px] leading-relaxed text-subtle">
        최종 법적 권리 확인은 관할 행정기관, 조합, 전문가의 검증이 필요합니다.
      </p>
    </div>
  );
}
