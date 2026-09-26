import type { Metadata } from "next";
import Link from "next/link";
import EstateMonitor from "@/components/realestate/EstateMonitor";

export const metadata: Metadata = {
  title: "ZIP:ON · 디지털전략부 AI LAB",
  description: "관심지역의 변화를 켜두세요. 청약부터 실거래까지, 내가 보고 있는 지역의 새로운 변화를 찾아냅니다.",
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

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-[#25070B] via-[#64131D] to-[#B42332] px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-rose-300/20 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-rose-200">Real Estate Signal Agent</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          ZIP:ON
        </h1>
        <p className="mt-3 text-lg font-bold sm:text-xl">관심지역의 변화를 켜두세요.</p>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-rose-100/90">
          청약부터 실거래까지,<br />내가 보고 있는 지역의 새로운 변화를 찾아냅니다.
        </p>
      </section>

      <EstateMonitor />
    </main>
  );
}
