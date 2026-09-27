"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Spinner, inputClass } from "@/components/golf/ui";
import DevelopmentCard from "./DevelopmentCard";
import RegionPicker from "./RegionPicker";
import ZiponMap, { type MapBounds, type MapFocus } from "./ZiponMap";
import {
  estateApi,
  type DevelopmentMapPoint,
  type DevelopmentProject,
  type DevelopmentSummary,
  type EstateOptions,
  type MapConfig,
} from "@/lib/realestate";

const MAX_DISTRICTS = 5;
const FILTERS = ["전체", "재개발", "재건축", "신속통합기획", "모아타운", "기타 정비사업"] as const;
const CHIP = "min-h-9 rounded-full px-3 py-1.5 text-xs font-bold transition";

function Kpi({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className={`rounded-xl px-3 py-2 ${accent ? "bg-estate-soft" : "bg-surface-muted"}`}>
      <div className="text-[11px] font-semibold text-muted">{label}</div>
      <div className={`text-lg font-extrabold leading-tight ${accent ? "text-estate" : ""}`}>{value}</div>
    </div>
  );
}

function matchesFilter(item: { type_label: string; program_label: string | null }, filter: string) {
  if (filter === "전체") return true;
  if (filter === "기타 정비사업") return !["재개발", "재건축", "모아타운"].includes(item.type_label);
  return item.type_label === filter || item.program_label === filter;
}

