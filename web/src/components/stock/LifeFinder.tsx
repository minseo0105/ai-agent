"use client";

// 뉴스 속 숨은 종목 탭: 오늘의 뉴스 → AI 해석 → 관련 회사 지도 → AI 해석 vs 실제 반응.
// 순서: 헤더(기준 시각) → 뉴스 카드(이슈별로 옆으로 넘기기) → AI 해석 → 관련 회사 지도 → 해석 vs 실제 반응 → 다른 이슈·섹터 → 고지.
// 서버가 미리 만든 것을 읽기만 한다(직접 입력한 단어만 대기열로 AI를 부른다 — WordInput).
// 휴대폰(640px 미만)에서는 바깥 상자 테두리·모서리·양옆 여백 없이 화면 끝까지. 글씨: 본문 15px+, 섹션 제목 18px+, 지도 회사 이름 13px+.
import { useEffect, useRef, useState } from "react";
import MindMap, { NEG, POS, pathColor, rateColor, rateText } from "@/components/stock/MindMap";
import { WhyBody } from "@/components/stock/StockOn";
import {
  lifeApi, stockApi, type LifeArticle, type LifeCompany, type LifeItem, type LifeOverview, type LifeStage, type LifeWordResult, type Stock, type Why,
} from "@/lib/stock";

// 이슈(섹터)별 강조색. 상승 빨강과 겹치지 않게 빨강 계열은 쓰지 않는다.
const ACCENTS: [RegExp, string][] = [
  [/반도체/, "#3b82f6"], [/보안|해킹|유출/, "#a855f7"], [/로봇/, "#f97316"], [/전장/, "#14b8a6"], [/금융|은행|증권/, "#22c55e"],
  [/AI|인공지능/, "#6366f1"], [/자동차|완성차/, "#06b6d4"], [/보험/, "#10b981"], [/2차전지|배터리/, "#84cc16"], [/바이오|제약/, "#ec4899"],
  [/방산|국방/, "#eab308"], [/조선|해운/, "#0ea5e9"], [/환율|외환/, "#f59e0b"], [/유가|정유|에너지/, "#d97706"], [/관세|무역|수출/, "#8b5cf6"],
];
const FALLBACK = ["#3b82f6", "#a855f7", "#f97316", "#14b8a6", "#22c55e"];
const accentFor = (it: LifeItem | undefined, i: number) =>
  ACCENTS.find(([re]) => re.test(`${it?.sector ?? ""} ${it?.name ?? ""}`))?.[1] ?? FALLBACK[i % FALLBACK.length];

const KST = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
function when(pub: string | null): { ymd: string; label: string } | null {
  if (!pub) return null;
  const d = new Date(pub);
  if (Number.isNaN(d.getTime())) return null;
  const p = Object.fromEntries(KST.formatToParts(d).map((x) => [x.type, x.value]));
  return { ymd: `${p.year}${p.month}${p.day}`, label: `${Number(p.month)}/${Number(p.day)} ${p.hour}:${p.minute}` };
}

type Pick = { c: LifeCompany; s?: LifeStage; color?: string };
type View = { kind: "topics" } | { kind: "sector"; name: string } | { kind: "word"; word: string };
type Drawing = { word: string; position: number; running: boolean };
const POLL_MS = 1500;
const POLL_MAX_MS = 100_000; // AI 한 번 45초 × 최대 2회 + 대기 여유

function ArticleMeta({ a, basis }: { a: LifeArticle; basis?: string }) {
  const w = when(a.pub);
  const other = w && basis && w.ymd !== basis;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[14px] text-slate-200">
      <span className="font-semibold">{a.press.replace(/^www\./, "")}</span>
      {w && <span className="tabular-nums">· {w.label}</span>}
      {other && (
        <span className="rounded-full bg-amber-300/20 px-2 py-0.5 text-[14px] font-extrabold text-amber-100 ring-1 ring-amber-200/40">
          {w!.ymd < basis! ? "기준일 전" : "기준일 뒤"}
        </span>
      )}
    </span>
  );
}

