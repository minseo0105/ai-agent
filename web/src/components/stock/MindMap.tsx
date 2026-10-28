"use client";

// 생활 속 종목 찾기 마인드맵. 노드가 최대 13개(중앙 1 · 단계 4 · 회사 8)라 라이브러리 없이 SVG로 그린다
// (react-flow·d3는 수십~백 KB, 휴대폰에서 이 크기에는 과함). 애니메이션은 transform·opacity·stroke-dashoffset만 써서 GPU로.
// 처음부터 모든 단계·회사가 펼쳐진 채로 시작한다(가지가 자라나는 연출만). 단계를 누르면 그 가지를 강조한다.
// 글자: 휴대폰(지도 폭 약 358px, 배율 약 0.85)에서 회사 이름 13px 이상이 되도록 SVG 단위 16.
// 버블 안에 이름(1~2줄)과 등락률을 함께 넣는다(버블 밖 라벨은 4단계일 때 옆 노드와 겹침).
import { useEffect, useMemo, useRef, useState } from "react";
import { type LifeCompany, type LifeMap, type LifeStage, type StageKey } from "@/lib/stock";

export const STAGE_COLOR: Record<StageKey, string> = {
  material: "#2dd4bf", // 원료 청록
  making: "#a78bfa",   // 제조 보라
  logistics: "#facc15", // 물류 노랑
  retail: "#a3e635",   // 유통 연두
};
export const UP = "#ff6b81";   // 상승 빨강(어두운 배경용)
export const DOWN = "#5aa9ff"; // 하락 파랑
const BUBBLE = { 강: 40, 중: 37, 약: 34 } as const;
const ANGLES: Record<number, number[]> = { 1: [0], 2: [180, 0], 3: [-90, 30, 150], 4: [-135, -45, 45, 135] };
const R_STAGE = 78;
const R_COMPANY = 150;
const SPREAD = 24; // 회사 두 곳이 단계 각도에서 벌어지는 정도(도)
const VIEW = 420;
const K_MIN = 1, K_MAX = 3;

