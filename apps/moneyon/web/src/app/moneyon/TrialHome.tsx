"use client";
import { useState } from "react";
import type { ReactNode } from "react";
import type { CoachMood } from "@/lib/moneyonCoach";
import type { BankTransaction } from "./Banking";
import type { RewardItem, State } from "./types";
import Izani from "./Izani";
import { CATEGORY_ICONS } from "./TrialActions";
import { PracticeNote, weekRange } from "./WeeklyJourney";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
// 100원 미만을 버리는 규칙에서 이자가 붙기 시작하는 금액(10% → 1,000원, 2% → 5,000원).
export const FROM={allowance_bonus:"용돈 1,000원부터 이자가 붙어요",savings_interest:"저축 5,000원부터 이자가 붙어요"};

// 홈 기록 한 줄: 아이 말로 된 이름과 아이콘, 받은 돈(+)과 쓴 돈(−)은 색으로 구분한다.
export function recordLine(t:BankTransaction){
  switch(t.transaction_type){
    case "ALLOWANCE_TRANSFER":return {icon:"👩",label:"엄마가 보내줬어요"};
    case "PARENT_REWARD_INTEREST":case "ALLOWANCE_SAVING_BONUS":return {icon:"✨",label:"엄마가 이자를 보내줬어요"};
    case "SAVINGS_DEPOSIT":return {icon:"🐷",label:"저축통장에 저금했어요"};
    case "SAVINGS_WITHDRAWAL":return {icon:"🐷",label:"저축통장에서 꺼냈어요"};
    case "ALLOWANCE_RETURN":return {icon:"↩️",label:"남은 용돈을 엄마 통장에 돌려줬어요"};
    case "PURCHASE_REVERSAL":return {icon:"↩️",label:"쓴 돈 기록을 취소했어요"};
    default:return {icon:CATEGORY_ICONS[t.category||""]??"🧾",label:t.merchant||t.category||t.note||"쓴 돈"};
  }
}

// 계산식: "22,500원 × 10% = 2,250원 → 2,200원". 100원 미만을 버렸을 때만 화살표가 붙는다.
export function formula(item:RewardItem){
  const raw=item.base*item.rate_bps/10000|0;
  return `${won(item.base)} × ${item.rate_bps/100}% = ${won(raw)}${raw!==item.amount?` → ${won(item.amount)}`:""}`;
}

// 체험 홈: 용돈기록장이 주인공. 이번 주 남은 용돈 + 쓴 돈 기록하기, 저축·예상 이자 카드, 이번 주 기록, 저금하기.
export default function TrialHome({state,walletId,say,mood,pending,records,onSpend,onDeposit,onSavings,onAll,onSettle}:{state:State;walletId:string;say:string;mood:CoachMood;pending:number|null;records:ReactNode;onSpend:()=>void;onDeposit:()=>void;onSavings:()=>void;onAll:()=>void;onSettle:()=>void}) {
  const [open,setOpen]=useState(false);
  const week=state.education;
  const estimate=(kind:RewardItem["reward_type"])=>state.rewards?.items.find(i=>i.status==="estimated"&&i.reward_type===kind);
  const allowance=estimate("allowance_bonus"),saving=estimate("savings_interest");
  const total=(allowance?.amount??0)+(saving?.amount??0);
  const rows=state.banking.transactions.filter(t=>t.account_id===walletId&&(!week||(week.start<=t.occurred_at.slice(0,10)&&t.occurred_at.slice(0,10)<week.end))).slice(0,5);
  return <div className="mk-trial-home">
    <div className="mk-say" role="status"><Izani mood={mood}/><p>{say}</p></div>
    <section className="mk-week-card" aria-label="이번 주 남은 용돈">
      <div className="mk-week-card-top"><span>이번 주 남은 용돈</span>{week&&<small>{weekRange(week.start,week.end)}</small>}</div>
      <strong key={state.wallet} className="mk-week-number mk-money-change" data-testid="child-balance">{won(state.wallet)}</strong>
      <button className="mk-spend-button" onClick={onSpend}><span aria-hidden="true">✏️</span>쓴 돈 기록하기</button>
    </section>
    <div className="mk-mini-cards">
      <button onClick={onSavings}><span>🐷 저축통장</span><strong data-testid="child-vault">{won(state.vault)}</strong></button>
      <button aria-expanded={open} aria-controls="mk-interest-detail" onClick={()=>setOpen(!open)}><span>✨ 다음 주 예상 이자</span><strong data-testid="trial-interest">+{won(total)}</strong>{total===0&&<small>{FROM.allowance_bonus}</small>}</button>
    </div>
    {open&&<div className="mk-interest-detail" id="mk-interest-detail">
      {[allowance,saving].map(item=>item&&<p key={item.reward_type}><b>{item.reward_type==="allowance_bonus"?"용돈 이자":"저축 이자"}</b>{item.amount?<span data-testid={item.reward_type==="allowance_bonus"?"interest-formula":undefined}>{formula(item)}</span>:<span>{FROM[item.reward_type]}</span>}</p>)}
      <small>100원 미만은 버려요. 다음 주 월요일에 정산하고, 내가 &lsquo;이자 받기&rsquo;를 눌러야 들어와요.</small>
      <PracticeNote/>
      {records}
    </div>}
    {pending!==null&&<section className="mk-settle-banner" aria-label="정산 알림"><span><span aria-hidden="true">📬</span> 지난주 정산이 왔어요</span><button onClick={onSettle}>{pending?`이자 ${won(pending)} 받기`:"정산 보기"}</button></section>}
    <section className="mk-week-records" aria-label="이번 주 기록">
      <div className="mk-section-title"><h2>이번 주 기록</h2><button className="mk-text-button" onClick={onAll}>모두 보기</button></div>
      {rows.length?<ul data-testid="recent-transactions">{rows.map(t=>{const line=recordLine(t);return <li key={`${t.transfer_id}:${t.account_id}`}><span className="mk-record-icon" aria-hidden="true">{line.icon}</span><span className="mk-record-name">{line.label}</span><span className={`mk-record-amount ${t.amount>0?"in":"out"}`}>{t.amount>0?"+":"−"}{won(Math.abs(t.amount))}</span></li>;})}</ul>:<p className="mk-empty">이번 주 기록이 아직 없어요. 쓴 돈을 기록해 봐요.</p>}
    </section>
    <button className="mk-deposit-button" onClick={onDeposit}><span aria-hidden="true">🐷</span>저금하기</button>
  </div>;
}
