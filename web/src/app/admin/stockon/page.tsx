import type { Metadata } from "next";
import StockonAdmin from "@/components/admin/StockonAdmin";
import { pageTitle } from "@/lib/site";

export const metadata: Metadata = { title: pageTitle("STOCK:ON 관리"), robots: { index: false, follow: false } };
export default function Page() {
  return <main className="mx-auto max-w-4xl px-4 pt-8 sm:px-6"><StockonAdmin /></main>;
}
