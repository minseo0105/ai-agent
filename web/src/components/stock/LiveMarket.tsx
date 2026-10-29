"use client";

// 오늘 시장 — 실시간 장중 동향(키움 웹소켓·REST를 수집기가 저장한 것만 읽는다. 화면은 15초마다 새로고침 없이).
// 순서: 실시간 표시 → AI 장중 한 줄 → 지수(현재값·등락률·오늘 시간대 미니 차트) → 시장 체온 → 투자자별 매매 → 업종 순위 → 거래대금 상위.
// 디자인은 '뉴스 속 숨은 종목'과 같은 남색 톤(흰 글씨·옅은 면·얇은 테두리), 휴대폰 우선, 본문 15px 이상.
// 값이 바뀌면 숫자가 1초쯤 빨강(오름)/파랑(내림)으로 반짝인다(globals.css .so-flash-*). 색에만 기대지 않게 ▲▼ 기호를 함께 쓴다.
import { useEffect, useRef, useState } from "react";
import { eok, type LiveIndex, type LiveSector, type LiveView, type Stock } from "@/lib/stock";

const UP = "#ff6b81", DOWN = "#5aa9ff";
const color = (v?: number | null) => (!v ? "#e2e8f0" : v > 0 ? UP : DOWN);
const signed = (v?: number | null, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const arrow = (v?: number | null) => (!v ? "" : v > 0 ? "▲" : "▼");
const hms = (ts?: number | null) =>
  ts ? new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Seoul" }) : "";
const hm = (ts?: number | null) =>
  ts ? new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Seoul" }) : "";
const MARKETS = [["KOSPI", "코스피"], ["KOSDAQ", "코스닥"]] as const;

/** 값이 바뀌면 잠깐 반짝인다(오름 빨강·내림 파랑). */
export function Flash({ v, children, className = "" }: { v?: number | null; children: React.ReactNode; className?: string }) {
  const prev = useRef(v);
  const [f, setF] = useState<{ cls: string; n: number }>({ cls: "", n: 0 });
  useEffect(() => {
    const p = prev.current;
    prev.current = v;
    if (p == null || v == null || p === v) return;
    setF((x) => ({ cls: v > p ? "so-flash-up" : "so-flash-down", n: x.n + 1 }));
  }, [v]);
  return <span key={f.n} className={`${className} rounded-md ${f.cls}`}>{children}</span>;
}

export function LiveBadge({ live }: { live: LiveView }) {
  const tone = live.state === "live" ? "bg-emerald-400/15 text-emerald-200 ring-emerald-300/40"
    : live.state === "delayed" ? "bg-amber-400/15 text-amber-100 ring-amber-300/40" : "bg-white/10 text-slate-100 ring-white/20";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[14px] font-extrabold ring-1 ${tone}`} role="status" aria-live="polite">
      {live.state === "live" && <span aria-hidden className="so-blink size-2 rounded-full bg-emerald-400" />}
      {live.state === "delayed" && <span aria-hidden className="size-2 rounded-full bg-amber-300" />}
      {live.state === "live" ? `실시간 · ${hms(live.updated_ts)} 갱신`
        : live.state === "delayed" ? `${live.label}${live.updated_ts ? ` · ${hms(live.updated_ts)} 기준` : ""}` : live.label}
    </span>
  );
}

function Card({ id, title, meta, children }: { id?: string; title: string; meta?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-16 rounded-3xl bg-white/[0.04] p-4 ring-1 ring-white/10 sm:p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-[18px] font-black text-white">{title}</h3>
        {meta && <span className="text-[14px] text-slate-300">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

function Seg<T extends string>({ value, onChange, label }: { value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="mb-3 inline-flex rounded-full bg-white/[0.06] p-1 ring-1 ring-white/10">
      {MARKETS.map(([v, l]) => (
        <button key={v} role="tab" type="button" aria-selected={value === v} onClick={() => onChange(v as T)}
          className={`rounded-full px-4 py-1.5 text-[15px] font-extrabold transition ${value === v ? "bg-white text-[#071226]" : "text-slate-200 hover:text-white"}`}>{l}</button>
      ))}
    </div>
  );
}

/** 오늘 시간대별 지수(5분봉 + 지금 값). 전일 종가 점선 위는 빨강, 아래는 파랑. */
function MiniChart({ idx }: { idx: LiveIndex }) {
  const pts = idx.series;
  const base = idx.close != null && idx.change != null ? idx.close - idx.change : null;
  if (pts.length < 2) return <div className="mt-2 flex h-14 items-center text-[14px] text-slate-400">장이 열리면 오늘 흐름이 그려져요</div>;
  const vals = [...pts.map((p) => p.c), ...(base != null ? [base] : [])];
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  // 가로: 09:00~15:30(390분) 기준 위치
  const x = (t: string) => Math.max(0, Math.min(100, ((Number(t.slice(0, 2)) * 60 + Number(t.slice(2, 4)) - 540) / 390) * 100));
  const y = (c: number) => 46 - ((c - min) / span) * 42;
  const d = pts.map((p) => `${x(p.t).toFixed(1)},${y(p.c).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg viewBox="0 0 100 50" preserveAspectRatio="none" className="mt-2 h-14 w-full" role="img"
      aria-label={`${idx.name} 오늘 흐름: ${pts[0].t.slice(0, 2)}:${pts[0].t.slice(2)} ${pts[0].c}에서 ${last.t.slice(0, 2)}:${last.t.slice(2)} ${last.c}`}>
      {base != null && <line x1="0" x2="100" y1={y(base)} y2={y(base)} stroke="#94a3b8" strokeWidth="1" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />}
      <polyline points={d} fill="none" stroke={color(idx.rate)} strokeWidth="2.2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
      <circle cx={x(last.t)} cy={y(last.c)} r="1.6" fill={color(idx.rate)} />
    </svg>
  );
}

function IndexCard({ idx }: { idx: LiveIndex }) {
  return (
    <div className="rounded-2xl bg-white/[0.05] p-3.5 ring-1 ring-white/10">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[15px] font-extrabold text-slate-100">{idx.name}</span>
        <Flash v={idx.rate} className="px-1 text-[15px] font-extrabold tabular-nums"><span style={{ color: color(idx.rate) }}>{arrow(idx.rate)} {signed(idx.rate)}</span></Flash>
      </div>
      <Flash v={idx.close} className="mt-1 inline-block px-1 text-[26px] font-black tabular-nums text-white">
        {idx.close != null ? idx.close.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
      </Flash>
      <div className="text-[14px] font-bold tabular-nums" style={{ color: color(idx.change) }}>
        {idx.change != null ? `${idx.change > 0 ? "+" : ""}${idx.change.toFixed(2)}` : ""}
      </div>
      <MiniChart idx={idx} />
      <div className="flex justify-between text-[13px] text-slate-400"><span>09:00</span><span>점선 = 전일 종가</span><span>15:30</span></div>
    </div>
  );
}

function Temperature({ b }: { b: LiveView["breadth"] }) {
  const up = b.up ?? 0, down = b.down ?? 0, flat = b.flat ?? 0, total = up + down + flat;
  if (!total) return <p className="text-[15px] text-slate-300">종목 수 자료가 아직 없어요.</p>;
  const pct = (n: number) => `${((n / total) * 100).toFixed(1)}%`;
  return (
    <div>
      <div className="flex h-4 overflow-hidden rounded-full" role="img" aria-label={`상승 ${up}, 보합 ${flat}, 하락 ${down}`}>
        <div style={{ width: pct(up), background: UP }} />
        <div style={{ width: pct(flat), background: "#64748b" }} />
        <div style={{ width: pct(down), background: DOWN }} />
      </div>
      <div className="mt-2.5 grid grid-cols-3 gap-2 text-center">
        {([["상승", up, UP], ["보합", flat, "#cbd5e1"], ["하락", down, DOWN]] as const).map(([l, n, c]) => (
          <div key={l} className="rounded-2xl bg-white/[0.05] py-2">
            <div className="text-[14px] font-bold text-slate-300">{l}</div>
            <Flash v={n} className="px-1 text-[20px] font-black tabular-nums"><span style={{ color: c }}>{n.toLocaleString()}</span></Flash>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[15px] text-slate-200">
        상한가 <b className="tabular-nums" style={{ color: UP }}>{b.upper ?? "—"}</b> · 하한가 <b className="tabular-nums" style={{ color: DOWN }}>{b.lower ?? "—"}</b>
        <span className="text-slate-400"> · 코스피+코스닥 {total.toLocaleString()}종목</span>
      </p>
    </div>
  );
}

function Investors({ live }: { live: LiveView }) {
  const [m, setM] = useState<"KOSPI" | "KOSDAQ">("KOSPI");
  const inv = live.investors?.[m];
  if (!live.investors) return <p className="text-[15px] text-slate-300">키움증권 API 시세일 때 보여 드려요(공공데이터에는 투자자별 자료가 없어요).</p>;
  const rows = inv ? ([["외국인", inv.foreign], ["기관", inv.inst], ["개인", inv.indiv]] as const) : [];
  const max = Math.max(1, ...rows.map(([, v]) => Math.abs(v)));
  return (
    <div>
      <Seg value={m} onChange={setM} label="투자자별 매매 시장" />
      {rows.length ? (
        <ul className="space-y-2.5">
          {rows.map(([name, v]) => (
            <li key={name} className="grid grid-cols-[3.5rem_1fr_6.5rem] items-center gap-2">
              <span className="text-[15px] font-extrabold text-slate-100">{name}</span>
              {/* 가운데 0선 기준 왼쪽 = 순매도(파랑), 오른쪽 = 순매수(빨강) */}
              <span className="relative h-5 rounded-full bg-white/[0.06]">
                <span className="absolute inset-y-0 left-1/2 w-px bg-white/30" />
                <span className="absolute inset-y-0.5 rounded-full transition-all duration-500"
                  style={{ background: v >= 0 ? UP : DOWN, width: `${(Math.abs(v) / max) * 50}%`, left: v >= 0 ? "50%" : `${50 - (Math.abs(v) / max) * 50}%` }} />
              </span>
              <Flash v={v} className="px-1 text-right text-[15px] font-extrabold tabular-nums">
                <span style={{ color: color(v) }}>{v > 0 ? "+" : ""}{Math.round(v).toLocaleString()}억</span>
              </Flash>
            </li>
          ))}
        </ul>
      ) : <p className="text-[15px] text-slate-300">자료를 모으는 중이에요.</p>}
      <p className="mt-2 text-[14px] text-slate-400">순매수 금액(억 원) · 오른쪽 빨강 = 순매수, 왼쪽 파랑 = 순매도{live.extra_ts ? ` · ${hm(live.extra_ts)} 기준(2분마다)` : ""}</p>
    </div>
  );
}

function SectorList({ title, rows }: { title: string; rows: LiveSector[] }) {
  return (
    <div>
      <div className="mb-1.5 text-[14px] font-extrabold text-slate-300">{title}</div>
      <ol className="space-y-1.5">
        {rows.map((r, i) => (
          <li key={r.code} className="flex items-center justify-between gap-2 rounded-xl bg-white/[0.04] px-3 py-2">
            <span className="min-w-0 truncate text-[15px] font-bold text-white">{i + 1}. {r.name}</span>
            <Flash v={r.rate} className="shrink-0 px-1 text-[15px] font-extrabold tabular-nums"><span style={{ color: color(r.rate) }}>{arrow(r.rate)} {signed(r.rate)}</span></Flash>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Sectors({ live }: { live: LiveView }) {
  const [m, setM] = useState<"KOSPI" | "KOSDAQ">("KOSPI");
  const s = live.sectors?.[m];
  if (!live.sectors) return <p className="text-[15px] text-slate-300">키움증권 API 시세일 때 보여 드려요.</p>;
  return (
    <div>
      <Seg value={m} onChange={setM} label="업종 순위 시장" />
      {s ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <SectorList title="많이 오른 업종" rows={s.top} />
          {s.bottom.length > 0 && <SectorList title="많이 내린 업종" rows={s.bottom} />}
        </div>
      ) : <p className="text-[15px] text-slate-300">자료를 모으는 중이에요.</p>}
    </div>
  );
}

function ValueTop({ rows, onPick }: { rows: Stock[]; onPick: (s: Stock) => void }) {
  if (!rows.length) return <p className="text-[15px] text-slate-300">자료가 아직 없어요.</p>;
  return (
    <ol className="divide-y divide-white/10">
      {rows.map((s, i) => (
        <li key={s.code}>
          <button type="button" onClick={() => onPick(s)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-white/[0.03]">
            <span className="w-5 text-center text-[15px] font-extrabold text-slate-400">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[16px] font-extrabold text-white">{s.name}</span>
              <span className="text-[14px] text-slate-400">거래대금 {eok(s.value)}</span>
            </span>
            <span className="text-right">
              <Flash v={s.close} className="block px-1 text-[16px] font-extrabold tabular-nums text-white">{s.close?.toLocaleString("ko-KR")}</Flash>
              <span className="text-[14px] font-bold tabular-nums" style={{ color: color(s.rate) }}>{arrow(s.rate)} {signed(s.rate)}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function LiveMarket({ live, onPick }: { live: LiveView; onPick: (s: Stock) => void }) {
  return (
    <div id="live" className="scroll-mt-16 space-y-4 text-slate-100">
      <div className="flex flex-wrap items-center gap-2">
        <LiveBadge live={live} />
        <span className="text-[14px] text-slate-300">{live.source === "kiwoom" ? "키움증권 모의투자 API · 참고용" : "공공데이터 · 참고용"} · 화면은 15초마다 자동으로 바뀌어요</span>
      </div>

      {live.ai && (
        <div className="rounded-2xl bg-sky-400/10 px-4 py-3 ring-1 ring-sky-300/25">
          <p className="text-[17px] font-extrabold leading-snug text-white">{live.ai.text}</p>
          <p className="mt-1 text-[14px] text-sky-100">
            {live.ai.ai ? "🤖 AI가 요약했어요" : "숫자로 정리했어요"} · {live.ai.kind === "close" ? "오늘 마감 요약 · " : ""}{hm(live.ai.ts)}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {live.indices.map((i) => <IndexCard key={i.market} idx={i} />)}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card id="temp" title="시장 체온" meta="상승·하락·보합 종목 수">
          <Temperature b={live.breadth} />
        </Card>
        <Card id="investors" title="투자자별 매매 동향">
          <Investors live={live} />
        </Card>
        <Card id="sectors" title="업종별 등락 순위" meta={live.extra_ts ? `${hm(live.extra_ts)} 기준 · 2분마다` : undefined}>
          <Sectors live={live} />
        </Card>
        <Card id="value" title="거래대금 상위 5" meta="누르면 '왜 움직였나'">
          <ValueTop rows={live.value_top} onPick={onPick} />
        </Card>
      </div>
    </div>
  );
}
