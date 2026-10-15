"use client";

import { useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { CATEGORIES, SERVICES, serviceLink, type Service, type ServiceCategory } from "@/lib/services";

type Filter = "전체" | ServiceCategory;
const FILTERS: Filter[] = ["전체", ...CATEGORIES];

/** "이름 · 한 줄 소개" 형태의 제목을 이름과 소개로 나눈다. 구분자가 없으면 제목만 쓴다. */
function splitTitle(title: string): { name: string; tagline?: string } {
  const i = title.indexOf(" · ");
  return i < 0 ? { name: title } : { name: title.slice(0, i), tagline: title.slice(i + 3) };
}

/** 이미지는 장식이다(서비스명·설명은 HTML 텍스트). 로드에 실패하면 같은 자리에 단색 대체 면을 보인다. */
function Visual({ service, className }: { service: Service; className: string }) {
  const [failed, setFailed] = useState(false);
  // WebP가 실패하면 기존 SVG로 한 번 더 시도하고, 그것도 실패하면 단색 대체 면을 보인다.
  const [src, setSrc] = useState(service.image);
  if (failed) {
    return (
      <div className={`${className} flex items-center justify-center bg-gradient-to-br from-navy to-woori text-3xl`} aria-hidden>
        <span className="opacity-90">{service.icon}</span>
      </div>
    );
  }
  return (
    // 정적 내보내기(unoptimized)라 next/image 대신 img를 쓴다. SVG는 이미 경량이다.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      width={640}
      height={480}
      onError={() => (service.imageFallback && src !== service.imageFallback ? setSrc(service.imageFallback) : setFailed(true))}
      className={`${className} object-cover`}
    />
  );
}

function Badges({ service, locked }: { service: Service; locked: boolean }) {
  if (service.href && !locked) return null;
  return (
    <span className="absolute right-2 top-2 flex gap-1">
      {!service.href && <span className="rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-slate-700">기존 버전</span>}
      {locked && (
        <span className="rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-slate-700" title="등록된 분만 이용할 수 있어요">
          🔒 등록자 전용
        </span>
      )}
    </span>
  );
}

function ArrowIcon() {
  return (
    <span
      aria-hidden
      className="flex size-7 shrink-0 items-center justify-center rounded-full border border-border text-muted transition group-hover:border-woori group-hover:bg-woori group-hover:text-white"
    >
      <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3.5 8h9M8.5 4l4 4-4 4" />
      </svg>
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
  const [filter, setFilter] = useState<Filter>("전체");
  // 관리자 설정에서 숨긴 서비스는 빼고, 권한이 없는 서비스는 자물쇠 표시 (들어가면 접속 코드 입력 화면)
  const visible = SERVICES.filter((s) => status?.services[s.id]?.visible ?? true);
  const locked = (s: Service) => status?.services[s.id]?.allowed === false;
  const shown = visible.filter((s) => filter === "전체" || s.category === filter);
  const featured = shown.find((s) => s.featured);
  const rest = shown.filter((s) => !s.featured);
  const count = (f: Filter) => visible.filter((s) => f === "전체" || s.category === f).length;

  if (!visible.length) return <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">지금 공개된 서비스가 없어요.</p>;

  return (
    <div>
      <div role="group" aria-label="서비스 분류" className="-mx-4 mb-5 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {FILTERS.filter((f) => count(f) > 0).map((f) => {
          const on = filter === f;
          return (
            <button
              key={f}
              type="button"
              aria-pressed={on}
              onClick={() => setFilter(f)}
              className={`min-h-10 shrink-0 rounded-full border px-4 text-[13px] font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-woori ${
                on ? "border-navy bg-navy text-white shadow-sm" : "border-border bg-surface text-muted hover:border-woori/50 hover:text-fg"
              }`}
            >
              {f}
              <span className={`ml-1.5 text-[11px] ${on ? "text-white/70" : "text-subtle"}`}>{count(f)}</span>
            </button>
          );
        })}
      </div>

      <div className="space-y-3 sm:space-y-4">
        {featured && (
          <ServiceLink
            service={featured}
            className="group grid overflow-hidden rounded-3xl border border-border bg-surface shadow-[0_1px_2px_rgba(16,42,67,.06)] transition duration-200 hover:shadow-[0_12px_32px_rgba(16,42,67,.12)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-woori md:grid-cols-[1.4fr_1fr]"
          >
            <div className="relative overflow-hidden">
              <Visual service={featured} className="aspect-video size-full min-h-full w-full transition duration-500 group-hover:scale-[1.02] md:aspect-auto md:h-full" />
              <Badges service={featured} locked={locked(featured)} />
            </div>
            <div className="flex flex-col justify-center p-5 sm:p-7">
              <span className="w-fit rounded-full bg-woori/10 px-2.5 py-0.5 text-[11px] font-bold text-woori">대표 서비스</span>
              <h3 className="mt-3 break-keep text-2xl font-extrabold leading-tight tracking-tight sm:text-[28px]">{splitTitle(featured.title).name}</h3>
              {splitTitle(featured.title).tagline && <p className="mt-1 text-[15px] font-semibold text-woori">{splitTitle(featured.title).tagline}</p>}
              <p className="mt-2.5 break-keep text-sm leading-relaxed text-muted">{featured.desc}</p>
              <div className="mt-3.5 flex flex-wrap gap-1.5">
                {featured.tags?.map((t) => (
                  <span key={t} className="rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-muted">
                    {t}
                  </span>
                ))}
              </div>
              <span className="mt-5 inline-flex min-h-11 w-fit items-center gap-2 rounded-full bg-navy px-5 text-sm font-bold text-white transition group-hover:bg-woori">
                골프장 찾아보기
                <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M3.5 8h9M8.5 4l4 4-4 4" />
                </svg>
              </span>
            </div>
          </ServiceLink>
        )}

        {rest.length > 0 && (
          <div className="grid grid-cols-2 items-stretch gap-3 sm:grid-cols-3 sm:gap-4">
            {rest.map((s) => {
              const { name, tagline } = splitTitle(s.title);
              return (
                <ServiceLink
                  key={s.id}
                  service={s}
                  className="group flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_1px_2px_rgba(16,42,67,.06)] transition duration-200 hover:-translate-y-0.5 hover:border-woori/30 hover:shadow-[0_10px_28px_rgba(16,42,67,.12)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-woori active:scale-[0.99]"
                >
                  <div className="relative overflow-hidden">
                    <Visual service={s} className="aspect-[4/3] w-full transition duration-500 group-hover:scale-[1.03]" />
                    <Badges service={s} locked={locked(s)} />
                  </div>
                  <div className="flex flex-1 flex-col p-3 sm:p-4">
                    <div className="break-keep text-[15px] font-bold leading-snug tracking-tight">{name}</div>
                    <p className="mt-1 line-clamp-2 break-keep text-xs leading-relaxed text-muted">{tagline ? `${tagline} · ${s.desc}` : s.desc}</p>
                    <div className="mt-auto flex items-center justify-between gap-2 pt-3">
                      <span className="truncate text-[11px] font-semibold text-subtle">{s.category}</span>
                      <ArrowIcon />
                    </div>
                  </div>
                </ServiceLink>
              );
            })}
          </div>
        )}

        {!featured && rest.length === 0 && (
          <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">이 분류에 공개된 서비스가 없어요.</p>
        )}
      </div>
    </div>
  );
}
