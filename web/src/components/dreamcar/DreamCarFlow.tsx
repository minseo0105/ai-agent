"use client";

import { useEffect, useRef, useState } from "react";
import { Segmented, Spinner, inputClass } from "@/components/golf/ui";
import {
  dreamApi,
  media,
  monthlyInstallment,
  type DreamConfig,
  type OwnedCar,
  type Recommendation,
} from "@/lib/dreamcar";

type Step = "tradein" | "persona" | "result";
type State = {
  step: Step;
  hasCar: boolean | null;
  plate: string;
  owned: OwnedCar | null;
  answers: number[];
  rec: Recommendation | null;
  model: string | null;
  color: string | null;
  months: number;
  deposit: number;
};
const INITIAL: State = {
  step: "tradein",
  hasCar: null,
  plate: "",
  owned: null,
  answers: [],
  rec: null,
  model: null,
  color: null,
  months: 48,
  deposit: 0,
};
const KEY = "dreamcar-flow-v1";
const won = (v: number) => `${Math.round(v).toLocaleString("ko-KR")}만원`;

function FlowBar({ step }: { step: Step }) {
  const current = { tradein: 1, persona: 2, result: 3 }[step];
  const labels = ["내 차 가치 확인", "라이프스타일 분석", "드림카 추천", "교체 견적"];
  return (
    <ol className="grid grid-cols-4 gap-1.5">
      {labels.map((l, i) => {
        const n = Math.min(i + 1, 3);
        const active = current >= n;
        return (
          <li key={l} className={`rounded-xl px-2 py-2 text-center ${active ? "bg-accent text-white" : "bg-surface-muted text-subtle"}`}>
            <div className="text-[10px] font-extrabold tracking-wider">STEP 0{i + 1}</div>
            <div className="text-[11px] font-semibold leading-tight sm:text-xs">{l}</div>
          </li>
        );
      })}
    </ol>
  );
}

