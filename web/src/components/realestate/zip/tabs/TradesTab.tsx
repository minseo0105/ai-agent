"use client";

import type { ReactNode } from "react";
import type { Connections } from "@/lib/realestate";
import FeatureStatusCard, { type StatusRow, type StatusTone } from "../FeatureStatusCard";
import type { DetailState } from "../useZoneDetail";

const MATCHING_TEXT: Record<Connections["trades"]["zone_matching"], string> = {
  BLOCKED_NO_VERIFIED_BOUNDARY: "공식 경계가 확인되지 않아 구역 안·밖 거래를 분류할 수 없음",
  NOT_IMPLEMENTED: "아직 제공하지 않음",
  AVAILABLE: "제공",
};

/** 실거래 탭. 연결 상태는 서버가 알려준 값(connections.trades)만 근거로 표시한다. */
export default function TradesTab({
  state,
  onOpenTradeSearch,
}: {
  state: DetailState;
  onOpenTradeSearch?: () => void;
}) {
  if (state.status === "idle" || state.status === "loading") {
    return <p aria-busy="true" className="rounded-xl bg-surface-muted px-3 py-3 text-xs text-muted">실거래 연결 상태를 불러오고 있어요…</p>;
  }
  if (state.status === "error") {
    return (
      <p role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-3 text-xs font-semibold text-amber-800 dark:text-amber-300">
        실거래 연결 상태를 확인하지 못했어요. {state.message}
      </p>
    );
  }
  const trades = state.data.connections.trades;
  const badge: Record<Connections["trades"]["state"], { label: string; tone: StatusTone }> = {
    NOT_CONNECTED: { label: "연결되지 않음", tone: "off" },
    REGIONAL_ONLY: { label: "구역 연동 전 · 지역 조회만 가능", tone: "partial" },
    CONNECTED: { label: "연결됨", tone: "ok" },
  };
  const rows: StatusRow[] = [
    { label: "국토교통부 실거래 API 키", value: trades.api_key_configured ? "서버에 설정됨" : "설정되지 않음", tone: trades.api_key_configured ? "ok" : "off" },
    { label: "연동된 거래 유형", value: trades.linked_types.join(", ") || "없음", tone: trades.linked_types.length ? "ok" : "off" },
    { label: "연동되지 않은 유형", value: trades.unlinked_types.join(", ") || "없음", tone: trades.unlinked_types.length ? "off" : "ok" },
    { label: "이 구역의 거래 목록", value: trades.zone_panel === "IMPLEMENTED" ? "제공" : "아직 제공하지 않음", tone: trades.zone_panel === "IMPLEMENTED" ? "ok" : "off" },
    { label: "구역 안·밖 거래 분류", value: MATCHING_TEXT[trades.zone_matching], tone: trades.zone_matching === "AVAILABLE" ? "ok" : "off" },
    { label: "거래 주소 좌표 변환", value: trades.coordinate_provider_configured ? "서버에 설정됨" : "설정되지 않음", tone: trades.coordinate_provider_configured ? "ok" : "off" },
  ];
  const notice =
    trades.state === "NOT_CONNECTED"
      ? "서버에 국토교통부 실거래 API 키가 설정되지 않아 실거래 조회가 연결되지 않았어요."
      : trades.state === "REGIONAL_ONLY"
        ? "이 구역만의 실거래 목록은 아직 제공하지 않아요. 자치구·월 단위 실거래 조회는 이용할 수 있어요."
        : undefined;
  let action: ReactNode = null;
  if (trades.state === "REGIONAL_ONLY" && onOpenTradeSearch) {
    action = (
      <button type="button" onClick={onOpenTradeSearch}
        className="min-h-10 rounded-xl bg-zip px-4 text-xs font-bold text-white transition hover:bg-zip-strong">
        실거래 조회 탭에서 자치구별로 보기
      </button>
    );
  }
  return (
    <FeatureStatusCard
      title="실거래"
      badge={badge[trades.state].label}
      badgeTone={badge[trades.state].tone}
      notice={notice}
      rows={rows}
      planned={[
        "이 구역 안·인근의 실거래 목록 (구역 내부 확인 / 구역 인근 추정 / 위치 확인 불가로 구분)",
        "계약일·거래금액·면적·층·건축연도와 위치 정확도 표시",
        "최근 거래 추이와 지도 위 실거래 가격 마커",
      ]}
      action={action}
    />
  );
}
