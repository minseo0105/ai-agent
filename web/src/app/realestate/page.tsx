import type { Metadata } from "next";
import Link from "next/link";
import EstateMonitor from "@/components/realestate/EstateMonitor";

export const metadata: Metadata = {
  title: "부동산 모니터 · 디지털전략부 AI LAB",
  description: "서울·경기 청약과 실거래를 조건별로 조회하고, 관심지역의 새 변화를 자동으로 알려줍니다.",
};

export default function RealEstatePage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          디지털전략부 AI LAB
        </Link>
        <span className="text-sm font-semibold text-muted">🏠 부동산 모니터</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-[#25070B] via-[#64131D] to-[#B42332] px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-rose-300/20 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-rose-200">REAL ESTATE MONITORING AGENT</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          내가 기다리던 청약과 부동산 변화,
          <br />
          놓치지 않도록.
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-rose-100/90">
          서울·경기의 청약과 아파트·빌라·단독/다가구·오피스텔 실거래를 조건별로 조회하고, 관심지역의 새로운 변화를 자동으로 탐지합니다.
        </p>
      </section>

      <EstateMonitor />
    </main>
  );
}
