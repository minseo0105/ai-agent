import GolfSearch from "@/components/golf/GolfSearch";

export default function GolfPage() {
  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-950 via-emerald-800 to-green-600 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-green-300/20 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.14em] text-emerald-200">AI GOLF FINDER</div>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">골프장 찾기</h1>
        <p className="mt-2 text-sm text-emerald-100">수도권 · 충청권 · 강원권 · AI 맞춤추천</p>
      </section>
      <GolfSearch />
    </div>
  );
}
