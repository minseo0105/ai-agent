"use client";

// 생활 속 종목 찾기 탭: 증시를 움직인 뉴스 → 증시 영향 → 종목을 한눈에.
// 지금 뜨는 이슈(토픽 키워드) · 섹터 칩 · 직접 입력 → 큰 토픽 카드(무슨 일 · 증시 영향 · 실제로 움직인 종목) → 마인드맵 → 근거 기사.
// 서버가 미리 그려 둔 마인드맵을 읽기만 한다(직접 입력한 새 단어만 대기열로 AI를 부른다 — WordInput).
// 글씨: 휴대폰 본문 15px 이상, 제목 20px 이상, 보조 글씨도 slate-300 이상 대비.
import { useEffect, useRef, useState } from "react";
import MindMap, { DOWN, rateText, STAGE_COLOR, UP } from "@/components/stock/MindMap";
import { WhyBody } from "@/components/stock/StockOn";
import {
  lifeApi, stockApi, type LifeArticle, type LifeCompany, type LifeMap, type LifeMovedStock, type LifeOverview, type LifeStage,
  type LifeTopic, type LifeWordResult, type Stock, type Why,
} from "@/lib/stock";

const rateStyle = (v?: number | null) => ({ color: !v ? "#e2e8f0" : v > 0 ? UP : DOWN });
const REL_LABEL = { 강: "연관도 강", 중: "연관도 중", 약: "연관도 약" } as const;

type Pick = { c: LifeCompany; s?: LifeStage; note?: string };
type Source = { kind: "topic"; i: number } | { kind: "sector"; name: string } | { kind: "word"; word: string };
type Drawing = { word: string; position: number; running: boolean };
const POLL_MS = 1500;
const POLL_MAX_MS = 100_000; // AI 한 번 45초 × 최대 2회 + 대기 여유

function Badges({ map, basis }: { map: LifeMap; basis?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[14px] font-extrabold">
      <span className="rounded-full bg-gradient-to-r from-sky-400/30 to-violet-400/30 px-2.5 py-1 text-sky-50 ring-1 ring-sky-300/40">✨ AI가 그렸어요</span>
      <span className="rounded-full bg-white/15 px-2.5 py-1 text-white">관련 종목 · 참고용</span>
      {basis && <span className="rounded-full bg-white/10 px-2.5 py-1 text-slate-100">{basis}</span>}
      {map.example && <span className="rounded-full bg-amber-400/25 px-2.5 py-1 text-amber-100">준비된 예시</span>}
    </div>
  );
}

function Chip({ on, onClick, children, tone = "white" }: { on: boolean; onClick: () => void; children: React.ReactNode; tone?: "white" | "sky" | "hot" }) {
  const base = "shrink-0 rounded-full px-3.5 py-2 text-[15px] font-extrabold ring-1 transition";
  const off = tone === "hot" ? "bg-rose-400/15 text-rose-50 ring-rose-300/40 hover:bg-rose-400/25"
    : tone === "sky" ? "bg-sky-400/15 text-sky-50 ring-sky-300/40 hover:bg-sky-400/25" : "bg-white/10 text-white ring-white/25 hover:bg-white/20";
  return <button type="button" onClick={onClick} aria-pressed={on} className={`${base} ${on ? "bg-white text-[#071226] ring-white" : off}`}>{children}</button>;
}

function MovedPills({ stocks, onPick }: { stocks: LifeMovedStock[]; onPick: (s: LifeMovedStock) => void }) {
  if (!stocks.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {stocks.map((s) => (
        <button key={s.code} type="button" onClick={() => onPick(s)}
          className="flex items-baseline gap-1.5 rounded-2xl bg-white/10 px-3 py-2 text-left ring-1 ring-white/20 hover:bg-white/15">
          <span className="text-[16px] font-extrabold text-white">{s.name}</span>
          <span className="text-[16px] font-black tabular-nums" style={rateStyle(s.rate)}>{rateText(s.rate)}</span>
        </button>
      ))}
    </div>
  );
}

