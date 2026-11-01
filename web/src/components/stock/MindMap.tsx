"use client";

// 뉴스 속 숨은 종목의 관련 회사 지도. 방사형(2026-11-01 복귀): 가운데 = 뉴스(이슈) → 영향 경로 동그라미(경로 이름) → 회사 동그라미.
//   경로는 360도에 고르게 펼치고(경로 수에 따라 각도 고정), 회사는 자기 경로 바깥쪽에 부채꼴로. 뉴스 당사자는 경로 없이 중심 가까이 바로 연결(두 겹 테두리).
//   경로마다 색이 달라 경로 동그라미·연결선·회사 테두리에 같은 색. AI 해석 방향은 동그라미 오른쪽 위 배지 ＋(도움 가능)·－(부담 가능), 불확실은 배지 없음.
//   회사명 아래에 시장 대비 등락 숫자(한국식: 올랐으면 빨강 ▲, 내렸으면 파랑 ▼, ±2%p 이내 회색). 크게 움직였으면(±3%p) 바깥 테두리 빛.
//   장이 닫힌 때는 마지막 종가 기준 숫자를 그대로 보이고 범례에 '금 종가 기준'처럼 표시. 검증된 회사가 3곳 미만이면 업종 참고(점선·작은 회색)를 빈 틈에.
// 노드가 최대 12개 안팎이라 라이브러리 없이 SVG로 그리고, 자리는 목표점에서 겹치지 않게 몇 번 밀어내 정한다(같은 입력이면 같은 자리).
// 애니메이션은 transform·opacity·stroke-dashoffset만. 글자: 휴대폰 390px(배율 약 0.89)에서 회사 이름 17px, 숫자 14px 이상.
import { useEffect, useMemo, useRef, useState } from "react";
import { type LifeCompany, type LifeMap, type LifeStage } from "@/lib/stock";

// 경로 색(순서대로). 상승 빨강·하락 파랑과 겹치지 않는 색
export const PATH_COLORS = ["#2dd4bf", "#a78bfa", "#facc15", "#a3e635"];
export const pathColor = (i: number) => PATH_COLORS[i % PATH_COLORS.length];
export const UP = "#ff6b81";   // 상승 빨강(어두운 배경용)
export const DOWN = "#5aa9ff"; // 하락 파랑
export const POS = "#34d399";  // AI 해석: 긍정 영향 가능
export const NEG = "#fb923c";  // AI 해석: 부정 영향 가능
const R = 46;      // 회사 동그라미(두 줄 이름 4자 × 19.5)
const R_REF = 22;  // 업종 참고(작은 회색)
const REF_BELOW = 38; // 참고 동그라미 아래 이름·숫자 두 줄 자리
const R_CENTER = 42;
const PATH_FONT = 15;  // 경로 이름 글자(390px에서 약 13.3px)
const RING_CO = 170;   // 회사 반지름 위치
const RING_PARTY = 100; // 뉴스 당사자(경로 없이 중심 가까이)
const W = 440, TOP = -220, H = 440; // viewBox: 정사각형, 중심 (0,0)
const K_MIN = 1, K_MAX = 3;

