import type { Metadata } from "next";
import Link from "next/link";
import StockTabs from "@/components/stock/StockTabs";

export const metadata: Metadata = {
  title: "STOCK:ON · 디지털전략부 AI LAB",
  description: "뉴스 한 줄, 연결된 회사까지. AI 해석과 실제 반응 · 지수 · 히트맵 · 등락 상위. 정보 제공용이며 투자 권유가 아닙니다.",
  robots: { index: false, follow: false },
};

export default function StockPage() {
  return (
    <main className="mx-auto max-w-6xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          디지털전략부 AI LAB
        </Link>
        <span className="text-sm font-semibold text-muted">📈 STOCK:ON</span>
      </header>

      {/* 상승(빨강)·하락(파랑)과 겹치지 않는 중립 남색 */}
      <section className="relative mb-3 overflow-hidden rounded-2xl bg-gradient-to-br from-[#0B1B33] via-[#13315C] to-[#1E4E8C] px-4 py-4 text-white shadow-md sm:px-6 sm:py-5">
        <div className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-sky-300/20 blur-3xl" />
        <h1 className="text-xl font-extrabold leading-none tracking-tight sm:text-2xl">STOCK:ON</h1>
        <p className="mt-1.5 text-[15px] font-bold leading-snug sm:text-base">뉴스 한 줄, 연결된 회사까지</p>
        <p className="mt-1 text-[13px] font-semibold text-sky-100/90 sm:text-sm">AI 해석과 실제 반응 · 지수 · 히트맵 · 등락 상위</p>
      </section>

      <StockTabs />
    </main>
  );
}