function NewsCard({ item, accent, basis, index, total, active, onSelect }: {
  item: LifeItem; accent: string; basis?: string; index?: number; total?: number; active: boolean; onSelect?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rep = item.articles.find((a) => a.rep) || item.articles[0];
  const rest = item.articles.filter((a) => a !== rep);
  return (
    <article onClick={onSelect} aria-current={active}
      className="flex w-[86vw] max-w-[560px] shrink-0 snap-center flex-col rounded-3xl p-4 sm:w-[520px]"
      style={{ border: `2px solid ${active ? accent : `${accent}66`}`, background: `linear-gradient(150deg, ${accent}40 0%, ${accent}12 45%, rgba(5,13,31,.6) 100%)`,
        boxShadow: active ? `0 0 28px ${accent}55` : "none" }}>
      <div className="flex items-center justify-between gap-2 text-[14px] font-extrabold">
        <span className="flex items-center gap-1.5 text-white">
          <span className="size-2.5 rounded-full" style={{ background: accent, boxShadow: `0 0 8px ${accent}` }} />
          {index != null ? `ISSUE ${index + 1}` : "ISSUE"}{item.sector ? ` · ${item.sector}` : ""}
        </span>
        <span className="text-slate-200">{total ? `${(index ?? 0) + 1} / ${total}` : ""}</span>
      </div>
      {rep ? (
        <a href={rep.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
          className="mt-2 block text-[19px] font-black leading-snug text-white underline-offset-4 hover:underline sm:text-[20px]">{rep.title}</a>
      ) : (
        <h3 className="mt-2 text-[19px] font-black leading-snug text-white sm:text-[20px]">{item.title}</h3>
      )}
      {rep && <div className="mt-1.5"><ArticleMeta a={rep} basis={basis} /></div>}
      <p className="mt-2.5 text-[15px] leading-relaxed text-slate-50"><b className="mr-1 text-white">{item.title}</b>{item.summary && ` — ${item.summary}`}</p>
      {rest.length > 0 && (
        <div className="mt-auto pt-3">
          <button type="button" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }} aria-expanded={open}
            className="rounded-full bg-white/10 px-3 py-1.5 text-[14px] font-extrabold text-white ring-1 ring-white/20 hover:bg-white/15">
            관련 기사 {rest.length}건 {open ? "▴" : "▾"}
          </button>
          {open && (
            <ul className="mt-2 space-y-2.5">
              {rest.map((a) => (
                <li key={a.url} className="text-[15px] leading-snug">
                  <a href={a.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
                    className="font-bold text-slate-50 underline-offset-2 hover:underline">{a.title}</a>
                  <div className="mt-0.5"><ArticleMeta a={a} basis={basis} /></div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

function SectionTitle({ children, badge }: { children: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h3 className="text-[19px] font-black text-white">{children}</h3>
      {badge}
    </div>
  );
}

const Dir = ({ d }: { d?: "pos" | "neg" }) => (
  <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[14px] font-extrabold text-[#071226]" style={{ background: d === "neg" ? NEG : POS }}>
    {d === "neg" ? "− 부정 가능" : "+ 긍정 가능"}
  </span>
);

function ReactionTable({ item, accent, onPick }: { item: LifeItem; accent: string; onPick: (c: LifeCompany, s: LifeStage, color: string) => void }) {
  const rows = item.map.stages.flatMap((s, i) => s.companies.map((c) => ({ c, s, color: pathColor(i) })));
  return (
    <div className="overflow-hidden rounded-2xl" style={{ border: `1.5px solid ${accent}88`, background: `linear-gradient(180deg, ${accent}22, rgba(255,255,255,.03))` }}>
      <table className="w-full text-left text-[15px]">
        <thead>
          <tr className="text-[14px] text-slate-200">
            <th className="px-3 py-2.5 font-extrabold">회사</th>
            <th className="px-2 py-2.5 font-extrabold">AI 해석</th>
            <th className="px-3 py-2.5 text-right font-extrabold">실제 등락률</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, s, color }) => (
            <tr key={c.code} onClick={() => onPick(c, s, color)} className="cursor-pointer border-t border-white/10 hover:bg-white/5">
              <td className="px-3 py-2.5">
                <div className="font-extrabold text-white">{c.name}</div>
                <div className="text-[14px] font-semibold" style={{ color }}>{s.label}</div>
              </td>
              <td className="px-2 py-2.5"><Dir d={c.direction} /></td>
              <td className="px-3 py-2.5 text-right">
                <div className="text-[17px] font-black tabular-nums" style={{ color: rateColor(c.rate) }}>{rateText(c.rate)}</div>
                {c.moved && <div className="text-[14px] font-extrabold text-amber-100">실제 반응 큼</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-white/10 px-3 py-2 text-[14px] text-slate-200">
        실제 등락률: {item.map.reaction_label || "기준 시점"} · AI 해석과 실제 반응을 나란히 보여 줄 뿐, 맞고 틀림을 매기지 않아요.
      </p>
    </div>
  );
}

function Detail({ pick, label, onClose }: { pick: Pick; label?: string; onClose?: () => void }) {
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
            {s && <span className="rounded-full px-2.5 py-0.5 text-[#071226]" style={{ background: pick.color }}>{s.label}</span>}
            <Dir d={c.direction} />
            <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-slate-100">관련 종목 · 참고용</span>
          </div>
          <h3 className="mt-2 text-[22px] font-extrabold leading-tight text-white">{c.name}</h3>
          <p className="text-[14px] text-slate-300">{c.code}{c.market ? ` · ${c.market}` : ""} · 연관도 {c.relevance}</p>
        </div>
        <div className="shrink-0 whitespace-nowrap text-right">
          {c.moved && <div className="mb-0.5 text-[14px] font-extrabold text-amber-200">실제 반응 큼</div>}
          <div className="text-[20px] font-black tabular-nums" style={{ color: rateColor(c.rate) }}>{rateText(c.rate)}</div>
          <div className="text-[14px] text-slate-300">{label || "실제 등락률"}</div>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 rounded-full px-2 text-2xl text-slate-200">✕</button>}
      </div>
      <div className="mt-3 rounded-2xl bg-white/[0.08] p-3.5 ring-1 ring-white/15">
        <div className="text-[15px] font-extrabold text-sky-200">왜 관련 있나</div>
        <p className="mt-1 text-[16px] font-bold leading-relaxed text-white">{c.reason}</p>
        <p className="mt-1.5 text-[14px] text-slate-300">🤖 AI가 해석했어요 · 영향을 받을 수 있다는 해석이며 틀릴 수 있어요</p>
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
        <span className="relative text-4xl">🤖</span>
      </div>
      <p className="mt-3 text-[18px] font-extrabold text-white">
        AI가 &lsquo;{d.word}&rsquo; 뉴스를 해석하는 중<span className="lm-dots ml-0.5"><span>.</span><span>.</span><span>.</span></span>
      </p>
      <p className="mt-1 text-[15px] text-slate-200">
        {d.running || d.position === 0 ? "최근 뉴스를 읽고 관련 회사를 찾고 있어요 · 보통 10~30초" : `앞에 ${d.position}개 단어가 먼저 해석되고 있어요 · 순서대로 해요`}
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
        placeholder="직접 입력 (예: 원전, 비만약, 금리)"
        className="min-w-0 flex-1 rounded-2xl bg-white/10 px-4 py-3 text-[16px] font-bold text-white placeholder:text-slate-400 ring-1 ring-white/25 focus:outline-none focus:ring-2 focus:ring-sky-300" />
      <button type="submit" disabled={disabled || !text.trim()}
        className="shrink-0 rounded-2xl bg-sky-400 px-4 py-3 text-[16px] font-extrabold text-[#071226] transition hover:bg-sky-300 disabled:opacity-40">🤖 해석</button>
    </form>
  );
}

function Chip({ on, onClick, children, color }: { on: boolean; onClick: () => void; children: React.ReactNode; color: string }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className="shrink-0 rounded-full px-3.5 py-2 text-[15px] font-extrabold ring-1 transition"
      style={on ? { background: "#fff", color: "#071226" } : { background: `${color}26`, color: "#fff", boxShadow: `inset 0 0 0 1px ${color}88` }}>
      {children}
    </button>
  );
}

export default function LifeFinder() {
  const [data, setData] = useState<LifeOverview | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>({ kind: "topics" });
  const [active, setActive] = useState(0);
  const [pick, setPick] = useState<Pick | null>(null);
  const [isPc, setIsPc] = useState(false);
  const [words, setWords] = useState<Record<string, LifeItem>>({});
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [notice, setNotice] = useState("");
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rail = useRef<HTMLDivElement>(null);
  const top = useRef<HTMLDivElement>(null);
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

  // 옆으로 넘긴 뉴스 카드 중 가운데 것이 지금 이슈
  function onRailScroll() {
    const el = rail.current;
    if (!el) return;
    const mid = el.scrollLeft + el.clientWidth / 2;
    let best = 0, dist = Infinity;
    [...el.children].forEach((ch, i) => {
      const c = ch as HTMLElement;
      const d = Math.abs(c.offsetLeft + c.offsetWidth / 2 - mid);
      if (d < dist) { dist = d; best = i; }
    });
    if (best !== active) { setActive(best); setPick(null); }
  }
  function goTopic(i: number) {
    setView({ kind: "topics" });
    setActive(i);
    setPick(null);
    setNotice("");
    requestAnimationFrame(() => {
      const card = rail.current?.children[i] as HTMLElement | undefined;
      rail.current?.scrollTo({ left: card ? card.offsetLeft - (rail.current.clientWidth - card.offsetWidth) / 2 : 0, behavior: "smooth" });
      top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  function goOther(v: View) {
    setView(v);
    setPick(null);
    setNotice("");
    requestAnimationFrame(() => top.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  /** 서버 응답 하나를 화면에 반영한다. 끝났으면 true. */
  function apply(r: LifeWordResult): boolean {
    if (r.status === "queued" || r.status === "running") {
      setDrawing({ word: r.word, position: r.position ?? 0, running: r.status === "running" });
      return false;
    }
    setDrawing(null);
    if (r.item) {
      setWords((w) => ({ ...w, [r.word]: r.item! }));
      goOther({ kind: "word", word: r.word });
    }
    setNotice(r.status === "ready" ? "" : r.message || (r.status === "none" ? "해석하던 내용을 찾지 못했어요. 한 번 더 눌러 주세요." : ""));
    return true;
  }

  async function draw(word: string) {
    if (drawing || !data) return;
    const t = data.topics.findIndex((x) => x.name === word);
    if (t >= 0) return goTopic(t);                       // 이미 있는 이슈·섹터는 만들어 둔 것
    if (data.sector_items[word]) return goOther({ kind: "sector", name: word });
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
          setNotice("해석하는 데 시간이 오래 걸려요. 잠시 뒤 같은 단어를 다시 눌러 주세요(다 되면 바로 보여요).");
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
  if (!data) return <div className="-mx-4 bg-[#071226] py-24 text-center text-[15px] text-slate-200 sm:mx-0 sm:rounded-3xl">뉴스를 불러오는 중…</div>;

  const item: LifeItem | undefined = view.kind === "topics" ? data.topics[active] : view.kind === "sector" ? data.sector_items[view.name] : words[view.word];
  const accent = accentFor(item, view.kind === "topics" ? active : 0);
  const basisYmd = data.basis.as_of;
  const label = item?.map.reaction_label;

  return (
    <div ref={top} className="lifemap-shell relative -mx-4 scroll-mt-2 overflow-hidden px-4 pb-8 pt-5 text-slate-100 sm:mx-0 sm:rounded-3xl sm:p-6 sm:shadow-xl"
      style={{ background: `linear-gradient(180deg, ${accent}55 0%, #0b1d40 22%, #071430 55%, #050d1f 100%)`, transition: "background 400ms" }}>
      <div className="pointer-events-none absolute inset-0 opacity-30 [background-image:radial-gradient(1px_1px_at_20%_30%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_70%_20%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_40%_80%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_85%_65%,#fff_50%,transparent_51%),radial-gradient(1px_1px_at_10%_75%,#fff_50%,transparent_51%)]" />
      <div className="relative">
        {/* 헤더 */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[22px] font-black leading-tight text-white sm:text-[26px]">오늘의 뉴스, 연결된 회사까지</h2>
          {data.basis.label && (
            <span className="rounded-full bg-black/30 px-3 py-1 text-[14px] font-extrabold text-amber-100 ring-1 ring-amber-200/40">
              🕒 {data.basis.label}{data.basis.source === "kiwoom" ? " · 키움증권 API" : ""}
            </span>
          )}
        </div>

        {/* 뉴스 카드 */}
        <div className="relative mt-4">
          {drawing && <DrawingOverlay d={drawing} />}
          {view.kind === "topics" ? (
            <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[15px] font-extrabold text-white">오늘의 이슈 {active + 1} / {data.topics.length}</span>
              <div className="flex gap-1.5">
                {[["‹", -1, "이전 이슈"], ["›", 1, "다음 이슈"]].map(([t, d, name]) => (
                  <button key={name as string} type="button" aria-label={name as string} disabled={active + (d as number) < 0 || active + (d as number) >= data.topics.length}
                    onClick={() => goTopic(active + (d as number))}
                    className="size-10 rounded-full border border-white/25 bg-white/10 text-xl font-bold text-white hover:bg-white/20 disabled:opacity-30">{t as string}</button>
                ))}
              </div>
            </div>
            <div ref={rail} onScroll={onRailScroll} className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] sm:mx-0 sm:px-0" aria-label="오늘의 이슈">
              {data.topics.map((t, i) => (
                <NewsCard key={t.name} item={t} accent={accentFor(t, i)} basis={basisYmd} index={i} total={data.topics.length}
                  active={i === active} onSelect={() => i !== active && goTopic(i)} />
              ))}
            </div>
            </>
          ) : item ? (
            <div className="space-y-2">
              <button type="button" onClick={() => goTopic(active)} className="text-[15px] font-extrabold text-sky-200 hover:underline">← 오늘의 이슈로</button>
              <div className="flex"><NewsCard item={item} accent={accent} basis={basisYmd} active /></div>
            </div>
          ) : null}
        </div>

        {item && (
          <div className="mt-8 lg:grid lg:grid-cols-[1.25fr_1fr] lg:gap-8">
            <div className="space-y-9">
              {/* AI 해석 */}
              <section aria-label="AI 해석">
                <SectionTitle badge={<span className="rounded-full bg-gradient-to-r from-sky-400/30 to-violet-400/30 px-2.5 py-1 text-[14px] font-extrabold text-sky-50 ring-1 ring-sky-300/40">🤖 AI가 해석했어요</span>}>
                  AI 해석
                </SectionTitle>
                {item.map.interpretation?.length ? (
                  <ul className="space-y-2.5">
                    {item.map.interpretation.map((t, i) => (
                      <li key={i} className="flex gap-2.5 text-[16px] leading-relaxed text-slate-50">
                        <span className="mt-2 size-2 shrink-0 rounded-full" style={{ background: accent }} />{t}
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-[15px] text-slate-200">해석을 준비하지 못했어요.</p>}
                {item.example && <p className="mt-2 text-[14px] font-bold text-amber-100">준비된 예시예요(지금 이슈가 아니에요).</p>}
              </section>

              {/* 관련 회사 지도 */}
              <section aria-label="관련 회사 지도">
                <SectionTitle badge={<span className="rounded-full bg-white/15 px-2.5 py-1 text-[14px] font-extrabold text-white">관련 종목 · 참고용</span>}>
                  영향을 받을 수 있는 회사
                </SectionTitle>
                {item.map.stages.length ? (
                  <>
                    <div className="-mx-4 sm:mx-0"><MindMap map={item.map} center={item.name} picked={pick?.c.code} onPick={(c, s, color) => setPick({ c, s, color })} /></div>
                    <div className="mt-3 space-y-2 text-[15px] leading-relaxed text-slate-100">
                      <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
                        {item.map.stages.map((s, i) => (
                          <li key={s.key} className="flex items-center gap-1.5">
                            <span className="size-3 rounded-full" style={{ background: pathColor(i), boxShadow: `0 0 8px ${pathColor(i)}` }} />
                            <b style={{ color: pathColor(i) }}>{s.label}</b>{s.detail && <span className="text-slate-100">{s.detail}</span>}
                          </li>
                        ))}
                      </ul>
                      <p>
                        <span className="font-extrabold" style={{ color: POS }}>＋ 긍정 영향 가능</span> · <span className="font-extrabold" style={{ color: NEG }}>－ 부정 영향 가능</span>(AI 해석) ·
                        버블이 클수록 연관이 커요 · <b className="text-white">빛나는 테두리 = 실제 반응</b>(±5% 이상) · 숫자는 {label || "실제 등락률"}
                      </p>
                    </div>
                  </>
                ) : (
                  <p className="rounded-2xl bg-white/[0.06] px-4 py-12 text-center text-[15px] text-slate-200">이 뉴스와 확실히 이어지는 상장사를 찾지 못했어요.</p>
                )}
              </section>

              {/* AI 해석 vs 실제 반응 */}
              {item.map.stages.length > 0 && (
                <section aria-label="AI 해석 vs 실제 반응">
                  <SectionTitle>AI 해석 vs 실제 반응</SectionTitle>
                  <ReactionTable item={item} accent={accent} onPick={(c, s, color) => setPick({ c, s, color })} />
                </section>
              )}
            </div>
            <aside className="hidden lg:block">
              <div className="sticky top-4 rounded-3xl bg-white/[0.06] p-5 ring-1 ring-white/15">
                {pick ? <Detail pick={pick} label={label} /> : (
                  <div className="py-12 text-center text-slate-200">
                    <div className="text-3xl">🔍</div>
                    <p className="mt-2 text-[16px] font-bold text-white">회사 버블이나 표의 회사를 눌러 보세요</p>
                    <p className="mt-1 text-[15px]">&lsquo;왜 관련 있나&rsquo;와 &lsquo;왜 움직였나&rsquo;를 볼 수 있어요.</p>
                  </div>
                )}
              </div>
            </aside>
          </div>
        )}

        {/* 다른 이슈·섹터 보기 */}
        <section aria-label="다른 이슈·섹터 보기" className="mt-10">
          <SectionTitle>다른 이슈·섹터 보기</SectionTitle>
          <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
            <span className="shrink-0 text-[15px] font-extrabold text-rose-100">🔥 지금 뜨는 이슈</span>
            {data.topics.map((t, i) => (
              <Chip key={t.name} color={accentFor(t, i)} on={view.kind === "topics" && active === i} onClick={() => goTopic(i)}>{t.name}</Chip>
            ))}
            <span className="ml-2 shrink-0 text-[15px] font-extrabold text-sky-100">섹터</span>
            {data.sectors.filter((s) => data.sector_items[s]).map((s, i) => (
              <Chip key={s} color={accentFor(data.sector_items[s], i)} on={view.kind === "sector" && view.name === s} onClick={() => goOther({ kind: "sector", name: s })}>{s}</Chip>
            ))}
            {Object.keys(words).map((w) => (
              <Chip key={`w-${w}`} color="#94a3b8" on={view.kind === "word" && view.word === w} onClick={() => goOther({ kind: "word", word: w })}>{w}</Chip>
            ))}
          </div>
          {data.live.enabled ? (
            <WordInput disabled={!!drawing} onSubmit={draw} />
          ) : (
            <p className="mt-2 text-[15px] text-slate-200">지금은 직접 입력을 쉬고 있어요. 이슈·섹터는 볼 수 있어요.</p>
          )}
          {notice && <p className="mt-2 rounded-xl bg-amber-400/15 px-3 py-2.5 text-[15px] font-bold text-amber-100 ring-1 ring-amber-300/30" role="status">{notice}</p>}
        </section>

        <footer className="mt-10 rounded-2xl bg-black/30 p-4 text-[15px] leading-relaxed text-slate-200 ring-1 ring-white/15">
          <p className="font-extrabold text-white">ⓘ 투자 권유가 아닌 참고 정보 · AI 해석은 틀릴 수 있어요</p>
          <p className="mt-1">
            뉴스를 읽고 영향을 받을 수 있는 회사를 AI가 해석한 것이며, 주가 방향을 말하지 않아요. 금융위원회 공공데이터 상장 종목 목록에 있는
            회사만 보여 주고, 실제 등락률은 표시한 시점 값이에요. 뉴스는 NAVER 뉴스 검색으로 찾았어요.
          </p>
        </footer>
      </div>

      {pick && !isPc && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`${pick.c.name} 상세`}>
          <button type="button" aria-label="닫기" onClick={() => setPick(null)} className="absolute inset-0 bg-black/55" />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-[#0b1a36] p-5 pb-8 shadow-2xl ring-1 ring-white/15">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/30" />
            <Detail pick={pick} label={label} onClose={() => setPick(null)} />
          </div>
        </div>
      )}
    </div>
  );
}
