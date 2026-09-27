"use client";

import { useState } from "react";

/** 기본은 접힌 상태. 판단에 필요한 정보만 먼저 보이고 상세는 눌러서 펼친다. */
export default function CollapsibleDetails({
  label = "상세보기",
  openLabel,
  children,
  count,
}: {
  label?: string;
  openLabel?: string;
  children: React.ReactNode;
  count?: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 border-t border-border pt-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex min-h-9 w-full items-center justify-between gap-2 text-left text-xs font-bold text-muted transition hover:text-fg"
      >
        <span>
          {open ? openLabel ?? "상세 접기" : label}
          {!open && count ? ` · ${count}개 항목` : ""}
        </span>
        <span aria-hidden className={`transition ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open && <div className="mt-2 space-y-1.5">{children}</div>}
    </div>
  );
}

/** 라벨·값 한 줄. 모바일에서 라벨 반복이 길어지지 않게 좌우로 나눈다. */
export function DetailRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="flex items-start justify-between gap-3 text-xs">
      <span className="shrink-0 text-subtle">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold">{value}</span>
    </div>
  );
}
