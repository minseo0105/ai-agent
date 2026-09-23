"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Field, Segmented, Spinner, inputClass } from "@/components/golf/ui";
import { sajuApi, type AiRequest, type BirthInput, type FlowDetail, type SajuOptions, type SajuResult } from "@/lib/saju";

const KEY = "saju-app-v1";
const TABS = ["핵심 해석", "직업·재물·관계", "인생 대운", "AI 명리상담"] as const;
type Tab = (typeof TABS)[number];

type Form = { gender: BirthInput["gender"]; calendar_type: BirthInput["calendar_type"]; year: string; month: string; day: string; time_text: string; lunar_leap: boolean };
type AiState = { text: string; loading: boolean; error: string; truncated: boolean };
type Saved = { form: Form; result: SajuResult | null; tab: Tab; cycleIdx: number; year: number | null; ai: Record<string, AiState> };

const INITIAL_FORM: Form = { gender: "여성", calendar_type: "양력", year: "1985", month: "1", day: "1", time_text: "17:00", lunar_leap: false };
const ELEMENT_TONE: Record<string, string> = {
  목: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  화: "bg-rose-500/12 text-rose-700 dark:text-rose-300",
  토: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  금: "bg-slate-500/12 text-slate-700 dark:text-slate-300",
  수: "bg-sky-500/12 text-sky-700 dark:text-sky-300",
};

/** '**굵게**' 표기만 처리하는 가벼운 렌더러 (정적 해석 문장용) */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i} className="font-bold text-fg">{part}</strong> : <Fragment key={i}>{part}</Fragment>))}
    </>
  );
}

