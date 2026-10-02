"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { recordPageView } from "@/lib/analytics";

export default function UsageTracker() {
  const pathname = usePathname();
  useEffect(() => {
    if (pathname) recordPageView(pathname);
  }, [pathname]);
  return null;
}
