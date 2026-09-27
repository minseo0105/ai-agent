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
  type EstateOptions,
  type MapConfig,
} from "@/lib/realestate";

const MAX_DISTRICTS = 5;
// 카드 렌더 상한. 넘으면 조용히 자르지 않고 몇 건을 보여주는지 화면에 적는다.
const MAX_CARDS = 200;
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
  const [districts, setDistricts] = useState<string[]>([]);
  const [projects, setProjects] = useState<DevelopmentProject[]>([]);
  const [points, setPoints] = useState<DevelopmentMapPoint[]>([]);
  const [filter, setFilter] = useState<string>("전체");
  const [keyword, setKeyword] = useState("");
  const [stageFilter, setStageFilter] = useState("전체");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    estateApi.mapConfig().then(setConfig).catch(() => {});
  }, []);

  // 목록과 marker를 한 응답에서 받는다. 자치구별 응답을 합치면 한 자치구가 실패했을 때
  // 그 사업들이 조용히 빠진 합계가 '전체'로 보인다. 지역 선택은 이 데이터를 화면에서
  // 거르는 것이고, 다시 조회하지 않는다.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    estateApi
      .developmentMap()
      .then((r) => {
        if (cancelled) return;
        if (r.status !== "ok") {
          setReady(false);
          setProjects([]);
          setPoints([]);
          return;
        }
        setReady(true);
        setProjects(r.projects);
        setPoints(r.points);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const search = keyword.trim();
  const selectedDistricts = useMemo(
    () => new Set(districts.map((r) => r.replace(/^(서울|경기) > /, "")).slice(0, MAX_DISTRICTS)),
    [districts],
  );
  const visible = useMemo(
    () =>
      projects.filter((p) => {
        if (selectedDistricts.size > 0 && !selectedDistricts.has(p.district ?? "")) return false;
        if (!matchesFilter(p, filter)) return false;
        if (stageFilter !== "전체" && p.stage.label !== stageFilter) return false;
        if (!search) return true;
        return [p.name, p.address, p.dong, p.district, p.type_label, p.program_label, p.stage.label]
          .filter(Boolean)
          .join(" ")
          .includes(search);
      }),
    [projects, selectedDistricts, filter, stageFilter, search],
  );
  // 진행단계는 응답에 실제로 있는 값만 제공한다. 단계를 추정하지 않는다.
  const stages = useMemo(() => [...new Set(projects.map((p) => p.stage.label))].sort(), [projects]);
  const visibleIds = useMemo(() => new Set(visible.map((p) => p.project_id)), [visible]);
  // 목록에 보이는 사업만 marker가 된다. 좌표가 없는 사업은 목록에 남고 marker만 없다.
  const visiblePoints = useMemo(
    () => points.filter((point) => visibleIds.has(point.project_id)),
    [points, visibleIds],
  );

  // 지역·유형을 고르지 않은 기본 상태의 분모는 API가 가진 전체 사업이다.
  const inRegion = useMemo(
    () =>
      selectedDistricts.size === 0
        ? projects
        : projects.filter((p) => selectedDistricts.has(p.district ?? "")),
    [projects, selectedDistricts],
  );
  const counts = {
    total: visible.length,
    재개발: inRegion.filter((p) => p.type_label === "재개발").length,
    재건축: inRegion.filter((p) => p.type_label === "재건축").length,
    신속통합기획: inRegion.filter((p) => p.program_label === "신속통합기획").length,
    모아타운: inRegion.filter((p) => p.type_label === "모아타운").length,
  };
  const selected = visible.find((p) => p.project_id === selectedId) ?? null;
  const selectedPoints = useMemo(
    () => visiblePoints.filter((point) => point.project_id === selectedId),
    [visiblePoints, selectedId],
  );
  const mappable = visiblePoints.filter((p) => p.latitude != null).length;
  const coordinateless = visible.length - mappable;
  const unavailable = !loading && !error && !ready;

  // marker를 누르면 같은 selectedProject가 되고 카드도 선택 상태가 된다. 화면을 강제로
  // 스크롤하지는 않고, 카드로 이동할지는 '사업정보 보기'로 사용자가 고른다.
  const selectFromMap = useCallback((projectId: string | null) => {
    setSelectedId(projectId);
  }, []);
  const scrollToCard = useCallback(() => {
    if (selectedId) cardRefs.current[selectedId]?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selectedId]);
  const onBounds = useCallback((_bounds: MapBounds) => {
    // bbox 조회 준비: 지금은 서울시 전체를 한 번 받아 두고 화면 범위는 지도에서만 쓴다.
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

      {ready && (
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

      {!loading && ready && (
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
                <button
                  type="button"
                  onClick={scrollToCard}
                  className={`${CHIP} mt-1.5 border border-border text-muted hover:text-fg`}
                >
                  사업정보 보기
                </button>
              </div>
            ) : (
              <p className="mt-1 text-xs text-muted">
                {visible.length}건 중 {mappable}건이 지도에 표시됩니다.
                {coordinateless > 0 && ` 좌표가 없는 ${coordinateless}건은 목록에만 남습니다.`}
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

          {selectedDistricts.size === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">
              서울시 전체 {projects.length}건을 보여드리고 있어요. 지역을 선택하면 해당 자치구만 남습니다.
            </p>
          )}
          {visible.length === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">조건에 맞는 개발사업이 없어요.</p>
          )}

          {selected && (
            <section className="rounded-xl border border-border bg-surface-muted p-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                <h3 className="text-[11px] font-extrabold tracking-wide text-muted">선택 사업 위치</h3>
                <span className="text-[11px] text-subtle">
                  {selected.mappable ? selected.location_accuracy.label : "좌표 미확보"}
                </span>
              </div>
              <div className="mt-0.5 text-xs font-extrabold">{selected.name}</div>
              <p className="text-[11px] text-muted">
                {[selected.type_label, selected.program_label].filter(Boolean).join(" · ")} · {selected.stage.label}
              </p>
              {selected.mappable ? (
                <div className="mt-2">
                  <ZiponMap
                    points={selectedPoints}
                    config={config}
                    selectedId={selected.project_id}
                    height={200}
                    compact
                  />
                </div>
              ) : (
                <p className="mt-2 rounded-lg bg-surface px-2.5 py-2 text-[11px] text-muted">
                  이 사업은 아직 좌표를 확보하지 못해 지도에 표시하지 않습니다. 목록에서는 계속 확인할 수 있어요.
                </p>
              )}
            </section>
          )}

          <div className="grid gap-2.5 md:grid-cols-2">
            {visible.slice(0, MAX_CARDS).map((p) => (
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
          {visible.length > MAX_CARDS && (
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">
              {visible.length}건 중 {MAX_CARDS}건을 카드로 보여드리고 있어요. 지역이나 유형을 좁혀 주세요.
            </p>
          )}
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
