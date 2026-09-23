import type { Metadata } from "next";
import Link from "next/link";
import ReportBuilder from "@/components/report/ReportBuilder";

export const metadata: Metadata = {
  title: "보고서 작성기 · 민서의 AI Lab",
  description: "메모를 경영진이 판단할 수 있는 보고서로 재구성합니다. 필요할 때만 DART·법령·웹검색을 활용합니다.",
};

export default function ReportPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-20 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          민서의 AI Lab
        </Link>
        <span className="text-sm font-semibold text-muted">📄 보고서 작성기</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-[#08152D] via-[#102B59] to-[#3156C8] px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-blue-400/25 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-blue-200">EXECUTIVE REPORT BUILDER</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          정보를 찾는 데서 끝내지 않고,
          <br />
          <span className="text-blue-200">경영진이 읽을 수 있는 보고서로.</span>
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-blue-100/90">
          핵심 메시지 → 주요 근거 → 시사점 → 실행 제안 순서로 재구성합니다. 기본은 빠른 작성이며, 필요할 때만 DART 공시·법령·웹 검색을 활용합니다.
        </p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {["Executive Summary", "DART", "법령정보", "Web Search", "Decision & Action"].map((c) => (
            <span key={c} className="rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-semibold">
              {c}
            </span>
          ))}
        </div>
      </section>

      <ReportBuilder />
    </main>
  );
}
