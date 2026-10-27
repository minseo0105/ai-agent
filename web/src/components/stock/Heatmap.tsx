"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { pct, type Stock } from "@/lib/stock";

type Rect = { x: number; y: number; w: number; h: number; item: Stock };

/** squarified treemap: 넓이 = 시가총액 비율. 좌표는 0~100(%)로 돌려준다. */
function squarify(items: Stock[], W = 100, H = 100): Rect[] {
  const total = items.reduce((s, i) => s + (i.cap || 0), 0);
  if (!total) return [];
  const nodes = items.map((item) => ({ item, a: ((item.cap || 0) / total) * W * H }));
  const out: Rect[] = [];
  let x = 0, y = 0, w = W, h = H;
  let row: typeof nodes = [];
  const worst = (r: typeof nodes, side: number) => {
    const s = r.reduce((t, n) => t + n.a, 0);
    const max = Math.max(...r.map((n) => n.a)), min = Math.min(...r.map((n) => n.a));
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };
  const layout = (r: typeof nodes) => {
    const s = r.reduce((t, n) => t + n.a, 0);
    if (w >= h) {
      const cw = s / h;
      let cy = y;
      for (const n of r) { const ch = n.a / cw; out.push({ x, y: cy, w: cw, h: ch, item: n.item }); cy += ch; }
      x += cw; w -= cw;
    } else {
      const ch = s / w;
      let cx = x;
      for (const n of r) { const cw = n.a / ch; out.push({ x: cx, y, w: cw, h: ch, item: n.item }); cx += cw; }
      y += ch; h -= ch;
    }
  };
  for (const n of nodes) {
    const side = Math.min(w, h);
    if (!row.length || worst([...row, n], side) <= worst(row, side)) row.push(n);
    else { layout(row); row = [n]; }
  }
  if (row.length) layout(row);
  return out;
}

/** 등락률 → 배경색. 상승 빨강·하락 파랑, ±5%에서 가장 진하다. */
function fill(rate: number | null): string {
  if (!rate) return "rgb(100 116 139 / 0.55)";
  const t = Math.min(Math.abs(rate) / 5, 1);
  const alpha = (0.28 + t * 0.67).toFixed(2);
  return rate > 0 ? `rgb(225 29 72 / ${alpha})` : `rgb(37 99 235 / ${alpha})`;
}

export default function Heatmap({ items, selected, onSelect }: { items: Stock[]; selected?: string; onSelect: (s: Stock) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(16 / 9);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e.contentRect.height && setRatio(e.contentRect.width / e.contentRect.height));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // 실제 가로세로 비율로 계산한 뒤 %로 바꾼다. 그래야 칸이 정사각형에 가깝게 나온다.
  const rects = useMemo(
    () => squarify(items.filter((i) => i.cap), 100 * ratio, 100).map((r) => ({ ...r, x: r.x / ratio, w: r.w / ratio })),
    [items, ratio],
  );
  return (
    <div ref={ref} className="relative aspect-[4/5] w-full overflow-hidden rounded-2xl bg-surface-muted sm:aspect-[16/9]">
      {rects.map(({ x, y, w, h, item }) => {
        const area = w * h; // 전체 = 10,000
        // 글자가 잘려 "▼-…"로 보이지 않을 만큼 넓은 칸에만 숫자를 쓴다. 작은 칸은 색·툴팁·클릭으로 본다.
        const big = area > 500 && w > 9, mid = area > 110 && w > 6, small = area > 60 && w > 6 && h > 5;
        return (
          <button
            key={item.code}
            type="button"
            onClick={() => onSelect(item)}
            title={`${item.name} ${pct(item.rate)} — 눌러서 '왜 움직였나' 보기`}
            aria-label={`${item.name} ${pct(item.rate)}, 왜 움직였나 보기`}
            aria-pressed={selected === item.code}
            className={`absolute flex flex-col items-center justify-center overflow-hidden border border-white/70 p-0.5 text-center text-white transition hover:z-10 hover:brightness-110 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-white dark:border-black/40 ${selected === item.code ? "z-10 ring-2 ring-inset ring-yellow-300" : ""}`}
            style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`, background: fill(item.rate) }}
          >
            {mid && <span className={`max-w-full truncate font-extrabold leading-tight ${big ? "text-sm sm:text-base" : "text-[10px] sm:text-xs"}`}>{item.name}</span>}
            {small && (
              <span className={`max-w-full truncate font-bold tabular-nums leading-tight ${big ? "text-xs sm:text-sm" : "text-[9px] sm:text-[11px]"}`}>
                {item.rate ? (item.rate > 0 ? "▲" : "▼") : ""}{pct(item.rate)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
