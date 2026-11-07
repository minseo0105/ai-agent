"use client";

import type { GyeonggiInfo } from "@/lib/realestate";

const MISSING_LABEL: Record<string, string> = { name: "사업명", sigun: "시군", address: "주소", type_label: "사업 유형", stage: "추진 단계" };

/**
 * 경기데이터드림 원본 정보. 필드명은 실제 응답으로 확인됐지만 값의 단위·날짜 형식·최신성은 검증되지 않아
 * 해석하지 않고 원문 그대로 보여 준다. 비어 있는 값은 '원본 미제공'으로 표시하고 만들지 않는다.
 */
export default function GyeonggiInfoCard({ info }: { info: GyeonggiInfo }) {
  const rows = [...info.values, ...info.stage_dates];
  return (
    <section data-gyeonggi-info aria-label="경기도 원본 정보" className="space-y-2 rounded-xl border border-border px-3 py-2.5">
      <h3 className="text-xs font-extrabold">경기도 원본 정보 <span className="font-semibold text-subtle">{info.dataset_title}</span></h3>
      <dl className="divide-y divide-border/60 text-xs">
        <div className="flex justify-between gap-3 py-1.5"><dt className="text-subtle">원본 추진 단계</dt><dd className="text-right font-semibold">{info.stage_raw ?? "원본 미제공"}</dd></div>
        <div className="flex justify-between gap-3 py-1.5"><dt className="text-subtle">표준 단계(집 분류)</dt><dd className="text-right">{info.stage_std_label ?? "대응 단계 없음"}</dd></div>
        {info.sigungu_raw && <div className="flex justify-between gap-3 py-1.5"><dt className="text-subtle">원본 시군구</dt><dd className="text-right">{info.sigungu_raw}</dd></div>}
        {rows.map((r) => (
          <div key={r.source_field} className="flex justify-between gap-3 py-1.5">
            <dt className="text-subtle">{r.label}</dt>
            <dd className={`text-right ${r.value ? "font-semibold" : "text-subtle"}`}>{r.value ?? "원본 미제공"}</dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] text-subtle">{info.format_note}{info.biz_div ? " 사업구분 코드(BIZ_DIV)의 공식 의미는 아직 확인되지 않아 세부 유형으로 바꾸지 않았어요." : ""}</p>
      {info.missing.length > 0 && (
        <p className="text-[11px] text-amber-800 dark:text-amber-300">원본에 없는 항목: {info.missing.map((m) => MISSING_LABEL[m] ?? m).join(", ")}</p>
      )}
      {info.duplicate_of.length > 0 && (
        <p data-duplicate className="text-[11px] text-amber-800 dark:text-amber-300">
          같은 시군에서 {info.duplicate_basis.includes("addr") ? (info.duplicate_basis.includes("name") ? "사업명·주소가" : "주소가") : "사업명이"} 같은 사업이 {info.duplicate_of.length}건 더 있어요(중복 후보, 합치지 않음).
        </p>
      )}
      <p className="text-[11px] text-subtle">출처: 경기데이터드림 {info.service} · 수집 {info.collected_at.slice(0, 10)} · {info.freshness_note}</p>
    </section>
  );
}
