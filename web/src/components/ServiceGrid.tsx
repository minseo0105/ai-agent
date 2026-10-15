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
function Visual({ service }: { service: Service }) {
  const [failed, setFailed] = useState(false);
  // WebP가 실패하면 기존 SVG로 한 번 더 시도하고, 그것도 실패하면 단색 대체 면을 보인다.
  const [src, setSrc] = useState(service.image);
  const box = "size-16 shrink-0 rounded-2xl";
  if (failed) {
    return (
      <div className={`${box} flex items-center justify-center bg-surface-muted text-lg`} aria-hidden>
        {service.icon}
      </div>
    );
  }
  return (
    // 정적 내보내기(unoptimized)라 next/image 대신 img를 쓴다.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" loading="lazy" decoding="async" width={72} height={72} onError={() => (service.imageFallback && src !== service.imageFallback ? setSrc(service.imageFallback) : setFailed(true))} className={`${box} object-cover`} />
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5 shrink-0 transition group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3.5 8h9M8.5 4l4 4-4 4" />
    </svg>
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

      <div className="grid grid-cols-2 items-stretch gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
        {shown.map((s) => {
          const { name, tagline } = splitTitle(s.title);
          return (
            <ServiceLink
              key={s.id}
              service={s}
              className="group flex min-h-[176px] min-w-0 flex-col rounded-3xl border border-border bg-surface p-3.5 transition duration-200 hover:-translate-y-0.5 hover:border-woori/40 hover:shadow-[0_8px_24px_-14px_rgba(37,99,235,.35)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-woori active:bg-surface-muted sm:p-4"
            >
              <div className="flex items-start justify-between">
                <Visual service={s} />
                <span className="flex size-7 items-center justify-center rounded-full bg-surface-muted text-muted transition group-hover:bg-woori group-hover:text-white">
                  <ArrowIcon />
                </span>
              </div>
              <div className="mt-2.5 break-keep text-base font-extrabold leading-snug tracking-tight text-slate-950 dark:text-fg">
                {name}
                {locked(s) && <span className="ml-1 text-xs" title="등록된 분만 이용할 수 있어요">🔒</span>}
              </div>
              <p className="mt-1 break-keep text-[13px] leading-[1.5] text-slate-600 dark:text-muted">{tagline ? `${tagline} · ${s.desc}` : s.desc}</p>
              <span className="mt-auto pt-2.5 text-xs font-bold text-woori">{!s.href ? "기존 버전" : s.category}</span>
            </ServiceLink>
          );
        })}
      </div>

      {shown.length === 0 && (
        <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">이 분류에 공개된 서비스가 없어요.</p>
      )}
    </div>
  );
}
