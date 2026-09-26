"use client";

import { useState } from "react";
import { ChoiceChips, Segmented, inputClass } from "@/components/golf/ui";

const short = (r: string) => r.replace(/^(서울|경기) > /, "");

/** 서울·경기 시군구 복수 선택: 범위 전환 + 검색 + 칩. 값은 "서울 > 송파구" 형식 그대로. */
export default function RegionPicker({
  regions,
  value,
  onChange,
  defaultScope = "전체",
  selectWholeScope = false,
}: {
  regions: { 서울: string[]; 경기: string[] };
  value: string[];
  onChange: (v: string[]) => void;
  defaultScope?: "서울" | "경기" | "전체";
  selectWholeScope?: boolean;
}) {
  const [scope, setScope] = useState<"서울" | "경기" | "전체">(defaultScope);
  const [q, setQ] = useState("");
  const pool = scope === "서울" ? regions.서울 : scope === "경기" ? regions.경기 : [...regions.서울, ...regions.경기];
  const visible = pool.filter((r) => !q.trim() || r.includes(q.trim()));

  // 칩에는 짧은 이름을 보여주고, 선택값은 원래 형식으로 유지한다.
  const toFull = (s: string) => visible.find((r) => short(r) === s) ?? s;
  const wholeSelected = selectWholeScope && pool.length > 0 && pool.every((r) => value.includes(r));
  const selectedShort = wholeSelected ? [] : value.filter((v) => visible.includes(v)).map(short);
  const wholeLabel = scope === "전체" ? "서울·경기 전체" : `${scope} 전체`;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented value={scope} options={["서울", "경기", "전체"] as const} onChange={(next) => {
          setScope(next);
          setQ("");

        }} ariaLabel="지역 범위" />
        <input className={`${inputClass} max-w-48 py-1.5`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="구·시 검색" />
        {value.length > 0 && (
          <button type="button" onClick={() => onChange([])} className="text-xs font-semibold text-muted hover:text-fg">
            선택 {value.length}곳 · 모두 해제
          </button>
        )}
      </div>
      {selectWholeScope && <p className="text-xs text-muted">아래에서 전체 또는 원하는 시·군·구를 선택하세요. 전체 선택 후 개별 지역을 누르면 해당 지역만 선택됩니다. 다른 시도의 선택은 유지됩니다.</p>}
      <div className="max-h-44 overflow-y-auto rounded-2xl border border-border p-3">
        {selectWholeScope && (
          <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-border pb-3">
            <button type="button" aria-pressed={wholeSelected} onClick={() => onChange(wholeSelected ? value.filter((r) => !pool.includes(r)) : [...new Set([...value, ...pool])])} className={`rounded-full border px-3 py-1.5 text-xs font-bold ${wholeSelected ? "border-estate bg-estate text-white" : "border-border text-estate"}`}>
              {wholeSelected ? "✓ " : ""}{wholeLabel}
            </button>
            <button type="button" onClick={() => onChange(value.filter((r) => !pool.includes(r)))} className="text-xs text-muted hover:text-fg">이 지역 선택 해제</button>
          </div>
        )}
        <ChoiceChips
          accent="estate"
          options={visible.map(short)}
          selected={selectedShort}
          onToggle={(s) => {
            const full = toFull(s);
            onChange(wholeSelected ? [...value.filter((r) => !pool.includes(r)), full] : value.includes(full) ? value.filter((x) => x !== full) : [...value, full]);
          }}
        />
        {visible.length === 0 && <p className="text-xs text-subtle">검색 결과가 없어요.</p>}
      </div>
      {value.some((v) => !visible.includes(v)) && (
        <p className="text-[11px] text-subtle">다른 범위에서 선택한 지역: {value.filter((v) => !visible.includes(v)).map(short).join(", ")}</p>
      )}
    </div>
  );
}
