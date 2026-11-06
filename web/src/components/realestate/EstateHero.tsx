/** ZIP:ON 소개 배너. 개발지도 대시보드에서는 상단 툴바가 그 역할을 해서 숨긴다. */
export default function EstateHero() {
  return (
    <section className="relative mb-3 overflow-hidden rounded-2xl bg-gradient-to-br from-[#25070B] via-[#64131D] to-[#B42332] px-4 py-4 text-white shadow-md sm:px-6 sm:py-5">
      <div className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-rose-300/20 blur-3xl" />
      <h1 className="text-xl font-extrabold leading-none tracking-tight sm:text-2xl">ZIP:ON</h1>
      <p className="mt-1.5 text-sm font-bold leading-snug sm:text-base">내 집과 관심지역의 부동산 변화를 한눈에</p>
      <p className="mt-1 text-[11px] font-semibold text-rose-100/80 sm:text-xs">실거래 · 청약 · 개발사업 · 관심지역 모니터링</p>
    </section>
  );
}
