import type { Metadata } from "next";
import AdminConsole from "@/components/admin/AdminConsole";
import SiteBrand from "@/components/SiteBrand";
import { pageTitle } from "@/lib/site";

export const metadata: Metadata = {
  title: pageTitle("관리자 설정"),
  robots: { index: false, follow: false },
};

export default function AdminPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 pb-10 pt-4 sm:px-6 sm:pt-8">
      <header className="mb-5 flex items-center justify-between">
        <SiteBrand />
        <span className="text-sm font-semibold text-muted">🛠 관리자</span>
      </header>
      <AdminConsole />
    </main>
  );
}
