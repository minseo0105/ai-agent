/**
 * 정렬 상태 전이. "출발지를 넣으면 가까운 순"이 어디서 결정되는지 한 곳에 모은다.
 *
 * 이 규칙이 제출 버튼 안의 삼항 연산자 하나로만 있으면, 다른 경로(정렬 버튼·조건 토글·
 * 문장 검색)가 생길 때마다 조용히 어긋난다. 그래서 순수 함수로 꺼내 두고 시험한다.
 *
 * 규칙
 *   1. 출발지가 없으면 기본 정렬이다. 가까운 순이라고 말하지 않는다.
 *   2. 출발지를 처음 넣으면 사용자가 버튼을 누르지 않아도 가까운 순이다.
 *   3. 출발지를 다른 곳으로 바꾸면 다시 가까운 순이다. 새 출발지 기준으로 다시 잰다.
 *   4. 출발지를 지우면 가까운 순을 풀고 기본 정렬로 돌아간다.
 *   5. 같은 출발지에서 사용자가 직접 고른 정렬은 그대로 둔다.
 *
 * 3과 5가 부딪히는 자리에서는 3이 이긴다. 출발지를 새로 넣거나 바꾼 것은 "여기서 가까운
 * 곳을 보고 싶다"는 새 요청이므로, 그 전에 골라 둔 정렬보다 방금의 입력을 따른다.
 */
export type GolfSort = "추천순" | "가까운순" | "가격순";

export const DEFAULT_SORT: GolfSort = "추천순";
export const DISTANCE_SORT: GolfSort = "가까운순";

export type SortInput = {
  /** 지금 화면의 출발지 입력값 */
  origin: string;
  /** 직전 검색에 쓴 출발지. 아직 검색한 적이 없으면 null */
  previousOrigin: string | null;
  /** 지금 화면의 정렬 */
  currentSort: GolfSort;
  /** 사용자가 정렬 버튼으로 직접 고른 상태인지 */
  userChose: boolean;
};

export type SortDecision = {
  sort: GolfSort;
  /** 이번 결정으로 '사용자가 직접 고름' 표시를 이어갈지 */
  keepUserChoice: boolean;
  reason:
    | "NO_ORIGIN_DEFAULT"
    | "NO_ORIGIN_KEEP_USER_CHOICE"
    | "ORIGIN_ENTERED"
    | "ORIGIN_CHANGED"
    | "ORIGIN_SAME_KEEP_USER_CHOICE"
    | "ORIGIN_SAME_DEFAULT_DISTANCE";
};

const clean = (value: string | null | undefined) => (value ?? "").trim();

/** 검색을 시작할 때 어떤 정렬로 보낼지. */
export function decideSort({ origin, previousOrigin, currentSort, userChose }: SortInput): SortDecision {
  const now = clean(origin);
  const before = previousOrigin === null ? null : clean(previousOrigin);

  if (!now) {
    // 출발지가 없으면 거리순은 의미가 없다. 사용자가 고른 다른 정렬(가격순)은 남긴다.
    if (userChose && currentSort !== DISTANCE_SORT) {
      return { sort: currentSort, keepUserChoice: true, reason: "NO_ORIGIN_KEEP_USER_CHOICE" };
    }
    return { sort: DEFAULT_SORT, keepUserChoice: false, reason: "NO_ORIGIN_DEFAULT" };
  }
  if (before === null) {
    return { sort: DISTANCE_SORT, keepUserChoice: false, reason: "ORIGIN_ENTERED" };
  }
  if (before !== now) {
    // 출발지를 바꿨다. 그 전에 골라 둔 정렬보다 방금의 입력을 따른다.
    return { sort: DISTANCE_SORT, keepUserChoice: false, reason: "ORIGIN_CHANGED" };
  }
  if (userChose) {
    return { sort: currentSort, keepUserChoice: true, reason: "ORIGIN_SAME_KEEP_USER_CHOICE" };
  }
  return { sort: DISTANCE_SORT, keepUserChoice: false, reason: "ORIGIN_SAME_DEFAULT_DISTANCE" };
}

/**
 * 서버 응답을 받은 뒤의 정렬. 출발지 좌표를 못 찾았으면 거리순이라고 말하지 않는다.
 * 순서를 바꾸는 것이 아니라, 서버가 실제로 쓴 정렬을 화면이 그대로 말하게 하는 것이다.
 */
export function settleSort(requested: GolfSort, hasDeparture: boolean): GolfSort {
  return requested === DISTANCE_SORT && !hasDeparture ? DEFAULT_SORT : requested;
}
