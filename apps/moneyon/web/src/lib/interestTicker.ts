// 이자 카운터의 표시 계산(순수 함수).
//
// ※ 연출용 표시다. 실제로 받는 이자는 월요일 정산 때 서버가 정한 금액(100원 미만 버림)뿐이고,
//   여기서 만든 숫자는 "이자가 쌓이는 느낌"을 보여 주려는 화면 효과라서 어디에도 저장·전송하지 않는다.
// 이자 금액 자체는 서버의 reward()(services/moneyon.py)와 같은 식이다: 기준 금액 × 이율(bps) ÷ 10000,
// 상한(cap)이 있으면 그 이하. 다만 서버는 unit(100원)으로 버리고 여기서는 버리지 않은 값을 쓴다.
import type { RewardItem } from "../app/moneyon/types";

// 몇 초마다 소수점 둘째 자리(0.01원)가 오르는지. 연출용.
export const TICK_MS = 1400;
export const TICK_WON = 0.01;

// 정산 전 예상 이자 한 건의 "버리기 전" 금액.
export function rawInterest(item: Pick<RewardItem, "base" | "rate_bps" | "cap">): number {
  const raw = (Math.max(0, item.base) * item.rate_bps) / 10000;
  return item.cap === null ? raw : Math.min(raw, item.cap);
}

// 이번 주 예상 이자(용돈 이자 + 저축 이자)의 버리기 전 합계.
export function estimatedRaw(items: RewardItem[] | undefined): number {
  return (items ?? []).filter(i => i.status === "estimated").reduce((n, i) => n + rawInterest(i), 0);
}

const MS_DAY = 86400000;
const dayNumber = (day: string) => Date.parse(day + "T00:00:00Z") / MS_DAY;

// 체험 날짜(day) 기준 주간 진행률 0~1. 하루 안에서는 실제 시계가 지나는 만큼만 조금씩 오른다(연출).
export function weekProgress(day: string, start: string, end: string, clock: Date): number {
  const span = dayNumber(end) - dayNumber(start);
  if (!(span > 0)) return 0;
  const intraday = (clock.getHours() * 3600 + clock.getMinutes() * 60 + clock.getSeconds()) / 86400;
  return Math.min(1, Math.max(0, (dayNumber(day) - dayNumber(start) + intraday) / span));
}

// 화면에 보이는 값: 진행률만큼 쌓인 금액 + 틱마다 0.01원. 예상 이자(target)를 넘지 않는다.
export function accrued(target: number, progress: number, ticks: number): number {
  return Math.min(target, Math.max(0, target) * progress + Math.max(0, ticks) * TICK_WON);
}

// 정산일(end, 다음 월요일)까지 남은 날 수. 오늘이 정산일이거나 지났으면 0.
export function daysLeft(day: string, end: string): number {
  return Math.max(0, Math.round(dayNumber(end) - dayNumber(day)));
}

// 기록 전후 예상 이자 변화량(원, 반올림). 0이면 보여 줄 변화가 없다.
export function deltaWon(before: number, after: number): number {
  return Math.round(after - before);
}

export const formatWon2 = (value: number) => value.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "원";
