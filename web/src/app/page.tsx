import AgentSection from "@/components/AgentSection";
import ServiceGrid from "@/components/ServiceGrid";
import SiteBrand from "@/components/SiteBrand";
import { SITE_NAME, SITE_SLOGAN, SITE_SUB } from "@/lib/site";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl pb-12 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-4 sm:pl-[max(1.5rem,env(safe-area-inset-left))] sm:pr-[max(1.5rem,env(safe-area-inset-right))] sm:pt-8">
      <header className="mb-5 flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <SiteBrand />
        <nav className="-ml-3 flex gap-2 sm:ml-0 text-sm font-semibold text-muted">
          <a href="#services" className="flex min-h-11 items-center rounded-full px-3 hover:bg-surface-muted hover:text-fg">서비스</a>
          <a href="#agent" className="flex min-h-11 items-center rounded-full px-3 hover:bg-surface-muted hover:text-fg">AI 에이전트</a>
        </nav>
      </header>

      <section className="relative overflow-hidden rounded-[28px] bg-[linear-gradient(135deg,#102a43_0%,#0d3a6b_55%,#0067c8_125%)] px-5 py-5 text-white shadow-[0_12px_32px_-16px_rgba(11,74,158,.5)] sm:px-12 sm:py-12">
        <div aria-hidden className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-[radial-gradient(circle,rgba(125,190,255,.45)_0%,rgba(125,190,255,0)_68%)]" />
        <div aria-hidden className="pointer-events-none absolute -bottom-28 left-1/4 size-80 rounded-full bg-[radial-gradient(circle,rgba(47,140,255,.35)_0%,rgba(47,140,255,0)_70%)]" />
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[linear-gradient(115deg,rgba(255,255,255,.08)_0%,rgba(255,255,255,0)_45%)]" />
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-[13px] font-semibold tracking-[0.12em] text-blue-50">
            <span aria-hidden className="size-1.5 rounded-full bg-sky-300" />
            {SITE_SUB}
          </div>
          <h1 className="mt-3 break-keep font-extrabold tracking-[-0.025em]">
            <span className="block text-[22px] leading-[1.3] sm:text-[32px]">아이디어를 서비스로 만드는 곳,</span>
            <span className="mt-0.5 block text-[44px] leading-[1.05] tracking-[0.01em] text-sky-200 sm:text-[72px]">{SITE_NAME}</span>
          </h1>
          <p className="mt-2.5 text-[20px] font-extrabold tracking-[0.04em] text-white sm:mt-4 sm:text-[26px]">{SITE_SLOGAN}</p>
          <p className="mt-2 max-w-xl break-keep text-[14px] leading-[1.6] text-white/90 sm:text-base">
            AI에게 묻고, 직접 실험하고, 서비스로 구현합니다.
          </p>
          <p className="mt-2 hidden max-w-xl break-keep text-[15px] leading-[1.7] text-white/75 sm:block">
            디지털전략부의 아이디어와 AI 기술이 만나 새로운 업무 방식과 서비스의 가능성을 탐색하는 공간입니다.
          </p>
          <div className="mt-4 flex flex-wrap gap-1.5 sm:mt-6 sm:gap-2">
            {["AI Agent", "API", "Vibe Coding", "Prototype"].map((b) => (
              <span key={b} className="rounded-full border border-white/25 bg-white/10 px-2.5 py-1 text-[13px] font-semibold text-white sm:px-3">
                {b}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="services" className="mt-10 scroll-mt-6 sm:mt-12">
        <h2 className="text-xl font-extrabold tracking-tight">{SITE_NAME} 서비스</h2>
        <p className="mb-5 mt-1 text-sm text-muted">새로운 서비스와 직접 만든 AI Prototype을 둘러보세요.</p>
        <ServiceGrid />
      </section>

      <AgentSection />
    </main>
  );
}
