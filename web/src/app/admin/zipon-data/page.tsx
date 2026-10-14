import type { Metadata } from "next";
import ZiponData from "@/components/admin/ZiponData";
import { pageTitle } from "@/lib/site";

export const metadata: Metadata = { title: pageTitle("ZIP 데이터 최신화"), robots: { index: false, follow: false } };
export default function Page() {
  return <main className="mx-auto max-w-4xl px-4 pt-8 sm:px-6"><ZiponData /></main>;
}
