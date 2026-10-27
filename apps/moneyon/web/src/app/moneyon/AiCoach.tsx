"use client";
// 목표 저축 코치: 일주일 저금액만 고른다(자유 문장 입력 없음). 몇 주가 걸리는지는 서버 코드가 계산하고 AI는 설명만 쓴다.
import { useState } from "react";
import AiCard, { type AiStream } from "./AiCard";
import TrialSheet from "./TrialSheet";
import type { State } from "./types";

const won = (n: number) => n.toLocaleString("ko-KR") + "원";
const PRESETS = [1000, 3000, 5000, 10000];

export function CoachButton({ onOpen }: { onOpen: () => void }) {
  return <button type="button" className="mk-button secondary mk-ai-coach-open" onClick={onOpen}><span aria-hidden="true">✨</span>목표까지 코치</button>;
}

export default function AiCoach({ book, stream, onClose }: { book: NonNullable<State["books"]>[number]; stream: AiStream; onClose: () => void }) {
  const [weekly, setWeekly] = useState(3000);
  const [asked, setAsked] = useState<number | null>(null);
  const left = Math.max(0, book.target - book.balance);
  return (
    <TrialSheet title="목표 저축 코치" onClose={onClose}>
      <div className="mk-panel mk-ai-coach">
        <p className="mk-ai-goal"><span aria-hidden="true">{book.icon}</span> 목표 {won(book.target)} · 지금 {won(book.balance)} · 남은 돈 {won(left)}</p>
        <label>일주일에 얼마씩 모을까?
          <span className="mk-experiment-amount">{won(weekly)}</span>
          <input type="range" min={100} max={20000} step={100} value={weekly} onChange={e => setWeekly(Number(e.target.value))} aria-label="일주일 저금액" />
        </label>
        <div className="mk-amount-presets" aria-label="일주일 저금액 고르기">
          {PRESETS.map(n => <button type="button" key={n} aria-pressed={weekly === n} onClick={() => setWeekly(n)}>{won(n)}</button>)}
        </div>
        {asked !== weekly ? (
          <button type="button" className="mk-button full" onClick={() => setAsked(weekly)}><span aria-hidden="true">✨</span>{won(weekly)}씩이면 언제 될까?</button>
        ) : (
          <AiCard key={`${book.id}:${weekly}`} feature="coach" stream={stream} body={{ book_id: book.id, weekly }} title="꿀벌 코치의 계획" button="계획 받기" again="다시 계획해 줘" autoStart />
        )}
        <p className="mk-caption">몇 주가 걸리는지와 이자는 앱이 계산해요. 저축 이자는 매주 2%(100원 미만 버림, 한 주 최대 2,000원)예요.</p>
      </div>
    </TrialSheet>
  );
}