type Pt = { x: number; y: number };
const polar = (deg: number, r: number): Pt => ({ x: Math.cos((deg * Math.PI) / 180) * r, y: Math.sin((deg * Math.PI) / 180) * r });
export const rateText = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(Math.abs(v) >= 10 ? 0 : 1)}%`);
const rateColor = (v?: number | null) => (!v ? "#e2e8f0" : v > 0 ? UP : DOWN);

/** 버블 안 이름: 4자 이하는 한 줄, 그보다 길면 두 줄(최대 4+4자, 넘치면 …). */
function nameLines(name: string): string[] {
  if (name.length <= 4) return [name];
  const s = name.length > 8 ? `${name.slice(0, 7)}…` : name;
  const half = Math.ceil(s.length / 2);
  return [s.slice(0, half), s.slice(half)];
}

/** 부모→자식 곡선(살짝 휜 2차 베지어). pathLength=1로 두고 dashoffset으로 그려지는 효과를 낸다. */
function curve(a: Pt, b: Pt, bend = 0.18): string {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const dx = b.x - a.x, dy = b.y - a.y;
  return `M${a.x.toFixed(1)},${a.y.toFixed(1)} Q${(mx - dy * bend).toFixed(1)},${(my + dx * bend).toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)}`;
}

type Placed = { stage: LifeStage; color: string; pos: Pt; companies: { c: LifeCompany; pos: Pt; r: number }[] };

function layout(stages: LifeStage[]): Placed[] {
  const angles = ANGLES[Math.min(stages.length, 4)] || [];
  return stages.slice(0, 4).map((stage, i) => {
    const a = angles[i];
    const n = Math.min(stage.companies.length, 2);
    return {
      stage, color: STAGE_COLOR[stage.key], pos: polar(a, R_STAGE),
      companies: stage.companies.slice(0, 2).map((c, j) => ({
        c, r: BUBBLE[c.relevance] ?? BUBBLE.약, pos: polar(n === 1 ? a : a + (j === 0 ? -SPREAD : SPREAD), R_COMPANY),
      })),
    };
  });
}

export default function MindMap({ map, onPick, picked }: { map: LifeMap; onPick: (c: LifeCompany, s: LifeStage) => void; picked?: string }) {
  const placed = useMemo(() => layout(map.stages), [map]);
  const [shown, setShown] = useState(false);
  const [focus, setFocus] = useState<StageKey | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const box = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, Pt>());
  const gesture = useRef<{ d: number; k: number; mid: Pt; x: number; y: number } | null>(null);
  const dragged = useRef(false);

  // 단어가 바뀌면 중앙에서 단계 → 회사 순서로 가지가 자라난다(모두 펼친 채로 끝남).
  useEffect(() => {
    setShown(false);
    setFocus(null);
    setView({ k: 1, x: 0, y: 0 });
    const t = setTimeout(() => setShown(true), 40);
    return () => clearTimeout(t);
  }, [map]);

  // 화면 px → SVG 좌표(중앙 0,0)
  const toSvg = (p: Pt): Pt => {
    const el = box.current;
    if (!el) return p;
    const r = el.getBoundingClientRect();
    const s = VIEW / Math.min(r.width, r.height);
    return { x: (p.x - r.left - r.width / 2) * s, y: (p.y - r.top - r.height / 2) * s };
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
      const lim = (VIEW / 2) * (view.k - 1);
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
  const toggleFocus = (k: StageKey) => setFocus((f) => (f === k ? null : k));
  const dim = (k: StageKey) => (focus && focus !== k ? 0.22 : 1);
  const centerSize = map.word.length > 6 ? 15 : map.word.length > 4 ? 18 : 22;

  return (
    <div>
      <div ref={box} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onPointerLeave={onUp}
        className="lifemap-canvas relative mx-auto aspect-square w-full max-w-[600px] select-none overflow-hidden rounded-3xl"
        style={{ touchAction: view.k > 1 ? "none" : "pan-y" }}>
        <svg viewBox={`${-VIEW / 2} ${-VIEW / 2} ${VIEW} ${VIEW}`} className="size-full" role="img"
          aria-label={`${map.word} 마인드맵: ${map.stages.map((s) => `${s.label} ${s.companies.map((c) => `${c.name} ${rateText(c.rate)}`).join(", ")}`).join(" / ")}`}>
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
            {/* 가지: 굵고 옅은 선 위에 가는 선을 겹쳐 빛나는 효과(필터 없이). 강조한 단계는 더 굵게 */}
            {placed.map((p, i) => (
              <g key={p.stage.key} style={{ opacity: dim(p.stage.key), transition: "opacity 250ms" }}>
                {[[focus === p.stage.key ? 16 : 10, 0.16], [focus === p.stage.key ? 4 : 2.6, 0.95]].map(([w, o], n) => (
                  <path key={n} d={curve({ x: 0, y: 0 }, p.pos)} pathLength={1} fill="none" stroke={p.color} strokeWidth={w} strokeOpacity={o} strokeLinecap="round"
                    className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${i * 90}ms` }} />
                ))}
                {p.companies.map(({ c, pos }, j) => (
                  [[focus === p.stage.key ? 14 : 8, 0.14], [focus === p.stage.key ? 3.4 : 2, 0.85]].map(([w, o], n) => (
                    <path key={`${c.code}-${n}`} d={curve(p.pos, pos, j === 0 ? -0.15 : 0.15)} pathLength={1} fill="none" stroke={p.color} strokeWidth={w} strokeOpacity={o} strokeLinecap="round"
                      className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${380 + i * 90 + j * 70}ms` }} />
                  ))
                ))}
              </g>
            ))}

            {/* 회사 노드: 버블 안에 이름과 등락률. 실제로 크게 움직인 회사는 빛나는 테두리 + '실제 ±n%' */}
            {placed.map((p, i) => p.companies.map(({ c, pos, r }, j) => {
              const lines = nameLines(c.name);
              const color = rateColor(c.rate);
              const at = shown ? pos : p.pos;
              const nameTop = lines.length === 2 ? -15 : -8;
              return (
                <g key={c.code} className="lm-node" role="button" tabIndex={0}
                  aria-label={`${c.name}, ${p.stage.label}, 연관도 ${c.relevance}, ${c.moved ? "실제로 크게 움직임, " : ""}등락률 ${rateText(c.rate)}`}
                  onClick={tap(() => onPick(c, p.stage))} onKeyDown={press(() => onPick(c, p.stage))}
                  style={{ transform: `translate(${at.x}px, ${at.y}px) scale(${shown ? 1 : 0.2})`, opacity: shown ? dim(p.stage.key) : 0,
                    transitionDelay: shown ? `${480 + i * 90 + j * 70}ms` : "0ms", cursor: "pointer" }}>
                  {c.moved && <circle r={r + 11} fill="none" stroke={color} strokeWidth={3} className="lm-pulse" />}
                  <circle r={r + 6} fill={p.color} opacity={picked === c.code ? 0.4 : 0.14} />
                  <circle r={r} fill="#0b1a36" stroke={c.moved ? color : p.color} strokeWidth={c.moved || picked === c.code ? 3.2 : 2} />
                  {lines.map((t, n) => (
                    <text key={n} textAnchor="middle" y={nameTop + n * 17} dy="0.36em" fontSize={16} fontWeight={800} fill="#f8fafc">{t}</text>
                  ))}
                  <text textAnchor="middle" y={nameTop + lines.length * 17 + 2} dy="0.36em" fontSize={15} fontWeight={900} fill={color}>{rateText(c.rate)}</text>
                  {c.moved && (
                    <g transform={`translate(0 ${-r - 4})`}>
                      <rect x={-22} y={-11} width={44} height={22} rx={11} fill={color} />
                      <text textAnchor="middle" dy="0.36em" fontSize={14} fontWeight={900} fill="#071226">실제</text>
                    </g>
                  )}
                </g>
              );
            }))}

            {/* 단계 노드: 누르면 그 가지 강조(다시 누르면 해제) */}
            {placed.map((p, i) => (
              <g key={p.stage.key} className="lm-node" role="button" tabIndex={0} aria-pressed={focus === p.stage.key}
                aria-label={`${p.stage.label} 단계 ${focus === p.stage.key ? "강조 해제" : "강조"}`}
                onClick={tap(() => toggleFocus(p.stage.key))} onKeyDown={press(() => toggleFocus(p.stage.key))}
                style={{ transform: `translate(${shown ? p.pos.x : 0}px, ${shown ? p.pos.y : 0}px) scale(${shown ? (focus === p.stage.key ? 1.12 : 1) : 0.3})`,
                  opacity: shown ? dim(p.stage.key) : 0, transitionDelay: shown ? `${80 + i * 90}ms` : "0ms", cursor: "pointer" }}>
                <circle r={32} fill={p.color} opacity={focus === p.stage.key ? 0.35 : 0.16} />
                <circle r={26} fill="#0b1a36" stroke={p.color} strokeWidth={2.6} />
                <text textAnchor="middle" dy="0.36em" fontSize={15} fontWeight={900} fill={p.color}>{p.stage.label}</text>
              </g>
            ))}

            {/* 빛나는 중앙 토픽. 누르면 강조 해제 */}
            <g className="lm-node" role="button" tabIndex={0} aria-label={`${map.word}, 강조 해제`} onClick={tap(() => setFocus(null))}
              onKeyDown={press(() => setFocus(null))} style={{ cursor: "pointer" }}>
              <circle r={84} fill="url(#lm-halo)" className="lm-glow" pointerEvents="none" />
              <circle r={48} fill="url(#lm-core)" />
              <text textAnchor="middle" dy="0.36em" fontSize={centerSize} fontWeight={900} fill="#0b1a36">{map.word.length > 8 ? `${map.word.slice(0, 7)}…` : map.word}</text>
            </g>
          </g>
        </svg>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="text-[14px] font-semibold text-slate-200">{focus ? "같은 단계를 다시 누르면 강조가 풀려요" : "단계를 누르면 그 가지를 강조해요"}</p>
        <div className="flex gap-1.5">
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
