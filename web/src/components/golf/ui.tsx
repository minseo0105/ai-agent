"use client";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  full,
  ariaLabel,
  disabled,
  disabledReason,
}: {
  value: T;
  options: readonly T[] | { value: T; label: string }[];
  onChange: (v: T) => void;
  full?: boolean;
  ariaLabel?: string;
  /**
   * 지금은 고를 수 없는 선택지. 목록에서 빼지 않고 흐리게 남긴다.
   * 사라지면 사용자는 그 기능이 없다고 생각하고, 왜 없는지도 알 수 없다.
   */
  disabled?: readonly T[];
  disabledReason?: string;
}) {
  const opts = (options as (T | { value: T; label: string })[]).map((o) =>
    typeof o === "string" ? { value: o, label: o } : o,
  );
  const off = (v: T) => (disabled ?? []).includes(v);
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      // 좁은 화면에서 밀려 잘리지 않게 한다. 넘치면 가로로만 스크롤된다.
      className={`${full ? "flex w-full" : "inline-flex"} max-w-full shrink-0 overflow-x-auto rounded-xl bg-surface-muted p-1`}
    >
      {opts.map((o) => {
        const isOff = off(o.value);
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            aria-disabled={isOff || undefined}
            disabled={isOff}
            title={isOff ? disabledReason : undefined}
            onClick={() => !isOff && onChange(o.value)}
            // 손가락으로 누를 수 있는 크기를 지킨다(모바일 최소 40px).
            className={`${full ? "flex-1" : ""} min-h-10 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-bold transition sm:min-h-0 sm:py-1.5 ${
              isOff
                ? "cursor-not-allowed text-subtle opacity-45"
                : value === o.value
                  ? "bg-surface text-fg shadow-sm"
                  : "text-muted hover:text-fg"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function ChoiceChips({
  options,
  selected,
  onToggle,
  disabled,
  labels,
  accent = "golf",
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  disabled?: boolean;
  labels?: Record<string, number>;
  accent?: "golf" | "estate";
}) {
  const activeClass = accent === "estate" ? "border-estate bg-estate text-white" : "border-golf bg-golf text-white";
  const hoverClass = accent === "estate" ? "hover:border-estate/50" : "hover:border-golf/50";
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
              active ? activeClass : `border-border bg-surface text-muted ${hoverClass} hover:text-fg`
            }`}
          >
            {active ? "✓ " : ""}
            {o}
            {labels?.[o] != null && <span className="ml-1 text-xs font-medium opacity-70">{labels[o]}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      {/* 라벨은 본문과 같은 크기로. 12px는 모바일에서 읽기 어려웠다 */}
      <div className="text-sm font-bold text-muted">
        {label}
        {hint && <span className="ml-1.5 text-xs font-medium text-subtle">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export const inputClass =
  "w-full rounded-xl border border-border bg-surface px-3 py-3 text-base outline-none transition placeholder:text-subtle focus:border-golf/60 sm:py-2.5 sm:text-sm";

export function Tag({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "golf" | "warn" }) {
  const tones = {
    default: "border-border bg-surface-muted text-muted",
    golf: "border-golf/25 bg-golf-soft text-golf",
    warn: "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="size-4 animate-spin rounded-full border-2 border-golf/30 border-t-golf" />
      {label}
    </div>
  );
}
