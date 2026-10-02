import type { Metadata } from "next";
import UsageDashboard from "@/components/admin/UsageDashboard";
import { pageTitle } from "@/lib/site";

export const metadata: Metadata = { title: pageTitle("AI LAB 운영현황"), robots: { index: false, follow: false } };

export default function UsagePage() {
  return <main className="mx-auto w-full max-w-4xl px-4 pt-6 sm:px-6 sm:pt-10"><UsageDashboard /></main>;
}
