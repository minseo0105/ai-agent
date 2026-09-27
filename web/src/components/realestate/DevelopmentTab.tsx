"use client";

import { useState } from "react";
import { ChoiceChips, Field, Spinner, inputClass } from "@/components/golf/ui";
import DevelopmentCard from "./DevelopmentCard";
import { estateApi, type DevelopmentSearch, type EstateOptions } from "@/lib/realestate";

/** 내 집 주변 재개발·재건축·신속통합기획을 자치구 단위로 찾는다. */
export default function DevelopmentTab({ options }: { options: EstateOptions }) {
  const districts = options.regions.서울.map((r) => r.replace("서울 > ", ""));
  const [district, setDistrict] = useState(districts.includes("강동구") ? "강동구" : districts[0] ?? "");
  const [keyword, setKeyword] = useState("");
  const [result, setResult] = useState<DevelopmentSearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search() {
    if (!district) return setError("자치구를 선택해주세요.");
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await estateApi.development({ sigungu: district, limit: 100 }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const projects = (result?.projects ?? []).filter((p) => {
    const q = keyword.trim();
    if (!q) return true;
    return [p.name, p.address, p.dong, p.stage.label, p.type_label].filter(Boolean).join(" ").includes(q);
  });

  return (
    <div className="space-y-3">
      <Field label="자치구" hint="공식 목록으로 수집한 정비사업을 찾습니다">
        <ChoiceChips accent="estate" options={districts} selected={[district]} onToggle={setDistrict} />
      </Field>
      <button
        type="button"
        onClick={search}
        disabled={loading}
        className="min-h-11 w-full rounded-xl bg-estate py-2.5 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40"
      >
        {district || "자치구"} 개발사업 찾기
      </button>
      {loading && <Spinner label="정비사업 정보를 불러오고 있어요…" />}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {result && !loading && result.status !== "ok" && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-300">
          개발정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}

      {result && !loading && result.status === "ok" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold">
              {district} {result.total}건
              {result.located > 0 && <span className="ml-1 font-semibold text-muted">· 위치 확인 {result.located}건</span>}
            </p>
            <input
              aria-label="사업명 검색"
              placeholder="사업명 · 동 검색"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              className={`${inputClass} max-w-44`}
            />
          </div>
          {result.located === 0 && (
            <p className="rounded-xl bg-surface-muted px-3 py-2 text-xs text-muted">{result.location_notice}</p>
          )}
          {projects.length === 0 && <p className="text-sm text-muted">조건에 맞는 개발사업이 없어요.</p>}
          <div className="grid gap-2.5 md:grid-cols-2">
            {projects.slice(0, 60).map((p) => (
              <DevelopmentCard key={p.project_id} project={p} />
            ))}
          </div>
          <p className="text-[11px] leading-relaxed text-subtle">
            공식 목록에서 수집한 자료입니다. 단계·상태는 상세 확인 전이며 확정된 사실로 보지 말아 주세요. 사업 진행 여부는 공식 출처로
            다시 확인해 주세요.
          </p>
        </div>
      )}
    </div>
  );
}
