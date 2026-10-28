"use client";

// 생활 속 종목 찾기 마인드맵. 노드가 최대 13개(중앙 1 · 단계 4 · 회사 8)라 라이브러리 없이 SVG로 그린다
// (react-flow·d3는 수십~백 KB, 휴대폰에서 이 크기에는 과함). 애니메이션은 transform·stroke-dashoffset만 써서 GPU로.
import { useEffect, useMemo, useRef, useState } from "react";
import { pct, type LifeCompany, type LifeMap, type LifeStage, type StageKey } from "@/lib/stock";

export const STAGE_COLOR: Record<StageKey, string> = {
  material: "#2dd4bf", // 원료 청록
  making: "#a78bfa",   // 제조 보라
  logistics: "#facc15", // 물류 노랑
  retail: "#a3e635",   // 유통 연두
};
const UP = "#ff6b81";   // 상승 빨강(어두운 배경용)
const DOWN = "#5aa9ff"; // 하락 파랑
const BUBBLE = { 강: 30, 중: 24, 약: 19 } as const;
const ANGLES: Record<number, number[]> = { 1: [0], 2: [180, 0], 3: [-90, 30, 150], 4: [-135, -45, 45, 135] };
const R_STAGE = 96;
const R_COMPANY = 168;
const SPREAD = 25; // 회사 두 곳이 단계 각도에서 벌어지는 정도(도)
const VIEW = 440;
const K_MIN = 1, K_MAX = 3;