function Legend({ map }: { map: LifeMap }) {
  return (
    <div className="mt-3 space-y-2">
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[15px]">
        {map.stages.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="size-3 rounded-full" style={{ background: STAGE_COLOR[s.key], boxShadow: `0 0 8px ${STAGE_COLOR[s.key]}` }} />
            <span className="font-extrabold" style={{ color: STAGE_COLOR[s.key] }}>{s.label}</span>
            {s.detail && <span className="text-slate-100">{s.detail}</span>}
          </li>
        ))}
      </ul>
      <p className="text-[15px] leading-relaxed text-slate-200">
        버블이 클수록 연관이 커요. <b className="text-white">빛나는 테두리 = 실제로 크게 움직인 종목</b>(±5% 이상).
        숫자는 {map.basis_label || "기준일"} 등락률(<span style={{ color: UP }}>▲ 상승</span> · <span style={{ color: DOWN }}>▼ 하락</span>)이에요.
      </p>
    </div>
  );
}

function Articles({ items }: { items: LifeArticle[] }) {
  if (!items.length) return null;
  return (
    <section aria-label="근거 기사" className="mt-5 rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/15">
      <h3 className="text-[16px] font-extrabold text-white">근거 기사</h3>
      <ul className="mt-2 space-y-2.5">
        {items.map((a) => (
          <li key={a.url} className="text-[15px] leading-snug">
            <a href={a.url} target="_blank" rel="noopener noreferrer" className="font-bold text-slate-50 underline-offset-2 hover:underline">{a.title}</a>
            <span className="ml-1.5 text-[14px] text-slate-300">{a.press}</span>
          </li>
        ))}
      </ul>
    </section>
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
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 text-[14px] font-extrabold">
            {s && <span className="rounded-full px-2.5 py-0.5 text-[#071226]" style={{ background: STAGE_COLOR[s.key] }}>{s.label}{s.detail ? ` · ${s.detail}` : ""}</span>}
            {c.relevance && <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-white">{REL_LABEL[c.relevance]}</span>}
            <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-slate-100">관련 종목 · 참고용</span>
          </div>
          <h3 className="mt-2 text-[22px] font-extrabold leading-tight text-white">{c.name}</h3>
          <p className="text-[14px] text-slate-300">{c.code}{c.market ? ` · ${c.market}` : ""}</p>
        </div>
        <div className="shrink-0 whitespace-nowrap text-right">
          {c.moved && <div className="mb-0.5 text-[14px] font-extrabold text-amber-200">실제로 크게 움직임</div>}
          <div className="text-[20px] font-black tabular-nums" style={rateStyle(c.rate)}>{rateText(c.rate)}</div>
          <div className="text-[14px] text-slate-300">기준 시점 등락률</div>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 rounded-full px-2 text-2xl text-slate-200">✕</button>}
      </div>
      <div className="mt-3 rounded-2xl bg-white/[0.08] p-3.5 ring-1 ring-white/15">
        <div className="text-[14px] font-extrabold text-sky-200">왜 관련 있나</div>
        <p className="mt-1 text-[16px] font-bold leading-relaxed text-white">{c.reason || pick.note}</p>
        <p className="mt-1.5 text-[14px] text-slate-300">✨ AI가 그렸어요 · 뉴스·사업 내용으로 이어 본 것이라 틀릴 수 있어요</p>
      </div>
      {!why && !loading && (
        <button type="button" onClick={loadWhy} className="mt-3 w-full rounded-2xl bg-sky-400 py-3 text-[16px] font-extrabold text-[#071226] hover:bg-sky-300">
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
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center rounded-3xl bg-[#050d1f]/85 px-4 text-center backdrop-blur-sm" role="status" aria-live="polite">
      <div className="relative flex size-24 items-center justify-center">
        <span className="lm-glow absolute inset-0 rounded-full bg-sky-400/30 blur-xl" />
        <span className="relative text-4xl">🎨</span>
      </div>
      <p className="mt-3 text-[18px] font-extrabold text-white">
        AI가 &lsquo;{d.word}&rsquo; 마인드맵을 그리는 중<span className="lm-dots ml-0.5"><span>.</span><span>.</span><span>.</span></span>
      </p>
      <p className="mt-1 text-[15px] text-slate-200">
        {d.running || d.position === 0 ? "관련 회사를 찾고 있어요 · 보통 10~30초" : `앞에 ${d.position}개 단어가 먼저 그려지고 있어요 · 순서대로 그려요`}
      </p>
    </div>
  );
}

function WordInput({ disabled, onSubmit }: { disabled: boolean; onSubmit: (w: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); const w = text.trim(); if (w) onSubmit(w); }}>
      <label className="sr-only" htmlFor="lifemap-word">직접 입력</label>
      <input id="lifemap-word" value={text} onChange={(e) => setText(e.target.value)} maxLength={12} enterKeyHint="go" autoComplete="off"
        placeholder="직접 입력 (예: 원전, 비만약, 라면)"
        className="min-w-0 flex-1 rounded-2xl bg-white/10 px-4 py-3 text-[16px] font-bold text-white placeholder:text-slate-400 ring-1 ring-white/25 focus:outline-none focus:ring-2 focus:ring-sky-300" />
      <button type="submit" disabled={disabled || !text.trim()}
        className="shrink-0 rounded-2xl bg-sky-400 px-4 py-3 text-[16px] font-extrabold text-[#071226] transition hover:bg-sky-300 disabled:opacity-40">✨ 그리기</button>
    </form>
  );
}

/** 지금 보고 있는 것의 맨 위 카드: 무슨 일이 있었나 · 증시 영향 · 실제로 움직인 종목. */
function HeadCard({ src, topic, map, onPickStock }: { src: Source; topic?: LifeTopic; map: LifeMap; onPickStock: (s: LifeMovedStock) => void }) {
  const movedInMap = map.stages.flatMap((s) => s.companies).filter((c) => c.moved && c.rate != null)
    .sort((a, b) => Math.abs(b.rate!) - Math.abs(a.rate!)).slice(0, 3).map((c) => ({ code: c.code, name: c.name, rate: c.rate! }));
  if (topic) {
    return (
      <div>
        <div className="text-[14px] font-extrabold text-rose-200">{topic.sector} · 무슨 일이 있었나</div>
        <h3 className="mt-1 text-[24px] font-black leading-snug text-white sm:text-[28px]">{topic.title}</h3>
        <p className="mt-2 text-[16px] leading-relaxed text-slate-50"><b className="mr-1.5 text-amber-200">증시 영향</b>{topic.impact}</p>
        <MovedPills stocks={topic.stocks} onPick={onPickStock} />
      </div>
    );
  }
  const title = src.kind === "sector" ? `${src.name} 섹터` : `‘${map.word}’`;
  return (
    <div>
      <div className="text-[14px] font-extrabold text-sky-200">{src.kind === "sector" ? "섹터 · 기준 시점 이슈 뉴스로 그렸어요" : "직접 입력한 단어"}</div>
      <h3 className="mt-1 text-[24px] font-black leading-snug text-white sm:text-[28px]">{title}</h3>
      <p className="mt-2 text-[16px] leading-relaxed text-slate-50">
        {movedInMap.length ? <><b className="mr-1.5 text-amber-200">실제로 크게 움직인 종목</b>아래 종목이 ±5% 넘게 움직였어요.</> : "크게(±5% 이상) 움직인 관련 종목은 없었어요."}
      </p>
      <MovedPills stocks={movedInMap} onPick={onPickStock} />
    </div>
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

  useEffect(() => {
    let alive = true;
    lifeApi.overview().then((d) => { if (alive) { setData(d); setError(""); } }).catch((e) => alive && setError((e as Error).message));
    const mq = window.matchMedia("(min-width: 1024px)");
    const on = () => setIsPc(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => { alive = false; mq.removeEventListener("change", on); };
  }, []);

  function choose(s: Source) { setSrc(s); setPick(null); setNotice(""); }

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
    if (drawing || !data) return;
    const t = data.topics.findIndex((x) => x.name === word);
    if (t >= 0) return choose({ kind: "topic", i: t });           // 이미 있는 이슈·섹터는 그려 둔 것
    if (data.sector_maps[word]) return choose({ kind: "sector", name: word });
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

  if (error && !data) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-[15px] text-red-600 dark:text-red-400">{error}</p>;
  if (!data) return <div className="rounded-3xl bg-[#071226] py-24 text-center text-[15px] text-slate-200">마인드맵을 불러오는 중…</div>;

  const topic = src.kind === "topic" ? data.topics[src.i] : undefined;
  const map: LifeMap | undefined = src.kind === "topic" ? topic?.map : src.kind === "sector" ? data.sector_maps[src.name] : words[src.word];
  const articles = topic ? topic.articles : map?.articles || [];
  const basisLabel = map?.basis_label || topic?.basis_label || data.basis.label;

  function pickStock(s: LifeMovedStock) {
    const inMap = map?.stages.flatMap((st) => st.companies.map((c) => ({ c, st }))).find((x) => x.c.code === s.code);
    if (inMap) return setPick({ c: inMap.c, s: inMap.st });
    setPick({ c: { code: s.code, name: s.name, rate: s.rate, relevance: "강", reason: "", moved: true },
      note: topic ? `${topic.title} — ${topic.impact}` : "" });
  }

  return (
    <div className="lifemap-shell relative overflow-hidden rounded-3xl bg-[radial-gradient(120%_80%_at_50%_0%,#13305e_0%,#0a1a38_45%,#050d1f_100%)] px-4 py-5 text-slate-100 shadow-xl sm:p-6">
      <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(1px_1px_at_20%_30%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_70%_20%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_40%_80%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_85%_65%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_10%_75%,#fff_50%,transparent_51%)]" />
      <div className="relative">
        <div className="text-[14px] font-extrabold tracking-[0.18em] text-sky-200">NEWS → MARKET → STOCKS</div>
        <h2 className="mt-1 text-[24px] font-black leading-tight text-white sm:text-[28px]">오늘 증시를 움직인 뉴스</h2>
        <p className="mt-1.5 text-[15px] leading-relaxed text-slate-200">
          실제로 크게 움직인 종목과 그 원인 뉴스를 찾아, 관련 회사들을 원료부터 유통까지 이어 그렸어요.
        </p>
        {data.basis.label && (
          <p className="mt-2 inline-block rounded-full bg-amber-300/15 px-3 py-1 text-[14px] font-extrabold text-amber-100 ring-1 ring-amber-200/30">
            🕒 {data.basis.label}{data.basis.source === "kiwoom" ? " · 키움증권 API" : " · 공공데이터 종가"}
          </p>
        )}

        <section aria-label="지금 뜨는 이슈" className="mt-4">
          <h3 className="mb-2 text-[15px] font-extrabold text-white">🔥 지금 뜨는 이슈</h3>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
            {data.topics.map((t, i) => (
              <Chip key={t.name} tone="hot" on={src.kind === "topic" && src.i === i} onClick={() => choose({ kind: "topic", i })}>{t.name}</Chip>
            ))}
          </div>
        </section>
        <section aria-label="섹터" className="mt-3">
          <h3 className="mb-2 text-[15px] font-extrabold text-white">섹터</h3>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
            {data.sectors.filter((s) => data.sector_maps[s]).map((s) => (
              <Chip key={s} tone="sky" on={src.kind === "sector" && src.name === s} onClick={() => choose({ kind: "sector", name: s })}>{s}</Chip>
            ))}
            {Object.keys(words).map((w) => (
              <Chip key={`w-${w}`} on={src.kind === "word" && src.word === w} onClick={() => choose({ kind: "word", word: w })}>{w}</Chip>
            ))}
          </div>
          {data.live.enabled ? (
            <WordInput disabled={!!drawing} onSubmit={draw} />
          ) : (
            <p className="mt-2 text-[15px] text-slate-200">지금은 직접 입력을 쉬고 있어요. 이슈·섹터는 볼 수 있어요.</p>
          )}
          {notice && <p className="mt-2 rounded-xl bg-amber-400/15 px-3 py-2.5 text-[15px] font-bold text-amber-100 ring-1 ring-amber-300/30" role="status">{notice}</p>}
        </section>

        <div className="mt-5 lg:grid lg:grid-cols-[1.25fr_1fr] lg:gap-6">
          <div className="relative">
            {drawing && <DrawingOverlay d={drawing} />}
            {map ? (
              <>
                <HeadCard src={src} topic={topic} map={map} onPickStock={pickStock} />
                <div className="mt-4"><Badges map={map} basis={basisLabel} /></div>
                {map.stages.length > 0 ? (
                  <>
                    <div className="-mx-4 mt-2 sm:mx-0"><MindMap map={map} picked={pick?.c.code} onPick={(c, s) => setPick({ c, s })} /></div>
                    <Legend map={map} />
                  </>
                ) : (
                  <p className="mt-3 rounded-2xl bg-white/[0.06] px-4 py-16 text-center text-[15px] text-slate-200">
                    &lsquo;{map.word}&rsquo;에서 이어지는 상장사를 찾지 못했어요. 다른 단어로 해 보세요.
                  </p>
                )}
                <Articles items={articles} />
              </>
            ) : (
              <p className="rounded-2xl bg-white/[0.06] px-4 py-16 text-center text-[15px] text-slate-200">위에서 이슈나 섹터를 골라 주세요.</p>
            )}
          </div>
          <aside className="hidden lg:block">
            <div className="sticky top-4 rounded-3xl bg-white/[0.06] p-5 ring-1 ring-white/15">
              {pick ? <Detail pick={pick} /> : (
                <div className="py-12 text-center text-slate-200">
                  <div className="text-3xl">🔍</div>
                  <p className="mt-2 text-[16px] font-bold text-white">회사 버블이나 종목을 눌러 보세요</p>
                  <p className="mt-1 text-[15px]">&lsquo;왜 관련 있나&rsquo;와 &lsquo;왜 움직였나&rsquo;를 볼 수 있어요.</p>
                </div>
              )}
            </div>
          </aside>
        </div>

        <footer className="mt-5 rounded-2xl bg-black/30 p-4 text-[15px] leading-relaxed text-slate-200 ring-1 ring-white/15">
          <p className="font-extrabold text-white">ⓘ 투자 권유가 아닌 참고 정보예요</p>
          <p className="mt-1">
            AI가 뉴스와 회사의 사업 내용을 이어 그린 그림이라 틀리거나 빠진 회사가 있을 수 있어요. 금융위원회 공공데이터 상장 종목 목록에 있는
            회사만 보여 주며, 등락률은 표시한 기준 시점 값이에요. 뉴스는 NAVER 뉴스 검색으로 찾았어요.
          </p>
        </footer>
      </div>

      {pick && !isPc && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${pick.c.name} 상세`}>
          <button type="button" aria-label="닫기" onClick={() => setPick(null)} className="absolute inset-0 bg-black/55" />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-[#0b1a36] p-5 pb-8 shadow-2xl ring-1 ring-white/15">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/30" />
            <Detail pick={pick} onClose={() => setPick(null)} />
          </div>
        </div>
      )}
    </div>
  );
}
