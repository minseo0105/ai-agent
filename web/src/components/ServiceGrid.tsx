"use client";

import { useAccess } from "@/components/access/AccessProvider";
import { SERVICES, serviceLink, type Service } from "@/lib/services";

function LegacyBadge() {
  return (
    <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-subtle">
      기존 버전
    </span>
  );
}

function LockBadge() {
  return (
    <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold text-subtle" title="등록된 분만 이용할 수 있어요">
      🔒 등록자 전용
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
  const { status } = useAccess();
  // 관리자 설정에서 숨긴 서비스는 빼고, 권한이 없는 서비스는 자물쇠 표시 (들어가면 접속 코드 입력 화면)
  const visible = SERVICES.filter((s) => status?.services[s.id]?.visible ?? true);
  const locked = (s: Service) => status?.services[s.id]?.allowed === false;
  const featured = visible.find((s) => s.featured);
  const main = visible.filter((s) => !s.featured && !s.secondary);
  const secondary = visible.filter((s) => s.secondary);

  if (!visible.length) return <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">지금 공개된 서비스가 없어요.</p>;

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
            {locked(featured) && <LockBadge />}
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

      {main.length > 0 && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {main.map((s) => (
            <ServiceLink
              key={s.id}
              service={s}
              className="group flex flex-col rounded-2xl border border-border bg-surface p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-1">
                <span className="flex size-10 items-center justify-center rounded-xl bg-surface-muted text-xl">{s.icon}</span>
                {!s.href && <LegacyBadge />}
                {locked(s) && <span title="등록된 분만 이용할 수 있어요">🔒</span>}
              </div>
              <div className="mt-3 text-[15px] font-bold leading-snug">{s.title}</div>
              <p className="mt-1 hidden text-xs leading-relaxed text-muted sm:block">{s.desc}</p>
            </ServiceLink>
          ))}
        </div>
      )}

      {secondary.length > 0 && (
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
                {locked(s) && " 🔒"}
              </ServiceLink>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
