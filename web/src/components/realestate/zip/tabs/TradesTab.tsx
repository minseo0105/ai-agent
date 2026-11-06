"use client";

import { useEffect, useState, type ReactNode } from "react";
import { estateApi, type Connections, type DevelopmentProject } from "@/lib/realestate";
import { STATUS_TEXT, classify, periodText, recentMonths, regionLabel, sameDong, withoutCancelled, type ZoneTradeRow, type ZoneTradeStatus } from "@/lib/zoneTrades";
import FeatureStatusCard, { type StatusRow, type StatusTone } from "../FeatureStatusCard";
import type { DetailState } from "../useZoneDetail";

const MATCHING_TEXT: Record<Connections["trades"]["zone_matching"], string> = {
  BLOCKED_NO_VERIFIED_BOUNDARY: "공식 경계가 확인되지 않아 구역 안·밖 거래를 분류할 수 없음",
  NOT_IMPLEMENTED: "아직 제공하지 않음",
  AVAILABLE: "제공",
};

/** 실거래 탭. 연결 상태는 서버가 알려준 값(connections.trades)만 근거로 표시한다. */
const TYPES = ["아파트", "연립·다세대", "단독·다가구", "오피스텔"];
const SHOW_LIMIT = 30;

/** 네이버부동산 연결(기존 링크 그대로). 호가·시세는 사용자가 직접 확인한다. 집은 매물정보를 수집·표시하지 않는다. */
function NaverFallback({ project, primary }: { project?: DevelopmentProject; primary: boolean }) {
  const naver = project?.naver_real_estate;
  return (
    <section aria-label="네이버부동산에서 직접 확인" className={`rounded-xl border px-3 py-2.5 ${primary ? "border-zip/40 bg-zip-soft/40" : "border-border"}`}>
      <p className="text-xs leading-relaxed text-muted">
        매물 호가와 시세는 네이버부동산에서 직접 확인해 주세요. 집은 네이버부동산 매물정보를 수집하지 않으며 실거래가로 표시하지 않습니다.
      </p>
      {naver ? (
        <a href={naver.url} target="_blank" rel="noopener noreferrer" title={naver.note}
          className="mt-2 inline-flex min-h-10 items-center rounded-xl border border-border bg-surface px-3 text-xs font-bold text-zip hover:border-zip">
          {naver.label} ↗
        </a>
      ) : (
        <p className="mt-1 text-[11px] text-subtle">이 사업은 대표 좌표가 없어 네이버부동산 위치 연결을 제공하지 않아요.</p>
      )}
    </section>
  );
}

