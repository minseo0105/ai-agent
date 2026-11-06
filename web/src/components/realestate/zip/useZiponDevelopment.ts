"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isTransient, withColdStartRetry } from "@/lib/coldStart";
import { distinctStages, filterProjects, typeCounts, visiblePoints as pickVisiblePoints } from "@/lib/developmentFilter";
import {
  estateApi,
  type DevelopmentMap,
  type DevelopmentMapPoint,
  type DevelopmentProject,
  type EstateOptions,
  type FreshnessBlock,
  type MapConfig,
} from "@/lib/realestate";

export const MAX_DISTRICTS = 5;

/**
 * 개발지도 목록 데이터와 검색·필터 상태. 기존 DevelopmentTab의 데이터 로딩과 필터 로직을 동작 변경 없이
 * 옮긴 것이다(필터 계산은 developmentFilter.ts, 변경 전 코드와 1,000개 넘는 조합으로 대조 검증).
 *
 * 선택(selectedId)은 목록에 보이는지와 무관하다. 완료사업을 숨겼거나 필터로 걸러져도 링크로 열 수 있고,
 * 상세 패널은 상세 조회 응답만으로도 그려진다.
 */
export function useZiponDevelopment(options: EstateOptions) {
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
  /** 기본 지도는 앞으로 변화가 남은 사업만 보여준다. 완료사업은 켤 때만 함께 본다. */
  const [includeCompleted, setIncludeCompleted] = useState(false);
  const [hiddenCompleted, setHiddenCompleted] = useState(0);
  const [waking, setWaking] = useState(false);
  /** 합치기에서 빠진 자치구. 조용히 빠뜨리면 틀린 합계가 전체로 보인다. */
  const [failedDistricts, setFailedDistricts] = useState<string[]>([]);
  /** limit에 닿아 더 있을 수 있는 응답인지 */
  const [truncated, setTruncated] = useState(false);
  /** 가장 최근 공식 확인 기준. 오래됐으면 지도 위에 알린다. */
  const [freshness, setFreshness] = useState<FreshnessBlock | null>(null);
  // DB 반영일(갱신 작업이 실제로 쓴 날). 공식 확인일이 아니다. 없으면 null → 화면은 '미기록'.
  const [dbReflected, setDbReflected] = useState(null as string | null);
  const [dataRevision, setDataRevision] = useState(0);

  useEffect(() => {
    estateApi.mapConfig().then(setConfig).catch(() => {});
  }, []);

  // 개발정보는 서울시 공식자료만 있다. 경기를 고를 수 있게 두면 고르는 순간 0건이 된다.
  const seoulOnly = useMemo(
    () => ({ 서울: options.regions.서울, 경기: [] as string[] }),
    [options.regions.서울],
  );
  const scope = useMemo(
    () => districts.map((r) => r.replace(/^(서울|경기) > /, "")).slice(0, MAX_DISTRICTS),
    [districts],
  );
  const scopeKey = scope.join(",");

  useEffect(() => {
    const refreshVisible = () => {
      if (!document.hidden) setDataRevision((v) => v + 1);
    };
    const timer = setInterval(refreshVisible, 300000);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, []);

  useEffect(() => {
    // 조건(지역·완료사업 포함 여부)이 바뀌면 이전 요청은 끊는다. 끊지 않으면 늦게
    // 도착한 이전 조건의 응답이 새 조건의 목록을 덮어쓴다.
    const controller = new AbortController();
    const requested = scopeKey ? scopeKey.split(",") : [];
    setLoading(true);
    setError("");
    // 조건이 바뀐 순간 이전 목록은 이 조건의 결과가 아니다.
    setProjects([]);
    setPoints([]);
    setFailedDistricts([]);
    setTruncated(false);
    setFreshness(null);
    setDbReflected(null);
    // 서버가 깨어나는 중일 수 있다. 읽기 요청이므로 잠깐 기다렸다가 다시 시도한다.
    const load = (sigungu: string | undefined) =>
      withColdStartRetry(
        (signal) => estateApi.developmentMap(sigungu, 500, undefined, { includeCompleted, init: { signal } }),
        { signal: controller.signal, onRetry: () => setWaking(true) },
      );
    const pending = requested.length
      ? Promise.all(requested.map((d) => load(d).then((r) => [d, r] as const).catch(() => [d, null] as const)))
      : load(undefined).then((r) => [[null, r] as const]);
    pending
      .then((responses) => {
        if (controller.signal.aborted) return;
        setWaking(false);
        const failed = responses.filter(([, r]) => !r || r.status !== "ok").map(([d]) => d);
        const ok = responses.filter(([, r]) => r && r.status === "ok") as [string | null, DevelopmentMap][];
        if (!ok.length) {
          setReady(false);
          setProjects([]);
          setPoints([]);
          setFailedDistricts(failed.filter((d): d is string => d !== null));
          return;
        }
        // project_id로 합친다. 자치구별 응답이 겹칠 일은 없지만, 겹쳐도 카드가 두 장
        // 생기지는 않게 한다.
        const seen = new Set<string>();
        const mergedProjects: DevelopmentProject[] = [];
        const mergedPoints: DevelopmentMapPoint[] = [];
        let hidden = 0;
        for (const [, r] of ok) {
          hidden += r.hidden_completed ?? 0;
          for (const project of r.projects) {
            if (seen.has(project.project_id)) continue;
            seen.add(project.project_id);
            mergedProjects.push(project);
          }
          mergedPoints.push(...r.points.filter((point) => seen.has(point.project_id)));
        }
        setReady(true);
        setProjects(mergedProjects);
        setPoints(mergedPoints);
        setHiddenCompleted(hidden);
        setFailedDistricts(failed.filter((d): d is string => d !== null));
        setTruncated(ok.some(([, r]) => r.truncated));
        // 자치구별 응답 중 가장 최근 확인일을 쓴다. 수집은 25개 자치구를 함께 돌기 때문이다.
        const known = ok.map(([, r]) => r.freshness).filter((f): f is FreshnessBlock => !!f);
        setFreshness(known.length ? known.reduce((a, b) => ((b.latest ?? "") > (a.latest ?? "") ? b : a)) : null);
        setDbReflected(ok.map(([, r]) => r.db_reflected_latest ?? null).filter((d): d is string => !!d).sort().pop() ?? null);
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        setWaking(false);
        // 실패한 조회를 '데이터 0건'으로 보이게 두지 않는다. 오류는 오류로만 보여야 한다.
        setReady(false);
        setError(
          isTransient(e) ? "서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요." : (e as Error).message,
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [includeCompleted, scopeKey, dataRevision]);

  const search = keyword.trim();
  const selectedDistricts = useMemo(() => new Set(scope), [scope]);
  const visible = useMemo(
    () => filterProjects(projects, { districts: selectedDistricts, filter, stageFilter, search }),
    [projects, selectedDistricts, filter, stageFilter, search],
  );
  // 진행단계는 응답에 실제로 있는 값만 제공한다. 단계를 추정하지 않는다.
  const stages = useMemo(() => distinctStages(projects), [projects]);
  // 목록에 보이는 사업만 marker가 된다. 좌표가 없는 사업은 목록에 남고 marker만 없다.
  const visiblePoints = useMemo(() => pickVisiblePoints(points, visible), [points, visible]);
  // 지역·유형을 고르지 않은 기본 상태의 분모는 API가 가진 전체 사업이다.
  const inRegion = useMemo(
    () => (selectedDistricts.size === 0 ? projects : projects.filter((p) => selectedDistricts.has(p.district ?? ""))),
    [projects, selectedDistricts],
  );
  const counts = typeCounts(inRegion, visible.length);
  // 선택은 필터와 무관하다. 목록에 로드된 사업이면 그 행을, 아니면 null(상세 응답이 대신 그린다).
  const selectedRow = useMemo(
    () => (selectedId ? projects.find((p) => p.project_id === selectedId) ?? null : null),
    [projects, selectedId],
  );
  const pointById = useMemo(() => new Map(points.map((point) => [point.project_id, point])), [points]);
  const mappable = visiblePoints.filter((p) => p.latitude != null).length;
  const coordinateless = visible.length - mappable;
  const unavailable = !loading && !error && !ready;

  // 빈 화면에는 세 가지 서로 다른 사정이 있고, 셋 다 같은 문장으로 보이면 안 된다.
  //  1) 조회 자체가 실패했다(error / unavailable) — 다시 시도할 일이다.
  //  2) 조회는 정상인데 고른 자치구에 등록된 사업이 0건이다 — 기다릴 일이다.
  //  3) 자치구에는 사업이 있는데 유형·단계·검색어가 다 걸러냈다 — 조건을 바꿀 일이다.
  const coveredDistricts = useMemo(
    () => new Set(projects.map((p) => p.district).filter(Boolean) as string[]),
    [projects],
  );
  const emptyDistricts = useMemo(
    () => [...selectedDistricts].filter((d) => !coveredDistricts.has(d)).sort(),
    [selectedDistricts, coveredDistricts],
  );
  // ready가 true일 때만 쓴다. 응답을 받지 못한 상태를 '0건'이라고 말하지 않는다.
  const noDataForRegion = ready && selectedDistricts.size > 0 && inRegion.length === 0;
  const lastSearch = useRef("");

  return {
    config, seoulOnly, districts, setDistricts, selectedDistricts,
    projects, points, visible, visiblePoints, pointById, inRegion, stages, counts,
    filter, setFilter, keyword, setKeyword, stageFilter, setStageFilter, lastSearch,
    includeCompleted, setIncludeCompleted, hiddenCompleted,
    selectedId, setSelectedId, selectedRow,
    loading, waking, error, ready, unavailable, failedDistricts, truncated, freshness, dbReflected,
    mappable, coordinateless, coveredDistricts, emptyDistricts, noDataForRegion,
  };
}

export type ZiponDevelopment = ReturnType<typeof useZiponDevelopment>;
