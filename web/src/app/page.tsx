import AgentSection from "@/components/AgentSection";
import ServiceGrid from "@/components/ServiceGrid";
import { SITE_NAME } from "@/lib/site";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 pb-12 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5 text-sm font-extrabold tracking-tight">
          <span aria-hidden className="flex size-8 items-center justify-center rounded-[10px] bg-navy text-[13px] text-white ring-1 ring-white/10">✦</span>
          {SITE_NAME}
        </div>
        <nav className="flex gap-1 text-sm font-semibold text-muted">
          <a href="#services" className="flex min-h-10 items-center rounded-full px-3 hover:bg-surface-muted hover:text-fg">서비스</a>
          <a href="#agent" className="flex min-h-10 items-center rounded-full px-3 hover:bg-surface-muted hover:text-fg">AI 에이전트</a>
        </nav>
      </header>

      <section className="relative overflow-hidden rounded-3xl bg-navy px-6 py-8 text-white sm:px-10 sm:py-12">
        <div className="relative">
          <div className="text-[11px] font-semibold tracking-[0.12em] text-blue-200/90">DIGITAL STRATEGY · AI LAB</div>
          <h1 className="mt-3 break-keep text-[28px] font-extrabold leading-[1.25] tracking-[-0.02em] sm:text-[40px]">
            아이디어를 서비스로 만드는
            <br />
            {SITE_NAME}
          </h1>
          <p className="mt-4 max-w-xl break-keep text-sm leading-relaxed text-blue-100/85 sm:text-base">
            AI Agent · API · Vibe Coding으로 만든 서비스들을 자유롭게 둘러보고 직접 체험해보세요.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {["AI Agent", "API", "Vibe Coding", "Prototype"].map((b) => (
              <span key={b} className="rounded-full border border-white/20 bg-white/[0.08] px-3 py-1 text-xs font-semibold text-blue-50">
                {b}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="services" className="mt-12 scroll-mt-6">
        <h2 className="text-xl font-extrabold tracking-tight">AI LAB 서비스</h2>
        <p className="mb-5 mt-1 text-sm text-muted">새로운 서비스와 직접 만든 AI Prototype을 둘러보세요.</p>
        <ServiceGrid />
      </section>

      <AgentSection />
    </main>
  );
}
