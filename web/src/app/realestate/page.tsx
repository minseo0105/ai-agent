import type { Metadata } from "next";
import Link from "next/link";
import EstateMonitor from "@/components/realestate/EstateMonitor";

export const metadata: Metadata = {
  title: "ZIP:ON · 디지털전략부 AI LAB",
  description: "내 집과 관심지역의 부동산 변화를 한눈에. 실거래가·청약·재개발을 공식 자료로 확인하고 변화를 모니터링합니다.",
};

export default function RealEstatePage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          디지털전략부 AI LAB
        </Link>
        <span className="text-sm font-semibold text-muted">🏠 ZIP:ON</span>
      </header>

      <section className="relative mb-4 overflow-hidden rounded-3xl bg-gradient-to-br from-[#25070B] via-[#64131D] to-[#B42332] px-5 py-6 text-white shadow-lg sm:px-8 sm:py-8">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-rose-300/20 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-rose-200">부동산 탐색 · 모니터링 에이전트</div>
        <h1 className="mt-1.5 text-2xl font-extrabold leading-tight tracking-tight sm:text-3xl">ZIP:ON</h1>
        <p className="mt-1.5 text-base font-bold leading-snug sm:text-lg">
          내 집과 관심지역의 부동산 변화를 한눈에
        </p>
        <p className="mt-2 max-w-md text-xs leading-relaxed text-rose-100/90 sm:text-sm">
          실거래가 · 청약 · 재개발까지 공식 자료로 확인하고, 관심지역의 새로운 변화를 계속 지켜봅니다.
        </p>
      </section>

      <EstateMonitor />
    </main>
  );
}
