import type { Metadata } from "next";
import Link from "next/link";
import AdminConsole from "@/components/admin/AdminConsole";
import { SITE_NAME, pageTitle } from "@/lib/site";

export const metadata: Metadata = {
  title: pageTitle("관리자 설정"),
  robots: { index: false, follow: false },
};

export default function AdminPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-5 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 text-sm font-extrabold tracking-tight">
          <span className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-slate-900 to-blue-700 text-xs text-white">✦</span>
          {SITE_NAME}
        </Link>
        <span className="text-sm font-semibold text-muted">🛠 관리자</span>
      </header>
      <AdminConsole />
    </main>
  );
}
