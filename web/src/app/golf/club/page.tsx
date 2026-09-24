"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import GolfDetail from "@/components/golf/GolfDetail";
import { Spinner } from "@/components/golf/ui";

// 정적 빌드(서버 한 곳에서 화면·API 제공)를 위해 /golf/[id] 대신 /golf/club?id= 로 연다
function ClubFromQuery() {
  const id = useSearchParams().get("id");
  if (!id) return <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">골프장 정보가 없어요. 검색 화면에서 다시 선택해 주세요.</p>;
  return <GolfDetail id={id} />;
}

export default function GolfClubPage() {
  return (
    <Suspense fallback={<Spinner label="불러오는 중…" />}>
      <ClubFromQuery />
    </Suspense>
  );
}
