import Link from "next/link";
import { SITE_NAME, SITE_SUB } from "@/lib/site";

/** 모든 화면 헤더의 로고. 'WAI LABS' + 작은 보조 문구. 머니온은 자체 헤더를 쓴다. */
export default function SiteBrand({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" aria-label={`${SITE_NAME} 홈`} className="flex min-h-11 min-w-0 items-center gap-2.5">
      <span
        aria-hidden
        className={`flex size-8 shrink-0 items-center justify-center rounded-[10px] text-[13px] ring-1 ${
          dark ? "bg-white/10 text-sky-200 ring-white/15" : "bg-navy text-white ring-white/10"
        }`}
      >
        ✦
      </span>
      <span className="flex min-w-0 flex-col leading-tight">
        <span className={`text-[17px] font-extrabold tracking-[0.02em] ${dark ? "text-white" : "text-fg"}`}>{SITE_NAME}</span>
        <span className={`truncate text-[13px] font-semibold tracking-[0.06em] sm:tracking-[0.12em] ${dark ? "text-slate-400" : "text-muted"}`}>
          {SITE_SUB}
        </span>
      </span>
    </Link>
  );
}
