"use client";

// 생활 속 종목 찾기 탭. 오늘의 토픽 3개 · 예시 단어 · 마인드맵 · 회사 상세(왜 관련 있나 → 왜 움직였나).
// 서버가 미리 그려 둔 마인드맵을 읽기만 한다(새 단어만 대기열로 AI를 부른다 — WordInput).
import { useEffect, useRef, useState } from "react";
import MindMap, { STAGE_COLOR } from "@/components/stock/MindMap";
import { WhyBody } from "@/components/stock/StockOn";
import { dateLabel, lifeApi, pct, stockApi, type LifeCompany, type LifeMap, type LifeOverview, type LifeStage, type LifeWordResult, type Stock, type Why } from "@/lib/stock";

const UP = "text-[#ff8a9c]", DOWN = "text-[#7cbcff]";
const rateTone = (v?: number | null) => (!v ? "text-slate-300" : v > 0 ? UP : DOWN);
const REL_LABEL = { 강: "연관도 강", 중: "연관도 중", 약: "연관도 약" } as const;

type Pick = { c: LifeCompany; s: LifeStage };
type Drawing = { word: string; position: number; running: boolean };
const POLL_MS = 1500;
const POLL_MAX_MS = 100_000; // AI 한 번 45초 × 최대 2회 + 대기 여유
type Source = { kind: "topic"; i: number } | { kind: "chip"; word: string } | { kind: "word"; word: string };

function Badges({ map }: { map: LifeMap }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-extrabold">
      <span className="rounded-full bg-gradient-to-r from-sky-400/25 to-violet-400/25 px-2 py-0.5 text-sky-100 ring-1 ring-sky-300/30">✨ AI가 그렸어요</span>
      <span className="rounded-full bg-white/10 px-2 py-0.5 text-slate-200">관련 종목 · 참고용</span>
      {map.example && <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-amber-200">준비된 예시</span>}
    </div>
  );
}

function Legend({ map }: { map: LifeMap }) {
  return (
    <div className="mt-2 space-y-1.5">
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {map.stages.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full" style={{ background: STAGE_COLOR[s.key], boxShadow: `0 0 8px ${STAGE_COLOR[s.key]}` }} />
            <span className="font-extrabold" style={{ color: STAGE_COLOR[s.key] }}>{s.label}</span>
            {s.detail && <span className="text-slate-300">{s.detail}</span>}
          </li>
        ))}
      </ul>
      <p className="text-[10px] leading-relaxed text-slate-400">
        버블 크기 = 연관도(강·중·약) · 숫자 = 전일 등락률(<span className={UP}>▲ 상승</span> · <span className={DOWN}>▼ 하락</span>
        {map.price_as_of ? ` · ${dateLabel(map.price_as_of)} 종가 기준` : ""}) · 가운데를 누르면 모두 펼쳐져요 · 두 손가락으로 확대
      </p>
    </div>
  );
}

