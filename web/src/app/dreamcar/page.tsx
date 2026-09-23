import type { Metadata } from "next";
import Link from "next/link";
import DreamCarFlow from "@/components/dreamcar/DreamCarFlow";

export const metadata: Metadata = {
  title: "내 차에서 드림카까지 · 민서의 AI Lab",
  description: "내 차의 가치를 확인하고, 라이프스타일로 다음 차를 추천받아 교체 견적까지 한 번에 확인하세요.",
};

export default function DreamCarPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-20 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          민서의 AI Lab
        </Link>
        <span className="text-sm font-semibold text-muted">🚙 드림카</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-indigo-950 to-indigo-700 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-indigo-400/25 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-indigo-200">MY CAR CHANGE JOURNEY</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          지금 타는 차의 가치에서,
          <br />
          <span className="text-indigo-200">다음 드림카까지 연결합니다.</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-indigo-100/90">
          내 차의 현재 가치를 확인하고, 라이프스타일로 새 차를 추천받은 뒤 시세를 반영한 교체 필요금액과 월 할부금까지 한 번에 확인해 보세요.
        </p>
      </section>

      <DreamCarFlow />
    </main>
  );
}
