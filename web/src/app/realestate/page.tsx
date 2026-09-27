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

      <section className="relative mb-3 overflow-hidden rounded-2xl bg-gradient-to-br from-[#25070B] via-[#64131D] to-[#B42332] px-4 py-4 text-white shadow-md sm:px-6 sm:py-5">
        <div className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-rose-300/20 blur-3xl" />
        <h1 className="text-xl font-extrabold leading-none tracking-tight sm:text-2xl">ZIP:ON</h1>
        <p className="mt-1.5 text-sm font-bold leading-snug sm:text-base">내 집과 관심지역의 부동산 변화를 한눈에</p>
        <p className="mt-1 text-[11px] font-semibold text-rose-100/80 sm:text-xs">실거래 · 청약 · 개발사업 · 관심지역 모니터링</p>
      </section>

      <EstateMonitor />
    </main>
  );
}
