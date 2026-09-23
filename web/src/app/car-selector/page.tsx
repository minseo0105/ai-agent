import type { Metadata } from "next";
import Link from "next/link";
import CarSelector from "@/components/car/CarSelector";

export const metadata: Metadata = {
  title: "차량 선택기 · 민서의 AI Lab",
  description: "세 번의 선택으로 이동 습관과 취향을 분석해 어울리는 차량과 이용 조건을 제안합니다.",
};

export default function CarSelectorPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-20 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          민서의 AI Lab
        </Link>
        <span className="text-sm font-semibold text-muted">🚗 차량 선택기</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-blue-950 to-blue-700 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full border border-white/10" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-blue-200">MY CAR MAKER · PERSONALIZED MOBILITY</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          나의 일상을 읽고,
          <br />
          <span className="text-blue-200">지금 가장 어울리는 차를 만납니다.</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-blue-100/90">세 번의 선택만으로 이동 습관과 취향을 분석해, 나에게 자연스럽게 어울리는 차량과 이용 조건을 제안합니다.</p>
      </section>

      <CarSelector />
    </main>
  );
}