/** 국토부 실거래 중 이 사업과 같은 법정동의 최근 거래. 구역 안 여부는 판단하지 않는다. */
function RecentTrades({ project, apiKeyConfigured }: { project: DevelopmentProject; apiKeyConfigured: boolean }) {
  const region = regionLabel(project.district);
  const [months] = useState(() => recentMonths(new Date()));
  const [result, setResult] = useState<{ status: ZoneTradeStatus | "LOADING"; rows: ZoneTradeRow[] }>({ status: "LOADING", rows: [] });
  useEffect(() => {
    let alive = true;
    if (!apiKeyConfigured || !region) {
      setResult({ status: apiKeyConfigured ? "FAILED" : "NOT_CONNECTED", rows: [] });
      return;
    }
    setResult({ status: "LOADING", rows: [] });
    (async () => {
      const rows: ZoneTradeRow[] = [];
      const errors: string[] = [];
      for (const month of months) {
        try {
          const res = await estateApi.trades({ regions: [region], property_types: TYPES, month });
          rows.push(...res.items);
          errors.push(...res.errors);
        } catch (e) {
          errors.push((e as Error).message);
        }
      }
      if (!alive) return;
      const local = withoutCancelled(sameDong(rows, project.dong)).sort((a, b) => b.date.localeCompare(a.date));
      setResult({ status: classify({ apiKeyConfigured, rows: local, errors }), rows: local });
    })();
    return () => {
      alive = false;
    };
  }, [apiKeyConfigured, region, project.dong, months]);

  const scope = [project.district, project.dong].filter(Boolean).join(" ");
  if (result.status === "LOADING") {
    return <p aria-busy="true" className="rounded-xl bg-surface-muted px-3 py-3 text-xs text-muted">{scope} 동일 법정동 참고 실거래를 불러오고 있어요…</p>;
  }
  if (result.status !== "OK") {
    return (
      <>
        <p role="status" className="rounded-xl border border-border px-3 py-2.5 text-xs font-semibold text-muted">
          {region ? STATUS_TEXT[result.status] : "자치구 정보가 없어 실거래를 조회하지 않았어요."}
        </p>
        <NaverFallback project={project} primary />
      </>
    );
  }
  return (
    <section aria-label="동일 법정동 참고 실거래">
      <h3 className="text-sm font-extrabold">동일 법정동 참고 실거래 · {scope}</h3>
      <p className="mt-0.5 text-[11px] text-subtle">
        국토교통부 실거래가, {periodText(months)}, 계약 해제 건 제외. 이 사업구역 안의 거래가 아니라 같은 법정동 전체의 참고 거래입니다.
      </p>
      <div className="mt-2 max-h-80 overflow-auto rounded-xl border border-border">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface-muted text-[11px] text-subtle">
            <tr><th className="px-2 py-1.5">계약일</th><th className="px-2 py-1.5">거래금액</th><th className="px-2 py-1.5">면적</th><th className="px-2 py-1.5">유형·이름</th></tr>
          </thead>
          <tbody>
            {result.rows.slice(0, SHOW_LIMIT).map((r, i) => (
              <tr key={`${r.date}-${r.name}-${i}`} className="border-t border-border/60">
                <td className="whitespace-nowrap px-2 py-1.5">{r.date}</td>
                <td className="whitespace-nowrap px-2 py-1.5 font-bold">{r.price_text}</td>
                <td className="whitespace-nowrap px-2 py-1.5">{r.area}㎡{r.area_basis ? ` (${r.area_basis})` : ""}</td>
                <td className="px-2 py-1.5 text-muted">{r.property_type} · {r.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.rows.length > SHOW_LIMIT && <p className="mt-1 text-[11px] text-subtle">최근 {SHOW_LIMIT}건만 표시했어요(전체 {result.rows.length}건).</p>}
      <div className="mt-2"><NaverFallback project={project} primary={false} /></div>
    </section>
  );
}

export default function TradesTab({
  state,
  project,
  onOpenTradeSearch,
}: {
  state: DetailState;
  project?: DevelopmentProject;
  onOpenTradeSearch?: () => void;
}) {
  if (state.status === "idle" || state.status === "loading") {
    return <p aria-busy="true" className="rounded-xl bg-surface-muted px-3 py-3 text-xs text-muted">실거래 연결 상태를 불러오고 있어요…</p>;
  }
  if (state.status === "error") {
    return (
      <div className="space-y-3">
        <p role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-3 text-xs font-semibold text-amber-800 dark:text-amber-300">
          실거래 연결 상태를 확인하지 못했어요. {state.message}
        </p>
        <NaverFallback project={project} primary />
      </div>
    );
  }
  const trades = state.data.connections.trades;
  const badge: Record<Connections["trades"]["state"], { label: string; tone: StatusTone }> = {
    NOT_CONNECTED: { label: "미연동 · 연결되지 않음", tone: "off" },
    REGIONAL_ONLY: { label: "이 구역 실거래 미연동 · 자치구 조회만 가능", tone: "partial" },
    CONNECTED: { label: "연결됨", tone: "ok" },
  };
  const rows: StatusRow[] = [
    { label: "국토교통부 실거래 API 키", value: trades.api_key_configured ? "서버에 설정됨" : "설정되지 않음", tone: trades.api_key_configured ? "ok" : "off" },
    { label: "연동된 거래 유형", value: trades.linked_types.join(", ") || "없음", tone: trades.linked_types.length ? "ok" : "off" },
    { label: "연동되지 않은 유형", value: trades.unlinked_types.join(", ") || "없음", tone: trades.unlinked_types.length ? "off" : "ok" },
    { label: "사업구역 단위 거래 목록", value: trades.zone_panel === "IMPLEMENTED" ? "제공" : "아직 제공하지 않음", tone: trades.zone_panel === "IMPLEMENTED" ? "ok" : "off" },
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
    <div className="space-y-3">
    {project ? <RecentTrades project={project} apiKeyConfigured={trades.api_key_configured} /> : <NaverFallback project={project} primary />}
    <FeatureStatusCard
      title="실거래"
      badge={badge[trades.state].label}
      badgeTone={badge[trades.state].tone}
      notice={notice}
      rows={rows}
      planned={[
        "사업 대표 위치 기준 반경 내 참고 거래(인근 추정 / 위치 확인 불가로 구분, 구역 내부 판정 아님)",
        "계약일·거래금액·면적·층·건축연도와 위치 정확도 표시",
        "최근 거래 추이와 지도 위 실거래 가격 마커",
      ]}
      action={action}
    />
    </div>
  );
}
