"use client";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  full,
  ariaLabel,
}: {
  value: T;
  options: readonly T[] | { value: T; label: string }[];
  onChange: (v: T) => void;
  full?: boolean;
  ariaLabel?: string;
}) {
  const opts = (options as (T | { value: T; label: string })[]).map((o) =>
    typeof o === "string" ? { value: o, label: o } : o,
  );
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={`${full ? "flex w-full" : "inline-flex"} rounded-xl bg-surface-muted p-1`}>
      {opts.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`${full ? "flex-1" : ""} whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-bold transition ${
            value === o.value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ChoiceChips({
  options,
  selected,
  onToggle,
  disabled,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const active = selected.includes(o);
        return (
          <button
            key={o}
            type="button"
            disabled={disabled}
            aria-pressed={active}
            onClick={() => onToggle(o)}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition disabled:opacity-40 ${
              active ? "border-golf bg-golf text-white" : "border-border bg-surface text-muted hover:border-golf/50 hover:text-fg"
            }`}
          >
            {active ? "✓ " : ""}
            {o}
          </button>
        );
      })}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-bold text-muted">
        {label}
        {hint && <span className="ml-1.5 font-medium text-subtle">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export const inputClass =
  "w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm outline-none transition placeholder:text-subtle focus:border-golf/60";

export function Tag({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "golf" | "warn" }) {
  const tones = {
    default: "border-border bg-surface-muted text-muted",
    golf: "border-golf/25 bg-golf-soft text-golf",
    warn: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="size-4 animate-spin rounded-full border-2 border-golf/30 border-t-golf" />
      {label}
    </div>
  );
}
