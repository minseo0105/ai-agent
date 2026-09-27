"use client";

import { useState } from "react";
import { ChoiceChips, Field, inputClass } from "@/components/golf/ui";
import RegionPicker from "./RegionPicker";

export type TradeFilterValue = {
  types: string[];
  regions: string[];
  month: string;
  maxPrice: string;
  maxArea: string;
  includeDevelopment: boolean;
};

const PRICE_CHIPS = ["전체", "3억 이하", "5억 이하", "7억 이하", "10억 이하"];
const AREA_CHIPS = ["면적 전체", "60㎡ 이하", "85㎡ 이하", "102㎡ 이하", "135㎡ 이하"];

/** 선택한 조건을 한 줄 칩으로 요약한다. 검색 후에도 조건 영역이 화면을 덮지 않게. */
export function FilterChips({ value, onClearRegion }: { value: TradeFilterValue; onClearRegion?: (region: string) => void }) {
  const month = `${value.month.slice(0, 4)}.${value.month.slice(4, 6)}`;
  return (
    <div className="flex flex-wrap gap-1.5">
      {value.regions.map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => onClearRegion?.(r)}
          className="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-bold text-muted transition hover:text-fg"
        >
          {r.split(" > ").pop()}
          {onClearRegion && <span aria-hidden className="ml-1 text-subtle">×</span>}
        </button>
      ))}
      {value.types.map((t) => (
        <span key={t} className="rounded-full bg-estate-soft px-2.5 py-1 text-[11px] font-bold text-estate">{t}</span>
      ))}
      <span className="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-bold text-muted">{month}</span>
      {value.maxPrice && <span className="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-bold text-muted">{value.maxPrice}억 이하</span>}
      {value.maxArea && <span className="rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-bold text-muted">{value.maxArea}㎡ 이하</span>}
    </div>
  );
}

export default function TradeFilters({
  options,
  value,
  onChange,
  onSearch,
  loading,
}: {
  options: { regions: { 서울: string[]; 경기: string[] }; property_types: string[] };
  value: TradeFilterValue;
  onChange: (next: TradeFilterValue) => void;
  onSearch: () => void;
  loading: boolean;
}) {
  const [advanced, setAdvanced] = useState(false);
  const set = <K extends keyof TradeFilterValue>(key: K, next: TradeFilterValue[K]) => onChange({ ...value, [key]: next });
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const monthValue = `${value.month.slice(0, 4)}-${value.month.slice(4, 6)}`;

  return (
    <div className="space-y-3">
      <Field label="조회지역">
        <RegionPicker regions={options.regions} value={value.regions} onChange={(next) => set("regions", next)} selectWholeScope />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="주택유형" hint="여러 개 선택 가능">
          <ChoiceChips accent="estate" options={options.property_types} selected={value.types} onToggle={(v) => set("types", toggle(value.types, v))} />
        </Field>
        <Field label="계약년월">
          <input
            type="month"
            aria-label="계약년월"
            className={`${inputClass} max-w-48`}
            value={monthValue}
            onChange={(e) => e.target.value && set("month", e.target.value.replace("-", ""))}
          />
        </Field>
      </div>

      <button
        type="button"
        onClick={() => setAdvanced(!advanced)}
        aria-expanded={advanced}
        className="flex min-h-9 items-center gap-1.5 text-xs font-bold text-muted transition hover:text-fg"
      >
        상세조건 {advanced ? "−" : "+"}
        {!advanced && (value.maxPrice || value.maxArea) && <span className="text-estate">· 적용 중</span>}
      </button>

      {advanced && (
        <div className="space-y-3 rounded-2xl bg-surface-muted p-3">
          <Field label="최대 매매가격" hint="억원 · 비워두면 전체 · 입력 금액 포함 이하">
            <div className="flex items-center gap-2">
              <input
                aria-label="최대 매매가격 (억원)"
                type="number"
                inputMode="decimal"
                min="0.01"
                max="10000"
                step="0.01"
                placeholder="예: 5"
                value={value.maxPrice}
                onChange={(e) => set("maxPrice", e.target.value)}
                className={`${inputClass} max-w-40`}
              />
              <span className="shrink-0 text-sm text-muted">억원 이하</span>
            </div>
            <div className="mt-2">
              <ChoiceChips
                accent="estate"
                options={PRICE_CHIPS}
                selected={[value.maxPrice === "" ? "전체" : `${value.maxPrice}억 이하`]}
                onToggle={(v) => set("maxPrice", v === "전체" ? "" : v.replace("억 이하", ""))}
              />
            </div>
          </Field>
          <Field label="최대 면적" hint="㎡ · 비워두면 전체 · 입력 면적 포함 이하">
            <div className="flex items-center gap-2">
              <input
                aria-label="최대 면적 (㎡)"
                type="number"
                inputMode="decimal"
                min="0.01"
                max="100000"
                step="0.01"
                placeholder="예: 85"
                value={value.maxArea}
                onChange={(e) => set("maxArea", e.target.value)}
                className={`${inputClass} max-w-40`}
              />
              <span className="shrink-0 text-sm text-muted">㎡ 이하</span>
            </div>
            <div className="mt-2">
              <ChoiceChips
                accent="estate"
                options={AREA_CHIPS}
                selected={[value.maxArea === "" ? "면적 전체" : `${value.maxArea}㎡ 이하`]}
                onToggle={(v) => set("maxArea", v === "면적 전체" ? "" : v.replace("㎡ 이하", ""))}
              />
            </div>
            {Number(value.maxArea) > 0 && Number.isFinite(Number(value.maxArea)) && (
              <p className="mt-1.5 text-xs text-estate">약 {(Number(value.maxArea) / 3.3058).toFixed(1)}평 이하</p>
            )}
          </Field>
          <label className="flex items-start gap-2 text-xs font-semibold">
            <input
              type="checkbox"
              checked={value.includeDevelopment}
              onChange={(e) => set("includeDevelopment", e.target.checked)}
              className="mt-0.5 size-4 accent-current"
            />
            <span>
              주변 개발정보 함께 보기
              <span className="mt-0.5 block font-normal text-subtle">정확한 좌표가 있는 거래에만 연결됩니다.</span>
            </span>
          </label>
          <p className="text-[11px] leading-relaxed text-subtle">
            실제 계약된 매매가격 기준이며 현재 호가가 아닙니다. 아파트·연립·오피스텔은 전용면적, 단독·다가구는 연면적 또는 건물면적
            기준입니다. 가격·면적 미확인 거래는 해당 조건 적용 시 제외합니다.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={onSearch}
        disabled={loading}
        className="min-h-11 w-full rounded-xl bg-estate py-2.5 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40"
      >
        실거래 조회 · {value.regions.length}개 지역 × {value.types.length}개 유형
      </button>
    </div>
  );
}
