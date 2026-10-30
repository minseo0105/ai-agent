import type { Metadata } from "next";
import Link from "next/link";
import SiteBrand from "@/components/SiteBrand";

export const metadata: Metadata = {
  title: "TEE:PICK · WAI LABS",
  description: "오늘, 어디서 칠까? 지역 · 시간 · 라운드 조건만 고르면 AI가 골프장을 찾아드립니다.",
};

export default function GolfLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-4xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <SiteBrand />
        <Link href="/golf" className="text-sm font-semibold text-muted hover:text-fg">
          ⛳ TEE:PICK
        </Link>
      </header>
      {children}
    </main>
  );
}
