import GolfSearch from "@/components/golf/GolfSearch";

export default function GolfPage() {
  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-950 via-emerald-800 to-green-600 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10">
        <div className="pointer-events-none absolute -right-16 -top-16 size-60 rounded-full bg-green-300/20 blur-3xl" />
        <div className="text-[11px] font-extrabold tracking-[0.2em] text-emerald-200">TEE:PICK</div>
        <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">오늘, 어디서 칠까? ⛳</h1>
        <p className="mt-3 text-sm leading-relaxed text-emerald-100">
          지역 · 시간 · 라운드 조건만 골라주세요.
          <br />
          내 조건에 맞는 골프장을 AI가 찾아드립니다.
        </p>
      </section>
      <GolfSearch />
    </div>
  );
}
