"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { inputClass } from "@/components/golf/ui";
import {
  DEFAULT_DELTAS, FORMULA_LINES, compareScenarios, formatManwon, INPUT_KEYS,
  type SimDeltas, type SimInputs, type SimKey, type SimResult,
} from "@/lib/investmentCalc";
import { parseNumberInput } from "@/lib/zipFormat";
import BudgetPanel from "./BudgetPanel";
import { StorageControls, useMoney } from "./MoneyForm";
import { readFin, writeFin } from "@/lib/finStorage";

const FIELDS: { key: SimKey; label: string; unit: string; hint?: string }[] = [
  { key: "purchasePrice", label: "매입가격", unit: "만원", hint: "매도인에게 지급하는 금액. 취득 관련 비용은 따로 입력해요." },
  { key: "appraisedValue", label: "종전자산 감정평가액", unit: "만원", hint: "이 물건의 감정평가 예상액(가정)" },
  { key: "proportionalRate", label: "비례율", unit: "%", hint: "가정값. 예: 100" },
  { key: "memberSalePrice", label: "조합원 분양가", unit: "만원", hint: "분양받을 주택의 조합원 분양가(가정)" },
  { key: "acquisitionCost", label: "취득 관련 비용", unit: "만원", hint: "취득세·중개보수·법무비 등의 합계(매입가격에 넣지 마세요)" },
  { key: "loanAmount", label: "대출금액", unit: "만원" },
  { key: "interestRate", label: "금리(연)", unit: "%" },
  { key: "holdingMonths", label: "보유기간", unit: "개월" },
  { key: "otherCost", label: "기타 비용", unit: "만원" },
  { key: "futureMarketValue", label: "가정 준공 후 시세", unit: "만원", hint: "가정값. 공식 자료가 아니에요." },
];
const LABEL = Object.fromEntries(FIELDS.map((f) => [f.key, f.label])) as Record<SimKey, string>;

const DELTA_FIELDS: { key: keyof SimDeltas; label: string; unit: string }[] = [
  { key: "proportionalRate", label: "비례율", unit: "%p" },
  { key: "salePricePct", label: "조합원 분양가", unit: "%" },
  { key: "marketValuePct", label: "가정 준공 후 시세", unit: "%" },
  { key: "holdingMonths", label: "보유기간", unit: "개월" },
  { key: "interestRate", label: "금리", unit: "%p" },
];

const EMPTY: Record<SimKey, string> = Object.fromEntries(INPUT_KEYS.map((k) => [k, ""])) as Record<SimKey, string>;
type Deltas = { conservative: SimDeltas; optimistic: SimDeltas };
const cloneDeltas = (): Deltas => ({ conservative: { ...DEFAULT_DELTAS.conservative }, optimistic: { ...DEFAULT_DELTAS.optimistic } });
const COLUMNS = [
  { key: "conservative", label: "보수" },
  { key: "base", label: "기준" },
  { key: "optimistic", label: "낙관" },
] as const;

function contributionText(r: SimResult): string {
  if (r.contribution === null) return "입력 필요";
  if (r.contributionKind === "REFUND") return `환급 ${formatManwon(r.refund)}`;
  if (r.contributionKind === "ZERO") return "없음(0원)";
  return `+${formatManwon(r.additionalPayment)}`;
}
function money(value: number | null): string {
  return value === null ? "입력 필요" : formatManwon(value);
}

const ROWS: { label: string; note?: string; get: (r: SimResult) => string; strong?: boolean }[] = [
  { label: "예상 권리가액", note: "참고값 · 총투자금에 더하지 않음", get: (r) => money(r.rightsValue) },
  { label: "추가분담금", note: "분양가 − 권리가액", get: contributionText },
  { label: "금융비용", get: (r) => (r.financeCost === null ? "대출 미입력" : formatManwon(r.financeCost)) },
  { label: "총투자금", get: (r) => money(r.totalInvestment), strong: true },
  { label: "자기자본 투입액", get: (r) => money(r.equity) },
  { label: "가정 손익", note: "가정 시세 − 총투자금", get: (r) => money(r.profit), strong: true },
  { label: "가정 수익률", note: "가정 기반 추정치", get: (r) => (r.roi === null ? "계산 불가" : `${(r.roi * 100).toFixed(1)}%`) },
];