function Card({ title, children, className = "" }: { title?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-border bg-surface p-4 shadow-sm sm:p-5 ${className}`}>
      {title && <h3 className="mb-1.5 text-sm font-extrabold">{title}</h3>}
      <div className="text-sm leading-relaxed text-muted">{children}</div>
    </div>
  );
}

function FlowGrid({ d, labels }: { d: FlowDetail; labels: [string, string, string, string] }) {
  const items: [string, string][] = [
    [labels[0], d.work],
    [labels[1], d.money],
    [labels[2], d.relation],
    [labels[3], d.action],
  ];
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="rounded-2xl bg-surface-muted p-3.5">
          <div className="text-xs font-extrabold">{k}</div>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">{v}</p>
        </div>
      ))}
    </div>
  );
}

function AiPanel({ state, onRun, runLabel, rerunLabel }: { state?: AiState; onRun: () => void; runLabel: string; rerunLabel?: string }) {
  if (!state || (!state.text && !state.loading)) {
    return (
      <div className="space-y-2">
        {state?.error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{state.error}</p>}
        <button type="button" onClick={onRun} className="w-full rounded-xl bg-violet-600 py-2.5 text-sm font-bold text-white transition hover:brightness-110">
          {runLabel}
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-3 rounded-2xl border border-violet-500/25 bg-surface p-4 sm:p-5">
      {state.loading && !state.text && <Spinner label="명식과 대운을 함께 해석하고 있어요… (30초~1분)" />}
      {state.text && (
        <div className="prose-answer">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{state.text}</ReactMarkdown>
        </div>
      )}
      {state.loading && state.text && <Spinner label="작성 중…" />}
      {state.truncated && <p className="text-xs text-amber-600">※ 답변이 길어 일부가 잘렸을 수 있어요. 다시 생성하면 달라질 수 있습니다.</p>}
      {state.error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{state.error}</p>}
      {!state.loading && rerunLabel && (
        <button type="button" onClick={onRun} className="w-full rounded-xl border border-border py-2 text-sm font-bold hover:bg-surface-muted">
          {rerunLabel}
        </button>
      )}
    </div>
  );
}

export default function SajuApp() {
  const [options, setOptions] = useState<SajuOptions | null>(null);
  const [form, setForm] = useState<Form>(INITIAL_FORM);
  const [result, setResult] = useState<SajuResult | null>(null);
  const [tab, setTab] = useState<Tab>("핵심 해석");
  const [cycleIdx, setCycleIdx] = useState(0);
  const [year, setYear] = useState<number | null>(null);
  const [ai, setAi] = useState<Record<string, AiState>>({});
  const [topic, setTopic] = useState("직장·승진");
  const [question, setQuestion] = useState("");
  const [qAnswerKey, setQAnswerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const restored = useRef(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const aborts = useRef<Record<string, AbortController>>({});

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    sajuApi.options().then(setOptions).catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) {
        const s = JSON.parse(raw) as Saved;
        setForm(s.form);
        setResult(s.result);
        setTab(s.tab);
        setCycleIdx(s.cycleIdx);
        setYear(s.year);
        // 진행 중이던 스트리밍은 복원하지 않는다
        setAi(Object.fromEntries(Object.entries(s.ai || {}).filter(([, v]) => v.text && !v.loading)));
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (!restored.current) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ form, result, tab, cycleIdx, year, ai } satisfies Saved));
    } catch {}
  }, [form, result, tab, cycleIdx, year, ai]);

  const input: BirthInput | null = result?.input ?? null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const birth = `${form.year}-${form.month.padStart(2, "0")}-${form.day.padStart(2, "0")}`;
      const r = await sajuApi.analyze({ birth, calendar_type: form.calendar_type, time_text: form.time_text, gender: form.gender, lunar_leap: form.lunar_leap });
      Object.values(aborts.current).forEach((c) => c.abort());
      setResult(r);
      setAi({});
      setTab("핵심 해석");
      setCycleIdx(r.daewoon.current_index);
      setYear(null);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runAi(key: string, extra: Omit<AiRequest, keyof BirthInput>) {
    if (!input) return;
    aborts.current[key]?.abort();
    const ctrl = new AbortController();
    aborts.current[key] = ctrl;
    const patch = (p: Partial<AiState>) => setAi((prev) => ({ ...prev, [key]: { ...(prev[key] ?? { text: "", loading: false, error: "", truncated: false }), ...p } }));
    patch({ text: "", loading: true, error: "", truncated: false });
    try {
      const { truncated } = await sajuApi.ai({ ...input, ...extra }, (t) => setAi((prev) => ({ ...prev, [key]: { ...prev[key], text: (prev[key]?.text ?? "") + t } })), ctrl.signal);
      patch({ loading: false, truncated });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      patch({ loading: false, error: (err as Error).message });
    }
  }

  if (error && !options) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!options) return <Spinner label="불러오는 중…" />;
  if (!options.available) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600">서버에 lunar_python 패키지가 설치되어 있지 않아 명식을 계산할 수 없어요.</p>;

  const maxDay = form.calendar_type === "음력" ? 30 : 31;
  const thisYear = new Date().getFullYear();

  return (
    <div className="space-y-6">
      {/* 입력 */}
      <form onSubmit={submit} className="space-y-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
        <h2 className="text-base font-extrabold">출생 정보</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="성별">
            <Segmented value={form.gender} options={["여성", "남성"] as const} onChange={(v) => setForm({ ...form, gender: v })} full ariaLabel="성별" />
          </Field>
          <Field label="달력">
            <Segmented
              value={form.calendar_type}
              options={["양력", "음력"] as const}
              onChange={(v) => setForm({ ...form, calendar_type: v, lunar_leap: v === "음력" && form.lunar_leap })}
              full
              ariaLabel="달력"
            />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-[1.3fr_1fr]">
          <Field label="생년월일" hint={form.calendar_type === "음력" ? "음력 날짜 그대로" : undefined}>
            <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-2">
              <select className={inputClass} value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} aria-label="출생 연도">
                {Array.from({ length: thisYear - 1930 + 1 }, (_, i) => thisYear - i).map((y) => (
                  <option key={y} value={y}>
                    {y}년
                  </option>
                ))}
              </select>
              <select className={inputClass} value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} aria-label="출생 월">
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {m}월
                  </option>
                ))}
              </select>
              <select className={inputClass} value={Math.min(Number(form.day), maxDay)} onChange={(e) => setForm({ ...form, day: e.target.value })} aria-label="출생 일">
                {Array.from({ length: maxDay }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>
                    {d}일
                  </option>
                ))}
              </select>
            </div>
          </Field>
          <Field label="출생시간" hint="모르면 '모름'">
            <select className={inputClass} value={form.time_text} onChange={(e) => setForm({ ...form, time_text: e.target.value })} aria-label="출생시간">
              {options.times.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {form.calendar_type === "음력" && (
          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={form.lunar_leap} onChange={(e) => setForm({ ...form, lunar_leap: e.target.checked })} className="size-4 accent-violet-600" />
            음력 생일이 윤달이에요
          </label>
        )}
        {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button type="submit" disabled={busy} className="w-full rounded-xl bg-violet-600 py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-50">
          {busy ? "계산 중…" : "명리 분석 시작하기"}
        </button>
      </form>

      {result && (
        <section ref={resultRef} className="scroll-mt-4 space-y-4">
          <div>
            <h2 className="text-xl font-extrabold tracking-tight">나의 명리 구조</h2>
            <p className="text-xs text-muted">
              양력 환산 {result.solar_ymd} · {result.unknown_time ? "출생시간 미상 · 시주 제외" : `${result.input.time_text} 출생`}
            </p>
          </div>

          <div className="grid grid-cols-4 gap-2">
            {result.pillars.map((p) => (
              <div key={p.label} className="rounded-2xl border border-border bg-surface px-2 py-3 text-center">
                <div className="text-[11px] font-bold text-subtle">{p.label}</div>
                <div className="mt-0.5 text-xl font-extrabold tracking-tight">{p.hangul}</div>
                {p.ganji && <div className="text-[11px] text-muted">{p.ganji}</div>}
                {p.gan_el && (
                  <div className="mt-1.5 flex justify-center gap-1">
                    {[p.gan_el, p.zhi_el].map((el, i) => (
                      <span key={i} className={`rounded-md px-1.5 text-[10px] font-bold ${ELEMENT_TONE[el ?? ""] ?? ""}`}>
                        {el}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div role="tablist" className="sticky top-0 z-10 -mx-4 flex gap-1 overflow-x-auto bg-bg/90 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-2xl sm:px-1">
            {TABS.map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`shrink-0 rounded-xl px-3.5 py-2 text-sm font-bold transition ${tab === t ? "bg-violet-600 text-white" : "text-muted hover:bg-surface-muted"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "핵심 해석" && (
            <div className="space-y-3">
              <div className="rounded-3xl bg-gradient-to-br from-violet-950 via-purple-900 to-fuchsia-800 p-5 text-white shadow-lg sm:p-6">
                <div className="text-[10px] font-bold tracking-widest text-violet-200">나를 가장 잘 설명하는 핵심</div>
                <div className="mt-1 text-2xl font-extrabold tracking-tight">{result.profile.title}</div>
                <p className="mt-2 text-sm leading-relaxed text-violet-100">{result.profile.one_line}</p>
                {result.top_gods.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <div className="text-xs font-bold text-violet-200">내 사주에서 실제로 반복되는 십성</div>
                    {result.top_gods.map((g) => (
                      <div key={g.god} className="rounded-2xl bg-white/10 p-3">
                        <div className="text-sm font-extrabold">
                          {g.god} · {g.count}회
                        </div>
                        <p className="text-[13px] text-violet-100">{g.sentence}</p>
                        {g.group_title && (
                          <p className="mt-1 text-[11px] text-violet-200">
                            쉽게 말하면 · {g.group_title} | 일에서는 {g.group_work}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Card title="💼 일할 때의 나">
                  {result.profile.work}
                  <div className="mt-1.5 text-[11px] text-subtle">월주 {result.profile.month} · 사회생활과 직업환경을 읽는 자리</div>
                </Card>
                <Card title="⚠️ 내가 과해질 때">{result.profile.shadow}</Card>
                <Card title="💰 돈을 다루는 방식">{result.profile.money}</Card>
                <Card title="🤝 관계에서의 나">{result.profile.relation}</Card>
              </div>
              {result.profile.cycle && <Card title="🧭 지금의 10년">{result.profile.cycle}</Card>}

              <Card title="🌿 내 오행 분포">
                <p className="text-xs text-subtle">천간·지지의 표면 오행을 기준으로 본 참고 분포입니다.</p>
                <div className="mt-3 grid grid-cols-5 gap-1.5">
                  {result.elements.map((e) => (
                    <div key={e.element} className={`rounded-xl px-1 py-2.5 text-center ${ELEMENT_TONE[e.element]}`} title={e.desc}>
                      <div className="text-xs font-bold">
                        {e.symbol} {e.element}
                      </div>
                      <div className="text-lg font-extrabold">{e.count}개</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 space-y-0.5 text-[13px]">
                  <div>
                    <b className="text-fg">가장 많이 드러나는 오행</b> · {result.strong_elements.join(" · ")} {result.max_count}개
                  </div>
                  <div>
                    <b className="text-fg">상대적으로 적게 드러나는 오행</b> · {result.weak_elements.join(" · ")} {result.min_count}개
                  </div>
                  <p className="pt-1 text-[11px] text-subtle">오행 개수는 성향을 이해하는 참고값입니다. 많고 적음만으로 좋고 나쁨이나 용신을 단정하지 않습니다.</p>
                </div>
              </Card>
              {result.basis_gods.length > 0 && (
                <p className="text-[11px] text-subtle">반복 십성 · {result.basis_gods.map((g) => `${g.god} ${g.count}회 (${g.desc})`).join(" / ")}</p>
              )}
              {result.unknown_time && (
                <p className="rounded-xl bg-sky-500/10 px-3 py-2.5 text-xs text-sky-700 dark:text-sky-300">
                  출생시간을 모름으로 선택해 시주는 제외했습니다. 연·월·일 중심 해석은 가능하지만 세부 시점 해석은 정밀도가 낮아질 수 있습니다.
                </p>
              )}
            </div>
          )}

          {tab === "직업·재물·관계" && (
            <div className="grid gap-3 sm:grid-cols-2">
              {result.domains.map((d) => (
                <Card
                  key={d.title}
                  title={
                    <>
                      {d.icon} {d.title}
                      <div className="text-xs font-bold text-violet-600 dark:text-violet-300">{d.headline}</div>
                    </>
                  }
                >
                  <p>
                    <Rich text={d.main} />
                  </p>
                  <div className="mt-2 space-y-1.5 text-[13px]">
                    {d.strength && (
                      <p>
                        <b className="text-fg">강하게 쓰이는 부분</b> · <Rich text={d.strength} />
                      </p>
                    )}
                    {d.risk && (
                      <p>
                        <b className="text-fg">과해질 때</b> · <Rich text={d.risk} />
                      </p>
                    )}
                    {d.cycle && (
                      <p>
                        <b className="text-fg">현재 대운에서는</b> · <Rich text={d.cycle} />
                      </p>
                    )}
                  </div>
                  {d.basis && <div className="mt-2 text-[11px] text-subtle">근거 십성 · {d.basis}</div>}
                </Card>
              ))}
            </div>
          )}

          {tab === "인생 대운" &&
            (() => {
              const dw = result.daewoon;
              const cur = dw.cycles[dw.current_index];
              const sel = dw.cycles[Math.min(cycleIdx, dw.cycles.length - 1)];
              const years = sel.years;
              const sy = years.find((y) => y.year === year) ?? years.find((y) => y.year === result.this_year) ?? years[0];
              return (
                <div className="space-y-4">
                  {cur?.current && (
                    <div className="rounded-3xl bg-gradient-to-br from-violet-950 to-purple-800 p-5 text-white shadow-lg">
                      <div className="text-[10px] font-bold tracking-widest text-violet-200">CURRENT 10-YEAR CYCLE</div>
                      <div className="mt-1 text-xl font-extrabold">
                        {cur.hangul} 대운 · {cur.start_year}~{cur.end_year}
                      </div>
                      <p className="mt-1 text-sm text-violet-100">
                        {cur.start_age}~{cur.end_age}세 · 천간은 <b>{cur.detail.gan_god || cur.detail.gan_group}</b>, 지지는 <b>{cur.detail.zhi_group}</b>의 성격으로 작동합니다.
                      </p>
                    </div>
                  )}
                  <details className="rounded-2xl border border-border bg-surface px-4 py-3 text-sm">
                    <summary className="cursor-pointer font-bold">대운 계산 기준 보기</summary>
                    <div className="mt-2 space-y-1 text-muted">
                      <p>
                        대운 방향: <b className="text-fg">{dw.direction}</b>
                      </p>
                      <p>
                        기산점: <b className="text-fg">{dw.start_phrase} 후</b>
                      </p>
                      <p>
                        계산된 대운 시작일: <b className="text-fg">{dw.start_solar || "시간 미상으로 근사"}</b>
                      </p>
                      <p className="text-xs text-subtle">대운은 10년 단위 환경 변화의 축입니다. 원국의 일간·월주와 대운 천간·지지가 만드는 십성/오행 관계를 함께 봅니다.</p>
                    </div>
                  </details>

                  <div>
                    <h3 className="text-sm font-extrabold">보고 싶은 대운을 눌러보세요</h3>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      {dw.cycles.map((c, i) => {
                        const active = sel === c;
                        return (
                          <button
                            key={c.ganji + i}
                            type="button"
                            aria-pressed={active}
                            onClick={() => {
                              setCycleIdx(i);
                              setYear(null);
                            }}
                            className={`rounded-2xl border px-2 py-2.5 text-center transition ${
                              active ? "border-violet-600 bg-violet-600 text-white" : "border-border bg-surface hover:border-violet-400"
                            }`}
                          >
                            <div className="text-sm font-extrabold">
                              {c.hangul} 대운{c.current ? " •" : ""}
                            </div>
                            <div className={`text-[11px] ${active ? "text-violet-100" : "text-muted"}`}>
                              {c.start_year}~{c.end_year} · {c.start_age}~{c.end_age}세
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="space-y-3 rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-5">
                    <div>
                      <div className="text-[10px] font-extrabold tracking-widest text-violet-600 dark:text-violet-300">SELECTED DAEWOON</div>
                      <div className="text-lg font-extrabold">
                        {sel.hangul} 대운 · {sel.start_year}~{sel.end_year}
                      </div>
                      <p className="text-xs text-muted">
                        천간 <b>{sel.detail.gan_hangul}</b> · {sel.detail.gan_el} · {sel.detail.gan_god || sel.detail.gan_group} | 지지 <b>{sel.detail.zhi_hangul}</b> · {sel.detail.zhi_el} ·{" "}
                        {sel.detail.zhi_group}
                      </p>
                      <p className="mt-1 text-sm font-semibold">{sel.detail.headline}</p>
                    </div>
                    <FlowGrid d={sel.detail} labels={["💼 직장 · 커리어", "💰 재물 · 현실", "🤝 관계 · 가족", "🎯 이 대운을 쓰는 법"]} />
                    <AiPanel
                      state={ai[`cycle-${sel.start_year}`]}
                      onRun={() => runAi(`cycle-${sel.start_year}`, { kind: "cycle", cycle_index: dw.cycles.indexOf(sel) })}
                      runLabel="선택한 대운을 GPT로 더 자세히 분석"
                      rerunLabel="다시 분석"
                    />
                  </div>

                  <div className="space-y-3 rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-5">
                    <div>
                      <h3 className="text-sm font-extrabold">선택한 대운 안에서 연도별 흐름 보기</h3>
                      <p className="text-xs text-muted">연도를 눌러 원국 × 대운 × 세운의 흐름을 살펴보세요.</p>
                    </div>
                    <div className="grid grid-cols-5 gap-1.5">
                      {years.map((y) => {
                        const active = y.year === sy.year;
                        return (
                          <button
                            key={y.year}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setYear(y.year)}
                            className={`rounded-xl border px-1 py-2 text-center transition ${active ? "border-violet-600 bg-violet-600 text-white" : "border-border hover:border-violet-400"}`}
                          >
                            <div className="text-xs font-extrabold">{y.year}</div>
                            <div className={`text-[11px] ${active ? "text-violet-100" : "text-muted"}`}>{y.hangul}</div>
                          </button>
                        );
                      })}
                    </div>
                    <div>
                      <div className="text-[10px] font-extrabold tracking-widest text-violet-600 dark:text-violet-300">YEAR FLOW</div>
                      <div className="text-lg font-extrabold">
                        {sy.year}년 · {sy.hangul}
                      </div>
                      <p className="text-xs text-muted">
                        천간 <b>{sy.gan_hangul}</b> · {sy.gan_god || sy.gan_group} | 지지 <b>{sy.zhi_hangul}</b> · {sy.zhi_group}
                      </p>
                      <p className="mt-1 text-sm font-semibold">{sy.headline}</p>
                    </div>
                    <FlowGrid d={sy} labels={["💼 직장·성과", "💰 재물·현실", "🤝 관계", "🎯 행동 포인트"]} />
                    <AiPanel
                      state={ai[`year-${sy.year}`]}
                      onRun={() => runAi(`year-${sy.year}`, { kind: "year", year: sy.year })}
                      runLabel={`${sy.year}년을 GPT로 깊게 보기`}
                      rerunLabel="다시 분석"
                    />
                  </div>
                  {result.unknown_time && (
                    <p className="rounded-xl bg-amber-500/10 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-400">
                      출생시간 미상인 경우 시주가 빠지므로 대운 기산점의 일·월 단위 정밀도와 세부 사건 시점 해석은 제한될 수 있습니다.
                    </p>
                  )}
                </div>
              );
            })()}

          {tab === "AI 명리상담" && (
            <div className="space-y-4">
              <Card title="AI 개인화 명리상담">내 명식의 실제 계산값과 현재 대운을 기준으로, 일반론보다 ‘왜 나에게 이런 패턴이 반복되는지’를 중심으로 해석합니다.</Card>
              <AiPanel state={ai.full} onRun={() => runAi("full", { kind: "full" })} runLabel="전문 명리상담 시작하기" rerunLabel="AI 해석 다시 생성" />

              <div className="space-y-3 rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-5">
                <h3 className="text-sm font-extrabold">추가로 궁금한 질문</h3>
                <Field label="주제">
                  <select className={inputClass} value={topic} onChange={(e) => setTopic(e.target.value)}>
                    {options.topics.map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </Field>
                <Field label="질문">
                  <textarea
                    className={`${inputClass} min-h-20 resize-y`}
                    value={question}
                    maxLength={1000}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="예: 현재 대운에서 직장 내 역할 변화는 어떤 의미인가요?"
                  />
                </Field>
                <button
                  type="button"
                  disabled={!question.trim() || ai[`q-${qAnswerKey}`]?.loading}
                  onClick={() => {
                    const k = qAnswerKey + 1;
                    setQAnswerKey(k);
                    runAi(`q-${k}`, { kind: "question", topic, question });
                  }}
                  className="w-full rounded-xl bg-violet-600 py-2.5 text-sm font-bold text-white transition hover:brightness-110 disabled:opacity-40"
                >
                  이 질문 분석하기
                </button>
                {ai[`q-${qAnswerKey}`] && <AiPanel state={ai[`q-${qAnswerKey}`]} onRun={() => {}} runLabel="" />}
              </div>
            </div>
          )}
        </section>
      )}

      <p className="rounded-2xl bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-subtle">
        ※ 본 서비스는 전통 명리학의 계산 체계와 해석 논리를 활용한 자기이해·참고용 콘텐츠입니다. 명리학은 과학적으로 미래를 확정하는 예측 도구가 아니며, 의료·투자·법률 등 중요한 의사결정을 대체하지
        않습니다. 특히 출생시간이 정확하지 않은 경우 시주 및 세부 시점 해석에는 한계가 있습니다.
      </p>
    </div>
  );
}
