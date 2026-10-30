"use client";

// 뉴스 속 숨은 종목 탭: 오늘의 뉴스 → AI 해석 → 관련 회사 지도 → AI 해석 vs 실제 등락.
// 순서: 헤더(기준 시각) → 오늘 시장 분위기 띠 → 뉴스 카드(이슈별로 옆으로 넘기기) → AI 해석 → 관련 회사 지도 → 해석 vs 실제 등락
//   → 이전/다음 이슈 → 다른 이슈·섹터 → 고지.
// 이슈 넘김은 위 ‹ ›·카드 밀기·고정 이슈 바(뉴스 카드를 지나 스크롤하면 화면 맨 위, PC 제외)·아래 버튼 모두 같은 동작이다:
//   이슈가 바뀌고 뉴스 카드도 함께 넘어가며, 아래 내용(AI 해석·지도·표)은 0.3초 옆으로 밀리며 바뀐다.
//   아래쪽을 보던 중이면 AI 해석 시작으로 올려 준다(고정 바에 가리지 않게 scroll-margin).
// 핵심 목적: 일상 뉴스를 보다가 → 그 뉴스와 연결된 상장사를 AI가 찾아낸다(뉴스 자체는 종목 이야기가 아니어도 된다).
// 실제 등락은 '시장보다'(회사 주가 등락 − 그 회사 시장 지수 등락, %p)를 크게, 주가 등락률을 작게 보여 준다.
// ±2%p 이내는 '시장과 비슷해요'(회색). 첫 보도가 15:20 이후면 다음 거래일과 비교하고, 그 값이 없으면 '반응 대기 중'.
// 첫 보도 이후 누적은 버블에 넣지 않고 회사 상세·표에만.
// 배경은 STOCK:ON 페이지 남색 하나(globals.css .stockon-theme). 이슈 색은 카드 테두리·작은 점·은은한 빛에만 쓴다.
// 서버가 미리 만든 것을 읽기만 한다(직접 입력한 단어만 대기열로 AI를 부른다 — WordInput).
// 휴대폰(640px 미만)에서는 바깥 상자 테두리·모서리·양옆 여백 없이 화면 끝까지. 글씨: 본문 15px+, 섹션 제목 18px+, 지도 회사 이름 13px+.
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import MindMap, { GRAY, NEG, POS, pathColor, ppText, rateColor, rateText, similar, vsColor } from "@/components/stock/MindMap";
import { WhyBody } from "@/components/stock/StockOn";
import {
  lifeApi, stockApi, type LifeArticle, type LifeCompany, type LifeItem, type LifeMarket, type LifeOverview, type LifeStage, type LifeWordResult, type Stock,
  type Why,
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
const BAR_ROOM = 72; // 고정 이슈 바(48px) + 여유. AI 해석 묶음의 scroll-mt-16(64px)과 함께 바가 제목을 가리지 않게
const POLL_MAX_MS = 100_000; // AI 한 번 45초 × 최대 2회 + 대기 여유

function ArticleMeta({ a, basis }: { a: LifeArticle; basis?: string }) {
  const w = when(a.pub);
  const other = w && basis && w.ymd !== basis;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[14px] text-slate-200">
      <span className="font-semibold">{a.press_name || a.press.replace(/^www\./, "")}{a.section ? ` ${a.section}` : ""}</span>
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
      className="flex w-[86vw] max-w-[560px] shrink-0 snap-center flex-col rounded-3xl px-3.5 py-3 sm:w-[520px] sm:p-4"
      style={{ border: `1.5px solid ${active ? `${accent}b3` : "rgba(255,255,255,.1)"}`, background: "rgba(255,255,255,.04)",
        boxShadow: active ? `0 0 24px ${accent}29` : "none" }}>
      <div className="flex items-center justify-between gap-2 text-[14px] font-extrabold">
        <span className="flex items-center gap-1.5 text-white">
          <span className="size-2.5 rounded-full" style={{ background: accent, boxShadow: `0 0 8px ${accent}` }} />
          {index != null ? `ISSUE ${index + 1}` : "ISSUE"}{item.label || item.sector ? ` · ${item.label || item.sector}` : ""}
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
      <IssueBadges item={item} />
      <p className="mt-2 text-[15px] leading-relaxed text-slate-50"><b className="mr-1 text-white">{item.title}</b>{item.summary && ` — ${item.summary}`}</p>
      {rest.length > 0 && (
        <div className="mt-auto pt-2">
          <button type="button" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }} aria-expanded={open}
            className="rounded-full bg-white/10 px-2.5 py-1 text-[14px] font-extrabold text-white ring-1 ring-white/20 hover:bg-white/15">
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

type IssueMark = { n: number; color: string };

function IssueDot({ issue }: { issue: IssueMark }) {
  return (
    <span className="inline-flex items-center gap-1 text-[14px] font-extrabold text-slate-100" aria-label={`이슈 ${issue.n}`}>
      <span className="size-2.5 rounded-full" style={{ background: issue.color, boxShadow: `0 0 8px ${issue.color}` }} />{issue.n}
    </span>
  );
}

function SectionTitle({ children, badge, issue }: { children: React.ReactNode; badge?: React.ReactNode; issue?: IssueMark }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h3 className="text-[19px] font-black text-white">{children}</h3>
      {issue && <IssueDot issue={issue} />}
      {badge}
    </div>
  );
}

/** 시장보다를 말로: ±3%p 이상 '많이', ±2%p 이내 '시장과 비슷해요', 그 사이 '조금'. */
const judge = (vs?: number | null) => (vs == null ? "" : vs >= 3 ? "시장보다 많이 올랐어요" : vs <= -3 ? "시장보다 많이 내렸어요"
  : similar(vs) ? "시장과 비슷해요" : vs > 0 ? "시장보다 조금 올랐어요" : "시장보다 조금 내렸어요");
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
const MARKET_NAME: Record<string, string> = { KOSPI: "코스피", KOSDAQ: "코스닥" };
const VS_NOTE = "시장보다 = 그 회사 주가 등락 − 시장 지수 등락. 시장 전체 움직임을 빼고 뉴스의 영향만 보려는 값이에요.";
const SINCE_NOTE = "주가는 기대·선반영·차익실현 등 여러 이유로 움직여요. 그래서 첫 보도 이후 흐름을 함께 보여드려요.";
const REFLECTED = "첫 보도 때 이미 반영됐을 수 있어요";
const WAITING = "반응 대기 중";

/** 오늘 시장 분위기 띠(지수 시황 기사 대신). 예: 코스피 +6.63% · 코스닥 +3.69% · 대부분 종목이 올랐어요 → … */
function MoodBand({ m }: { m: LifeMarket }) {
  return (
    <div className="mb-2.5 rounded-2xl bg-white/[0.06] px-3.5 py-2.5 ring-1 ring-white/15" role="note" aria-label="오늘 시장 분위기">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-[14px] font-extrabold text-amber-100">오늘 시장 분위기</span>
        {m.label && <span className="text-[14px] text-slate-300">{m.label}</span>}
      </div>
      <p className="mt-0.5 text-[15px] font-bold leading-snug text-white">
        {m.indices.map((i, n) => (
          <Fragment key={i.market}>
            {n > 0 && " · "}{i.name} <span className="tabular-nums" style={{ color: rateColor(i.rate) }}>{signed(i.rate)}</span>
          </Fragment>
        ))}
        {m.crowd && <> · {m.crowd}</>}
        <span className="text-sky-200"> → 시장보다 더/덜 움직인 회사를 보세요</span>
      </p>
    </div>
  );
}

const Dir = ({ d }: { d?: LifeCompany["direction"] }) => (
  <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[14px] font-extrabold text-[#071226]" style={{ background: d === "neg" ? NEG : d === "unk" ? GRAY : POS }}>
    {d === "neg" ? "− 부정 가능" : d === "unk" ? "? 영향 가능" : "+ 긍정 가능"}
  </span>
);

/** 이슈 카드 배지: 시장 전체 영향 이슈·예상대로·오늘 실제 방향, 그리고 첫 보도·장 마감 후 뉴스·반응 대기 중 한 줄 */
function IssueBadges({ item }: { item: LifeItem }) {
  const m = item.map, t = m.timing;
  const pill = "rounded-full px-2.5 py-0.5 text-[14px] font-extrabold ring-1";
  const badges: React.ReactNode[] = [];
  if (item.ongoing) badges.push(<span key="ongoing" className={`${pill} bg-sky-300/15 text-sky-100 ring-sky-200/40`}>계속되는 이슈</span>);
  if (m.macro || item.macro) badges.push(<span key="macro" className={`${pill} bg-amber-300/15 text-amber-100 ring-amber-200/40`}>시장 전체 영향 이슈</span>);
  if (m.expected === "예상대로") badges.push(<span key="exp" className={`${pill} bg-white/10 text-white ring-white/25`}>예상대로</span>);
  if (m.move) badges.push(
    <span key="move" className={`${pill} bg-white/10 text-white ring-white/25`}>
      오늘 {m.move.subject}: {m.move.today === "불확실" ? "방향 불확실"
        : <span style={{ color: m.move.today === "상승" ? rateColor(1) : m.move.today === "하락" ? rateColor(-1) : undefined }}>{m.move.today}</span>}
    </span>,
  );
  return (
    <>
      {badges.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{badges}</div>}
      {(t || item.coverage) && (
        <p className="mt-2 text-[14px] leading-snug text-slate-200">
          {item.coverage && <span className="font-bold">최근 {item.coverage.hours}시간 기사 {item.coverage.articles}건 · 언론사 {item.coverage.presses}곳</span>}
          {item.coverage && t && " · "}
          {t && <span className="font-bold">첫 보도 {t.first}</span>}
          {t?.after_close && (
            <> · <b className="text-amber-100">장 마감 후 뉴스 · 다음 거래일 반응을 보여드려요</b>
              {t.waiting ? <> · <b className="text-white">{WAITING}</b> ({t.reaction_label})</> : ` (${t.reaction_label})`}</>
          )}
        </p>
      )}
    </>
  );
}

function OtherNote({ c }: { c: LifeCompany }) {
  if (!c.opposite || !c.other) return null;
  return (
    <p className="text-[14px] leading-snug text-slate-300">
      <span className="font-extrabold text-amber-100">해석과 반대로 움직였어요</span> · {c.other.text}
      {c.other.url && (
        <> · <a href={c.other.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
          title={c.other.title} className="font-bold text-sky-200 underline underline-offset-2">기사 ↗</a></>
      )}
    </p>
  );
}

function ReactionTable({ item, accent, onPick }: { item: LifeItem; accent: string; onPick: (c: LifeCompany, s: LifeStage, color: string) => void }) {
  const rows = item.map.stages.flatMap((s, i) => s.companies.map((c) => ({ c, s, color: pathColor(i) })));
  const idx = Object.entries(item.map.indices ?? {}).map(([k, v]) => `${MARKET_NAME[k] ?? k} ${signed(v as number)}`).join(" · ");
  return (
    <div className="overflow-hidden rounded-2xl bg-white/[0.03]" style={{ border: `1px solid ${accent}55` }}>
      {/* 휴대폰 폭에 네 열: AI 해석(긍정/부정)은 회사 이름 아래, 판단(말)은 '시장보다' 숫자 아래 */}
      {/* 열 너비 고정: 긴 회사 이름은 줄바꿈하고 숫자 열이 390px 카드 밖으로 밀리지 않게 */}
      <table className="w-full table-fixed text-left text-[15px]">
        <colgroup><col className="w-[33%]" /><col className="w-[18%]" /><col className="w-[25%]" /><col className="w-[24%]" /></colgroup>
        <thead>
          <tr className="text-[14px] text-slate-200">
            <th className="py-2.5 pl-3 pr-1 font-extrabold">회사 · AI 해석</th>
            <th className="px-1.5 py-2.5 text-right font-extrabold">주가</th>
            <th className="px-1.5 py-2.5 text-right font-extrabold">시장보다</th>
            <th className="py-2.5 pl-1.5 pr-3 text-right font-extrabold">첫 보도<br className="sm:hidden" /> 이후</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, s, color }) => (
            <Fragment key={c.code}>
              <tr onClick={() => onPick(c, s, color)} className="cursor-pointer border-t border-white/10 align-top hover:bg-white/5">
                <td className="py-2.5 pl-3 pr-1">
                  <div className="font-extrabold leading-snug text-white">{c.name}</div>
                  <div className="text-[14px] font-semibold" style={{ color }}>{s.label}</div>
                  <div className="mt-1"><Dir d={c.direction} /></div>
                </td>
                {c.waiting ? (
                  <td colSpan={3} className="py-2.5 pl-1.5 pr-3 text-right text-[14px] font-extrabold leading-snug text-slate-200">
                    {WAITING}<div className="font-semibold text-slate-300">다음 거래일 값을 기다려요</div>
                  </td>
                ) : (
                  <>
                    <td className="whitespace-nowrap px-1.5 py-2.5 text-right">
                      <div className="text-[15px] font-extrabold tabular-nums" style={{ color: rateColor(c.rate) }}>{rateText(c.rate)}</div>
                    </td>
                    <td className="px-1.5 py-2.5 text-right">
                      <div className="whitespace-nowrap text-[16px] font-black tabular-nums" style={{ color: vsColor(c.vs_market) }}>{ppText(c.vs_market)}</div>
                      {c.vs_market != null && (
                        <div className="text-[14px] font-extrabold leading-snug" style={{ color: similar(c.vs_market) ? GRAY : "#f1f5f9" }}>{judge(c.vs_market)}</div>
                      )}
                      {c.moved && <div className="text-[14px] font-extrabold text-amber-100">실제 등락 큼</div>}
                    </td>
                    <td className="py-2.5 pl-1.5 pr-3 text-right">
                      <div className="whitespace-nowrap text-[14px] font-extrabold tabular-nums" style={{ color: c.since ? vsColor(c.since.vs) : GRAY }}>
                        {c.since ? ppText(c.since.vs) : "—"}
                      </div>
                      {c.since && <div className="text-[14px] text-slate-300">{c.since.days}거래일</div>}
                    </td>
                  </>
                )}
              </tr>
              {((c.opposite && c.other) || c.reflected) && (
                <tr onClick={() => onPick(c, s, color)} className="cursor-pointer hover:bg-white/5">
                  <td colSpan={4} className="space-y-1 px-3 pb-2.5 pt-0">
                    {c.reflected && <p className="text-[14px] font-bold leading-snug text-amber-100">{REFLECTED}</p>}
                    <OtherNote c={c} />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      <div className="space-y-1 border-t border-white/10 px-3 py-2 text-[14px] text-slate-200">
        <p className="font-bold text-slate-100">{SINCE_NOTE}</p>
        <p>
          {item.map.reaction_label || "기준 시점"}{idx ? ` · 같은 시각 지수 ${idx}` : " · 지수 값이 없어 '시장보다'는 비워 뒀어요"} ·
          시장과 비슷해요 = ±2%p 이내 · 첫 보도 이후 = 첫 보도 뒤 거래일부터 누적(최대 5거래일) ·
          AI 해석과 실제 등락을 나란히 보여 줄 뿐, 이 뉴스 때문에 움직였다는 뜻은 아니에요.
        </p>
      </div>
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
          {c.moved && <div className="mb-0.5 text-[14px] font-extrabold text-amber-200">실제 등락 큼</div>}
          {c.waiting ? (
            <div className="text-[18px] font-black text-slate-100">{WAITING}</div>
          ) : c.vs_market != null ? (
            <>
              <div className="text-[20px] font-black tabular-nums" style={{ color: vsColor(c.vs_market) }}>시장보다 {ppText(c.vs_market)}</div>
              <div className="text-[14px] font-bold tabular-nums text-slate-200">주가 {rateText(c.rate)}</div>
            </>
          ) : (
            <div className="text-[20px] font-black tabular-nums" style={{ color: rateColor(c.rate) }}>주가 {rateText(c.rate)}</div>
          )}
          <div className="text-[14px] text-slate-300">{c.waiting ? "다음 거래일 값을 기다려요" : label || "실제 등락률"}</div>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 rounded-full px-2 text-2xl text-slate-200">✕</button>}
      </div>
      {!c.waiting && (c.since || c.vs_market != null) && (
        <div className="mt-3 rounded-2xl bg-white/[0.05] px-3.5 py-2.5 text-[15px] ring-1 ring-white/10">
          {c.vs_market != null && <p className="font-bold" style={{ color: similar(c.vs_market) ? GRAY : "#f8fafc" }}>오늘 {judge(c.vs_market)}</p>}
          {c.since && (
            <p className="mt-0.5 text-slate-100">
              첫 보도 이후 <b className="tabular-nums" style={{ color: vsColor(c.since.vs) }}>시장보다 {ppText(c.since.vs)}</b>
              <span className="text-[14px] text-slate-300"> · {c.since.from === c.since.to ? c.since.from : `${c.since.from}~${c.since.to}`} {c.since.days}거래일 · 주가 {rateText(c.since.rate)}</span>
            </p>
          )}
          {c.reflected && <p className="mt-0.5 font-bold text-amber-100">{REFLECTED}</p>}
        </div>
      )}
      <div className="mt-3 rounded-2xl bg-white/[0.08] p-3.5 ring-1 ring-white/15">
        <div className="text-[15px] font-extrabold text-sky-200">왜 관련 있나</div>
        <p className="mt-1 text-[16px] font-bold leading-relaxed text-white">{c.reason}</p>
        <p className="mt-1.5 text-[14px] text-slate-300">🤖 AI가 해석했어요 · 영향을 받을 수 있다는 해석이며 틀릴 수 있어요</p>
        {c.opposite && c.other && <div className="mt-2.5 border-t border-white/10 pt-2.5"><OtherNote c={c} /></div>}
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
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-[15px] font-extrabold ring-1 transition ${on
        ? "bg-white text-[#071226] ring-white" : "bg-white/[0.06] text-white ring-white/15 hover:bg-white/10"}`}>
      <span className="size-2 rounded-full" style={{ background: color, boxShadow: on ? "none" : `0 0 6px ${color}` }} />
      {children}
    </button>
  );
}

// 가로 스크롤 줄: 스크롤바 없이, 더 있는 쪽 끝을 흐리게(globals.css .so-row)
function FadeRow({ className, children, label }: { className: string; children: React.ReactNode; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [fade, setFade] = useState("none");
  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const start = el.scrollLeft > 4, end = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
    setFade(start && end ? "both" : start ? "start" : end ? "end" : "none");
  }, []);
  useEffect(() => {
    update();
    const ro = new ResizeObserver(update);
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, [update, children]);
  return <div ref={ref} onScroll={update} data-fade={fade} aria-label={label} className={`so-row ${className}`}>{children}</div>;
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
  const [pastCards, setPastCards] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rail = useRef<HTMLDivElement>(null);
  const top = useRef<HTMLDivElement>(null);
  const cards = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  // 버튼으로 카드를 옮기는 동안(부드러운 스크롤)은 지나가는 카드로 이슈를 바꾸지 않는다
  const railTarget = useRef<{ i: number; t: ReturnType<typeof setTimeout> } | null>(null);
  // 이슈가 바뀐 방향(다음/이전) → 아래 내용이 밀리는 방향
  const slide = useRef({ active: 0, dir: "next" as "next" | "prev" });
  if (slide.current.active !== active) slide.current = { active, dir: active > slide.current.active ? "next" : "prev" };
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  // 뉴스 카드 영역을 지나 아래로 스크롤했으면 고정 이슈 바를 보인다. 바 높이(48px)+여유만큼은 지난 것으로 본다
  // (바에서 넘기면 AI 해석 시작으로 올라가 카드 아래 끝이 바 밑에 조금 남는데, 그때 바가 사라지지 않게).
  const hasData = !!data;
  useEffect(() => {
    const el = cards.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setPastCards(!e.isIntersecting && e.boundingClientRect.top < 0),
      { rootMargin: `-${BAR_ROOM}px 0px 0px 0px` });
    io.observe(el);
    return () => io.disconnect();
  }, [hasData]);

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
    // 끝까지 밀었으면 끝 카드(PC처럼 카드가 좁아 마지막 카드가 가운데까지 못 올 때)
    if (el.scrollLeft >= el.scrollWidth - el.clientWidth - 2) best = el.children.length - 1;
    else if (el.scrollLeft <= 2) best = 0;
    if (railTarget.current) {
      if (best !== railTarget.current.i) return;
      clearTimeout(railTarget.current.t);
      railTarget.current = null;
    }
    if (best !== active) { setActive(best); setPick(null); }
  }
  /** 뉴스 카드 줄을 i번째 카드로(가운데) 옮긴다. */
  function moveRail(i: number) {
    if (railTarget.current) clearTimeout(railTarget.current.t);
    railTarget.current = { i, t: setTimeout(() => { railTarget.current = null; }, 900) };
    requestAnimationFrame(() => {
      const el = rail.current, card = el?.children[i] as HTMLElement | undefined;
      if (!el) return;
      // 화면 위치로 계산한다(카드 줄의 -mx-4 때문에 offsetLeft는 기준이 어긋난다)
      const left = card ? el.scrollLeft + card.getBoundingClientRect().left - el.getBoundingClientRect().left - (el.clientWidth - card.offsetWidth) / 2 : 0;
      el.scrollTo({ left, behavior: "smooth" });
    });
  }
  function goTopic(i: number) {
    setView({ kind: "topics" });
    setActive(i);
    setPick(null);
    setNotice("");
    moveRail(i);
    requestAnimationFrame(() => top.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  /** 이전/다음 이슈: 위 ‹ ›·고정 바·아래 버튼이 모두 이것. 카드도 함께 넘어가고, 아래를 보던 중이면 AI 해석 시작으로. */
  function step(d: number) {
    if (!data) return;
    const i = active + d;
    if (i < 0 || i >= data.topics.length) return;
    setActive(i);
    setPick(null);
    moveRail(i);
    const el = body.current;
    if (el && el.getBoundingClientRect().top < 0) requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
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
  if (!data) return <div className="rounded-3xl bg-white/[0.03] py-24 text-center text-[15px] text-slate-200 ring-1 ring-white/10">뉴스를 불러오는 중…</div>;

  const item: LifeItem | undefined = view.kind === "topics" ? data.topics[active] : view.kind === "sector" ? data.sector_items[view.name] : words[view.word];
  const accent = accentFor(item, view.kind === "topics" ? active : 0);
  const basisYmd = data.basis.as_of;
  const label = item?.map.reaction_label;
  const total = data.topics.length;
  const topics = view.kind === "topics";
  const issue = topics ? { n: active + 1, color: accent } : undefined;
  const hasVs = !!item?.map.stages.some((s) => s.companies.some((c) => c.vs_market != null));
  const hasUnk = !!item?.map.stages.some((s) => s.companies.some((c) => c.direction === "unk"));
  const arrows = (size: string) => (
    <div className="flex shrink-0 gap-1.5">
      {([["‹", -1, "이전 이슈"], ["›", 1, "다음 이슈"]] as const).map(([t, d, name]) => (
        <button key={name} type="button" aria-label={name} disabled={active + d < 0 || active + d >= total} onClick={() => step(d)}
          className={`${size} rounded-full border border-white/25 bg-white/10 text-xl font-bold text-white hover:bg-white/20 disabled:opacity-30`}>{t}</button>
      ))}
    </div>
  );

  return (
    <div ref={top} className="lifemap-shell relative scroll-mt-2 pb-8 pt-3 text-slate-100">
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

        <p className="mt-1.5 text-[14px] leading-snug text-slate-300">{VS_NOTE}</p>

        {/* 뉴스 카드 */}
        <div ref={cards} className="relative mt-4">
          {drawing && <DrawingOverlay d={drawing} />}
          {view.kind === "topics" ? (
            <>
            {data.market && <MoodBand m={data.market} />}
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[15px] font-extrabold text-white">오늘의 이슈 {active + 1} / {total}</span>
              {arrows("size-10")}
            </div>
            <div ref={rail} onScroll={onRailScroll} className="so-row -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0" aria-label="오늘의 이슈">
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
          <div ref={body} className="mt-5 scroll-mt-16 lg:grid lg:grid-cols-[1.25fr_1fr] lg:gap-8">
            {/* 이슈가 바뀌면 다시 그려지며 0.3초 옆으로 밀려 들어온다(globals.css .lm-slide-*) */}
            <div key={topics ? `t${active}` : `${view.kind}:${item.name}`} className={`space-y-9 ${topics ? `lm-slide-${slide.current.dir}` : ""}`}>
              {/* AI 해석 */}
              <section aria-label="AI 해석">
                <SectionTitle issue={issue} badge={<span className="rounded-full bg-white/10 px-2.5 py-1 text-[14px] font-extrabold text-sky-50 ring-1 ring-sky-300/30">🤖 AI가 해석했어요</span>}>
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
                <SectionTitle issue={issue} badge={<span className="rounded-full bg-white/15 px-2.5 py-1 text-[14px] font-extrabold text-white">관련 종목 · 참고용</span>}>
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
                        <span className="font-extrabold" style={{ color: POS }}>＋ 긍정 영향 가능</span> · <span className="font-extrabold" style={{ color: NEG }}>－ 부정 영향 가능</span>
                        {hasUnk && <> · <span className="font-extrabold" style={{ color: GRAY }}>? 방향 불확실(영향 가능)</span></>}(AI 해석) ·
                        버블이 클수록 연관이 커요 · {hasVs ? (
                          <><b className="text-white">큰 숫자 = 시장보다(%p)</b>, 작은 글씨 = 주가 등락률 · 회색 = 시장과 비슷해요(±2%p 이내) ·{" "}
                            <b className="text-white">빛나는 테두리 = 실제 등락 큼</b>(시장보다 ±3%p 이상)</>
                        ) : (
                          <><b className="text-white">빛나는 테두리 = 실제 등락 큼</b>(주가 ±5% 이상)</>
                        )} · {label || "실제 등락률"}
                      </p>
                    </div>
                  </>
                ) : (
                  <p className="rounded-2xl bg-white/[0.06] px-4 py-12 text-center text-[15px] text-slate-200">이 뉴스와 확실히 이어지는 상장사를 찾지 못했어요.</p>
                )}
              </section>

              {/* AI 해석 vs 실제 등락 */}
              {item.map.stages.length > 0 && (
                <section aria-label="AI 해석 vs 실제 등락">
                  <SectionTitle issue={issue}>AI 해석 vs 실제 등락</SectionTitle>
                  <ReactionTable item={item} accent={accent} onPick={(c, s, color) => setPick({ c, s, color })} />
                </section>
              )}

              {/* 아래에서도 이슈 넘기기(위·고정 바와 같은 동작) */}
              {topics && total > 1 && (
                <nav aria-label="이슈 넘기기" className="grid grid-cols-2 gap-2">
                  {([[-1, "← 이전 이슈"], [1, "다음 이슈 →"]] as const).map(([d, t]) => {
                    const j = active + d;
                    const off = j < 0 || j >= total;
                    return (
                      <button key={d} type="button" disabled={off} onClick={() => step(d)}
                        className={`flex min-h-12 flex-col justify-center rounded-2xl bg-white/[0.06] px-3 py-2 ring-1 ring-white/15 hover:bg-white/10 disabled:opacity-30 ${d > 0 ? "items-end text-right" : "items-start"}`}>
                        <span className="text-[15px] font-extrabold text-white">{t}</span>
                        {!off && (
                          <span className="flex max-w-full items-center gap-1 text-[14px] font-semibold text-slate-300">
                            <span className="size-2 shrink-0 rounded-full" style={{ background: accentFor(data.topics[j], j) }} />
                            <span className="truncate">{j + 1}. {data.topics[j].name}</span>
                          </span>
                        )}
                      </button>
                    );
                  })}
                </nav>
              )}
            </div>
            <aside className="hidden lg:block">
              <div className="sticky top-4 rounded-3xl bg-white/[0.04] p-5 ring-1 ring-white/10">
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
          <FadeRow label="이슈·섹터 고르기" className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
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
          </FadeRow>
          {data.live.enabled ? (
            <WordInput disabled={!!drawing} onSubmit={draw} />
          ) : (
            <p className="mt-2 text-[15px] text-slate-200">지금은 직접 입력을 쉬고 있어요. 이슈·섹터는 볼 수 있어요.</p>
          )}
          {notice && <p className="mt-2 rounded-xl bg-amber-400/15 px-3 py-2.5 text-[15px] font-bold text-amber-100 ring-1 ring-amber-300/30" role="status">{notice}</p>}
        </section>

        <footer className="mt-10 rounded-2xl bg-white/[0.03] p-4 text-[15px] leading-relaxed text-slate-300 ring-1 ring-white/10">
          <p className="font-extrabold text-white">ⓘ 투자 권유가 아닌 참고 정보 · AI 해석은 틀릴 수 있어요</p>
          <p className="mt-1">
            뉴스를 읽고 영향을 받을 수 있는 회사를 AI가 해석한 것이며, 주가 방향을 말하지 않아요. 금융위원회 공공데이터 상장 종목 목록에 있는
            회사만 보여 주고, 실제 등락률은 표시한 시점 값이에요. 뉴스는 NAVER 뉴스 검색으로 찾았어요.
          </p>
          {data.price_note && <p className="mt-2 font-bold text-slate-100">{data.price_note}</p>}
        </footer>
      </div>

      {/* 고정 이슈 바: 뉴스 카드를 지나 스크롤하면 화면 맨 위(휴대폰·태블릿). 여기서 넘겨도 같은 동작 */}
      {topics && pastCards && !isPc && item && (
        <div className="fixed inset-x-0 top-0 z-40 border-b border-white/15 bg-[#071226]/95 backdrop-blur" role="region" aria-label="지금 보는 이슈">
          <div className="mx-auto flex h-12 max-w-6xl items-center gap-2 px-4">
            <span className="size-2.5 shrink-0 rounded-full" style={{ background: accent, boxShadow: `0 0 8px ${accent}` }} />
            <span className="shrink-0 text-[14px] font-extrabold tabular-nums text-slate-200">{active + 1}/{total}</span>
            <span className="min-w-0 flex-1 truncate text-[15px] font-black text-white">{item.name}</span>
            {arrows("size-9")}
          </div>
        </div>
      )}

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