type Pt = { x: number; y: number };
export const rateText = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(Math.abs(v) >= 10 ? 0 : 1)}%`);
export const rateColor = (v?: number | null) => (!v ? "#e2e8f0" : v > 0 ? UP : DOWN);
export const GRAY = "#cbd5e1";
/** 잡음 구간: 시장보다 ±2%p 이내는 '시장과 비슷해요'(회색). */
export const SIMILAR_PP = 2;
export const similar = (vs?: number | null) => vs != null && Math.abs(vs) <= SIMILAR_PP;
/** 시장보다 색: 잡음 구간은 회색, 그 밖은 상승 빨강·하락 파랑. */
export const vsColor = (vs?: number | null) => (similar(vs) ? GRAY : rateColor(vs));
/** 시장보다(%p): ▲/▼와 %p. 10 이상은 정수. */
export const ppText = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(Math.abs(v) >= 9.95 ? 0 : 1)}%p`);
export const dirName = (d?: LifeCompany["direction"]) => (d === "neg" ? "부담 받을 수 있는 회사" : d === "unk" || d === "neu" ? "영향 받을 수 있는 회사" : "도움 받을 수 있는 회사");
/** AI 해석 방향 색: 도움 가능 초록 · 부담 가능 주황 · 영향 가능(방향 불확실) 회색 */
export const dirColor = (d?: LifeCompany["direction"]) => (d === "neg" ? NEG : d === "unk" || d === "neu" ? GRAY : POS);
/** 동그라미 꼬리표(이름 아래 글자) */
/** 화면 읽기용 방향 말 */
const dirTag = (d?: LifeCompany["direction"]) => (d === "neg" ? "부담" : d === "unk" || d === "neu" ? "불확실" : "도움");
/** 실제 등락 테두리 빛: 크게 움직였을 때만(시장 대비 ±3%p, 서버 moved). 오르면 빨강·내리면 파랑. 반응 대기 중이면 없음. */
function moveGlow(c: LifeCompany): string | null {
  const v = c.vs_market ?? c.rate;
  if (c.waiting || !c.moved || v == null) return null;
  return v > 0 ? UP : DOWN;
}
/** 회사명 아래 숫자: 시장 대비(%p, 없으면 주가 %). ±2%p 이내 회색. 장이 닫힌 때도 마지막 종가 기준 숫자를 그대로 보인다. */
function moveText(c: LifeCompany): { text: string; color: string } | null {
  if (c.vs_market != null) return { text: ppText(c.vs_market), color: vsColor(c.vs_market) };
  if (c.rate != null) return { text: rateText(c.rate), color: similar(c.rate) ? GRAY : rateColor(c.rate) };
  return null;
}
/** 방향 배지(오른쪽 위): 도움 가능 ＋ · 부담 가능 －, 방향 불확실·중립은 없음 */
const dirBadge = (d?: LifeCompany["direction"]) => (d === "neg" ? "－" : d === "pos" || d == null ? "＋" : null);

/** 원 안 이름: 4자 이하는 한 줄, 그보다 길면 두 줄(최대 4+4자, 넘치면 …). */
function nameLines(name: string): string[] {
  if (name.length <= 4) return [name];
  const s = name.length > 8 ? `${name.slice(0, 7)}…` : name;
  const half = Math.ceil(s.length / 2);
  return [s.slice(0, half), s.slice(half)];
}

/** 중앙→회사 곡선(살짝 휜 2차 베지어). pathLength=1로 두고 dashoffset으로 그려지는 효과를 낸다. */
function curve(a: Pt, b: Pt, bend = 0.12): string {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = b.x - a.x, dy = b.y - a.y;
  return `M${a.x.toFixed(1)},${a.y.toFixed(1)} Q${(mx - dy * bend).toFixed(1)},${(my + dx * bend).toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)}`;
}

type Region = "party" | "co" | "ref";
type Node = { c: LifeCompany; stage?: LifeStage; color: string; region: Region; r: number; pos: Pt };
type PathNode = { stage: LifeStage; color: string; idx: number; ang: number; pos: Pt; r: number; lines: string[] };

/** 경로 이름 줄바꿈: 짧으면 한 줄, 아니면 두 줄(공백이 있고 균형이 맞으면 공백에서, 아니면 반으로). 말줄임 없이 그대로 보여준다. */
function pathLines(label: string): string[] {
  const t = label.trim();
  if (t.length <= 3) return [t];
  const sp = t.indexOf(" ", 1);
  const half = Math.ceil(t.length / 2);
  if (sp > 0 && sp <= half + 1 && t.length - sp - 1 <= half + 1) return [t.slice(0, sp), t.slice(sp + 1).trim()];
  const h = Math.ceil(t.replace(/\s/g, "").length / 2);
  const c = t.replace(/\s/g, "");
  return [c.slice(0, h), c.slice(h)];
}
/** 글자가 들어가는 만큼 동그라미 반지름(넘치면 조금 키운다) */
const pathRadius = (lines: string[]) =>
  Math.max(26, Math.ceil(Math.hypot((Math.max(...lines.map((l) => l.length)) * PATH_FONT) / 2, (lines.length * (PATH_FONT + 2)) / 2)) + 3);