type Pt = { x: number; y: number };
const polar = (deg: number, r: number): Pt => ({ x: Math.cos((deg * Math.PI) / 180) * r, y: Math.sin((deg * Math.PI) / 180) * r });
const short = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

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
    const n = stage.companies.length;
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
  const [open, setOpen] = useState<Set<StageKey>>(new Set());
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const box = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, Pt>());
  const gesture = useRef<{ d: number; k: number; mid: Pt; x: number; y: number; moved: number } | null>(null);
  const dragged = useRef(false);

  // 단어가 바뀌면 중앙에서 단계 가지가 다시 펼쳐진다. 회사는 단계를 눌러야 펼쳐진다(가운데를 누르면 모두).
  useEffect(() => {
    setShown(false);
    setOpen(new Set());
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
    gesture.current = { d, k: view.k, mid, x: view.x, y: view.y, moved: gesture.current?.moved ?? 0 };
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
  const toggle = (k: StageKey) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const allOpen = placed.length > 0 && placed.every((p) => open.has(p.stage.key));
  const toggleAll = () => setOpen(allOpen ? new Set() : new Set(placed.map((p) => p.stage.key)));

  return (
    <div className="relative">
      <div ref={box} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onPointerLeave={onUp}
        className="lifemap-canvas relative mx-auto aspect-square w-full max-w-[560px] select-none overflow-hidden rounded-3xl"
        style={{ touchAction: view.k > 1 ? "none" : "pan-y" }}>
        <svg viewBox={`${-VIEW / 2} ${-VIEW / 2} ${VIEW} ${VIEW}`} className="size-full" role="img"
          aria-label={`${map.word} 마인드맵: ${map.stages.map((s) => `${s.label} ${s.companies.map((c) => c.name).join(", ")}`).join(" / ")}`}>
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
            {/* 가지: 굵고 옅은 선 위에 가는 선을 겹쳐 빛나는 효과(필터 없이) */}
            {placed.map((p, i) => (
              <g key={p.stage.key}>
                {[[10, 0.14], [2.4, 0.95]].map(([w, o]) => (
                  <path key={w} d={curve({ x: 0, y: 0 }, p.pos)} pathLength={1} fill="none" stroke={p.color} strokeWidth={w} strokeOpacity={o} strokeLinecap="round"
                    className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: shown ? 0 : 1, transitionDelay: `${i * 90}ms` }} />
                ))}
                {p.companies.map(({ c, pos }, j) => (
                  [[8, 0.12], [1.8, 0.85]].map(([w, o]) => (
                    <path key={`${c.code}-${w}`} d={curve(p.pos, pos, j === 0 ? -0.15 : 0.15)} pathLength={1} fill="none" stroke={p.color} strokeWidth={w} strokeOpacity={o} strokeLinecap="round"
                      className="lm-branch" style={{ strokeDasharray: 1, strokeDashoffset: open.has(p.stage.key) ? 0 : 1, transitionDelay: open.has(p.stage.key) ? `${j * 80}ms` : "0ms" }} />
                  ))
                ))}
              </g>
            ))}

            {/* 회사 노드: 단계 위치에서 튀어나온다. 버블 크기 = 연관도, 안의 숫자 = 전일 등락률 */}
            {placed.map((p) => p.companies.map(({ c, pos, r }, j) => {
              const on = open.has(p.stage.key);
              const rateColor = !c.rate ? "#cbd5e1" : c.rate > 0 ? UP : DOWN;
              const at = on ? pos : p.pos;
              return (
                <g key={c.code} className="lm-node" role="button" tabIndex={on ? 0 : -1} aria-label={`${c.name}, ${p.stage.label}, 연관도 ${c.relevance}, 전일 ${pct(c.rate)}`}
                  onClick={tap(() => onPick(c, p.stage))} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(c, p.stage); } }}
                  style={{ transform: `translate(${at.x}px, ${at.y}px) scale(${on ? 1 : 0.2})`, opacity: on ? 1 : 0, pointerEvents: on ? "auto" : "none", transitionDelay: on ? `${120 + j * 80}ms` : "0ms", cursor: "pointer" }}>
                  <circle r={r + 7} fill={p.color} opacity={picked === c.code ? 0.35 : 0.12} />
                  <circle r={r} fill="#0b1a36" stroke={p.color} strokeWidth={picked === c.code ? 3 : 1.8} />
                  <text textAnchor="middle" dy="0.35em" fontSize={r >= 24 ? 11.5 : 9} fontWeight={800} fill={rateColor}>
                    {c.rate == null ? "—" : `${c.rate > 0 ? "▲" : c.rate < 0 ? "▼" : ""}${Math.abs(c.rate).toFixed(Math.abs(c.rate) >= 10 ? 0 : 1)}%`}
                  </text>
                  <text y={r + 15} textAnchor="middle" fontSize={12.5} fontWeight={800} fill="#f8fafc" className="lm-label">{short(c.name, 8)}</text>
                </g>
              );
            }))}

            {/* 단계 노드 */}
            {placed.map((p, i) => (
              <g key={p.stage.key} className="lm-node" role="button" tabIndex={0} aria-expanded={open.has(p.stage.key)} aria-label={`${p.stage.label} 단계 ${open.has(p.stage.key) ? "접기" : "펼치기"}`}
                onClick={tap(() => toggle(p.stage.key))} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(p.stage.key); } }}
                style={{ transform: `translate(${shown ? p.pos.x : 0}px, ${shown ? p.pos.y : 0}px) scale(${shown ? 1 : 0.3})`, opacity: shown ? 1 : 0, transitionDelay: `${80 + i * 90}ms`, cursor: "pointer" }}>
                <circle r={31} fill={p.color} opacity={0.16} className={open.has(p.stage.key) ? "" : "lm-pulse"} />
                <circle r={24} fill="#0b1a36" stroke={p.color} strokeWidth={2.4} />
                <text textAnchor="middle" dy="0.35em" fontSize={13} fontWeight={900} fill={p.color}>{p.stage.label}</text>
                <text y={-34} textAnchor="middle" fontSize={10} fontWeight={700} fill="#cbd5e1" opacity={open.has(p.stage.key) ? 0 : 0.9} style={{ transition: "opacity 200ms" }}>
                  {open.has(p.stage.key) ? "" : `${p.stage.companies.length}곳 ▾`}
                </text>
              </g>
            ))}

            {/* 빛나는 중앙 토픽 */}
            <g className="lm-node" role="button" tabIndex={0} aria-label={allOpen ? "모두 접기" : "모두 펼치기"} onClick={tap(toggleAll)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleAll(); } }} style={{ cursor: "pointer" }}>
              <circle r={78} fill="url(#lm-halo)" className="lm-glow" />
              <circle r={44} fill="url(#lm-core)" />
              <text textAnchor="middle" dy="0.36em" fontSize={map.word.length > 4 ? (map.word.length > 6 ? 12 : 14) : 18} fontWeight={900} fill="#0b1a36">{short(map.word, 8)}</text>
            </g>
          </g>
        </svg>
      </div>
      <div className="mt-1 flex justify-end gap-1.5">
        {[["+", () => setView((v) => zoomAt({ x: 0, y: 0 }, v.k * 1.4, v)), "확대"], ["−", () => setView((v) => zoomAt({ x: 0, y: 0 }, v.k / 1.4, v)), "축소"],
          ["⟲", () => setView({ k: 1, x: 0, y: 0 }), "원래 크기"]].map(([label, fn, name]) => (
          <button key={name as string} type="button" aria-label={name as string} onClick={fn as () => void}
            className="size-7 rounded-full border border-white/15 bg-white/10 text-sm font-bold text-white backdrop-blur hover:bg-white/20">{label as string}</button>
        ))}
      </div>
    </div>
  );
}
