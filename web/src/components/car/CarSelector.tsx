"use client";

import { useEffect, useRef, useState } from "react";
import { Segmented, Spinner } from "@/components/golf/ui";
import { carApi, media, type CarQuestion, type CarRecommendation } from "@/lib/carSelector";

const KEY = "car-selector-v1";
type Saved = { answers: number[]; rec: CarRecommendation | null; color: string | null; months: number };
const INITIAL: Saved = { answers: [], rec: null, color: null, months: 60 };

/** 원본 페이지의 모션 SVG 애니메이션 */
const SCENE_CSS = `
.scene svg{width:100%;height:100%;display:block}
.scene .scene-bg{animation:cs-scene 7s ease-in-out infinite}
.scene .scene-car{animation:cs-drive 5s ease-in-out infinite}
.scene .scene-float{animation:cs-float 4s ease-in-out infinite}
.scene .scene-glow{animation:cs-glow 2.8s ease-in-out infinite}
@keyframes cs-scene{50%{transform:translateX(-5px)}}
@keyframes cs-drive{0%,100%{transform:translateX(-8px)}50%{transform:translateX(12px)}}
@keyframes cs-float{50%{transform:translateY(-7px)}}
@keyframes cs-glow{0%,100%{opacity:.45}50%{opacity:1}}
@keyframes cs-carfloat{50%{transform:translateY(-5px)}}
@media (prefers-reduced-motion: reduce){.scene *{animation:none!important}}
`;

// 서버에 고정된 SVG 마크업만 렌더링한다 (사용자 입력이 섞이지 않음)
function Scene({ svg, className }: { svg: string; className: string }) {
  return <div className={`scene ${className}`} dangerouslySetInnerHTML={{ __html: svg }} />;
}

