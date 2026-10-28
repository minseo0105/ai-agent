"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Heatmap from "@/components/stock/Heatmap";
import {
  arrow, basisLabel, dateLabel, eok, pct, stockApi, timeLabel, tone, won,
  type EventItem, type Fx, type IndexCard, type Market, type NewsItem, type Overview, type Source, type Stock, type Why,
} from "@/lib/stock";

const SECTIONS = [
  ["brief", "브리핑"], ["indices", "지수"], ["heatmap", "히트맵"], ["movers", "등락 상위"],
  ["flows", "수급"], ["watch", "관심 종목"], ["news", "뉴스"], ["week", "일정"],
] as const;

function Section({ id, eyebrow, title, meta, children, className = "" }: { id: string; eyebrow: string; title: string; meta?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section id={id} className={`scroll-mt-20 rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-5 ${className}`}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-x-3 gap-y-1">
        <div>
          <div className="text-[10px] font-extrabold tracking-[0.16em] text-[#1E4E8C] dark:text-sky-300">{eyebrow}</div>
          <h2 className="text-base font-extrabold tracking-tight sm:text-lg">{title}</h2>
        </div>
        {meta && <div className="text-[11px] font-semibold text-subtle">{meta}</div>}
      </div>
      {children}
    </section>
  );
}

