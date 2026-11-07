"use client";

import { inputClass } from "@/components/golf/ui";
import { trackUsage } from "@/lib/analytics";
import { FILTER_OPTIONS } from "@/lib/developmentFilter";
import RegionPicker from "../RegionPicker";
import { MAX_DISTRICTS, type ZiponDevelopment } from "./useZiponDevelopment";

const CHIP = "min-h-9 shrink-0 rounded-full px-3 py-1.5 text-xs font-bold transition";

/** 상단 영역: 로고, 통합 검색, 지역, 유형·단계 필터. 기존 개발지도의 검색·필터를 그대로 쓴다. */
export default function DashboardToolbar({ data }: { data: ZiponDevelopment }) {
  const { counts, stages, projects, ready } = data;
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex items-center gap-2" aria-label="ZIP 개발지도">
          <span aria-hidden className="flex size-8 items-center justify-center rounded-lg bg-zip text-sm font-extrabold text-white">집</span>
          <div className="leading-tight">
            <div className="text-sm font-extrabold tracking-tight">ZIP 개발지도</div>
            <div className="text-[11px] text-subtle">재개발 · 재건축 · 서울시 공식자료</div>
          </div>
        </div>
        <input
          aria-label="사업명 · 동 · 유형 검색"
          placeholder="지역 · 주소 · 사업명 검색 (예: 천호동, 재개발)"
          value={data.keyword}
          onChange={(e) => data.setKeyword(e.target.value)}
          onBlur={() => {
            if (data.keyword.trim() && data.keyword !== data.lastSearch.current) trackUsage("search", "address_search");
            data.lastSearch.current = data.keyword;
          }}
          className={`${inputClass} min-w-0 flex-1 basis-56`}
        />
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span className="text-xs font-bold text-subtle">지역</span>
          <RegionPicker regions={data.seoulOnly} value={data.districts} onChange={data.setDistricts} max={MAX_DISTRICTS} />
        </div>
      </div>

      {data.keyword.trim() && (
        // 지역과 검색어가 함께 걸려 있으면 결과가 둘 다로 줄어든다. 무엇이 걸려 있는지 보여 주고 바로 지울 수 있게 한다.
        <p data-active-conditions className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <span>
            적용 중: {data.selectedDistricts.size ? [...data.selectedDistricts].join("·") : "서울 전체"} · 검색어 “{data.keyword.trim()}” →{" "}
            {data.visible.length.toLocaleString("ko-KR")}건
          </span>
          <button type="button" onClick={() => data.setKeyword("")} className="rounded-full border border-border px-2 py-0.5 font-bold text-zip">
            검색어 지우기
          </button>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5">
          {FILTER_OPTIONS.filter((f) => f === "전체" || f === "기타 정비사업" || counts[f as "재개발"] > 0).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={data.filter === f}
              onClick={() => data.setFilter(f)}
              className={`${CHIP} ${data.filter === f ? "bg-zip text-white" : "border border-border text-muted hover:text-fg"}`}
            >
              {f}
              {f !== "전체" && f !== "기타 정비사업" && <span className="ml-1 opacity-70">{counts[f as "재개발"]}</span>}
            </button>
          ))}
        </div>
        {stages.length > 1 && (
          <select aria-label="진행단계" value={data.stageFilter} onChange={(e) => data.setStageFilter(e.target.value)} className={`${inputClass} max-w-44`}>
            <option value="전체">진행단계 전체</option>
            {stages.map((stage) => (
              <option key={stage} value={stage}>{stage} ({projects.filter((p) => p.stage.label === stage).length})</option>
            ))}
          </select>
        )}
        {ready && (
          // 기본은 꺼짐. 완료·취소 사업은 지우지 않고 감춰 둘 뿐이다.
          <button
            type="button"
            onClick={() => data.setIncludeCompleted((v) => !v)}
            aria-pressed={data.includeCompleted}
            className={`${CHIP} border ${data.includeCompleted ? "border-zip bg-zip-soft text-zip" : "border-border bg-surface text-muted hover:bg-surface-muted"}`}
          >
            완료사업 보기
          </button>
        )}
      </div>
    </header>
  );
}
