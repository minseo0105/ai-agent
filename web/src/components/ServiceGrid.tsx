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
  const box = "size-11 shrink-0 rounded-xl";
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
    <img src={service.image} alt="" loading="lazy" decoding="async" width={44} height={44} onError={() => setFailed(true)} className={`${box} object-cover`} />
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3 shrink-0 transition group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
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
              className="group flex min-h-[156px] min-w-0 flex-col rounded-2xl border border-border bg-surface p-4 transition duration-200 hover:border-woori/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-woori active:bg-surface-muted"
            >
              <div className="break-keep text-[15px] font-bold leading-snug tracking-tight">
                {name}
                {locked(s) && <span className="ml-1 text-xs" title="등록된 분만 이용할 수 있어요">🔒</span>}
              </div>
              <p className="mt-1 line-clamp-2 break-keep text-xs leading-relaxed text-muted">{tagline ? `${tagline} · ${s.desc}` : s.desc}</p>
              <div className="mt-auto flex items-end justify-between gap-2 pt-3">
                <span className="flex min-w-0 items-center gap-1 text-[11px] font-semibold text-subtle transition group-hover:text-woori">
                  <span className="truncate">{!s.href ? "기존 버전" : s.category}</span>
                  <ArrowIcon />
                </span>
                <Visual service={s} />
              </div>
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
