import type { Metadata } from "next";
import SiteBrand from "@/components/SiteBrand";
import EstateMonitor from "@/components/realestate/EstateMonitor";

export const metadata: Metadata = {
  title: "ZIP:ON · WAI LABS",
  description: "내 집과 관심지역의 부동산 변화를 한눈에. 실거래가·청약·재개발을 공식 자료로 확인하고 변화를 모니터링합니다.",
};

export default function RealEstatePage() {
  return (
    <main className="mx-auto max-w-[1680px] px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <SiteBrand />
        <span className="text-sm font-semibold text-muted">🏠 ZIP:ON</span>
      </header>

      <EstateMonitor />
    </main>
  );
}
