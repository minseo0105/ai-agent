"use client";

import { useState } from "react";
import { Segmented, inputClass } from "@/components/golf/ui";

const short = (r: string) => r.replace(/^(서울|경기) > /, "");
const CHIP = "min-h-9 rounded-full px-3 py-1.5 text-xs font-bold transition";

/**
 * 기본은 접힌 상태. '지역 선택 / 지역 변경'을 눌렀을 때만 목록을 펼치고, 선택을 마치면 다시 접는다.
 * 값은 "서울 > 송파구" 형식을 그대로 유지한다.
 */
export default function RegionPicker({
  regions,
  value,
  onChange,
  selectWholeScope = false,
  max,
}: {
  regions: { 서울: string[]; 경기: string[] };
  value: string[];
  onChange: (v: string[]) => void;
  selectWholeScope?: boolean;
  max?: number;
}) {
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<"서울" | "경기">("서울");
  const [q, setQ] = useState("");
  // 비어 있는 범위는 탭으로도, 검색 대상으로도 올리지 않는다. 고를 수 없는 지역을
  // 보여주면 눌러 본 사람에게 0건이 고장처럼 읽힌다.
  const scopes = (["서울", "경기"] as const).filter((name) => regions[name].length > 0);
  const active = scopes.includes(scope) ? scope : scopes[0] ?? "서울";
  const all = scopes.flatMap((name) => regions[name]);
  const pool = regions[active] ?? [];
  const keyword = q.trim();
  const visible = keyword ? all.filter((r) => r.includes(keyword)) : pool;
  const atLimit = typeof max === "number" && value.length >= max;

  function pick(region: string) {
    if (value.includes(region)) return onChange(value.filter((r) => r !== region));
    if (max === 1) return onChange([region]);
    if (atLimit) return;
    onChange([...value, region]);
  }

  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {value.length === 0 ? (
          <>
            {selectWholeScope && (
              <button type="button" onClick={() => onChange(all)} className={`${CHIP} border border-border text-muted hover:text-fg`}>
                {scopes.join("·")} 전체
              </button>
            )}
            <button type="button" onClick={() => setOpen(true)} className={`${CHIP} bg-estate px-3.5 text-white`}>
              지역 선택 ›
            </button>
          </>
        ) : (
          <>
            {value.slice(0, 8).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onChange(value.filter((x) => x !== r))}
                aria-label={`${short(r)} 선택 해제`}
                className={`${CHIP} bg-estate-soft text-estate`}
              >
                {short(r)} <span aria-hidden className="ml-0.5 opacity-60">×</span>
              </button>
            ))}
            {value.length > 8 && <span className="text-xs font-semibold text-muted">+{value.length - 8}곳</span>}
            <button type="button" onClick={() => setOpen(true)} className={`${CHIP} border border-border text-muted hover:text-fg`}>
              지역 변경
            </button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        {scopes.length > 1 && (
          <Segmented value={active} options={scopes} onChange={(next) => setScope(next)} ariaLabel="지역 범위" />
        )}
        <input
          className={`${inputClass} min-w-0 flex-1 py-1.5`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          // 고를 수 있는 범위가 하나면 그 범위만 검색한다고 적는다.
          placeholder={scopes.length > 1 ? "구·시 검색" : `${active} 자치구 검색`}
          aria-label="지역 검색"
        />
      </div>
      {keyword && <p className="mt-1.5 text-[11px] text-subtle">‘{keyword}’ 검색 결과 · {scopes.join("·")} 전체에서 찾습니다.</p>}
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {visible.map((r) => {
          const selected = value.includes(r);
          return (
            <button
              key={r}
              type="button"
              aria-pressed={selected}
              disabled={!selected && atLimit && max !== 1}
              onClick={() => pick(r)}
              className={`${CHIP} ${
                selected ? "bg-estate text-white" : "border border-border text-muted hover:text-fg disabled:opacity-40"
              }`}
            >
              {short(r)}
            </button>
          );
        })}
        {visible.length === 0 && <p className="text-xs text-subtle">검색 결과가 없어요.</p>}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-border pt-2.5">
        <div className="flex flex-wrap gap-2 text-xs font-semibold text-muted">
          {selectWholeScope && max !== 1 && (
            <button type="button" onClick={() => onChange([...new Set([...value, ...pool])])} className="hover:text-fg">
              {active} 전체 추가
            </button>
          )}
          {value.length > 0 && (
            <button type="button" onClick={() => onChange([])} className="hover:text-fg">
              모두 해제
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            setQ("");
            setOpen(false);
          }}
          className="min-h-11 rounded-xl bg-estate px-5 text-sm font-extrabold text-white"
        >
          선택 완료{value.length > 0 ? ` · ${value.length}곳` : ""}
        </button>
      </div>
      {atLimit && max !== 1 && <p className="mt-1.5 text-[11px] text-subtle">최대 {max}곳까지 선택할 수 있어요.</p>}
    </div>
  );
}