export default function CarSelector() {
  const [questions, setQuestions] = useState<CarQuestion[] | null>(null);
  const [s, setS] = useState<Saved>(INITIAL);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const restored = useRef(false);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    carApi
      .questions()
      .then((r) => setQuestions(r.questions))
      .catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    try {
      const raw = sessionStorage.getItem(KEY);
      if (raw) setS({ ...INITIAL, ...(JSON.parse(raw) as Saved) });
    } catch {}
  }, []);

  useEffect(() => {
    if (!restored.current) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify(s));
    } catch {}
  }, [s]);

  const scrollTop = () => requestAnimationFrame(() => topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));

  async function choose(i: number) {
    if (!questions) return;
    const answers = [...s.answers, i];
    if (answers.length < questions.length) {
      setS((p) => ({ ...p, answers }));
      scrollTop();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const rec = await carApi.recommend(answers);
      setS({ answers, rec, color: rec.colors[0]?.color ?? null, months: 60 });
      setDone("");
      scrollTop();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !questions) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!questions) return <Spinner label="불러오는 중…" />;

  const rec = s.rec;
  return (
    <div className="space-y-5">
      <style>{SCENE_CSS}</style>
      <div ref={topRef} className="scroll-mt-4" />
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!rec &&
        (() => {
          const idx = Math.min(s.answers.length, questions.length - 1);
          const q = questions[idx];
          return (
            <section className="space-y-4">
              <div className="rounded-3xl border border-border bg-surface p-5 shadow-sm">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="tracking-widest text-accent">LIFESTYLE SIGNAL {idx + 1}</span>
                  <span className="text-muted">
                    {idx + 1} / {questions.length}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                  <div className="h-full rounded-full bg-gradient-to-r from-accent to-violet-500 transition-all" style={{ width: `${((idx + 1) / questions.length) * 100}%` }} />
                </div>
                <h2 className="mt-4 text-xl font-extrabold tracking-tight">{q.title}</h2>
                <p className="text-sm text-muted">{q.desc}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {q.options.map((o, i) => (
                  <button
                    key={o.label}
                    type="button"
                    disabled={busy}
                    onClick={() => choose(i)}
                    className="group overflow-hidden rounded-3xl border border-border bg-surface p-2 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md disabled:opacity-60"
                  >
                    <Scene svg={o.art} className="aspect-[2/1] overflow-hidden rounded-2xl bg-surface-muted" />
                    <div className="px-3 pb-3 pt-3">
                      <div className="font-extrabold">{o.label}</div>
                      <div className="mt-0.5 text-xs text-muted">{o.desc}</div>
                      <div className="mt-2 text-xs font-bold text-accent transition group-hover:translate-x-0.5">이 선택이 나와 가까워요 →</div>
                    </div>
                  </button>
                ))}
              </div>
              {busy && <Spinner label="추천 차량을 찾고 있어요…" />}
              {s.answers.length > 0 && (
                <button type="button" onClick={() => setS((p) => ({ ...p, answers: p.answers.slice(0, -1) }))} className="text-sm font-semibold text-muted hover:text-fg">
                  ← 이전
                </button>
              )}
            </section>
          );
        })()}

      {rec &&
        (() => {
          const color = rec.colors.find((c) => c.color === s.color) ?? rec.colors[0];
          const monthly = color.monthly[String(s.months)] ?? 0;
          return (
            <section className="space-y-4">
              <div>
                <div className="text-[11px] font-extrabold tracking-[0.14em] text-accent">PERSONALIZED MATCH COMPLETE</div>
                <h2 className="mt-1 text-2xl font-extrabold tracking-tight">당신의 이동 취향을 찾았습니다.</h2>
                <p className="text-sm text-muted">선택한 라이프스타일 신호를 바탕으로 가장 자연스럽게 어울리는 차량을 제안합니다.</p>
              </div>

              <div className="grid items-center gap-5 rounded-3xl bg-gradient-to-br from-slate-950 via-blue-950 to-blue-800 p-5 text-white shadow-lg sm:grid-cols-[190px_1fr] sm:p-6">
                <Scene svg={rec.persona.art} className="aspect-[2/1] overflow-hidden rounded-2xl border border-white/10 sm:aspect-[5/4]" />
                <div>
                  <div className="text-[10px] font-bold tracking-widest text-blue-200">YOUR MOBILITY PERSONA</div>
                  <div className="mt-1 text-2xl font-extrabold tracking-tight">{rec.persona.name}</div>
                  <div className="text-sm font-semibold text-blue-100">{rec.persona.sub}</div>
                  <p className="mt-2 text-sm leading-relaxed text-blue-100/90">{rec.persona.copy}</p>
                  <span className="mt-2 inline-block rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs">{rec.persona.quote}</span>
                </div>
              </div>

              <div className="overflow-hidden rounded-3xl border border-border bg-surface shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3 p-5 sm:p-6">
                  <div>
                    <span className="rounded-full bg-accent-soft px-2.5 py-1 text-[10px] font-extrabold tracking-widest text-accent">RECOMMENDED FOR YOU</span>
                    <div className="mt-2 text-2xl font-extrabold tracking-tight">{rec.model}</div>
                    <div className="text-xs text-muted">당신의 선택 패턴과 가장 자연스럽게 이어지는 차량입니다.</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[9px] font-extrabold tracking-widest text-subtle">LIFESTYLE MATCH</div>
                    <div className="text-3xl font-extrabold text-accent">{rec.match}%</div>
                  </div>
                </div>
                <div className="relative flex h-60 items-center justify-center bg-gradient-to-b from-surface to-surface-muted sm:h-80">
                  <div className="absolute bottom-10 h-4 w-1/2 rounded-full bg-black/15 blur-lg" />
                  {color.image && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={media(color.image)}
                      alt={`${rec.model} ${color.color}`}
                      className="relative z-10 h-[86%] w-[84%] object-contain drop-shadow-xl motion-safe:animate-[cs-carfloat_4.8s_ease-in-out_infinite]"
                    />
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2 p-4 sm:p-5">
                  {rec.reasons.map((r, i) => (
                    <div key={r} className="border-t border-border pt-2.5">
                      <div className="text-[9px] font-extrabold tracking-widest text-accent">MATCH 0{i + 1}</div>
                      <div className="text-xs font-bold sm:text-sm">{r}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:grid-cols-2">
                <div className="space-y-1.5">
                  <div className="text-[10px] font-extrabold tracking-widest text-muted">COLOR</div>
                  <Segmented value={color.color} options={rec.colors.map((c) => c.color)} onChange={(v) => setS((p) => ({ ...p, color: v }))} full ariaLabel="색상" />
                </div>
                <div className="space-y-1.5">
                  <div className="text-[10px] font-extrabold tracking-widest text-muted">TERM</div>
                  <Segmented
                    value={String(s.months)}
                    options={rec.terms.map((t) => ({ value: String(t), label: `${t}개월` }))}
                    onChange={(v) => setS((p) => ({ ...p, months: Number(v) }))}
                    full
                    ariaLabel="이용기간"
                  />
                </div>
              </div>

              <div className="rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <div className="text-[10px] font-extrabold tracking-widest text-accent">PERSONALIZED SMART QUOTE</div>
                    <div className="mt-1 text-xs text-muted">나에게 맞춘 예상 이용금액</div>
                    <div className="text-4xl font-extrabold tracking-tight">
                      월 <span className="text-accent">{monthly.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}만원</span>부터
                    </div>
                  </div>
                  <span className="rounded-full bg-accent-soft px-3 py-1.5 text-xs font-bold text-accent">
                    {s.months}개월 · {color.color}
                  </span>
                </div>
                <dl className="grid grid-cols-2 gap-2 pt-4 text-sm sm:grid-cols-4">
                  {[
                    ["추천 차량", rec.model],
                    ["선택 색상", color.color],
                    ["이용기간", `${s.months}개월`],
                    ["차량가격", `${color.price.toLocaleString("ko-KR")}만원`],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-surface-muted px-3 py-2">
                      <dt className="text-[11px] text-subtle">{k}</dt>
                      <dd className="font-bold">{v}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-3 text-[11px] text-subtle">시연용 예상 금액이며 실제 계약 조건에 따라 달라질 수 있습니다.</p>
              </div>

              {done && <p className="rounded-xl bg-emerald-500/10 px-3 py-2.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300">{done}</p>}
              <div className="grid grid-cols-[2fr_1fr] gap-2">
                <button
                  type="button"
                  onClick={() => setDone(`${rec.model} / ${color.color} / ${s.months}개월 조건이 선택되었습니다.`)}
                  className="rounded-xl bg-gradient-to-r from-accent to-violet-600 py-3 text-sm font-extrabold text-white transition hover:brightness-110"
                >
                  이 차량으로 내 견적 완성하기 →
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setS(INITIAL);
                    setDone("");
                    scrollTop();
                  }}
                  className="rounded-xl border border-border py-3 text-sm font-bold hover:bg-surface-muted"
                >
                  처음부터 다시
                </button>
              </div>
            </section>
          );
        })()}
    </div>
  );
}
