"use client";
// 이번 주 쌓이는 이자 카운터 + 기록 직후 이자 변화량.
//
// ※ 연출용 표시다. 숫자는 서버가 정한 "다음 주 예상 이자"를 주간 진행률에 맞춰 보여 주고(lib/interestTicker.ts),
//   몇 초마다 0.01원씩 올려 쌓이는 느낌을 낸다. 실제로 들어오는 이자는 월요일 정산 금액(100원 미만 버림)뿐이다.
import { useEffect, useRef, useState } from "react";
import { TICK_MS, accrued, daysLeft, deltaWon, estimatedRaw, formatWon2, weekProgress } from "@/lib/interestTicker";
import type { State } from "./types";
import "./interest.css";

const INTRO_MS = 1500;
const DELTA_SHOW_MS = 4000;
const DELTA_ROLL_MS = 700;
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const reducedMotion = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// 0에서 to까지 ms 동안 올라가는 값(0~1 진행률). 움직임 줄이기 설정이면 바로 1.
function useRoll(ms: number, restartKey: unknown) {
  const [t, setT] = useState(() => (reducedMotion() ? 1 : 0));
  useEffect(() => {
    if (reducedMotion()) { setT(1); return; }
    let frame = 0;
    const start = performance.now();
    setT(0);
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setT(ease(p));
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [ms, restartKey]);
  return t;
}

// "다음 주 이자 +100원 ⬆️" / "−100원 ⬇️". 같은 주 안에서 예상 이자가 바뀔 때만 잠깐 나온다.
function InterestDelta({ state }: { state: State }) {
  const raw = estimatedRaw(state.rewards?.items);
  const week = state.education?.start ?? "";
  const previous = useRef<{ raw: number; week: string } | null>(null);
  const [shown, setShown] = useState<{ amount: number; id: number } | null>(null);
  useEffect(() => {
    const before = previous.current;
    previous.current = { raw, week };
    if (!before || before.week !== week) return;
    const amount = deltaWon(before.raw, raw);
    if (!amount) return;
    const id = Date.now();
    setShown({ amount, id });
    const timer = setTimeout(() => setShown(s => (s?.id === id ? null : s)), DELTA_SHOW_MS);
    return () => clearTimeout(timer);
  }, [raw, week]);
  const roll = useRoll(DELTA_ROLL_MS, shown?.id);
  if (!shown) return null;
  const up = shown.amount > 0;
  const value = Math.round(Math.abs(shown.amount) * roll);
  return <p key={shown.id} className={`mk-interest-delta ${up ? "up" : "down"}`} role="status" data-testid="interest-delta">
    다음 주 이자 <b>{up ? "+" : "−"}{value.toLocaleString("ko-KR")}원</b> <span aria-hidden="true">{up ? "⬆️" : "⬇️"}</span>
  </p>;
}

export default function InterestTicker({ state, day }: { state: State; day?: string }) {
  const week = state.education;
  const target = estimatedRaw(state.rewards?.items);
  const [ticks, setTicks] = useState(0);
  const [clock, setClock] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => { setTicks(n => Math.min(99, n + 1)); setClock(new Date()); }, TICK_MS);
    return () => clearInterval(timer);
  }, []);
  const intro = useRoll(INTRO_MS, null);
  if (!week || !day) return null;
  const live = accrued(target, weekProgress(day, week.start, week.end, clock), ticks);
  const left = daysLeft(day, week.end);
  return <section className="mk-interest-ticker" aria-label="이번 주 쌓이는 이자">
    <div className="mk-interest-ticker-top">
      <span>✨ 이번 주 쌓이는 이자</span>
      <small className="mk-payday-chip" data-testid="payday-countdown">{left > 0 ? `이자 받는 날까지 D-${left}` : "오늘 정산해요!"}</small>
    </div>
    <strong className="mk-interest-ticker-number" data-testid="interest-ticker" aria-hidden="true">+{formatWon2(live * intro)}</strong>
    <span className="sr-only">{`이번 주 예상 이자는 약 ${Math.floor(target).toLocaleString("ko-KR")}원이에요`}</span>
    <InterestDelta state={state} />
    <small className="mk-interest-ticker-note">쌓이는 모습을 보여 주는 화면이에요. 진짜 이자는 월요일에 정산하고, 100원 미만은 버려요.</small>
  </section>;
}