function Detail({ pick, onClose }: { pick: Pick; onClose?: () => void }) {
  const [why, setWhy] = useState<Why | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { c, s } = pick;
  useEffect(() => { setWhy(null); setError(""); setLoading(false); }, [c.code]);

  async function loadWhy() {
    setLoading(true);
    setError("");
    try {
      setWhy(await stockApi.why(c.code));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  const stock = { code: c.code, name: c.name, market: c.market ?? "", close: c.close ?? 0, change: null, rate: c.rate ?? null,
    value: c.value ?? null, cap: c.cap ?? null } as Stock;

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-extrabold">
            <span className="rounded-full px-2 py-0.5 text-[#071226]" style={{ background: STAGE_COLOR[s.key] }}>{s.label}{s.detail ? ` · ${s.detail}` : ""}</span>
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-slate-200">{REL_LABEL[c.relevance]}</span>
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-slate-300">관련 종목 · 참고용</span>
          </div>
          <h3 className="mt-1.5 text-lg font-extrabold text-white">{c.name}</h3>
          <p className="text-[11px] text-slate-400">{c.code}{c.market ? ` · ${c.market}` : ""}</p>
        </div>
        <div className="shrink-0 whitespace-nowrap text-right">
          <div className="text-sm font-bold tabular-nums text-white">{c.close != null ? c.close.toLocaleString("ko-KR") : "—"}</div>
          <div className={`text-xs font-extrabold tabular-nums ${rateTone(c.rate)}`}>{c.rate ? (c.rate > 0 ? "▲ " : "▼ ") : ""}{pct(c.rate)}</div>
          <div className="text-[10px] text-slate-500">전일 종가 기준</div>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 rounded-full px-2 text-lg text-slate-400">✕</button>}
      </div>
      <div className="mt-3 rounded-2xl bg-white/[0.06] p-3 ring-1 ring-white/10">
        <div className="text-[10px] font-extrabold tracking-[0.14em] text-sky-300">왜 관련 있나</div>
        <p className="mt-1 text-sm font-bold leading-relaxed text-slate-100">{c.reason}</p>
        <p className="mt-1.5 text-[10px] text-slate-500">✨ AI가 그렸어요 · 사업 내용으로 이어 본 것이라 틀릴 수 있어요</p>
      </div>
      {!why && !loading && (
        <button type="button" onClick={loadWhy} className="mt-3 w-full rounded-2xl bg-sky-400 py-2.5 text-sm font-extrabold text-[#071226] hover:bg-sky-300">
          📈 이 종목 &lsquo;왜 움직였나&rsquo; 보기
        </button>
      )}
      {(why || loading || error) && (
        <div className="mt-3 rounded-2xl bg-surface p-4 text-fg">
          <WhyBody stock={stock} why={why} error={error} loading={loading} />
        </div>
      )}
    </div>
  );
}

function DrawingOverlay({ d }: { d: Drawing }) {
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center rounded-3xl bg-[#050d1f]/80 text-center backdrop-blur-sm" role="status" aria-live="polite">
      <div className="relative flex size-24 items-center justify-center">
        <span className="lm-glow absolute inset-0 rounded-full bg-sky-400/30 blur-xl" />
        <span className="relative text-4xl">🎨</span>
      </div>
      <p className="mt-3 text-base font-extrabold text-white">
        AI가 &lsquo;{d.word}&rsquo; 마인드맵을 그리는 중<span className="lm-dots ml-0.5"><span>.</span><span>.</span><span>.</span></span>
      </p>
      <p className="mt-1 text-xs text-slate-300">
        {d.running || d.position === 0 ? "원료부터 유통까지 이어지는 회사를 찾고 있어요 · 보통 10~30초" : `앞에 ${d.position}개 단어가 먼저 그려지고 있어요 · 순서대로 그려요`}
      </p>
    </div>
  );
}

function WordInput({ disabled, onSubmit }: { disabled: boolean; onSubmit: (w: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); const w = text.trim(); if (w) onSubmit(w); }}>
      <label className="sr-only" htmlFor="lifemap-word">생활 단어</label>
      <input id="lifemap-word" value={text} onChange={(e) => setText(e.target.value)} maxLength={12} enterKeyHint="go" autoComplete="off"
        placeholder="다른 생활 단어 (예: 붕어빵, 전기차, 캠핑)"
        className="min-w-0 flex-1 rounded-2xl bg-white/[0.08] px-3.5 py-2.5 text-sm font-bold text-white placeholder:text-slate-500 ring-1 ring-white/15 focus:outline-none focus:ring-2 focus:ring-sky-300" />
      <button type="submit" disabled={disabled || !text.trim()}
        className="shrink-0 rounded-2xl bg-sky-400 px-4 py-2.5 text-sm font-extrabold text-[#071226] transition hover:bg-sky-300 disabled:opacity-40">✨ 그리기</button>
    </form>
  );
}

