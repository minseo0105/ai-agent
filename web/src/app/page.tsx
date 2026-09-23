import AgentChat from "@/components/AgentChat";
import ServiceGrid from "@/components/ServiceGrid";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 pb-20 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          민서의 AI Lab
        </div>
        <nav className="flex gap-4 text-sm font-semibold text-muted">
          <a href="#services" className="hover:text-fg">서비스</a>
          <a href="#agent" className="hover:text-fg">AI 에이전트</a>
        </nav>
      </header>

      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-950 to-blue-700 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-12">
        <div className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full bg-blue-400/25 blur-3xl" />
        <div className="text-[11px] font-bold tracking-[0.14em] text-blue-200">MINSEO&apos;S AI LAB</div>
        <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
          아이디어를 서비스로 만드는
          <br />
          나만의 AI 실험실
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-blue-100/90 sm:text-base">
          AI Agent · API · Vibe Coding으로 만든 작은 서비스들을 자유롭게 둘러보고 직접 체험해보세요.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {["AI Agent", "API", "Vibe Coding", "Prototype"].map((b) => (
            <span key={b} className="rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold">
              {b}
            </span>
          ))}
        </div>
      </section>

      <section id="services" className="mt-10 scroll-mt-6">
        <h2 className="text-xl font-extrabold tracking-tight">내가 만든 서비스</h2>
        <p className="mb-4 mt-1 text-sm text-muted">새로운 서비스와 직접 만든 AI Prototype을 둘러보세요.</p>
        <ServiceGrid />
      </section>

      <section id="agent" className="mt-10 scroll-mt-6">
        <h2 className="text-xl font-extrabold tracking-tight">AI 에이전트</h2>
        <p className="mb-4 mt-1 text-sm text-muted">공시·법령·웹 검색을 필요한 순간에 호출하는 도구형 에이전트입니다.</p>
        <AgentChat />
      </section>

      <footer className="mt-12 text-center text-xs text-subtle">
        개인적으로 기획하고 직접 구현해보는 AI Prototype 공간입니다.
      </footer>
    </main>
  );
}
