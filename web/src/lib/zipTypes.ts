/**
 * 하위 프로젝트 2(경계)·3(실거래)·4(사전진단)·6(매물)이 채울 자리의 타입.
 * 1단계에서는 이 값을 만들어 내는 코드가 없고, 화면은 서버의 connections 상태에 따라
 * "연결되지 않음"을 안내한다. 탭과 컴포넌트가 이 타입을 받도록 미리 정해 두어 화면을 다시 설계하지 않는다.
 */

/** 거래와 개발구역의 위치 관계. 좌표가 정확하지 않으면 구역 내부로 확정하지 않는다. */
export type ZoneRelation = "INSIDE_CONFIRMED" | "NEARBY_ESTIMATED" | "UNKNOWN";

export type ZoneTrade = {
  trade_id: string;
  property_type: string; // 아파트·연립·다세대·단독·다가구·토지 등 실제 연동된 유형만
  price_manwon: number;
  contract_date: string; // 계약일
  area_m2: number | null;
  floor: string | null;
  build_year: string | null;
  location_quality: "EXACT" | "DONG_ONLY" | "UNKNOWN"; // 위치 정보의 정확도
  zone_relation: ZoneRelation;
  source: string;
  collected_at: string;
};

/** 거래·권리 사전진단 결과(하위 프로젝트 4). 정보가 부족하면 '제한사항 미확인'으로 확정하지 않는다. */
export type RightsAssessment = {
  result: "NO_LIMITATION_FOUND" | "NEEDS_CHECK" | "LEGAL_RISK";
  basis: string[]; // 판단 근거
  laws: Array<{ name: string; article: string; effective_from: string }>; // 적용 법령과 시행일
  as_of: string; // 기준일
  missing_info: string[]; // 확인이 필요한 추가 정보
};

/** 현재 판매 중인 매물(하위 프로젝트 6). 호가이며 국토부 실거래가와 화면에서 구분한다. */
export type ListingRecord = {
  listing_id: string;
  listing_type: string;
  asking_price_manwon: number;
  address: string;
  latitude: number | null;
  longitude: number | null;
  exclusive_area_m2: number | null;
  land_share_m2: number | null;
  agency: string | null;
  registered_at: string;
  confirmed_at: string | null;
  source_url: string | null;
  provider: string;
  rights_check: "UNCHECKED" | "CHECKED";
};