export default function DreamCarFlow() {
  const [config, setConfig] = useState<DreamConfig | null>(null);
  const [s, setS] = useState<State>(INITIAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const restored = useRef(false);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    dreamApi.config().then(setConfig).catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) setS({ ...INITIAL, ...(JSON.parse(raw) as State) });
    } catch {}
  }, []);

  useEffect(() => {
    if (!restored.current) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify(s));
    } catch {}
  }, [s]);

  const update = (patch: Partial<State>) => setS((prev) => ({ ...prev, ...patch }));
  const scrollTop = () => requestAnimationFrame(() => topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));

  async function lookup() {
    setError("");
    setBusy(true);
    try {
      update({ owned: await dreamApi.lookup(s.plate) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function answer(optionIndex: number) {
    if (!config) return;
    const answers = [...s.answers, optionIndex];
    if (answers.length < config.questions.length) {
      update({ answers });
      scrollTop();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const rec = await dreamApi.recommend(answers);
      update({ answers, rec, step: "result", model: rec.top[0]?.model ?? null, color: rec.top[0]?.colors[0]?.color ?? null });
      scrollTop();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !config) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!config) return <Spinner label="불러오는 중…" />;

  return (
    <div className="space-y-5">
      <div ref={topRef} className="scroll-mt-4" />
      <FlowBar step={s.step} />
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {/* STEP 1. 내 차 */}
      {s.step === "tradein" && (
        <section className="space-y-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-7">
          <div>
            <div className="text-[11px] font-bold tracking-[0.12em] text-accent">MY CURRENT CAR</div>
            <h2 className="mt-1 text-xl font-extrabold tracking-tight">지금 타고 있는 차가 있으신가요?</h2>
            <p className="mt-1 text-sm text-muted">차량이 있다면 번호판으로 예상 중고차 시세를 확인하고, 없다면 바로 드림카 찾기로 넘어갑니다.</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { v: true, label: "🚘 내 차가 있어요" },
              { v: false, label: "✨ 차량이 없어요" },
            ].map((o) => (
              <button
                key={String(o.v)}
                type="button"
                aria-pressed={s.hasCar === o.v}
                onClick={() => update({ hasCar: o.v, owned: o.v ? s.owned : null })}
                className={`rounded-2xl border px-4 py-4 text-sm font-extrabold transition ${
                  s.hasCar === o.v ? "border-accent bg-accent text-white" : "border-border hover:border-accent/50"
                }`}
              >
                {s.hasCar === o.v ? "✓ " : ""}
                {o.label}
              </button>
            ))}
          </div>

          {s.hasCar === true && (
            <div className="space-y-3">
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  lookup();
                }}
              >
                <input className={inputClass} value={s.plate} onChange={(e) => update({ plate: e.target.value })} placeholder="차량 번호 · 예: 123가4567" />
                <button type="submit" disabled={busy || !s.plate.trim()} className="shrink-0 rounded-xl bg-accent px-4 text-sm font-bold text-white disabled:opacity-40">
                  시세 조회
                </button>
              </form>
              {s.owned && (
                <div className="grid gap-3 rounded-2xl bg-gradient-to-br from-slate-900 to-indigo-900 p-5 text-white sm:grid-cols-2">
                  <div>
                    <div className="text-[10px] font-bold tracking-widest text-indigo-200">MY CAR ESTIMATED VALUE</div>
                    <div className="mt-1 text-lg font-extrabold">{s.owned.model}</div>
                    <div className="text-xs text-indigo-200">
                      {s.owned.plate} · {s.owned.year}년식
                    </div>
                    <div className="mt-3 text-xs text-indigo-200">예상 중고차 시세</div>
                    <div className="text-3xl font-extrabold">{won(s.owned.market)}</div>
                  </div>
                  <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-1">
                    {[
                      ["주행거리", `${s.owned.mileage.toLocaleString("ko-KR")} km`],
                      ["시세범위", `${s.owned.range_low.toLocaleString("ko-KR")} ~ ${won(s.owned.range_high)}`],
                      ["차량 상태", s.owned.grade],
                    ].map(([k, v]) => (
                      <div key={k} className="rounded-xl bg-white/10 px-3 py-2">
                        <dt className="text-[11px] text-indigo-200">{k}</dt>
                        <dd className="font-bold">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
              <p className="text-[11px] text-subtle">현재 차량 조회와 시세는 프로토타입 시연용 데이터입니다. 실제 서비스에서는 차량등록정보·중고차 시세 API로 교체할 수 있어요.</p>
            </div>
          )}
          {s.hasCar === false && <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">보상판매 금액 없이 신차 전체 가격을 기준으로 견적을 계산합니다.</p>}

          {s.hasCar !== null && (
            <button
              type="button"
              onClick={() => {
                update({ step: "persona", answers: [], ...(s.hasCar ? {} : { owned: null }) });
                scrollTop();
              }}
              className="w-full rounded-xl bg-accent py-3 text-sm font-extrabold text-white transition hover:brightness-110"
            >
              {s.hasCar && !s.owned ? "조회 없이 드림카 찾기 →" : "내 드림카 찾기 시작 →"}
            </button>
          )}
        </section>
      )}

      {/* STEP 2. 라이프스타일 질문 */}
      {s.step === "persona" && (() => {
        const idx = Math.min(s.answers.length, config.questions.length - 1);
        const q = config.questions[idx];
        return (
          <section className="space-y-4">
            <div className="rounded-3xl border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="tracking-widest text-accent">MY DREAM CAR SIGNAL {idx + 1}</span>
                <span className="text-muted">
                  {idx + 1} / {config.questions.length}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${((idx + 1) / config.questions.length) * 100}%` }} />
              </div>
              <h2 className="mt-4 text-xl font-extrabold tracking-tight">{q.title}</h2>
              <p className="text-sm text-muted">{q.desc}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {q.options.map((o, i) => (
                <button
                  key={o.label}
                  type="button"
                  disabled={busy}
                  onClick={() => answer(i)}
                  className="group overflow-hidden rounded-3xl border border-border bg-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md disabled:opacity-60"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={media(o.art)} alt="" loading="lazy" className="aspect-[4/3] w-full bg-surface-muted object-cover" />
                  <div className="p-4">
                    <div className="font-extrabold">{o.label}</div>
                    <div className="mt-0.5 text-xs text-muted">{o.desc}</div>
                    <div className="mt-2 text-xs font-bold text-accent transition group-hover:translate-x-0.5">이 선택으로 진행 →</div>
                  </div>
                </button>
              ))}
            </div>
            {busy && <Spinner label="라이프스타일을 분석하고 있어요…" />}
            <button
              type="button"
              onClick={() => (s.answers.length ? update({ answers: s.answers.slice(0, -1) }) : update({ step: "tradein" }))}
              className="text-sm font-semibold text-muted hover:text-fg"
            >
              ← 이전
            </button>
          </section>
        );
      })()}

      {/* STEP 3/4. 추천 + 견적 */}
      {s.step === "result" && s.rec && (() => {
        const rec = s.rec;
        const car = rec.top.find((t) => t.model === s.model) ?? rec.top[0];
        const color = car.colors.find((c) => c.color === s.color) ?? car.colors[0];
        const tradein = s.owned?.market ?? 0;
        const replacement = Math.max(color.price - tradein, 0);
        const depositAmount = Math.round((replacement * s.deposit) / 100);
        const principal = Math.max(replacement - depositAmount, 0);
        const { monthly, interest } = monthlyInstallment(principal, s.months, config.apr);

        return (
          <section className="space-y-5">
            <div className="flex flex-col gap-4 overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-indigo-800 p-5 text-white shadow-lg sm:flex-row sm:items-center sm:p-7">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={media(rec.persona.art)} alt="" className="aspect-square w-full max-w-40 rounded-2xl object-cover sm:w-40" />
              <div>
                <div className="text-[10px] font-bold tracking-widest text-indigo-200">YOUR MOBILITY PERSONA</div>
                <div className="mt-1 text-2xl font-extrabold tracking-tight">{rec.persona.name}</div>
                <div className="text-sm font-semibold text-indigo-100">{rec.persona.sub}</div>
                <p className="mt-2 text-sm leading-relaxed text-indigo-100/90">{rec.persona.copy}</p>
                <p className="mt-2 text-sm italic text-indigo-200">{rec.persona.quote}</p>
              </div>
            </div>

            <div>
              <h2 className="text-lg font-extrabold tracking-tight">당신에게 가장 잘 맞는 드림카 TOP 3</h2>
              <p className="text-xs text-muted">총 {rec.total_models}개 차종을 비교해 가장 적합한 3대만 추천했어요. 카드를 눌러 견적을 바꿔 보세요.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                {rec.top.map((t, i) => {
                  const selected = t.model === car.model;
                  return (
                    <button
                      key={t.model}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => update({ model: t.model, color: t.colors[0]?.color ?? null })}
                      className={`overflow-hidden rounded-3xl border bg-surface text-left shadow-sm transition hover:-translate-y-0.5 ${
                        selected ? "border-accent ring-2 ring-accent/30" : "border-border hover:border-accent/40"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={media(t.colors[0]?.image)} alt={t.model} loading="lazy" className="aspect-[16/10] w-full bg-surface-muted object-cover" />
                      <div className="flex items-start justify-between gap-2 p-4">
                        <div className="min-w-0">
                          <div className="text-[10px] font-extrabold tracking-widest text-accent">
                            TOP {i + 1}
                            {selected ? " · 선택됨" : ""}
                          </div>
                          <div className="truncate font-extrabold">{t.model}</div>
                          <div className="text-xs text-muted">{t.tagline}</div>
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="text-lg font-extrabold text-accent">{t.match}%</div>
                          <div className="text-[11px] text-muted">{won(t.price)}</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="overflow-hidden rounded-3xl border border-border bg-surface shadow-sm">
              <div className="flex items-start justify-between gap-3 p-5 sm:p-6">
                <div>
                  <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[10px] font-extrabold tracking-widest text-accent">YOUR DREAM CAR</span>
                  <div className="mt-2 text-2xl font-extrabold tracking-tight">{car.model}</div>
                  <div className="text-xs text-muted">
                    {[car.segment, car.seats].filter(Boolean).join(" · ")} · 내 라이프스타일에 가장 잘 맞는 선택
                  </div>
                </div>
                <div className="rounded-2xl bg-accent-soft px-3 py-2 text-center">
                  <div className="text-[9px] font-extrabold tracking-widest text-accent">LIFESTYLE MATCH</div>
                  <div className="text-2xl font-extrabold text-accent">{car.match}%</div>
                </div>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {color.image ? <img src={media(color.image)} alt={`${car.model} ${color.color}`} className="aspect-[16/9] w-full bg-surface-muted object-cover" /> : null}
              <div className="grid grid-cols-3 gap-2 p-5 sm:p-6">
                {car.reasons.map((r, i) => (
                  <div key={r} className="rounded-2xl bg-surface-muted px-3 py-2.5">
                    <div className="text-[9px] font-extrabold tracking-widest text-accent">MATCH 0{i + 1}</div>
                    <div className="text-xs font-bold leading-snug sm:text-sm">{r}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
              <div>
                <h3 className="text-base font-extrabold">내 견적 조건</h3>
                <p className="text-xs text-muted">색상 · 할부기간 · 보증금을 고르면 월 할부금이 바로 다시 계산돼요.</p>
              </div>
              <div className="space-y-1.5">
                <div className="text-xs font-bold text-muted">색상</div>
                <Segmented value={color.color} options={car.colors.map((c) => c.color)} onChange={(v) => update({ color: v })} full ariaLabel="색상" />
              </div>
              <div className="space-y-1.5">
                <div className="text-xs font-bold text-muted">할부기간</div>
                <Segmented
                  value={String(s.months)}
                  options={config.terms.map((t) => ({ value: String(t), label: `${t}개월` }))}
                  onChange={(v) => update({ months: Number(v) })}
                  full
                  ariaLabel="할부기간"
                />
              </div>
              <div className="space-y-1.5">
                <div className="text-xs font-bold text-muted">보증금 <span className="font-medium text-subtle">교체 필요금액 기준</span></div>
                <Segmented
                  value={String(s.deposit)}
                  options={config.deposit_rates.map((d) => ({ value: String(d), label: `${d}%` }))}
                  onChange={(v) => update({ deposit: Number(v) })}
                  full
                  ariaLabel="보증금"
                />
              </div>
            </div>

            <div className="overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 to-indigo-900 p-5 text-white shadow-lg sm:p-7">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <div className="text-[10px] font-bold tracking-widest text-indigo-200">DREAM CAR CHANGE QUOTE</div>
                  <div className="text-sm text-indigo-100">보상판매 반영 예상 월 할부금</div>
                  <div className="mt-1 text-4xl font-extrabold tracking-tight">
                    월 {monthly.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}
                    <span className="text-xl">만원</span>
                  </div>
                </div>
                <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-bold">
                  {s.months}개월 · 연 {config.apr.toFixed(1)}%
                </span>
              </div>
              <dl className="mt-5 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                {[
                  ["신차가격", won(color.price)],
                  ["내 차 시세", won(tradein)],
                  [`보증금 ${s.deposit}%`, won(depositAmount)],
                  ["최종 할부원금", won(principal)],
                  ["현재 차량", s.owned?.model ?? "보유차량 없음"],
                  ["선택 색상", color.color],
                  ["예상 총 이자", won(interest)],
                  ["할부기간", `${s.months}개월`],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl bg-white/10 px-3 py-2">
                    <dt className="text-[11px] text-indigo-200">{k}</dt>
                    <dd className="font-bold">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-[11px] text-indigo-200">※ 프로토타입 기준 · 실제 시세·금리·수수료·신용도·옵션에 따라 달라질 수 있습니다.</p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  update({ step: "persona", answers: [], rec: null, model: null, color: null });
                  scrollTop();
                }}
                className="rounded-xl border border-border py-2.5 text-sm font-bold hover:bg-surface-muted"
              >
                추천 다시 받기
              </button>
              <button
                type="button"
                onClick={() => {
                  setS(INITIAL);
                  scrollTop();
                }}
                className="rounded-xl border border-border py-2.5 text-sm font-bold hover:bg-surface-muted"
              >
                처음부터
              </button>
            </div>
          </section>
        );
      })()}
    </div>
  );
}
