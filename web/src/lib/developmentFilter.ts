/**
 * 개발지도 검색·필터. 변경 전 DevelopmentTab의 인라인 코드를 동작 변경 없이 옮긴 것이다.
 * tests/js/development_filter.test.mjs가 변경 전 코드의 사본과 결과를 대조한다.
 */
export const FILTER_OPTIONS = ["전체", "재개발", "재건축", "신속통합기획", "모아타운", "기타 정비사업"] as const;

/** 경기 범위에서만 보이는 유형 칩. 서울 필터 목록(FILTER_OPTIONS)과 그 동작은 바꾸지 않는다. */
export const GYEONGGI_FILTER_OPTIONS = ["소규모정비", "주거환경개선"] as const;

export type FilterableProject = {
  project_id: string;
  name: string;
  address: string | null;
  dong: string | null;
  district: string | null;
  type_label: string;
  program_label: string | null;
  stage: { label: string };
};
export type FilterQuery = { districts: Set<string>; filter: string; stageFilter: string; search: string };

export function matchesFilter(item: { type_label: string; program_label: string | null }, filter: string): boolean {
  if (filter === "전체") return true;
  if (filter === "기타 정비사업") return !["재개발", "재건축", "모아타운"].includes(item.type_label);
  // 경기 소규모주택정비는 BIZ_DIV 세부 유형을 확인하지 못해 한 묶음으로만 거른다.
  if (filter === "소규모정비") return item.program_label === "소규모주택정비";
  return item.type_label === filter || item.program_label === filter;
}

export function filterProjects<T extends FilterableProject>(projects: T[], query: FilterQuery): T[] {
  const { districts, filter, stageFilter, search } = query;
  return projects.filter((p) => {
    if (districts.size > 0 && !districts.has(p.district ?? "")) return false;
    if (!matchesFilter(p, filter)) return false;
    if (stageFilter !== "전체" && p.stage.label !== stageFilter) return false;
    if (!search) return true;
    return [p.name, p.address, p.dong, p.district, p.type_label, p.program_label, p.stage.label]
      .filter(Boolean)
      .join(" ")
      .includes(search);
  });
}

/** 진행단계는 응답에 실제로 있는 값만 제공한다. 단계를 추정하지 않는다. */
export function distinctStages(projects: Array<{ stage: { label: string } }>): string[] {
  return [...new Set(projects.map((p) => p.stage.label))].sort();
}

/** 화면에 보이는 사업의 좌표만 마커 대상이 된다. 좌표가 없는 사업은 목록에 남고 마커만 없다. */
export function visiblePoints<P extends { project_id: string }>(points: P[], visible: Array<{ project_id: string }>): P[] {
  const ids = new Set(visible.map((p) => p.project_id));
  return points.filter((point) => ids.has(point.project_id));
}

/** 유형별 건수는 지역만 적용한 목록(inRegion) 기준이다. total은 화면에 보이는 건수(visibleCount). */
export function typeCounts(inRegion: Array<{ type_label: string; program_label: string | null }>, visibleCount: number) {
  return {
    total: visibleCount,
    재개발: inRegion.filter((p) => p.type_label === "재개발").length,
    재건축: inRegion.filter((p) => p.type_label === "재건축").length,
    신속통합기획: inRegion.filter((p) => p.program_label === "신속통합기획").length,
    모아타운: inRegion.filter((p) => p.type_label === "모아타운").length,
  };
}
