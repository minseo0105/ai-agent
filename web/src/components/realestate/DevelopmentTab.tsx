"use client";

import { useCallback, useEffect, useState } from "react";
import { Spinner, inputClass } from "@/components/golf/ui";
import DevelopmentCard from "./DevelopmentCard";
import RegionPicker from "./RegionPicker";
import {
  estateApi,
  type DevelopmentProject,
  type DevelopmentSummary,
  type EstateOptions,
} from "@/lib/realestate";

const MAX_DISTRICTS = 5;
const TYPE_FILTERS = ["전체", "재개발", "재건축", "신속통합기획"];
const CHIP = "min-h-9 rounded-full px-3 py-1.5 text-xs font-bold transition";

function Kpi({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`rounded-xl px-3 py-2 ${accent ? "bg-estate-soft" : "bg-surface-muted"}`}>
      <div className="text-[11px] font-semibold text-muted">{label}</div>
      <div className={`text-lg font-extrabold leading-tight ${accent ? "text-estate" : ""}`}>{value}</div>
    </div>
  );
}

/** 들어오면 바로 현황이 보이는 개발사업 현황판. 조회 버튼을 누르지 않아도 자동으로 불러온다. */
export default function DevelopmentTab({ options }: { options: EstateOptions }) {
  const [summary, setSummary] = useState<DevelopmentSummary | null>(null);
  const [districts, setDistricts] = useState<string[]>([]);
  const [projects, setProjects] = useState<DevelopmentProject[]>([]);
  const [typeFilter, setTypeFilter] = useState("전체");
  const [stageFilter, setStageFilter] = useState("전체");
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 자치구 목록은 실제 적재 현황에서 가져온다. 데이터가 있는 지역을 기본 선택한다.
  useEffect(() => {
    estateApi
      .developmentSummary()
      .then((r) => {
        setSummary(r);
        setDistricts(r.districts.slice(0, 3).map((d) => `서울 > ${d.district}`));
        if (r.status !== "ok" || r.districts.length === 0) setLoading(false);
      })
      .catch((e) => {
        setError((e as Error).message);
        setLoading(false);
      });
  }, []);

  const load = useCallback(async (selected: string[]) => {
    const names = selected.map((r) => r.replace(/^(서울|경기) > /, "")).slice(0, MAX_DISTRICTS);
    if (names.length === 0) {
      setProjects([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const responses = await Promise.all(names.map((name) => estateApi.development({ sigungu: name, limit: 100 })));
      setProjects(responses.flatMap((r) => (r.status === "ok" ? r.projects : [])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (summary) load(districts);
  }, [districts, summary, load]);

  const byType = (p: DevelopmentProject) =>
    typeFilter === "전체" || p.type_label === typeFilter || p.program_label === typeFilter;
  const stages = [...new Set(projects.map((p) => p.stage.label))].sort();
  const visible = projects.filter((p) => {
    if (!byType(p)) return false;
    if (stageFilter !== "전체" && p.stage.label !== stageFilter) return false;
    const q = keyword.trim();
    return !q || [p.name, p.address, p.dong, p.type_label].filter(Boolean).join(" ").includes(q);
  });
  const counts = {
    total: projects.filter(byType).length,
    재건축: projects.filter((p) => p.type_label === "재건축").length,
    재개발: projects.filter((p) => p.type_label === "재개발").length,
    신속통합기획: projects.filter((p) => p.program_label === "신속통합기획").length,
  };
  const unavailable = summary?.status !== "ok";

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-extrabold tracking-tight">
          {districts.length === 1 ? `${districts[0].replace(/^(서울|경기) > /, "")} 개발사업` : "개발사업"}
        </h2>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">
          재개발 · 재건축 · 신속통합기획 등 공식자료 기반 개발사업을 확인합니다.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-xs font-bold text-subtle">지역</span>
        <RegionPicker regions={options.regions} value={districts} onChange={setDistricts} max={MAX_DISTRICTS} />
      </div>

      {!unavailable && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi label="전체" value={counts.total} accent />
          {counts.재건축 > 0 && <Kpi label="재건축" value={counts.재건축} />}
          {counts.재개발 > 0 && <Kpi label="재개발" value={counts.재개발} />}
          {counts.신속통합기획 > 0 && <Kpi label="신속통합기획" value={counts.신속통합기획} />}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {TYPE_FILTERS.filter((t) => t === "전체" || t === "재건축" ? true : counts[t as "재개발" | "신속통합기획"] > 0).map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={typeFilter === t}
            onClick={() => setTypeFilter(t)}
            className={`${CHIP} ${typeFilter === t ? "bg-estate text-white" : "border border-border text-muted hover:text-fg"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {stages.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="진행단계"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className={`${inputClass} max-w-44`}
          >
            <option value="전체">진행단계 전체</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {s} ({projects.filter((p) => p.stage.label === s).length})
              </option>
            ))}
          </select>
          <input
            aria-label="사업명 검색"
            placeholder="사업명 · 동 검색"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className={`${inputClass} min-w-0 flex-1`}
          />
        </div>
      )}

      {loading && <Spinner label="개발사업 현황을 불러오고 있어요…" />}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!loading && unavailable && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-300">
          개발사업 정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      {!loading && !unavailable && (
        <div className="space-y-3">
          {districts.length === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">
              지역을 선택하면 해당 자치구의 개발사업을 보여드려요.
              {summary && summary.total > 0 && ` 현재 ${summary.total}건이 등록돼 있어요.`}
            </p>
          )}
          {districts.length > 0 && visible.length === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">조건에 맞는 개발사업이 없어요.</p>
          )}
          <div className="grid gap-2.5 md:grid-cols-2">
            {visible.slice(0, 60).map((p) => (
              <DevelopmentCard key={p.project_id} project={p} />
            ))}
          </div>
          {visible.length > 0 && (
            <p className="text-[11px] leading-relaxed text-subtle">
              공식 목록에서 수집한 자료입니다. ‘공식 목록 기준’ 표시는 상세 확인 전이므로 확정된 사실로 보지 말아 주세요.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