const polar = (deg: number, r: number): Pt => ({ x: Math.cos((deg * Math.PI) / 180) * r, y: Math.sin((deg * Math.PI) / 180) * r });

/** 중심(뉴스) → 경로 동그라미(360도 고르게) → 회사(경로 바깥 부채꼴). 당사자·참고는 경로 사이 빈 틈에.
 *  목표점에서 서로 겹치지 않게 밀어낸다(같은 입력이면 같은 자리). */
function layout(stages: LifeStage[], refs: LifeCompany[]): { nodes: Node[]; paths: PathNode[] } {
  const active = stages.map((s, i) => ({ s, i })).filter(({ s }) => s.companies.some((c) => !c.party));
  const n = active.length;
  const start = n % 2 === 0 && n > 0 ? -90 - 180 / n : -90; // 1·3곳은 위가 한 곳, 2·4곳은 대칭
  const angs = active.map((_, k) => start + (k * 360) / Math.max(n, 1));
  const paths: PathNode[] = active.map(({ s, i }, k) => {
    const lines = pathLines(s.label), r = pathRadius(lines);
    return { stage: s, color: pathColor(i), idx: i, ang: angs[k], pos: polar(angs[k], R_CENTER + r + 10), r, lines };
  });
  const hasParty = stages.some((s) => s.companies.some((c) => c.party));
  const nodes: (Node & { t: Pt })[] = [];
  const put = (c: LifeCompany, stage: LifeStage | undefined, color: string, region: Region, r: number, t: Pt) =>
    nodes.push({ c, stage, color, region, r, t, pos: { ...t } });

  active.forEach(({ s, i }, k) => {
    const cos = s.companies.filter((c) => !c.party);
    const sector = n === 1 ? 150 : (360 / n) * (hasParty ? 0.62 : 0.8);
    const step = Math.min(n === 1 ? 52 : n === 2 ? 62 : 40, sector / cos.length);
    cos.forEach((c, j) => put(c, s, pathColor(i), "co", R, polar(angs[k] + (j - (cos.length - 1) / 2) * step, cos.length === 1 ? RING_CO + 4 : RING_CO)));
  });

  // 빈 틈(경로와 경로 사이) 자리: 당사자 먼저, 이어서 참고
  const mids = n === 0 ? [-90, 90, 30, 150, -30, -150] : n === 1 ? [angs[0] + 180, angs[0] + 125, angs[0] + 235] : angs.map((a) => a + 180 / n);
  const slot = (j: number) => mids[j % mids.length] + [0, 24, -24, 48][Math.min(Math.floor(j / mids.length), 3)];
  const parties = stages.flatMap((s, i) => s.companies.filter((c) => c.party).map((c) => ({ c, s, i })));
  parties.forEach(({ c, s, i }, j) => put(c, s, pathColor(i), "party", R, polar(slot(j), RING_PARTY)));
  refs.slice(0, 3).forEach((c, j) => put(c, undefined, GRAY, "ref", R_REF, polar(slot(parties.length + j), 170)));

  const pad = (x: Node) => (x.region === "ref" ? 24 : 6); // 참고 동그라미는 아래 이름·숫자 자리까지
  for (let it = 0; it < 320; it++) {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      const d0 = Math.hypot(a.pos.x, a.pos.y) || 1, m0 = a.r + R_CENTER + 10; // 중심(고정)과 겹치지 않게
      if (d0 < m0) { a.pos.x = (a.pos.x * m0) / d0; a.pos.y = (a.pos.y * m0) / d0; }
      for (const p of paths) { // 경로 동그라미(고정)와 겹치지 않게
        const dx = a.pos.x - p.pos.x, dy = a.pos.y - p.pos.y, d = Math.hypot(dx, dy) || 1, m = a.r + p.r + 8 + (a.region === "ref" ? 4 : 0);
        if (d < m) { a.pos.x = p.pos.x + (dx * m) / d; a.pos.y = p.pos.y + (dy * m) / d; }
      }
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.pos.x - a.pos.x, dy = b.pos.y - a.pos.y;
        let d = Math.hypot(dx, dy);
        if (d < 0.01) { dx = 1; dy = 0; d = 1; }
        const min = a.r + b.r + pad(a) + pad(b);
        if (d < min) {
          const push = (min - d) / 2;
          a.pos.x -= (dx / d) * push; a.pos.y -= (dy / d) * push;
          b.pos.x += (dx / d) * push; b.pos.y += (dy / d) * push;
        }
      }
    }
    for (const q of nodes) {
      if (it < 180) { // 마지막 몇 번은 밀어내기만(겹침이 남지 않게)
        q.pos.x += (q.t.x - q.pos.x) * 0.06;
        q.pos.y += (q.t.y - q.pos.y) * 0.06;
      }
      const below = q.region === "ref" ? REF_BELOW : 0; // 참고 이름·숫자가 동그라미 아래에 붙는다
      const m = q.r + (q.region === "ref" ? 6 : 12); // 빛나는 테두리 몫
      q.pos.x = Math.max(-W / 2 + m, Math.min(W / 2 - m, q.pos.x));
      q.pos.y = Math.max(TOP + m, Math.min(TOP + H - m - below - 3, q.pos.y));
    }
  }
  return { nodes: nodes.map(({ t: _t, ...q }) => q), paths };
}

