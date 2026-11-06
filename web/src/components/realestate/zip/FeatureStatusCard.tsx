"use client";

import type { ReactNode } from "react";

export type StatusTone = "ok" | "partial" | "off";
export type StatusRow = { label: string; value: string; tone?: StatusTone };

const TONE: Record<StatusTone, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  partial: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  off: "bg-surface-muted text-subtle",
};

/**
 * 아직 구현되지 않았거나 일부만 연결된 기능의 안내. 빈 화면 대신 무엇이 연결됐고 무엇이 안 됐는지,
 * 어떤 기능이 제공될 예정인지, 지금 할 수 있는 일을 보여 준다. 상태는 서버가 알려준 값만 쓴다.
 */
export default function FeatureStatusCard({
  title,
  badge,
  badgeTone,
  rows,
  planned,
  notice,
  action,
}: {
  title: string;
  badge: string;
  badgeTone: StatusTone;
  rows: StatusRow[];
  planned: string[];
  notice?: string;
  action?: ReactNode;
}) {
  return (
    <section aria-label={`${title} 연결 상태`} className="rounded-xl border border-border bg-surface px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-extrabold">{title}</h3>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${TONE[badgeTone]}`}>{badge}</span>
      </div>
      {notice && <p className="mt-1.5 text-xs leading-relaxed text-muted">{notice}</p>}
      <dl className="mt-2 divide-y divide-border/60">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start justify-between gap-3 py-1.5 text-xs">
            <dt className="shrink-0 text-subtle">{row.label}</dt>
            <dd className="flex min-w-0 items-start justify-end gap-1.5 text-right">
              <span className="min-w-0 break-words font-semibold">{row.value}</span>
              {row.tone && <span aria-hidden className={`mt-0.5 size-2 shrink-0 rounded-full ${row.tone === "ok" ? "bg-emerald-500" : row.tone === "partial" ? "bg-amber-500" : "bg-border"}`} />}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-2.5">
        <div className="text-[11px] font-bold text-subtle">제공 예정 기능</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted">
          {planned.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
      {action && <div className="mt-3">{action}</div>}
    </section>
  );
}
