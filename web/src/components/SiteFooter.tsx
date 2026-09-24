"use client";

import Link from "next/link";
import { useAccess } from "@/components/access/AccessProvider";
import { CREDIT, SITE_NAME } from "@/lib/site";

export default function SiteFooter() {
  const { status, logout } = useAccess();
  const me = status?.me;
  return (
    <footer className="mx-auto max-w-5xl px-4 pb-10 pt-6 text-center sm:px-6">
      <div className="border-t border-border pt-6">
        <div className="text-[13px] font-extrabold tracking-tight text-muted">{SITE_NAME}</div>
        <div className="mt-1 text-[10px] font-semibold tracking-[0.12em] text-subtle">{CREDIT}</div>
        <div className="mt-3 flex items-center justify-center gap-3 text-[11px] text-subtle">
          {me && (
            <>
              <span>
                {me.role === "admin" ? "🛠 관리자" : `👤 ${me.name}`}님으로 이용 중
              </span>
              <button type="button" onClick={logout} className="underline-offset-2 hover:text-fg hover:underline">
                나가기
              </button>
              <span aria-hidden>·</span>
            </>
          )}
          <Link href="/admin" className="underline-offset-2 hover:text-fg hover:underline">
            관리자
          </Link>
        </div>
      </div>
    </footer>
  );
}