/** 부동산 개발정보 지도. 지도가 주인공이고 목록은 지도를 설명하는 보조 역할이다. */
export default function DevelopmentTab({
  options,
  property = null,
}: {
  options: EstateOptions;
  property?: MapFocus;
}) {
  const [config, setConfig] = useState<MapConfig | null>(null);
  const [summary, setSummary] = useState<DevelopmentSummary | null>(null);
  const [districts, setDistricts] = useState<string[]>([]);
  const [projects, setProjects] = useState<DevelopmentProject[]>([]);
  const [points, setPoints] = useState<DevelopmentMapPoint[]>([]);
  const [filter, setFilter] = useState<string>("전체");
  const [keyword, setKeyword] = useState("");
  const [stageFilter, setStageFilter] = useState("전체");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    estateApi.mapConfig().then(setConfig).catch(() => {});
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
      setPoints([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [lists, maps] = await Promise.all([
        Promise.all(names.map((name) => estateApi.development({ sigungu: name, limit: 100 }))),
        Promise.all(names.map((name) => estateApi.developmentMap(name, 200))),
      ]);
      setProjects(lists.flatMap((r) => (r.status === "ok" ? r.projects : [])));
      setPoints(maps.flatMap((r) => (r.status === "ok" ? r.points : [])));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (summary) load(districts);
  }, [districts, summary, load]);

  const search = keyword.trim();
  const visible = useMemo(
    () =>
      projects.filter((p) => {
        if (!matchesFilter(p, filter)) return false;
        if (stageFilter !== "전체" && p.stage.label !== stageFilter) return false;
        if (!search) return true;
        return [p.name, p.address, p.dong, p.district, p.type_label, p.program_label, p.stage.label]
          .filter(Boolean)
          .join(" ")
          .includes(search);
      }),
    [projects, filter, stageFilter, search],
  );
  // 진행단계는 응답에 실제로 있는 값만 제공한다. 단계를 추정하지 않는다.
  const stages = useMemo(() => [...new Set(projects.map((p) => p.stage.label))].sort(), [projects]);
  const visibleIds = useMemo(() => new Set(visible.map((p) => p.project_id)), [visible]);
  const visiblePoints = useMemo(
    () => points.filter((point) => matchesFilter(point, filter) && (!search || visibleIds.has(point.project_id))),
    [points, filter, search, visibleIds],
  );

  const counts = {
    total: visible.length,
    재개발: projects.filter((p) => p.type_label === "재개발").length,
    재건축: projects.filter((p) => p.type_label === "재건축").length,
    신속통합기획: projects.filter((p) => p.program_label === "신속통합기획").length,
    모아타운: projects.filter((p) => p.type_label === "모아타운").length,
  };
  const selected = visible.find((p) => p.project_id === selectedId) ?? null;
  const mappable = visiblePoints.filter((p) => p.latitude != null).length;
  const unavailable = summary?.status !== "ok";

  // 지도 marker를 누르면 해당 카드로 이동하고, 카드를 누르면 marker를 강조한다.
  const selectFromMap = useCallback((projectId: string | null) => {
    setSelectedId(projectId);
    if (projectId) cardRefs.current[projectId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, []);
  const onBounds = useCallback((_bounds: MapBounds) => {
    // bbox 조회 준비: 현재는 자치구 단위로 받아오고 화면 범위는 지도에서만 사용한다.
  }, []);

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-extrabold tracking-tight">부동산 개발정보 지도</h2>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">
          재개발 · 재건축 · 신속통합기획 · 모아타운을 지도에서 확인합니다. 서울시 공식자료 기준입니다.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-xs font-bold text-subtle">지역</span>
        <RegionPicker regions={options.regions} value={districts} onChange={setDistricts} max={MAX_DISTRICTS} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label="사업명 · 동 · 유형 검색"
          placeholder="사업명 · 동 · 유형 검색 (예: 천호동, 재개발)"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className={`${inputClass} min-w-0 flex-1`}
        />
        {stages.length > 1 && (
          <select
            aria-label="진행단계"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className={`${inputClass} max-w-40`}
          >
            <option value="전체">진행단계 전체</option>
            {stages.map((stage) => (
              <option key={stage} value={stage}>
                {stage} ({projects.filter((p) => p.stage.label === stage).length})
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5">
        {FILTERS.filter((f) => f === "전체" || f === "기타 정비사업" || counts[f as "재개발"] > 0).map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
            className={`${CHIP} shrink-0 ${filter === f ? "bg-estate text-white" : "border border-border text-muted hover:text-fg"}`}
          >
            {f}
          </button>
        ))}
      </div>

      {!unavailable && districts.length > 0 && (
        <ZiponMap
          points={visiblePoints}
          property={property}
          config={config}
          selectedId={selectedId}
          height={340}
          onSelect={selectFromMap}
          onBoundsChange={onBounds}
        />
      )}

      {loading && <Spinner label="개발정보를 불러오고 있어요…" />}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!loading && unavailable && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-300">
          개발정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      {!loading && !unavailable && (
        <>
          <section className="rounded-xl bg-surface-muted p-2.5">
            <h3 className="text-[11px] font-extrabold tracking-wide text-muted">이 위치의 개발정보</h3>
            {selected ? (
              <div className="mt-1 text-xs">
                <div className="font-extrabold">{selected.name}</div>
                <p className="mt-0.5 text-muted">
                  {[selected.type_label, selected.program_label].filter(Boolean).join(" · ")} · {selected.stage.label}
                </p>
                <p className="mt-0.5 text-subtle">
                  {selected.address ?? "대표주소 확인 중"} · {selected.location_accuracy.label}
                </p>
              </div>
            ) : (
              <p className="mt-1 text-xs text-muted">
                {visible.length}건 중 {mappable}건이 지도에 표시됩니다.
                {mappable === 0 && " 좌표를 확보하는 중이라 아직 지도에 핀이 없습니다."}
                {" 지도나 아래 목록에서 사업을 선택하면 해석을 보여드려요."}
              </p>
            )}
          </section>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <Kpi label="전체 사업" value={counts.total} accent />
            {counts.재개발 > 0 && <Kpi label="재개발" value={counts.재개발} />}
            {counts.재건축 > 0 && <Kpi label="재건축" value={counts.재건축} />}
            {counts.신속통합기획 > 0 && <Kpi label="신속통합기획" value={counts.신속통합기획} />}
            {counts.모아타운 > 0 && <Kpi label="모아타운" value={counts.모아타운} />}
          </div>

          {districts.length === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">
              지역을 선택하면 해당 자치구의 개발사업을 지도에 보여드려요.
              {summary && summary.total > 0 && ` 현재 ${summary.total}건이 등록돼 있어요.`}
            </p>
          )}
          {districts.length > 0 && visible.length === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">조건에 맞는 개발사업이 없어요.</p>
          )}

          <div className="grid gap-2.5 md:grid-cols-2">
            {visible.slice(0, 60).map((p) => (
              <div
                key={p.project_id}
                ref={(node) => {
                  cardRefs.current[p.project_id] = node;
                }}
                onClick={() => setSelectedId(p.project_id)}
                className={`rounded-2xl transition ${selectedId === p.project_id ? "ring-2 ring-estate" : ""}`}
              >
                <DevelopmentCard project={p} />
              </div>
            ))}
          </div>
          {visible.length > 0 && (
            <p className="text-[11px] leading-relaxed text-subtle">
              사업별로 공식 상세정보 또는 목록에서 확인한 단계와 확인일을 표시합니다. 진행단계의 근거는 각 카드의 서울시 공식자료에서 확인할 수 있습니다.
            </p>
          )}
        </>
      )}
    </div>
  );
}
