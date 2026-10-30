"use client";

import Link from "next/link";
import { useAccess } from "@/components/access/AccessProvider";
import { SITE_NAME } from "@/lib/site";

export default function SiteFooter() {
  const { status, logout } = useAccess();
  const me = status?.me;
  return (
    <footer className="mx-auto max-w-5xl px-4 pb-[max(2.5rem,env(safe-area-inset-bottom))] pt-6 text-center sm:px-6">
      <div className="border-t border-border pt-6">
        <div className="text-[15px] font-extrabold tracking-[0.04em] text-fg">{SITE_NAME}</div>
        <div className="mt-0.5 text-[13px] font-semibold text-muted">Digital Strategy AI LAB</div>
        <div className="mt-2 text-[13px] font-bold text-accent">우리를 아니까, 일이 된다.</div>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2 text-[13px] text-muted">
          {me && (
            <>
              <span>
                {me.role === "admin" ? "🛠 관리자" : `👤 ${me.name}`}님으로 이용 중
              </span>
              <button type="button" onClick={logout} className="inline-flex min-h-11 min-w-11 items-center justify-center px-2 underline-offset-2 hover:text-fg hover:underline">
                나가기
              </button>
              <span aria-hidden>·</span>
            </>
          )}
          <Link href="/admin" className="inline-flex min-h-11 min-w-11 items-center justify-center px-2 underline-offset-2 hover:text-fg hover:underline">
            관리자
          </Link>
        </div>
      </div>
    </footer>
  );
}