function SourceLink({ s }: { s: Source }) {
  return s.url ? (
    <a href={s.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted underline-offset-2 hover:text-fg">{s.name}</a>
  ) : (
    <span>{s.name}</span>
  );
}

/** 문장 + 출처 번호. 번호를 누르면 출처 링크로 간다. */
function Sentences({ sentences, sources, numbered }: { sentences: { text: string; sources: number[] }[]; sources: Source[]; numbered?: boolean }) {
  return (
    <ol className="space-y-2">
      {sentences.map((s, i) => (
        <li key={i} className="flex gap-2 text-sm leading-relaxed sm:text-[15px]">
          {numbered && <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-[#13315C] text-[11px] font-extrabold text-white">{i + 1}</span>}
          <span>
            {s.text}
            {s.sources.map((n) => {
              const src = sources[n - 1];
              return src?.url ? (
                <a key={n} href={src.url} target="_blank" rel="noopener noreferrer" title={src.name} className="ml-0.5 align-super text-[10px] font-extrabold text-[#1E4E8C] hover:underline dark:text-sky-300">[{n}]</a>
              ) : (
                <sup key={n} title={src?.name} className="ml-0.5 text-[10px] font-extrabold text-subtle">[{n}]</sup>
              );
            })}
          </span>
        </li>
      ))}
    </ol>
  );
}

function SourceList({ sources, used }: { sources: Source[]; used?: number[] }) {
  const [open, setOpen] = useState(false);
  const list = sources.map((s, i) => ({ s, n: i + 1 })).filter(({ n }) => !used || used.includes(n));
  if (!list.length) return null;
  return (
    <div className="mt-3 border-t border-border pt-2">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="text-xs font-bold text-muted hover:text-fg">
        출처 {list.length}개 {open ? "접기 ▴" : "보기 ▾"}
      </button>
      {open && (
        <ol className="mt-2 space-y-1 text-xs text-muted">
          {list.map(({ s, n }) => (
            <li key={n}>[{n}] <SourceLink s={s} /></li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** 30거래일 추이. 그날 등락(빨강·파랑)과 헷갈리지 않게 중립 남색으로 그린다. */
function Spark({ series }: { series: { c: number | null }[] }) {
  const pts = series.map((p) => p.c).filter((c): c is number => c != null);
  if (pts.length < 2) return null;
  const min = Math.min(...pts), max = Math.max(...pts), span = max - min || 1;
  const d = pts.map((c, i) => `${((i / (pts.length - 1)) * 100).toFixed(1)},${(28 - ((c - min) / span) * 26).toFixed(1)}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="mt-2 h-8 w-full" aria-hidden>
      <polyline points={d} fill="none" strokeWidth="2" vectorEffect="non-scaling-stroke" className="stroke-[#1E4E8C] dark:stroke-sky-300" />
    </svg>
  );
}

function IndexTile({ card, fx, asOf, basis }: { card?: IndexCard; fx?: Fx | null; asOf?: string; basis?: string }) {
  if (fx !== undefined) {
    return (
      <div className="min-w-[44%] flex-1 rounded-2xl bg-surface-muted p-3 sm:min-w-0">
        <div className="text-xs font-bold text-muted">원/달러</div>
        {fx?.status === "ok" ? (
          <>
            <div className="mt-1 text-xl font-extrabold tabular-nums">{fx.close?.toLocaleString("ko-KR", { minimumFractionDigits: 1 })}</div>
            <div className={`text-xs font-bold tabular-nums ${tone(fx.change)}`}>{arrow(fx.change)} {fx.change != null ? Math.abs(fx.change).toFixed(1) : "—"} ({pct(fx.rate)})</div>
            <div className="mt-2 text-[10px] text-subtle">매매기준율 · {dateLabel(fx.as_of)} · <SourceLink s={fx.source} /></div>
          </>
        ) : (
          <div className="mt-2 text-xs text-subtle">{fx?.status === "not_configured" ? "환율 키 미설정 (관리자)" : "환율을 불러오지 못했어요"}</div>
        )}
      </div>
    );
  }
  if (!card || card.close == null) return <div className="min-w-[44%] flex-1 rounded-2xl bg-surface-muted p-3 text-xs text-subtle sm:min-w-0">{card?.name ?? "지수"} 자료 없음</div>;
  return (
    <div className="min-w-[44%] flex-1 rounded-2xl bg-surface-muted p-3 sm:min-w-0">
      <div className="text-xs font-bold text-muted">{card.name}</div>
      <div className="mt-1 text-xl font-extrabold tabular-nums">{card.close.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
      <div className={`text-xs font-bold tabular-nums ${tone(card.rate)}`}>{arrow(card.rate)} {card.change != null ? Math.abs(card.change).toFixed(2) : "—"} ({pct(card.rate)})</div>
      <Spark series={card.series || []} />
      <div className="text-[10px] text-subtle">{basis ?? `${dateLabel(card.as_of)} 종가`} · 최근 30거래일</div>
      {asOf && card.as_of !== asOf && (
        <div className="mt-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">지수 자료가 아직 {dateLabel(asOf)} 전이에요</div>
      )}
    </div>
  );
}

function StockRow({ s, rank, onWhy }: { s: Stock; rank: number; onWhy: (s: Stock) => void }) {
  return (
    <li>
      <button type="button" onClick={() => onWhy(s)} className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface-muted">
        <span className="w-5 text-center text-xs font-extrabold text-subtle">{rank}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold">{s.name}</span>
          <span className="text-[11px] text-subtle">{s.market} · 거래대금 {eok(s.value)}</span>
        </span>
        <span className="text-right">
          <span className="block text-sm font-bold tabular-nums">{won(s.close)}</span>
          <span className={`text-xs font-bold tabular-nums ${tone(s.rate)}`}>{arrow(s.rate)} {pct(s.rate)}</span>
        </span>
      </button>
    </li>
  );
}

function Tabs<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="so-row mb-3 flex gap-1 overflow-x-auto rounded-xl bg-surface-muted p-1">
      {options.map(([v, l]) => (
        <button key={v} role="tab" type="button" aria-selected={value === v} onClick={() => onChange(v)}
          className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold transition ${value === v ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}>
          {l}
        </button>
      ))}
    </div>
  );
}

/** 기사 발행일(한국시간) YYYYMMDD */
const kstDay = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" }).replaceAll("-", "") : "";

function NewsList({ items, limit, basis }: { items: NewsItem[]; limit?: number; basis?: string }) {
  if (!items.length) return <p className="py-4 text-center text-xs text-subtle">관련 뉴스가 없어요.</p>;
  return (
    <ul className="divide-y divide-border">
      {items.slice(0, limit).map((n) => {
        const day = kstDay(n.pub);
        const after = !!basis && !!day && day > basis;
        return (
          <li key={n.url} className="py-2.5">
            <a href={n.url} target="_blank" rel="noopener noreferrer" className="text-sm font-bold leading-snug hover:underline">{n.title}</a>
            {n.summary && <p className="mt-0.5 text-xs leading-relaxed text-muted"><span className="mr-1 rounded bg-[#13315C]/10 px-1 text-[10px] font-extrabold text-[#1E4E8C] dark:bg-sky-400/10 dark:text-sky-300">AI 요약</span>{n.summary}</p>}
            <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-subtle">
              {day && (
                <span className={`rounded px-1 font-extrabold ${after ? "bg-amber-500/15 text-amber-800 dark:text-amber-300" : "bg-surface-muted text-muted"}`}>
                  {dateLabel(day)}{after ? " · 시세 기준일 이후" : ""}
                </span>
              )}
              {n.press}{n.pub ? ` · ${new Date(n.pub).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" })}` : ""}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

/** 카테고리 뉴스: 시세 기준일 이후 기사와 그 이전 기사를 나눠 보여 준다(지수는 전일 하락인데 오늘 급등 기사가 섞여 헷갈리지 않게). */
function SplitNews({ items, basis }: { items: NewsItem[]; basis?: string }) {
  const later = basis ? items.filter((n) => kstDay(n.pub) > basis) : [];
  const upto = basis ? items.filter((n) => !(kstDay(n.pub) > basis)) : items;
  if (!later.length || !upto.length) {
    return (
      <>
        {later.length > 0 && <p className="mb-1 rounded-lg bg-amber-500/10 px-2 py-1 text-[11px] font-bold text-amber-800 dark:text-amber-300">모두 시세 기준일({dateLabel(basis)}) 이후 기사예요. 위 지수·종목 숫자보다 나중 소식이에요.</p>}
        <NewsList items={items} basis={basis} />
      </>
    );
  }
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-xs font-extrabold text-amber-800 dark:text-amber-300">시세 기준일({dateLabel(basis)}) 이후 새 소식</h3>
        <NewsList items={later} basis={basis} />
      </div>
      <div>
        <h3 className="text-xs font-extrabold text-muted">{dateLabel(basis)}까지 소식 · 위 시세와 같은 시점</h3>
        <NewsList items={upto} basis={basis} />
      </div>
    </div>
  );
}

export function WhyBody({ stock, why, error, loading, live }: { stock: Stock; why: Why | null; error: string; loading: boolean; live?: boolean }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <div className="text-[10px] font-extrabold tracking-[0.16em] text-[#1E4E8C] dark:text-sky-300">WHY IT MOVED</div>
          <h3 className="text-lg font-extrabold">{stock.name}</h3>
        </div>
        <div className="text-right">
          <div className="text-sm font-bold tabular-nums">{won(stock.close)}</div>
          <div className={`text-xs font-bold tabular-nums ${tone(stock.rate)}`}>{arrow(stock.rate)} {pct(stock.rate)}</div>
        </div>
      </div>
      <p className="mt-0.5 text-[11px] text-subtle">{stock.market} · 시가총액 {eok(stock.cap)} · 거래대금 {eok(stock.value)}</p>
      {why && live && (
        <p className="mt-2 text-[11px] font-bold text-amber-700 dark:text-amber-300">아래 설명은 {dateLabel(why.as_of)}(전일) 움직임 기준이에요. 위 가격은 오늘 키움 시세예요.</p>
      )}
      <div className="mt-3 rounded-2xl bg-surface-muted p-3">
        {loading && <p className="text-sm text-muted">불러오는 중…</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {why && (
          <>
            {why.sentences.length > 0 && <Sentences sentences={why.sentences} sources={why.sources} />}
            {why.note && <p className="text-sm text-muted">{why.note}</p>}
            {!why.ready && (
              <a href={`https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(stock.name)}`} target="_blank" rel="noopener noreferrer"
                className="mt-2 inline-block text-xs font-bold text-[#1E4E8C] underline underline-offset-2 dark:text-sky-300">네이버 뉴스에서 &lsquo;{stock.name}&rsquo; 찾아보기 ↗</a>
            )}
            {why.ai && <p className="mt-2 text-[10px] text-subtle">AI가 아래 뉴스·공시 제목과 요약문만으로 정리했어요. 원문을 꼭 확인해 주세요.</p>}
          </>
        )}
      </div>
      {why && why.disclosures.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-extrabold text-muted">최근 공시 (DART)</div>
          <ul className="space-y-1">
            {why.disclosures.map((d) => (
              <li key={d.url} className="text-xs"><a href={d.url} target="_blank" rel="noopener noreferrer" className="font-bold hover:underline">{d.title}</a> <span className="text-subtle">{dateLabel(d.date)}</span></li>
            ))}
          </ul>
        </div>
      )}
      {why && why.news.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-extrabold text-muted">관련 뉴스</div>
          <NewsList items={why.news} />
        </div>
      )}
      {why && <SourceList sources={why.sources} />}
    </div>
  );
}

const BASIS_TONE = {
  live: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  auction: "bg-violet-500/15 text-violet-800 dark:text-violet-300",
  closed: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  prev: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
};

function Freshness({ market }: { market?: Market | null }) {
  const b = basisLabel(market);
  if (!b) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-extrabold ${BASIS_TONE[b.tone]}`}>
      {b.tone === "live" && <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-emerald-500" />}
      {b.text}
    </span>
  );
}

function FlowList({ title, rows, sell }: { title: string; rows: { name: string; amount: number }[]; sell?: boolean }) {
  return (
    <div className="rounded-2xl bg-surface-muted p-3">
      <div className="mb-1 text-xs font-extrabold text-muted">{title}</div>
      {rows.length ? (
        <ol className="space-y-1 text-sm">
          {rows.map((r, i) => (
            <li key={`${r.name}-${i}`} className="flex justify-between gap-2">
              <span className="truncate font-bold">{i + 1}. {r.name}</span>
              <span className={`shrink-0 tabular-nums text-xs font-bold ${sell ? "text-blue-600 dark:text-blue-400" : "text-rose-600 dark:text-rose-400"}`}>{eok(r.amount)}</span>
            </li>
          ))}
        </ol>
      ) : <p className="text-xs text-subtle">자료 없음</p>}
    </div>
  );
}

function groupByDate(events: EventItem[]) {
  const map = new Map<string, EventItem[]>();
  for (const e of events) map.set(e.date, [...(map.get(e.date) || []), e]);
  return [...map.entries()];
}

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

export default function StockOn() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [heatTab, setHeatTab] = useState<"KOSPI" | "KOSDAQ">("KOSPI");
  const [moverTab, setMoverTab] = useState<"up" | "down" | "value">("up");
  const [newsTab, setNewsTab] = useState("market");
  const [moversAll, setMoversAll] = useState(false);
  const [picked, setPicked] = useState<Stock | null>(null);
  const [why, setWhy] = useState<Why | null>(null);
  const [whyError, setWhyError] = useState("");
  const [whyLoading, setWhyLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const polls = useRef(0);

  const load = useCallback(async () => {
    try {
      const d = await stockApi.overview();
      setData(d);
      setError("");
      return d;
    } catch (e) {
      // 이미 보이는 화면이 있으면 지우지 않는다(장 상태가 바뀌는 순간·일시 오류에도 화면이 비지 않게).
      setError((e as Error).message);
      return null;
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const d = await load();
      // 처음 자료를 모으는 동안에는 5초마다(최대 2분), 그 뒤에는 1분마다 저장된 스냅샷을 다시 읽는다.
      const firstFill = d?.enabled && d.refreshing && !d.market && polls.current++ < 24;
      timer = setTimeout(tick, firstFill ? 5000 : 60000);
    };
    tick();
    return () => clearTimeout(timer);
  }, [load]);

  async function openWhy(s: Stock) {
    setPicked(s);
    setWhy(null);
    setWhyError("");
    setWhyLoading(true);
    if (window.matchMedia("(min-width: 1024px)").matches) panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    try {
      setWhy(await stockApi.why(s.code));
    } catch (e) {
      setWhyError((e as Error).message);
    } finally {
      setWhyLoading(false);
    }
  }

  if (error && !data) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!data) return <p className="py-10 text-center text-sm text-muted">불러오는 중…</p>;
  if (!data.enabled) {
    return (
      <div className="rounded-3xl border border-border bg-surface p-6 text-center">
        <p className="text-sm font-bold">STOCK:ON은 오라클 서버에서 제공합니다.</p>
        <a href={data.oracle_url} className="mt-3 inline-block rounded-xl bg-[#13315C] px-4 py-2 text-sm font-bold text-white">STOCK:ON 열기</a>
      </div>
    );
  }

  const { market, fx, briefing, news, watch, events } = data;
  const heat = market?.heatmap?.[heatTab] || [];
  const movers = market?.movers?.[moverTab] || [];
  const cats = news?.categories || [];
  const cat = cats.find((c) => c.id === newsTab) || cats[0];
  const usedSources = briefing ? [...new Set(briefing.sentences.flatMap((s) => s.sources))].sort((a, b) => a - b) : [];
  const basis = basisLabel(market);
  const marketSource = market && basis ? `${market.source.name} · ${basis.text}` : "";
  const live = data.price_source === "kiwoom";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-[#13315C]/30 bg-[#13315C]/5 px-2.5 py-1 text-[11px] font-extrabold text-[#13315C] dark:border-sky-300/30 dark:text-sky-200">ⓘ {data.disclaimer}</span>
        <Freshness market={market} />
        {live && <span className="text-[11px] font-bold text-muted">{market?.source.name}</span>}
        <span className="text-[11px] text-subtle">갱신 {timeLabel(market?.fetched_ts)}{data.refreshing ? " · 새 자료 확인 중…" : ""}</span>
        {error && <span className="text-[11px] font-bold text-amber-700 dark:text-amber-300">· 최신 자료를 잠시 못 불러왔어요(이전 화면 유지)</span>}
      </div>

      <nav aria-label="섹션 바로가기" className="so-row sticky top-0 z-20 -mx-4 flex gap-1.5 overflow-x-auto bg-bg/90 px-4 py-2 backdrop-blur sm:mx-0 sm:px-0">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-bold text-muted hover:border-[#1E4E8C]/40 hover:text-fg">{label}</a>
        ))}
      </nav>

      {!market && (
        <div className="rounded-3xl border border-border bg-surface p-6 text-center text-sm text-muted">
          {data.refreshing ? "처음 자료를 모으는 중이에요. 1분 정도 걸려요…" : data.errors?.market === "not_registered" ? "시세 자료 연결을 준비 중이에요(공공데이터 활용 승인 대기)." : "시세 자료를 아직 불러오지 못했어요. 잠시 후 다시 확인해 주세요."}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <Section id="brief" eyebrow="MARKET BRIEF" title="AI 브리핑 3줄" meta={briefing ? `${briefing.ai ? "AI 요약" : "자동 문장"} · ${dateLabel(briefing.as_of)} 시장 기준 · ${timeLabel(briefing.fetched_ts)}` : undefined}>
          {briefing ? (
            <>
              <Sentences sentences={briefing.sentences} sources={briefing.sources} numbered />
              <SourceList sources={briefing.sources} used={usedSources} />
            </>
          ) : (
            <p className="text-sm text-muted">브리핑을 준비 중이에요.</p>
          )}
        </Section>

        <Section id="indices" eyebrow="INDICES" title={fx && fx.status !== "not_configured" ? "지수 · 환율" : "지수"} meta={market ? marketSource : undefined}>
          {/* 환율 키(KOREAEXIM_API_KEY)가 없으면 원/달러 카드는 숨기고 지수 두 칸만 */}
          <div className={`-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:grid sm:overflow-visible ${fx?.status === "not_configured" || !fx ? "sm:grid-cols-2" : "sm:grid-cols-3"}`}>
            <IndexTile card={market?.indices.find((i) => i.name === "코스피")} asOf={market?.as_of} basis={live ? basis?.text : undefined} />
            <IndexTile card={market?.indices.find((i) => i.name === "코스닥")} asOf={market?.as_of} basis={live ? basis?.text : undefined} />
            {fx && fx.status !== "not_configured" && <IndexTile fx={fx} />}
          </div>
          {market && <p className="mt-2 text-[11px] text-muted">상승 {market.breadth.up.toLocaleString()} · 하락 {market.breadth.down.toLocaleString()} · 보합 {market.breadth.flat.toLocaleString()} (전체 {market.breadth.total.toLocaleString()}종목)</p>}
        </Section>
      </div>

      {market && (
        <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <Section id="heatmap" eyebrow="HEATMAP" title="시가총액 상위 40" meta={`크기 = 시가총액 · 색 = 등락률 · ${marketSource}`}>
            <Tabs label="시장" value={heatTab} onChange={setHeatTab} options={[["KOSPI", "코스피"], ["KOSDAQ", "코스닥"]]} />
            <Heatmap items={heat} selected={picked?.code} onSelect={openWhy} />
            <p className="mt-2 text-[11px] text-subtle">칸을 누르면 그 종목이 &lsquo;왜 움직였나&rsquo;를 뉴스·공시로 정리해 보여줘요.</p>
          </Section>
          <div ref={panelRef} className="hidden lg:block">
            <section className="sticky top-14 rounded-3xl border border-border bg-surface p-5 shadow-sm">
              {picked ? <WhyBody stock={picked} why={why} error={whyError} loading={whyLoading} live={live} /> : (
                <div className="py-10 text-center text-sm text-muted">
                  <div className="text-3xl">🔍</div>
                  <p className="mt-2 font-bold">히트맵이나 순위에서 종목을 눌러 보세요</p>
                  <p className="mt-1 text-xs">관련 뉴스·공시와 AI 정리가 여기에 나와요.</p>
                </div>
              )}
            </section>
          </div>
        </div>
      )}

      {market && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Section id="movers" eyebrow="MOVERS" title="등락 상위" meta={`거래대금 ${eok(market.mover_min_value)} 이상 종목 · ${basis?.text ?? ""}`}>
            <Tabs label="순위 종류" value={moverTab} onChange={(v) => { setMoverTab(v); setMoversAll(false); }} options={[["up", "상승률"], ["down", "하락률"], ["value", "거래대금"]]} />
            <ol>
              {movers.slice(0, moversAll ? 10 : 5).map((s, i) => <StockRow key={s.code} s={s} rank={i + 1} onWhy={openWhy} />)}
            </ol>
            {!moversAll && movers.length > 5 && (
              <button type="button" onClick={() => setMoversAll(true)} className="mt-1 w-full rounded-xl py-2 text-xs font-bold text-muted hover:bg-surface-muted">TOP 10 더 보기 ▾</button>
            )}
          </Section>
          <Section id="flows" eyebrow="FLOWS" title="외국인 · 기관 동향" meta={market.flows ? `순매수·순매도 금액 상위 · ${marketSource}` : undefined}>
            {market.flows ? (
              <div className="grid grid-cols-2 gap-2">
                <FlowList title="외국인 순매수" rows={market.flows.foreign_buy} />
                <FlowList title="외국인 순매도" rows={market.flows.foreign_sell} sell />
                <FlowList title="기관 순매수" rows={market.flows.inst_buy} />
                <FlowList title="기관 순매도" rows={market.flows.inst_sell} sell />
              </div>
            ) : (
              <div className="flex min-h-40 flex-col items-center justify-center rounded-2xl bg-surface-muted p-6 text-center">
                <div className="text-2xl">🧭</div>
                <p className="mt-2 text-sm font-bold">키움증권 API 시세일 때 제공</p>
                <p className="mt-1 text-xs text-muted">공공데이터(전일 기준)에는 투자자별 매매 자료가 없어요.</p>
              </div>
            )}
          </Section>
        </div>
      )}

      <Section id="watch" eyebrow="TEAM WATCHLIST" title="팀 관심 종목" meta={watch ? `관리자 지정 · 뉴스·공시 ${timeLabel(watch.fetched_ts)}` : "관리자 지정"}>
        {!watch?.items?.length ? (
          <p className="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-muted">관리자가 아직 팀 관심 종목을 정하지 않았어요.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {watch.items.map((w) => (
              <article key={w.code} className="rounded-2xl border border-border p-3">
                <button type="button" disabled={!w.price} onClick={() => w.price && openWhy({ code: w.code, ...w.price } as Stock)} className="flex w-full items-start justify-between gap-2 text-left">
                  <span>
                    <span className="block font-extrabold">{w.name}</span>
                    <span className="text-[11px] text-subtle">{w.code} · {w.price?.market}</span>
                  </span>
                  {w.price && (
                    <span className="text-right">
                      <span className="block text-sm font-bold tabular-nums">{won(w.price.close)}</span>
                      <span className={`text-xs font-bold tabular-nums ${tone(w.price.rate)}`}>{arrow(w.price.rate)} {pct(w.price.rate)}</span>
                    </span>
                  )}
                </button>
                <NewsList items={w.news} limit={2} basis={market?.as_of} />
                {w.disclosures[0] && (
                  <p className="mt-1 border-t border-border pt-2 text-xs">
                    <span className="mr-1 rounded bg-surface-muted px-1 text-[10px] font-extrabold text-muted">공시</span>
                    <a href={w.disclosures[0].url} target="_blank" rel="noopener noreferrer" className="font-bold hover:underline">{w.disclosures[0].title}</a>
                    <span className="text-subtle"> {dateLabel(w.disclosures[0].date)}</span>
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </Section>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Section id="news" eyebrow="NEWS" title="카테고리별 뉴스" meta={news?.status === "ok" ? `NAVER 뉴스 검색 · ${timeLabel(news.fetched_ts)}` : undefined}>
          {news?.status === "ok" && cat ? (
            <>
              <Tabs label="뉴스 카테고리" value={cat.id} onChange={setNewsTab} options={cats.map((c) => [c.id, c.label] as [string, string])} />
              <SplitNews items={cat.items} basis={market?.as_of} />
              <p className="mt-2 text-[10px] text-subtle">제목·링크는 언론사 원문 그대로이고, &lsquo;AI 요약&rsquo;은 검색 요약문만으로 만든 한 줄이에요.</p>
            </>
          ) : (
            <p className="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-muted">{news?.status === "not_configured" ? "뉴스 검색 키가 아직 설정되지 않았어요." : "뉴스를 준비 중이에요."}</p>
          )}
        </Section>

        <Section id="week" eyebrow="THIS WEEK" title="이번 주 일정">
          {events?.events.length ? (
            <ul className="space-y-3">
              {groupByDate(events.events).map(([d, list]) => {
                const day = new Date(`${d}T00:00:00+09:00`);
                return (
                  <li key={d} className="flex gap-3">
                    <div className="w-12 shrink-0 rounded-xl bg-surface-muted py-1.5 text-center">
                      <div className="text-[10px] font-bold text-muted">{WEEKDAY[day.getDay()]}</div>
                      <div className="text-sm font-extrabold">{day.getMonth() + 1}/{day.getDate()}</div>
                    </div>
                    <ul className="flex-1 space-y-1">
                      {list.map((e) => (
                        <li key={e.title} className="text-sm">
                          <span className="font-bold">{e.title}</span>
                          <span className="block text-[10px] text-subtle">{e.note ? `${e.note} · ` : ""}<SourceLink s={e.source} /></span>
                        </li>
                      ))}
                    </ul>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-muted">이번 주와 다음 주에 등록된 일정이 없어요.</p>
          )}
        </Section>
      </div>

      <footer className="rounded-3xl bg-surface-muted p-4 text-[11px] leading-relaxed text-muted">
        <p className="font-extrabold text-fg">ⓘ {data.disclaimer}</p>
        <p className="mt-1">STOCK:ON은 공개된 시세·공시·뉴스를 모아 보여 주는 화면이며, 특정 종목의 매수·매도를 권하지 않습니다. 시세는 전일 종가 기준이라 현재 가격과 다를 수 있습니다. AI 문장은 뉴스 제목·요약문과 공시 제목만으로 만들며 틀릴 수 있으니 출처 원문을 확인해 주세요.</p>
        <p className="mt-2">
          출처: <SourceLink s={{ name: "금융위원회 공공데이터(주식·지수 시세, 공공누리 제4유형)", url: "https://www.data.go.kr/data/15094808/openapi.do" }} /> ·{" "}
          <SourceLink s={{ name: "한국수출입은행 환율", url: "https://www.koreaexim.go.kr" }} /> · <SourceLink s={{ name: "DART 전자공시", url: "https://dart.fss.or.kr" }} /> ·{" "}
          <SourceLink s={{ name: "NAVER 뉴스 검색", url: "https://news.naver.com" }} />
        </p>
      </footer>

      {picked && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label={`${picked.name} 왜 움직였나`}>
          <button type="button" aria-label="닫기" onClick={() => setPicked(null)} className="absolute inset-0 bg-black/40" />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-surface p-5 pb-8 shadow-2xl">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-border" />
            <button type="button" onClick={() => setPicked(null)} className="absolute right-4 top-4 rounded-full px-2 text-lg text-muted" aria-label="닫기">✕</button>
            <WhyBody stock={picked} why={why} error={whyError} loading={whyLoading} live={live} />
          </div>
        </div>
      )}
    </div>
  );
}
