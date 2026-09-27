"use client";

import CollapsibleDetails, { DetailRow } from "./CollapsibleDetails";
import DevelopmentImpact from "./DevelopmentImpact";
import type { MapFocus } from "./ZiponMap";
import type { Trade } from "@/lib/realestate";

const PYEONG = 3.3058;

/** 기본 카드는 가격·위치·면적·개발사업 영향까지. 원문 항목은 접는다. */
export default function TransactionCard({
  trade,
  onShowMap,
}: {
  trade: Trade;
  onShowMap?: (focus: MapFocus) => void;
}) {
  const area = trade.area > 0 ? `${trade.area.toFixed(1)}㎡ (${(trade.area / PYEONG).toFixed(1)}평)` : "면적정보 없음";
  const address = [trade.region_label, trade.canonical_address ?? trade.region].filter(Boolean).join(" ");
  const detail = trade.detail ?? {};
  const raw = trade.raw_detail ?? {};
  const impact = trade.development_impact;

  return (
    <div className="rounded-2xl border border-border bg-surface p-3 sm:p-3.5">
      <div className="flex items-start justify-between gap-2.5">
        <div className="min-w-0">
          <div className="truncate text-[15px] font-extrabold leading-snug">{trade.name}</div>
          <p className="mt-0.5 break-words text-xs text-muted">{address || "지역 확인 필요"}</p>
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
        {trade.build_year && trade.build_year !== "-" && <span>{trade.build_year}년 준공</span>}
      </div>

      {impact && (
        <DevelopmentImpact
          impact={impact}
          onShowMap={
            onShowMap && trade.latitude != null && trade.longitude != null
              ? () => onShowMap({ latitude: trade.latitude as number, longitude: trade.longitude as number, label: trade.name })
              : undefined
          }
        />
      )}

      <CollapsibleDetails label="거래 원문 정보">
        <DetailRow label="도로명 주소" value={trade.address_road} />
        <DetailRow label="지번 주소" value={trade.address_jibun} />
        <DetailRow label="면적 기준" value={`${trade.area_basis ?? "면적 기준 미확인"} · ${area}`} />
        {Object.keys(detail).map((key) => (
          <DetailRow key={key} label={key} value={detail[key]} />
        ))}
        {Object.keys(raw).map((key) => (
          <DetailRow key={key} label={key} value={raw[key]} />
        ))}
        <DetailRow label="데이터 출처" value={trade.source_label ?? "국토교통부 실거래가 공개시스템"} />
        <a href={trade.naver_url} target="_blank" rel="noopener noreferrer" className="inline-block text-xs font-bold text-estate hover:underline">
          네이버부동산 주변 매물 ↗
        </a>
      </CollapsibleDetails>
    </div>
  );
}
