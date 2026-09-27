"use client";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import DevelopmentCard from "./DevelopmentCard";
import type { Trade } from "@/lib/realestate";

const PYEONG = 3.3058;

/** 카드 기본 상태에는 판단에 필요한 값만 둔다: 금액 · 단지 · 유형 · 면적 · 계약일 · 층. */
export default function TransactionCard({ trade }: { trade: Trade }) {
  const area = trade.area > 0 ? `${trade.area.toFixed(1)}㎡ (${(trade.area / PYEONG).toFixed(1)}평)` : "면적정보 없음";
  const place = [trade.region_label, trade.region].filter(Boolean).join(" ");
  const detail = trade.detail ?? {};
  const detailKeys = Object.keys(detail);
  const development = trade.development;

  return (
    <div className="rounded-2xl border border-border bg-surface p-3 shadow-sm sm:p-3.5">
      <div className="flex items-start justify-between gap-2.5">
        <div className="min-w-0">
          <div className="truncate text-[15px] font-extrabold leading-snug">{trade.name}</div>
          <p className="mt-0.5 truncate text-xs text-muted">{place || "지역 확인 필요"}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-xl font-extrabold leading-none text-estate">{trade.price_text}</div>
          <div className="mt-1 text-[11px] text-subtle">{trade.date}</div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span className="rounded-full bg-estate-soft px-2 py-0.5 text-[11px] font-bold text-estate">{trade.property_type}</span>
        <span>{area}</span>
        {trade.floor && trade.floor !== "-" && <span>{trade.floor}층</span>}
      </div>

      <CollapsibleDetails label="상세보기" count={detailKeys.length + 3}>
        <DetailRow label="상세 주소" value={[trade.road_name, trade.jibun].filter(Boolean).join(" · ") || null} />
        <DetailRow label="면적 기준" value={`${trade.area_basis ?? "면적 기준 미확인"} · ${area}`} />
        <DetailRow label="건축년도" value={trade.build_year && trade.build_year !== "-" ? `${trade.build_year}년` : null} />
        {detailKeys.map((key) => (
          <DetailRow key={key} label={key} value={detail[key]} />
        ))}
        <DetailRow label="데이터 출처" value={trade.source_label ?? "국토교통부 실거래가 공개시스템"} />
        <a href={trade.naver_url} target="_blank" rel="noopener noreferrer" className="inline-block text-xs font-bold text-estate hover:underline">
          네이버부동산 주변 매물 ↗
        </a>
      </CollapsibleDetails>

      {development && (
        <CollapsibleDetails
          label={`주변 개발정보 · ${development.label}`}
          openLabel="주변 개발정보 접기"
          count={development.projects.length || undefined}
        >
          {development.available ? (
            <div className="space-y-2">
              {development.projects.slice(0, 5).map((p) => (
                <DevelopmentCard key={p.project_id} project={p} compact />
              ))}
            </div>
          ) : (
            <p className="text-xs text-subtle">
              {development.reason_label ? `${development.reason_label} ` : ""}
              {development.notice}
            </p>
          )}
        </CollapsibleDetails>
      )}
    </div>
  );
}
