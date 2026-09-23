import { SERVICES, serviceLink, type Service } from "@/lib/services";

function LegacyBadge() {
  return (
    <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-subtle">
      기존 버전
    </span>
  );
}

function ServiceLink({ service, className, children }: { service: Service; className: string; children: React.ReactNode }) {
  const { href, external } = serviceLink(service);
  return (
    <a href={href} className={className} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
      {children}
    </a>
  );
}

export default function ServiceGrid() {
  const featured = SERVICES.find((s) => s.featured);
  const main = SERVICES.filter((s) => !s.featured && !s.secondary);
  const secondary = SERVICES.filter((s) => s.secondary);

  return (
    <div className="space-y-3">
      {featured && (
        <ServiceLink
          service={featured}
          className="group relative block overflow-hidden rounded-3xl border border-golf/25 bg-gradient-to-br from-surface to-golf-soft p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md sm:p-6"
        >
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-golf px-2 py-0.5 text-[10px] font-extrabold tracking-wider text-white">NEW</span>
            <span className="text-xs font-bold tracking-wide text-muted">GOLF INTELLIGENCE</span>
            {!featured.href && <LegacyBadge />}
          </div>
          <h3 className="text-xl font-extrabold tracking-tight sm:text-2xl">
            {featured.icon} {featured.title}
          </h3>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{featured.desc}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {featured.tags?.map((t) => (
              <span key={t} className="rounded-full border border-border bg-surface/80 px-2.5 py-1 text-[11px] font-semibold text-muted">
                {t}
              </span>
            ))}
          </div>
          <span className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-golf">
            둘러보기 <span className="transition group-hover:translate-x-0.5">→</span>
          </span>
        </ServiceLink>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {main.map((s) => (
          <ServiceLink
            key={s.id}
            service={s}
            className="group flex flex-col rounded-2xl border border-border bg-surface p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
          >
            <div className="flex items-start justify-between">
              <span className="flex size-10 items-center justify-center rounded-xl bg-surface-muted text-xl">{s.icon}</span>
              {!s.href && <LegacyBadge />}
            </div>
            <div className="mt-3 text-[15px] font-bold leading-snug">{s.title}</div>
            <p className="mt-1 hidden text-xs leading-relaxed text-muted sm:block">{s.desc}</p>
          </ServiceLink>
        ))}
      </div>

      <details className="group rounded-2xl border border-border bg-surface px-4 py-3">
        <summary className="cursor-pointer list-none text-sm font-semibold text-muted marker:hidden">
          기타 도구 <span className="inline-block transition group-open:rotate-90">›</span>
        </summary>
        <div className="mt-3 flex flex-wrap gap-2">
          {secondary.map((s) => (
            <ServiceLink
              key={s.id}
              service={s}
              className="rounded-xl border border-border px-3 py-2 text-sm font-semibold transition hover:border-accent/40 hover:bg-accent-soft"
            >
              {s.icon} {s.title}
            </ServiceLink>
          ))}
        </div>
      </details>
    </div>
  );
}
