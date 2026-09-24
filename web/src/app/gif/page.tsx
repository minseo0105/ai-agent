import type { Metadata } from "next";
import Link from "next/link";
import GifMaker from "@/components/gif/GifMaker";

export const metadata: Metadata = {
  title: "GIF 변환기 · 디지털전략부 AI LAB",
  description: "배경 제거와 합성부터 달리기 · 줌 · 바운스 · 틸트 · 패닝까지 조합해 차량 이미지를 모션 GIF로 만듭니다.",
};

const CHIPS = ["Background Remove", "Drive Motion", "Zoom", "Bounce", "Tilt", "Boomerang"];

export default function GifPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          디지털전략부 AI LAB
        </Link>
        <span className="text-sm font-semibold text-muted">🎞️ GIF 변환기</span>
      </header>

      <section className="relative mb-5 overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-blue-950 to-blue-700 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full border border-white/10" />
        <div className="text-[11px] font-bold tracking-[0.16em] text-blue-200">MOTION MAKER · IMAGE TO GIF</div>
        <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          정적인 차량 이미지를,
          <br />
          <span className="text-blue-200">짧고 자연스러운 모션 콘텐츠로.</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-blue-100/90">배경 제거와 합성부터 달리기 · 줌 · 흔들림 · 바운스 · 틸트 · 패닝까지 한 화면에서 조합해 GIF를 만들 수 있습니다.</p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {CHIPS.map((c) => (
            <span key={c} className="rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[10px] font-bold text-blue-50">
              {c}
            </span>
          ))}
        </div>
      </section>

      <GifMaker />
    </main>
  );
}
