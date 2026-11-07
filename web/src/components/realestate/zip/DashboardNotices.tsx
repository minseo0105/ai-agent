"use client";

import { Spinner } from "@/components/golf/ui";
import type { ZiponDevelopment } from "./useZiponDevelopment";

/** 로딩·오류·오래된 데이터·일부 실패를 서로 다른 문구로 구분해 알린다. 빈 화면과 실패를 같은 문장으로 보이지 않게 한다. */
export default function DashboardNotices({ data }: { data: ZiponDevelopment }) {
  const { loading, waking, error, ready, unavailable, failedDistricts, truncated, includeCompleted, hiddenCompleted, selectedDistricts, projects } = data;
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
      {/* 최신성 경고는 지도 하단 상태 표시줄(MapStatusBar)로 옮겼다. */}
      {data.sido !== "서울" && data.ggStatus.state === "error" && (
        <p role="alert" data-gg-notice="error" className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-xs font-semibold text-amber-800 dark:text-amber-300">
          경기도 정비사업을 불러오지 못했어요({data.ggStatus.message}). 경기 사업이 없는 것이 아니라 조회에 실패한 거예요. 잠시 후 다시 시도해 주세요.
        </p>
      )}
      {data.sido !== "서울" && data.ggStatus.state === "partial" && (
        <p role="status" data-gg-notice="partial" className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-xs text-amber-800 dark:text-amber-300">
          경기도 자료 일부를 받지 못했어요:{" "}
          {Object.entries(data.ggStatus.datasets).filter(([, d]) => d.status !== "OK").map(([k, d]) => `${k === "general" ? "일반 정비사업" : "소규모주택정비"}(${d.code ?? d.status})`).join(", ")}. 받은 자료만 보여 줘요.
        </p>
      )}
      {data.sido !== "서울" && (data.ggStatus.state === "ok" || data.ggStatus.state === "partial") && (
        <p data-gg-notice="basis" className="rounded-xl bg-surface-muted px-3 py-2.5 text-[11px] leading-relaxed text-muted">
          경기 사업은 경기데이터드림 목록 자료예요(판매 중 매물 아님). 원본에 기준일이 없어 수집일만 확인됐고, 검증된 좌표가 없는 사업은 지도에 표시하지 않고 목록에만 보여 줘요.
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