export default function LifeFinder() {
  const [data, setData] = useState<LifeOverview | null>(null);
  const [error, setError] = useState("");
  const [src, setSrc] = useState<Source>({ kind: "topic", i: 0 });
  const [pick, setPick] = useState<Pick | null>(null);
  const [isPc, setIsPc] = useState(false);
  const [words, setWords] = useState<Record<string, LifeMap>>({});
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [notice, setNotice] = useState("");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  /** 서버 응답 하나를 화면에 반영한다. 끝났으면 true. */
  function apply(r: LifeWordResult): boolean {
    if (r.status === "queued" || r.status === "running") {
      setDrawing({ word: r.word, position: r.position ?? 0, running: r.status === "running" });
      return false;
    }
    setDrawing(null);
    if (r.map) {
      setWords((w) => ({ ...w, [r.word]: r.map! }));
      setSrc({ kind: "word", word: r.word });
      setPick(null);
    }
    setNotice(r.status === "ready" ? "" : r.message || (r.status === "none" ? "그리던 내용을 찾지 못했어요. 한 번 더 눌러 주세요." : ""));
    return true;
  }

  async function draw(word: string) {
    if (drawing) return;
    const chip = data?.chips.includes(word) && data.chip_maps[word];
    if (chip) { setNotice(""); return choose({ kind: "chip", word }); } // 예시 단어는 이미 그려 둔 것
    setNotice("");
    try {
      const first = await lifeApi.request(word);
      if (apply(first)) return;
      const started = Date.now();
      const poll = async () => {
        try {
          const r = await lifeApi.status(first.word);
          if (apply(r)) return;
        } catch { /* 일시 오류는 다음 확인에서 다시 */ }
        if (Date.now() - started > POLL_MAX_MS) {
          setDrawing(null);
          setNotice("그리는 데 시간이 오래 걸려요. 잠시 뒤 같은 단어를 다시 눌러 주세요(다 그려지면 바로 보여요).");
          return;
        }
        pollRef.current = setTimeout(poll, POLL_MS);
      };
      pollRef.current = setTimeout(poll, POLL_MS);
    } catch (e) {
      setDrawing(null);
      setNotice((e as Error).message);
    }
  }

  useEffect(() => {
    let alive = true;
    lifeApi.overview().then((d) => { if (alive) { setData(d); setError(""); } }).catch((e) => alive && setError((e as Error).message));
    const mq = window.matchMedia("(min-width: 1024px)");
    const on = () => setIsPc(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => { alive = false; mq.removeEventListener("change", on); };
  }, []);

  if (error && !data) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!data) return <div className="lifemap-shell rounded-3xl bg-[#071226] py-24 text-center text-sm text-slate-300">마인드맵을 불러오는 중…</div>;

  const topic = src.kind === "topic" ? data.topics[src.i] : undefined;
  const map: LifeMap | undefined = src.kind === "topic" ? topic?.map : src.kind === "chip" ? data.chip_maps[src.word] : words[src.word];
  function choose(s: Source) { setSrc(s); setPick(null); }

  return (
    <div className="lifemap-shell relative overflow-hidden rounded-3xl bg-[radial-gradient(120%_80%_at_50%_0%,#13305e_0%,#0a1a38_45%,#050d1f_100%)] p-4 text-slate-100 shadow-xl sm:p-6">
      <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(1px_1px_at_20%_30%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_70%_20%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_40%_80%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_85%_65%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_10%_75%,#fff_50%,transparent_51%)]" />
      <div className="relative">
        <div className="text-[10px] font-extrabold tracking-[0.2em] text-sky-300">LIFE → STOCKS</div>
        <h2 className="mt-1 text-xl font-extrabold leading-tight text-white sm:text-2xl">생활 속 종목 찾기</h2>
        <p className="mt-1 text-xs text-slate-300">오늘 뉴스 속 생활 단어가 어떤 회사들로 이어지는지, 원료부터 유통까지 AI가 그려 봤어요.</p>

        <section aria-label="오늘의 토픽" className="mt-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-extrabold text-white">오늘의 토픽</h3>
            <span className="text-[10px] text-slate-400">{data.day ? `${Number(data.day.slice(5, 7))}/${Number(data.day.slice(8, 10))} 아침 뉴스 · AI 선정` : "준비된 예시"}</span>
          </div>
          <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0">
            {data.topics.map((t, i) => {
              const on = src.kind === "topic" && src.i === i;
              return (
                <button key={t.name} type="button" onClick={() => choose({ kind: "topic", i })} aria-pressed={on}
                  className={`w-[72%] shrink-0 snap-start rounded-2xl p-3 text-left ring-1 transition sm:w-auto ${on ? "bg-sky-400/15 ring-sky-300/70 shadow-[0_0_24px_rgba(56,189,248,.25)]" : "bg-white/[0.05] ring-white/10 hover:bg-white/10"}`}>
                  <div className="text-[10px] font-extrabold text-sky-300">TOPIC {i + 1}{t.carried ? " · 지난 토픽" : ""}</div>
                  <div className="mt-0.5 text-base font-extrabold text-white">{t.name}</div>
                  <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-slate-300">{t.summary}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section aria-label="예시 단어" className="mt-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] font-bold text-slate-400">이런 단어도</span>
            {data.chips.filter((w) => data.chip_maps[w]).map((w) => {
              const on = src.kind === "chip" && src.word === w;
              return (
                <button key={w} type="button" onClick={() => choose({ kind: "chip", word: w })} aria-pressed={on}
                  className={`rounded-full px-3 py-1.5 text-xs font-extrabold ring-1 transition ${on ? "bg-white text-[#071226] ring-white" : "bg-white/[0.06] text-slate-100 ring-white/15 hover:bg-white/15"}`}>{w}</button>
              );
            })}
            {Object.keys(words).map((w) => {
              const on = src.kind === "word" && src.word === w;
              return (
                <button key={`w-${w}`} type="button" onClick={() => choose({ kind: "word", word: w })} aria-pressed={on}
                  className={`rounded-full px-3 py-1.5 text-xs font-extrabold ring-1 transition ${on ? "bg-sky-300 text-[#071226] ring-sky-200" : "bg-sky-400/10 text-sky-100 ring-sky-300/30 hover:bg-sky-400/20"}`}>{w}</button>
              );
            })}
          </div>
          {data.live.enabled ? (
            <WordInput disabled={!!drawing} onSubmit={draw} />
          ) : (
            <p className="mt-2 text-[11px] text-slate-400">지금은 새 단어 그리기를 쉬고 있어요. 위 단어들은 볼 수 있어요.</p>
          )}
          {notice && <p className="mt-2 rounded-xl bg-amber-400/10 px-3 py-2 text-xs font-bold text-amber-200 ring-1 ring-amber-300/20" role="status">{notice}</p>}
        </section>

        <div className="mt-4 lg:grid lg:grid-cols-[1.25fr_1fr] lg:gap-5">
          <div className="relative">
            {drawing && <DrawingOverlay d={drawing} />}
            {map && (
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <Badges map={map} />
              </div>
            )}
            {map && map.stages.length > 0 ? (
              <>
                <MindMap map={map} picked={pick?.c.code} onPick={(c, s) => setPick({ c, s })} />
                <Legend map={map} />
              </>
            ) : (
              <p className="rounded-2xl bg-white/[0.05] px-4 py-16 text-center text-sm text-slate-300">
                {map ? `‘${map.word}’에서 이어지는 상장사를 찾지 못했어요. 다른 단어로 해 보세요.` : "마인드맵을 고르세요."}
              </p>
            )}
            {topic && topic.articles.length > 0 && (
              <div className="mt-3 rounded-2xl bg-white/[0.04] p-3 ring-1 ring-white/10">
                <div className="text-[10px] font-extrabold tracking-[0.14em] text-slate-400">근거 기사</div>
                <ul className="mt-1 space-y-1">
                  {topic.articles.map((a) => (
                    <li key={a.url} className="text-xs">
                      <a href={a.url} target="_blank" rel="noopener noreferrer" className="font-bold text-slate-100 underline-offset-2 hover:underline">{a.title}</a>
                      <span className="ml-1 text-[10px] text-slate-500">{a.press}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <aside className="hidden lg:block">
            <div className="sticky top-4 rounded-3xl bg-white/[0.05] p-5 ring-1 ring-white/10">
              {pick ? <Detail pick={pick} /> : (
                <div className="py-12 text-center text-sm text-slate-300">
                  <div className="text-3xl">🔍</div>
                  <p className="mt-2 font-bold text-white">단계를 누르면 회사가 펼쳐져요</p>
                  <p className="mt-1 text-xs">회사 버블을 누르면 &lsquo;왜 관련 있나&rsquo;와 &lsquo;왜 움직였나&rsquo;를 볼 수 있어요.</p>
                </div>
              )}
            </div>
          </aside>
        </div>

        <footer className="mt-5 rounded-2xl bg-black/25 p-3 text-[11px] leading-relaxed text-slate-300 ring-1 ring-white/10">
          <p className="font-extrabold text-white">ⓘ 투자 권유가 아닌 참고 정보예요</p>
          <p className="mt-1">AI가 생활 단어와 회사의 사업 내용을 이어 그린 그림이라 틀리거나 빠진 회사가 있을 수 있어요. 금융위원회 공공데이터 상장 종목 목록에 있는 회사만 보여 주며, 등락률은 전일 종가 기준이에요. 토픽은 NAVER 뉴스 검색 헤드라인으로 골랐어요.</p>
        </footer>
      </div>

      {pick && !isPc && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${pick.c.name} 상세`}>
          <button type="button" aria-label="닫기" onClick={() => setPick(null)} className="absolute inset-0 bg-black/50" />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-[#0b1a36] p-5 pb-8 shadow-2xl ring-1 ring-white/10">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/20" />
            <Detail pick={pick} onClose={() => setPick(null)} />
          </div>
        </div>
      )}
    </div>
  );
}
