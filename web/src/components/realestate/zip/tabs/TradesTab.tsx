"use client";

import { useEffect, useState, type ReactNode } from "react";
import { estateApi, type Connections, type DevelopmentProject } from "@/lib/realestate";
import { STATUS_TEXT, classify, partialFailureText, periodText, recentMonths, regionLabel, sameDong, withoutCancelled, type ZoneTradeRow, type ZoneTradeStatus } from "@/lib/zoneTrades";
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

/**
 * 네이버부동산 연결 버튼. 실거래 조회 결과와 무관하게 실거래 탭 상단에 한 번만 고정 표시한다.
 * URL은 서버의 기존 naver_real_estate(사업 대표좌표 기반)를 그대로 쓴다. 좌표가 없으면 비활성.
 * 네이버 매물 호가·시세는 국토부 실거래가와 다르며, 집은 네이버 매물정보를 수집·표시하지 않는다.
 */
export function NaverListingButton({ project }: { project?: DevelopmentProject }) {
  const naver = project?.naver_real_estate;
  const cls = "inline-flex min-h-10 items-center rounded-xl px-3 text-xs font-bold";
  return (
    <section aria-label="네이버부동산 매물·시세 확인" className="sticky top-0 z-10 rounded-xl border border-border bg-surface px-3 py-2.5">
      {naver ? (
        <a href={naver.url} target="_blank" rel="noopener noreferrer" title={naver.note} data-naver-link
          className={`${cls} bg-zip text-white transition hover:bg-zip-strong`}>
          네이버부동산에서 매물·시세 확인 ↗
        </a>
      ) : (
        <>
          <button type="button" disabled aria-disabled="true" data-naver-link
            className={`${cls} cursor-not-allowed border border-border bg-surface-muted text-subtle`}>
            네이버부동산에서 매물·시세 확인
          </button>
          <p className="mt-1 text-[11px] text-subtle">위치정보가 없어 연결할 수 없습니다.</p>
        </>
      )}
      <p className="mt-1.5 text-[11px] leading-relaxed text-subtle">
        네이버부동산의 매물 호가·시세는 외부 사이트 정보이며, 아래 국토교통부 실거래가(신고된 계약 금액)와 다릅니다.
      </p>
    </section>
  );
}

/** 국토부 실거래 중 이 사업과 같은 법정동의 최근 거래. 구역 안 여부는 판단하지 않는다. */
function RecentTrades({ project, apiKeyConfigured }: { project: DevelopmentProject; apiKeyConfigured: boolean }) {
  const region = regionLabel(project.district);
  const [months] = useState(() => recentMonths(new Date()));
  const [result, setResult] = useState<{ status: ZoneTradeStatus | "LOADING"; rows: ZoneTradeRow[]; errors?: string[] }>({ status: "LOADING", rows: [] });
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
      // 3개월을 동시에 요청한다(서버가 유형별 호출을 제한적으로 병렬 처리하고 결과를 30분 캐시한다).
      const settled = await Promise.allSettled(
        months.map((month) => estateApi.trades({ regions: [region], property_types: TYPES, month })),
      );
      for (const r of settled) {
        if (r.status === "fulfilled") {
          rows.push(...r.value.items);
          errors.push(...r.value.errors);
        } else {
          errors.push((r.reason as Error)?.message ?? String(r.reason));
        }
      }
      if (!alive) return;
      const local = withoutCancelled(sameDong(rows, project.dong)).sort((a, b) => b.date.localeCompare(a.date));
      setResult({ status: classify({ apiKeyConfigured, rows: local, errors }), rows: local, errors });
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
      <p role="status" className="rounded-xl border border-border px-3 py-2.5 text-xs font-semibold text-muted">
        {region ? STATUS_TEXT[result.status] : "자치구 정보가 없어 실거래를 조회하지 않았어요."}
      </p>
    );
  }
  return (
    <section aria-label="동일 법정동 참고 실거래">
      <h3 className="text-sm font-extrabold">동일 법정동 참고 실거래 · {scope}</h3>
      <p className="mt-0.5 text-[11px] text-subtle">
        국토교통부 실거래가, {periodText(months)}, 계약 해제 건 제외. 이 사업구역 안의 거래가 아니라 같은 법정동 전체의 참고 거래입니다.
      </p>
      {partialFailureText(result.errors ?? []) && (
        <p role="status" data-partial-failure className="mt-1.5 rounded-lg bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-300">
          {partialFailureText(result.errors ?? [])}
        </p>
      )}
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
    </section>
  );
}

function TradesBody({
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
    {project && <RecentTrades project={project} apiKeyConfigured={trades.api_key_configured} />}
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

export default function TradesTab(props: { state: DetailState; project?: DevelopmentProject; onOpenTradeSearch?: () => void }) {
  return (
    <div className="space-y-3">
      <NaverListingButton project={props.project} />
      <TradesBody {...props} />
    </div>
  );
}