/**
 * 투자금·추가분담금 시뮬레이터. 입력값은 모두 사용자가 정한 가정이며 공식 사업 자료가 아니다.
 * 계산은 lib/investmentCalc(단위 테스트로 관계식·중복 계산 방지 검증)가 하고, 이 화면은 입력과 표시만 한다.
 */
export default function InvestmentSimulator({ projectId, onCeiling }: { projectId: string; onCeiling?: (manwon: number | null) => void }) {
  const storageKey = `zip:sim:v1:${projectId}`;
  const [values, setValues] = useState<Record<SimKey, string>>(EMPTY);
  const [deltas, setDeltas] = useState<Deltas>(cloneDeltas);
  const loaded = useRef<string | null>(null);
  const prevKey = useRef<string | null>(null);
  const prevCleared = useRef<number | null>(null);
  const current = useRef(values);
  current.current = values;
  const moneyState = useMoney();
  const { consent, consentAt, clearedAt } = moneyState;

  // 사업별 입력은 '금융 입력값 저장'에 동의했을 때만 이 브라우저에 저장·복원한다(lib/finStorage).
  // 지우기를 누르면 화면 값도 비운다. 동의를 켤 때 화면에 입력값이 있으면 화면 값이 우선한다.
  useEffect(() => {
    loaded.current = null;
    const switched = prevKey.current !== storageKey;
    const cleared = prevCleared.current !== null && clearedAt !== prevCleared.current;
    prevKey.current = storageKey;
    prevCleared.current = clearedAt;
    const saved = readFin<{ values?: Partial<Record<SimKey, string>>; deltas?: Partial<Deltas> }>(storageKey);
    const typed = INPUT_KEYS.some((k) => current.current[k].trim() !== "");
    if (cleared) {
      setValues(EMPTY);
      setDeltas(cloneDeltas());
    } else if (saved && (switched || !typed)) {
      setValues({ ...EMPTY, ...(saved.values ?? {}) });
      setDeltas({
        conservative: { ...DEFAULT_DELTAS.conservative, ...(saved.deltas?.conservative ?? {}) },
        optimistic: { ...DEFAULT_DELTAS.optimistic, ...(saved.deltas?.optimistic ?? {}) },
      });
    } else if (switched) {
      setValues(EMPTY);
      setDeltas(cloneDeltas());
    }
    loaded.current = storageKey;
  }, [storageKey, consentAt, clearedAt]);
  useEffect(() => {
    if (loaded.current !== storageKey) return;
    writeFin(storageKey, { values, deltas }); // 동의가 없으면 저장하지 않는다.
  }, [values, deltas, storageKey, consent]);

  const inputs = useMemo(
    () => Object.fromEntries(INPUT_KEYS.map((k) => [k, parseNumberInput(values[k])])) as SimInputs,
    [values],
  );
  const scenarios = useMemo(() => compareScenarios(inputs, deltas), [inputs, deltas]);
  const base = scenarios.base.result;
  const filled = INPUT_KEYS.some((k) => values[k].trim() !== "");

  return (
    <div className="space-y-3">
      <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-xs leading-relaxed text-muted">
        입력한 값은 <b className="text-fg">사용자가 정한 가정</b>이며 공식 사업 자료가 아닙니다. 결과는 확정 수익이 아니라
        가정 기반 추정치예요. 비례율·분양가는 사업 진행에 따라 달라질 수 있어요.
      </p>
      <StorageControls state={moneyState} />

      <section aria-label="입력값" className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {FIELDS.map((field) => {
          const invalid = base.invalid.includes(field.key);
          return (
            <label key={field.key} className="block text-xs">
              <span className="mb-0.5 flex items-baseline justify-between gap-2 font-bold">
                {field.label}
                <span className="font-semibold text-subtle">{field.unit}</span>
              </span>
              <input
                inputMode="decimal"
                value={values[field.key]}
                onChange={(e) => setValues((v) => ({ ...v, [field.key]: e.target.value }))}
                aria-invalid={invalid}
                aria-label={`${field.label} (${field.unit})`}
                placeholder="입력"
                className={`${inputClass} w-full ${invalid ? "border-red-500" : ""}`}
              />
              {invalid ? (
                <span className="mt-0.5 block text-[11px] text-red-600 dark:text-red-400">0 이상의 숫자만 입력할 수 있어요.</span>
              ) : (
                field.hint && <span className="mt-0.5 block text-[11px] leading-snug text-subtle">{field.hint}</span>
              )}
            </label>
          );
        })}
      </section>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setValues(EMPTY)}
          disabled={!filled}
          className="min-h-9 rounded-xl border border-border px-3 text-xs font-bold text-muted transition enabled:hover:text-fg disabled:opacity-40"
        >
          입력 지우기
        </button>
      </div>

      <BudgetPanel sim={inputs} result={base} onCeiling={onCeiling} />

      <section aria-label="계산 결과">
        <h3 className="text-[11px] font-extrabold tracking-wide text-muted">시나리오 비교 (같은 계산식)</h3>
        {base.missingRequired.length > 0 && (
          <p role="status" className="mt-1 rounded-lg bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-800 dark:text-amber-300">
            입력이 더 있어야 계산돼요: {base.missingRequired.map((k) => LABEL[k]).join(", ")}
          </p>
        )}
        <div className="mt-1.5 overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[320px] border-collapse text-xs">
            <thead>
              <tr className="bg-surface-muted text-[11px] text-muted">
                <th scope="col" className="px-2 py-1.5 text-left font-bold">항목</th>
                {COLUMNS.map((c) => (
                  <th key={c.key} scope="col" className={`px-2 py-1.5 text-right font-bold ${c.key === "base" ? "text-zip" : ""}`}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label} className="border-t border-border/60">
                  <th scope="row" className="px-2 py-1.5 text-left font-semibold">
                    {row.label}
                    {row.note && <span className="block text-[10px] font-normal text-subtle">{row.note}</span>}
                  </th>
                  {COLUMNS.map((c) => (
                    <td key={c.key} className={`whitespace-nowrap px-2 py-1.5 text-right ${row.strong ? "font-extrabold" : ""} ${c.key === "base" ? "bg-zip-soft/40" : ""}`}>
                      {row.get(scenarios[c.key].result)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {base.missingOptional.length > 0 && base.missingRequired.length === 0 && (
          <p className="mt-1 text-[11px] text-subtle">미입력 항목은 0으로 계산했어요: {base.missingOptional.map((k) => LABEL[k]).join(", ")}</p>
        )}
        {base.warnings.map((w) => (
          <p key={w.code} role="alert" className="mt-1 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
            ⚠ {w.message}
          </p>
        ))}
      </section>

      <details className="rounded-xl border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-bold text-zip">시나리오 조정폭 (예시 가정 · 수정 가능)</summary>
        <p className="mt-1.5 text-[11px] leading-relaxed text-subtle">
          보수·낙관은 기준 입력에 아래 조정폭을 더해 같은 계산식으로 계산해요. 기본값은 예시 가정일 뿐 사실이나 전망이 아닙니다.
        </p>
        <table className="mt-1.5 w-full text-xs">
          <thead>
            <tr className="text-[11px] text-muted">
              <th scope="col" className="py-1 text-left font-bold">항목</th>
              <th scope="col" className="py-1 text-right font-bold">보수</th>
              <th scope="col" className="py-1 text-right font-bold">낙관</th>
            </tr>
          </thead>
          <tbody>
            {DELTA_FIELDS.map((f) => (
              <tr key={f.key} className="border-t border-border/60">
                <th scope="row" className="py-1 text-left font-semibold">
                  {f.label} <span className="font-normal text-subtle">({f.unit})</span>
                </th>
                {(["conservative", "optimistic"] as const).map((name) => (
                  <td key={name} className="py-1 text-right">
                    <input
                      type="number"
                      step="0.5"
                      aria-label={`${name === "conservative" ? "보수" : "낙관"} ${f.label} 조정폭 (${f.unit})`}
                      value={Number.isFinite(deltas[name][f.key]) ? deltas[name][f.key] : ""}
                      onChange={(e) => {
                        const next = e.target.value === "" ? 0 : Number(e.target.value);
                        setDeltas((d) => ({ ...d, [name]: { ...d[name], [f.key]: Number.isFinite(next) ? next : 0 } }));
                      }}
                      className={`${inputClass} w-20 text-right`}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <button
          type="button"
          onClick={() => setDeltas(cloneDeltas())}
          className="mt-2 min-h-9 rounded-xl border border-border px-3 text-xs font-bold text-muted hover:text-fg"
        >
          기본 조정폭으로 되돌리기
        </button>
      </details>

      <details className="rounded-xl border border-border px-3 py-2">
        <summary className="cursor-pointer text-xs font-bold text-zip">계산식 보기</summary>
        <ul className="mt-1.5 space-y-1 text-[11px] leading-relaxed text-muted">
          {FORMULA_LINES.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