/** 장이 닫힌 때(평일 9:00~15:30 밖·주말)면 기준일의 요일로 '금 종가 기준', 장중이면 null */
function closeBasis(ymd?: string): string | null {
  const now = new Date(Date.now() + 9 * 3600_000); // KST를 UTC 필드로
  const dow = now.getUTCDay(), mins = now.getUTCHours() * 60 + now.getUTCMinutes();
  const open = dow >= 1 && dow <= 5 && mins >= 9 * 60 && mins < 15 * 60 + 30;
  if (open) return null;
  if (!ymd || ymd.length < 8) return "종가 기준";
  const d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8)));
  return `${"일월화수목금토"[d.getUTCDay()]} 종가 기준`;
}

export default function MindMap({ map, refs = [], center, onPick, picked, basisYmd }: {
  map: LifeMap; refs?: LifeCompany[]; center: string; basisYmd?: string; onPick: (c: LifeCompany, s: LifeStage, color: string) => void; picked?: string;
}) {
  // 자리·애니메이션은 회사 구성(코드·방향·당사자·경로)이 바뀔 때만 다시. 15초 갱신(등락률)이나 다시 그리기로는 다시 자라지 않는다
  const sig = `${center}|${map.stages.map((s) => `${s.key}:${s.companies.map((c) => `${c.code}${c.direction ?? ""}${c.party ? "p" : ""}`).join(",")}`).join("/")}|${refs.map((c) => c.code).join(",")}`;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const { nodes: placed, paths } = useMemo(() => layout(map.stages, refs), [sig]);
  const current = new Map([...map.stages.flatMap((s) => s.companies), ...refs].map((c) => [c.code, c]));
  const nodes = placed.map((n) => ({ ...n, c: current.get(n.c.code) ?? n.c }));
  const [closed, setClosed] = useState<string | null>(null); // 장이 닫힌 때의 기준 표시(서버·브라우저 시계 차이를 피해 마운트 뒤에)
  useEffect(() => setClosed(closeBasis(basisYmd)), [basisYmd]);
  const [shown, setShown] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const box = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, Pt>());
  const gesture = useRef<{ d: number; k: number; mid: Pt; x: number; y: number } | null>(null);
  const dragged = useRef(false);

  // 이슈가 바뀌면 중앙에서 회사 쪽으로 가지가 자라난다(모두 펼친 채로 끝남).
  useEffect(() => {
    setShown(false);
    setFocus(null);
    setView({ k: 1, x: 0, y: 0 });
    const t = setTimeout(() => setShown(true), 40);
    return () => clearTimeout(t);
  }, [sig]);

  // 화면 px → SVG 좌표(중앙 0,0)
  const toSvg = (p: Pt): Pt => {
    const el = box.current;
    if (!el) return p;
    const r = el.getBoundingClientRect();
    const s = W / r.width;
    return { x: (p.x - r.left - r.width / 2) * s, y: (p.y - r.top) * s + TOP };
  };
  const zoomAt = (p: Pt, k1: number, base = view) => {
    const k = Math.min(K_MAX, Math.max(K_MIN, k1));
    if (k === K_MIN) return { k, x: 0, y: 0 };
    return { k, x: p.x - ((p.x - base.x) * k) / base.k, y: p.y - ((p.y - base.y) * k) / base.k };
  };

  function start() {
    const pts = [...pointers.current.values()];
    const mid = pts.length === 2 ? { x: (pts[0].x + pts[1].x) / 2, y: (pts[0].y + pts[1].y) / 2 } : pts[0];
    const d = pts.length === 2 ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0;
    gesture.current = { d, k: view.k, mid, x: view.x, y: view.y };
  }
  function onDown(e: React.PointerEvent) {
    if (pointers.current.size === 0) dragged.current = false;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size <= 2) start();
  }
  function onMove(e: React.PointerEvent) {
    if (!pointers.current.has(e.pointerId) || !gesture.current) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    const pts = [...pointers.current.values()];
    if (pts.length === 2 && g.d) {
      const mid = { x: (pts[0].x + pts[1].x) / 2, y: (pts[0].y + pts[1].y) / 2 };
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const next = zoomAt(toSvg(g.mid), (g.k * d) / g.d, { k: g.k, x: g.x, y: g.y });
      const shift = toSvg(mid), from = toSvg(g.mid);
      setView(next.k === K_MIN ? next : { ...next, x: next.x + shift.x - from.x, y: next.y + shift.y - from.y });
      dragged.current = true;
    } else if (pts.length === 1 && view.k > 1) {
      const a = toSvg(g.mid), b = toSvg(pts[0]);
      const lim = (W / 2) * (view.k - 1);
      setView({ k: view.k, x: Math.max(-lim, Math.min(lim, g.x + b.x - a.x)), y: Math.max(-lim, Math.min(lim, g.y + b.y - a.y)) });
      if (Math.hypot(b.x - a.x, b.y - a.y) > 6) dragged.current = true;
    }
  }
  function onUp(e: React.PointerEvent) {
    pointers.current.delete(e.pointerId);
    gesture.current = null;
    if (pointers.current.size) start();
  }

  // PC 트랙패드 핀치(ctrl+휠)·ctrl+휠 확대. 그냥 휠은 페이지 스크롤로 둔다.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setView((v) => zoomAt(toSvg({ x: e.clientX, y: e.clientY }), v.k * Math.exp(-e.deltaY / 200), v));
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  });

  const tap = (fn: () => void) => () => { if (!dragged.current) fn(); };
  const press = (fn: () => void) => (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } };
  const toggleFocus = (k: string) => setFocus((f) => (f === k ? null : k));
  const dim = (n: Node) => (focus && (n.region === "ref" || n.stage?.key !== focus) ? 0.22 : 1);
  const dimKey = (k: string) => (focus && focus !== k ? 0.22 : 1);
  const word = center.length > 8 ? `${center.slice(0, 7)}…` : center;
  const centerLines = word.length > 5 && word.includes(" ") ? [word.slice(0, word.indexOf(" ")), word.slice(word.indexOf(" ") + 1)] : [word];
  const centerSize = word.length > 6 ? 15 : word.length > 4 ? 17 : 21;
  const pathOf = (n: Node) => paths.find((p) => p.stage.key === n.stage?.key);

  return (
    <div>
      <div ref={box} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onPointerLeave={onUp}
        className="lifemap-canvas relative mx-auto w-full max-w-[600px] select-none overflow-hidden rounded-3xl"
        style={{ aspectRatio: `${W} / ${H}`, touchAction: view.k > 1 ? "none" : "pan-y" }}>
        <svg viewBox={`${-W / 2} ${TOP} ${W} ${H}`} className="size-full" role="img"
          aria-label={`${center} 관련 회사 지도. 가운데 뉴스에서 영향 경로를 거쳐 회사로 이어져요: ${nodes.map((n) =>
            `${n.c.name} ${n.region === "ref" ? "업종 참고" : `${n.c.party ? "뉴스 당사자 " : ""}${dirTag(n.c.direction)}`}`).join(", ")}`}>
          <defs>
            <radialGradient id="lm-core" cx="50%" cy="45%" r="60%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="55%" stopColor="#bdf3ff" />
              <stop offset="100%" stopColor="#38bdf8" />
            </radialGradient>
            <radialGradient id="lm-halo">
              <stop offset="0%" stopColor="#7dd3fc" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0" />
            </radialGradient>
          </defs>
          <g style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, transition: pointers.current.size ? "none" : "transform 200ms ease-out" }}>
            {/* 가지: 중심 → 경로 동그라미 → 회사, 당사자는 중심에서 바로. 굵고 옅은 선 위에 가는 선(필터 없이). 선 색 = 영향 경로, 참고는 회색 점선 */}
            {paths.map((p, i) => {
              const on = focus === p.stage.key;
              return (
                <g key={`pe-${p.stage.key}`} style={{ opacity: dimKey(p.stage.key), transition: "opacity 250ms" }}>
                  <path d={curve({ x: 0, y: 0 }, p.pos, 0)} pathLength={1} fill="none" stroke={p.color} strokeWidth={on ? 14 : 8} strokeOpacity={0.15}
                    strokeLinecap="round" className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${i * 80}ms` }} />
                  <path d={curve({ x: 0, y: 0 }, p.pos, 0)} pathLength={1} fill="none" stroke={p.color} strokeWidth={on ? 4 : 2.8} strokeOpacity={0.95}
                    strokeLinecap="round" className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${i * 80}ms` }} />
                </g>
              );
            })}
            {nodes.map((n, i) => {
              const ref = n.region === "ref";
              const on = !!focus && n.stage?.key === focus;
              const from = n.region === "co" ? (pathOf(n)?.pos ?? { x: 0, y: 0 }) : { x: 0, y: 0 };
              return (
                <g key={`e-${n.c.code}`} style={{ opacity: dim(n), transition: "opacity 250ms" }}>
                  {!ref && <path d={curve(from, n.pos)} pathLength={1} fill="none" stroke={n.color} strokeWidth={on ? 14 : 8} strokeOpacity={0.15}
                    strokeLinecap="round" className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${150 + i * 80}ms` }} />}
                  {ref ? (
                    <path d={curve(from, n.pos)} fill="none" stroke={GRAY} strokeWidth={1.6} strokeOpacity={shown ? 0.45 : 0} strokeDasharray="4 5"
                      style={{ transition: "stroke-opacity 400ms", transitionDelay: `${300 + i * 80}ms` }} />
                  ) : (
                    <path d={curve(from, n.pos)} pathLength={1} fill="none" stroke={n.color} strokeWidth={on ? 3.6 : 2.4} strokeOpacity={0.9}
                      strokeLinecap="round" className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${150 + i * 80}ms` }} />
                  )}
                </g>
              );
            })}

            {/* 영향 경로 동그라미(경로 이름): 누르면 그 경로만 강조 */}
            {paths.map((p, i) => (
              <g key={`p-${p.stage.key}`} className="lm-node" role="button" tabIndex={0} aria-label={`영향 경로 ${p.stage.label}`}
                onClick={tap(() => toggleFocus(p.stage.key))} onKeyDown={press(() => toggleFocus(p.stage.key))}
                style={{ cursor: "pointer", transform: `translate(${shown ? p.pos.x : 0}px, ${shown ? p.pos.y : 0}px) scale(${shown ? 1 : 0.2})`,
                  opacity: shown ? dimKey(p.stage.key) : 0, transitionDelay: shown ? `${100 + i * 80}ms` : "0ms" }}>
                <title>{p.stage.label}</title>
                <circle r={p.r} fill="#0b1a36" stroke={p.color} strokeWidth={focus === p.stage.key ? 4 : 2.8} />
                {p.lines.map((t, k) => (
                  <text key={k} textAnchor="middle" y={(k - (p.lines.length - 1) / 2) * (PATH_FONT + 2)} dy="0.36em" fontSize={PATH_FONT} fontWeight={900} fill={p.color}>{t}</text>
                ))}
              </g>
            ))}

            {/* 회사 노드 */}
            {nodes.map((n, i) => {
              const { c } = n;
              const at = shown ? n.pos : { x: 0, y: 0 };
              const style = { transform: `translate(${at.x}px, ${at.y}px) scale(${shown ? 1 : 0.2})`, opacity: shown ? dim(n) : 0,
                transitionDelay: shown ? `${200 + i * 80}ms` : "0ms" };
              if (n.region === "ref") {
                const nm = c.name.length > 6 ? `${c.name.slice(0, 5)}…` : c.name;
                const mv = moveText(c);
                return (
                  <g key={c.code} className="lm-node" style={style} aria-hidden>
                    <title>{`${c.name} · 업종 참고(근거로 확인된 연결 아님)`}</title>
                    <circle r={n.r} fill="#1e293b" stroke={GRAY} strokeOpacity={0.7} strokeWidth={1.6} strokeDasharray="3 3" />
                    <text textAnchor="middle" dy="0.36em" fontSize={14} fontWeight={800} fill="#cbd5e1">참고</text>
                    <text textAnchor="middle" y={n.r + 16} fontSize={15} fontWeight={700} fill="#94a3b8" className="lm-label">{nm}</text>
                    {mv && <text textAnchor="middle" y={n.r + 33} fontSize={15} fontWeight={800} fill={mv.color} className="lm-label tabular-nums">{mv.text}</text>}
                  </g>
                );
              }
              const lines = nameLines(c.name);
              const glow = moveGlow(c);
              const on = picked === c.code;
              const badge = dirBadge(c.direction);
              const mv = moveText(c);
              const nameY = lines.length === 1 ? [-8] : [-17, 4];
              const bx = n.r * 0.87, by = -n.r * 0.87; // 오른쪽 위 배지 자리(테두리에 걸쳐, 두 줄 이름 첫 줄과 닿지 않게)
              return (
                <g key={c.code} className="lm-node" role="button" tabIndex={0}
                  aria-label={`${c.name}${c.party ? ", 뉴스 당사자" : ""}, ${n.stage ? `${n.stage.label}, ` : ""}${dirName(c.direction)}${mv ? `, 시장보다 ${mv.text}` : ""}${glow ? ", 크게 움직였어요" : ""}. 누르면 아래 목록에서 펼쳐요`}
                  onClick={tap(() => n.stage && onPick(c, n.stage, n.color))} onKeyDown={press(() => n.stage && onPick(c, n.stage, n.color))}
                  style={{ ...style, cursor: "pointer" }}>
                  {/* 실제로 크게 움직임(±3%p): 바깥 테두리 빛(빨강 오름·파랑 내림), 숨쉬듯 */}
                  {glow && <circle r={n.r + 12} fill="none" stroke={glow} strokeWidth={8} strokeOpacity={0.22} className="lm-pulse" />}
                  {glow && <circle r={n.r + 8} fill="none" stroke={glow} strokeWidth={3.4} />}
                  {c.party && <circle r={n.r + 3.5} fill="none" stroke="#f8fafc" strokeOpacity={0.85} strokeWidth={1.6} />}
                  <circle r={n.r} fill="#10244a" stroke={on ? "#ffffff" : n.color} strokeOpacity={on ? 1 : 0.95} strokeWidth={on ? 3.6 : 2.8} />
                  {lines.map((t, k) => (
                    <text key={k} textAnchor="middle" y={nameY[k]} dy="0.36em" fontSize={19.5} fontWeight={800} fill="#f8fafc">{t}</text>
                  ))}
                  {mv && <text textAnchor="middle" y={lines.length === 1 ? 17 : 26} dy="0.36em" fontSize={16} fontWeight={900} fill={mv.color} className="tabular-nums">{mv.text}</text>}
                  {badge && (
                    <g transform={`translate(${bx} ${by})`} aria-hidden>
                      <circle r={11.5} fill={dirColor(c.direction)} stroke="#0b1a36" strokeWidth={2.5} />
                      <text textAnchor="middle" dy="0.36em" fontSize={17} fontWeight={900} fill="#0b1a36">{badge}</text>
                    </g>
                  )}
                </g>
              );
            })}

            {/* 빛나는 중앙 = 뉴스. 누르면 강조 해제 */}
            <g className="lm-node" role="button" tabIndex={0} aria-label={`${center}, 강조 해제`} onClick={tap(() => setFocus(null))}
              onKeyDown={press(() => setFocus(null))} style={{ cursor: "pointer", transform: `translate(0px, 0px)` }}>
              <circle r={78} fill="url(#lm-halo)" className="lm-glow" pointerEvents="none" />
              <circle r={R_CENTER} fill="url(#lm-core)" />
              {centerLines.map((t, n) => (
                <text key={n} textAnchor="middle" y={(n - (centerLines.length - 1) / 2) * 19} dy="0.36em" fontSize={centerSize} fontWeight={900} fill="#0b1a36">{t}</text>
              ))}
            </g>
          </g>
        </svg>
      </div>

      {/* 범례(390px에서 글자가 겹치지 않게 항목 단위로만 줄바꿈) */}
      <p className="mt-1.5 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 px-3 text-[13px] font-bold tracking-tight text-slate-200 sm:px-0 sm:text-[14px]" aria-label="범례">
        <span className="flex items-center gap-0.5 whitespace-nowrap"><span className="flex size-4 items-center justify-center rounded-full text-[13px] font-black text-[#0b1a36]" style={{ background: POS }}>＋</span>도움 가능</span>·
        <span className="flex items-center gap-0.5 whitespace-nowrap"><span className="flex size-4 items-center justify-center rounded-full text-[13px] font-black text-[#0b1a36]" style={{ background: NEG }}>－</span>부담 가능</span>
        <span className="whitespace-nowrap text-slate-300">(AI 해석)</span>·
        <span className="whitespace-nowrap">숫자 = 시장보다 등락</span>·
        <span className="whitespace-nowrap">선 색 = 영향 경로</span>
        {closed && <><span>·</span><span className="whitespace-nowrap text-amber-100">{closed}</span></>}
      </p>

      {/* 영향 경로(선 색): 누르면 그 경로만 강조 */}
      <div className="mt-2 flex flex-wrap gap-1.5 px-4 sm:px-0" aria-label="영향 경로">
        {map.stages.map((s, i) => (
          <button key={s.key} type="button" aria-pressed={focus === s.key} onClick={() => toggleFocus(s.key)}
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[14px] font-extrabold ring-1 transition ${focus === s.key ? "bg-white/15 ring-white/60" : "bg-white/[0.05] ring-white/15"}`}
            style={{ color: pathColor(i) }}>
            <span className="h-[3px] w-4 rounded-full" style={{ background: pathColor(i) }} />{s.label}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2 px-4 sm:px-0">
        <p className="text-[14px] font-semibold text-slate-300">{focus ? "같은 경로를 다시 누르면 강조가 풀려요" : "경로 단추나 경로 동그라미를 누르면 그 경로만 강조해요"}</p>
        <div className="flex shrink-0 gap-1.5">
          {[["+", () => setView((v) => zoomAt({ x: 0, y: 0 }, v.k * 1.4, v)), "확대"], ["−", () => setView((v) => zoomAt({ x: 0, y: 0 }, v.k / 1.4, v)), "축소"],
            ["⟲", () => setView({ k: 1, x: 0, y: 0 }), "원래 크기"]].map(([label, fn, name]) => (
            <button key={name as string} type="button" aria-label={name as string} onClick={fn as () => void}
              className="size-9 rounded-full border border-white/20 bg-white/10 text-base font-bold text-white backdrop-blur hover:bg-white/20">{label as string}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
