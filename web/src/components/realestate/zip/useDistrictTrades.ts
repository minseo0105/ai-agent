"use client";

import { useEffect, useState } from "react";
import { estateApi } from "@/lib/realestate";
import { recentMonths, regionLabel, withoutCancelled, type ZoneTradeRow } from "@/lib/zoneTrades";

export const TRADE_TYPES = ["아파트", "연립·다세대", "단독·다가구", "오피스텔"];
export type DistrictTrades = { loading: boolean; region: string | null; rows: ZoneTradeRow[]; errors: string[]; months: string[] };

// 실거래 탭과 투자분석 탭이 같은 자치구 3개월 조회를 공유한다(탭 전환 시 재호출하지 않음, 10분).
const TTL = 10 * 60 * 1000;
const memo = new Map<string, { at: number; p: Promise<{ rows: ZoneTradeRow[]; errors: string[] }> }>();

function load(region: string, months: string[]) {
  const key = `${region}|${months.join(",")}`;
  const hit = memo.get(key);
  if (hit && Date.now() - hit.at < TTL) return hit.p;
  const p = (async () => {
    const rows: ZoneTradeRow[] = [];
    const errors: string[] = [];
    // 3개월을 동시에 요청한다(서버가 유형별 호출을 제한적으로 병렬 처리하고 결과를 30분 캐시한다).
    const settled = await Promise.allSettled(months.map((month) => estateApi.trades({ regions: [region], property_types: TRADE_TYPES, month })));
    for (const r of settled) {
      if (r.status === "fulfilled") {
        rows.push(...r.value.items);
        errors.push(...r.value.errors);
      } else {
        errors.push((r.reason as Error)?.message ?? String(r.reason));
      }
    }
    return { rows: withoutCancelled(rows).sort((a, b) => b.date.localeCompare(a.date)), errors };
  })();
  memo.set(key, { at: Date.now(), p });
  p.then((v) => { if (!v.rows.length && v.errors.length) memo.delete(key); }, () => memo.delete(key));
  return p;
}

/** 사업이 속한 자치구의 최근 3개월 실거래(계약 해제 제외, 최신순). 키가 없거나 자치구를 모르면 호출하지 않는다. */
export function useDistrictTrades(district: string | null | undefined, enabled: boolean): DistrictTrades {
  const region = regionLabel(district);
  const [months] = useState(() => recentMonths(new Date()));
  const [state, setState] = useState<DistrictTrades>({ loading: enabled && !!region, region, rows: [], errors: [], months });
  useEffect(() => {
    let alive = true;
    if (!enabled || !region) {
      setState({ loading: false, region, rows: [], errors: [], months });
      return;
    }
    setState({ loading: true, region, rows: [], errors: [], months });
    load(region, months).then((v) => alive && setState({ loading: false, region, rows: v.rows, errors: v.errors, months }));
    return () => {
      alive = false;
    };
  }, [enabled, region, months]);
  return state;
}
