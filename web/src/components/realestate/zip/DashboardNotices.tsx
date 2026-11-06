"use client";

import { Spinner } from "@/components/golf/ui";
import type { ZiponDevelopment } from "./useZiponDevelopment";

/** 로딩·오류·오래된 데이터·일부 실패를 서로 다른 문구로 구분해 알린다. 빈 화면과 실패를 같은 문장으로 보이지 않게 한다. */
export default function DashboardNotices({ data }: { data: ZiponDevelopment }) {
  const { loading, waking, error, ready, unavailable, failedDistricts, freshness, truncated, includeCompleted, hiddenCompleted, selectedDistricts, projects } = data;
  return (
    <div className="space-y-2 empty:hidden">
      {loading && <Spinner label={waking ? "서버를 깨우는 중이에요…" : "개발정보를 불러오고 있어요…"} />}
      {error && <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!loading && unavailable && (
        <p role="alert" className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-300">
          개발정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}
      {!loading && failedDistricts.length > 0 && (
        <p role="alert" className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-300">
          {failedDistricts.join("·")}의 개발정보를 받지 못했어요. 아래 합계에는 빠져 있습니다.
        </p>
      )}
      {!loading && ready && freshness && freshness.state !== "fresh" && (
        <p role="status" className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-xs text-amber-800 dark:text-amber-300">
          {freshness.label} 지도의 단계와 일정은 현재와 다를 수 있으니 공식 사업정보를 함께 확인해 주세요.
        </p>
      )}
      {!loading && ready && truncated && (
        <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-xs text-muted">
          표시 한도에 닿아 일부만 받았어요. 지역을 선택하면 그 자치구의 사업을 모두 볼 수 있습니다.
        </p>
      )}
      {!loading && ready && (
        <p className="text-[11px] text-subtle">
          {includeCompleted
            ? "완료·취소된 사업을 함께 보고 있어요."
            : hiddenCompleted > 0
              ? `완료된 사업 ${hiddenCompleted}건은 숨겨져 있어요.`
              : "앞으로 변화가 남은 사업만 보고 있어요."}
          {selectedDistricts.size === 0 && ` 서울시 전체 ${projects.length.toLocaleString("ko-KR")}건${truncated ? " 미리보기" : ""}입니다.`}
        </p>
      )}
    </div>
  );
}
