import type { Metadata } from "next";
import Link from "next/link";
import SajuApp from "@/components/saju/SajuApp";

export const metadata: Metadata = {
  title: "AI 사주 · 대운 분석 · 민서의 AI Lab",
  description: "일간 · 반복 십성 · 현재 대운을 연결해 나에게 반복되는 패턴과 지금의 흐름을 읽습니다.",
};

export default function SajuPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-20 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          민서의 AI Lab
        </Link>
        <span className="text-sm font-semibold text-muted">🔮 사주 · 대운</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-violet-950 via-purple-900 to-fuchsia-800 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-fuchsia-400/25 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-violet-200">AI MYEONGRI INSIGHT</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          나에게 반복되는 패턴과
          <br />
          <span className="text-violet-200">지금의 흐름을 읽습니다.</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-violet-100/90">
          일간 · 반복 십성 · 현재 대운을 연결해, ‘나는 어떤 방식으로 일하고 관계 맺는가’를 중심으로 봅니다.
        </p>
      </section>

      <SajuApp />
    </main>
  );
}
