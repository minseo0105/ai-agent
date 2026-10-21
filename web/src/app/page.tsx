import AgentSection from "@/components/AgentSection";
import ServiceGrid from "@/components/ServiceGrid";
import { SITE_NAME } from "@/lib/site";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl pb-12 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-4 sm:pl-[max(1.5rem,env(safe-area-inset-left))] sm:pr-[max(1.5rem,env(safe-area-inset-right))] sm:pt-8">
      <header className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5 text-sm font-extrabold tracking-tight">
          <span aria-hidden className="flex size-8 items-center justify-center rounded-[10px] bg-navy text-[13px] text-white ring-1 ring-white/10">✦</span>
          {SITE_NAME}
        </div>
        <nav className="flex gap-2 text-sm font-semibold text-muted">
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
            DIGITAL STRATEGY · AI LAB
          </div>
          <h1 className="mt-3 break-keep text-[24px] font-extrabold leading-[1.3] tracking-[-0.025em] sm:text-[40px] sm:leading-[1.22]">
            아이디어를 서비스로 만드는
            <br />
            <span className="text-sky-200">{SITE_NAME}</span>
          </h1>
          <p className="mt-2.5 max-w-xl break-keep text-[13px] leading-[1.6] text-white/90 sm:mt-4 sm:text-base">
            AI Agent · API · Vibe Coding으로 만든 서비스들을 자유롭게 둘러보고 직접 체험해보세요.
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
        <h2 className="text-xl font-extrabold tracking-tight">AI LAB 서비스</h2>
        <p className="mb-5 mt-1 text-sm text-muted">새로운 서비스와 직접 만든 AI Prototype을 둘러보세요.</p>
        <ServiceGrid />
      </section>

      <AgentSection />
    </main>
  );
}
