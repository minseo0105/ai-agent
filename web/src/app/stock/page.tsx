import type { Metadata } from "next";
import SiteBrand from "@/components/SiteBrand";
import StockTabs from "@/components/stock/StockTabs";

export const metadata: Metadata = {
  title: "STOCK:ON · WAI LABS",
  description: "뉴스 한 줄, 연결된 회사까지. AI 해석과 실제 등락 · 지수 · 히트맵 · 등락 상위. 정보 제공용이며 투자 권유가 아닙니다.",
  robots: { index: false, follow: false },
};

export default function StockPage() {
  // stockon-theme: 이 화면이 열려 있는 동안만 페이지 배경·사이트 푸터까지 어두운 남색(globals.css)
  return (
    <main className="stockon-theme mx-auto max-w-6xl px-4 pb-10 pt-4 text-fg sm:px-6 sm:pt-6">
      <header className="flex items-center justify-between">
        <SiteBrand dark />
        <span className="text-sm font-semibold text-slate-400">📈 STOCK:ON</span>
      </header>

      {/* 카드로 띄우지 않고 페이지 배경 위에 바로. 상승(빨강)·하락(파랑)과 겹치지 않는 중립 남색 */}
      <section className="relative pb-4 pt-5 sm:pb-5 sm:pt-7">
        <div className="pointer-events-none absolute -left-10 -top-6 size-56 rounded-full bg-sky-500/10 blur-3xl" />
        <h1 className="relative flex items-center gap-2 text-2xl font-extrabold leading-none tracking-tight text-white sm:text-3xl">
          STOCK:ON
          <span className="rounded-full px-2 py-0.5 text-[10px] font-extrabold tracking-[0.14em] text-amber-200 ring-1 ring-amber-200/40 sm:text-[11px]">PROTOTYPE</span>
        </h1>
        <p className="relative mt-2 text-[16px] font-bold leading-snug text-slate-100 sm:text-lg">뉴스 한 줄, 연결된 회사까지</p>
        <p className="relative mt-1 text-[13px] font-semibold text-slate-400 sm:text-sm">AI 해석과 실제 등락 · 지수 · 히트맵 · 등락 상위</p>
      </section>

      <StockTabs />
    </main>
  );
}
