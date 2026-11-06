"use client";

import type { EstateOptions } from "@/lib/realestate";
import type { MapFocus } from "./ZiponMap";
import ZipDashboard from "./zip/ZipDashboard";

/**
 * 개발지도 탭. 지도 중심 대시보드(ZipDashboard)가 화면을 그린다.
 * 데이터 로딩·필터 로직은 zip/useZiponDevelopment(구 DevelopmentTab의 로직, 동작 변경 없음)로 옮겼다.
 */
export default function DevelopmentTab({
  options,
  property = null,
  onOpenTradeSearch,
}: {
  options: EstateOptions;
  property?: MapFocus;
  onOpenTradeSearch?: () => void;
}) {
  return <ZipDashboard options={options} property={property} onOpenTradeSearch={onOpenTradeSearch} />;
}
