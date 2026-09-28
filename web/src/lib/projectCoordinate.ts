/**
 * 사업 좌표를 한 곳에서만 해석한다.
 *
 * 지도(메인/미니)와 카드가 각자 좌표를 꺼내 쓰면 필드 이름이나 숫자 변환이 조금씩
 * 달라지고, 한쪽만 조용히 틀린다. 그래서 필드 매핑·숫자 변환·서울 범위 확인을 여기서
 * 한 번만 한다. 좌표를 만들어내지 않으며, 믿을 수 없으면 null을 돌려준다.
 *
 * 축 규칙: DB와 NAVER geocode는 x=경도, y=위도이고 API는 longitude/latitude로 내려준다.
 * NAVER 지도 SDK는 new naver.maps.LatLng(위도, 경도) 순서다. 이 파일이 그 경계다.
 */
export type ProjectCoordinate = { lat: number; lng: number };

/** 서울 범위. 이 밖의 값은 대표위치로 쓰지 않는다. */
export const SEOUL_LAT = [37.413, 37.715] as const;
export const SEOUL_LNG = [126.734, 127.27] as const;

type CoordinateSource = {
  latitude?: number | string | null;
  longitude?: number | string | null;
} | null | undefined;

function asNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const within = (value: number, [low, high]: readonly [number, number]) => value >= low && value <= high;

/**
 * 좌표가 쓸 수 있는 상태면 {lat, lng}, 아니면 null.
 *
 * 위도와 경도가 뒤바뀐 것처럼 보이면 조용히 교환하지 않고 null을 돌려준다. 교환해서
 * 그리면 엉뚱한 자리에 핀이 꽂히고도 정상처럼 보이기 때문이다.
 */
export function getProjectCoordinate(source: CoordinateSource): ProjectCoordinate | null {
  const lat = asNumber(source?.latitude);
  const lng = asNumber(source?.longitude);
  if (lat === null || lng === null) return null;
  if (within(lat, SEOUL_LAT) && within(lng, SEOUL_LNG)) return { lat, lng };
  return null;
}

/** 진단용: 왜 좌표를 쓸 수 없는지. 화면 문구가 아니라 테스트와 로그를 위한 것이다. */
export function coordinateProblem(source: CoordinateSource): string | null {
  const lat = asNumber(source?.latitude);
  const lng = asNumber(source?.longitude);
  if (lat === null || lng === null) return "NO_COORDINATE";
  if (within(lat, SEOUL_LAT) && within(lng, SEOUL_LNG)) return null;
  if (within(lng, SEOUL_LAT) && within(lat, SEOUL_LNG)) return "SUSPECT_SWAPPED";
  return "OUTSIDE_SEOUL";
}
