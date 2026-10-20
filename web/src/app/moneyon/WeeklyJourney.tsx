import type { ReactNode } from "react";
import type { State } from "./types";
import Izani from "./Izani";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
// 이자 숫자 옆에 늘 함께 보이는 안내. 이율 자체는 바꾸지 않고, 실제 금리로 오해하지 않게 한다.
export const PRACTICE="배우기 위한 연습용 이자예요 (실제 은행보다 훨씬 높아요)";
export function PracticeNote(){return <small className="mk-practice-note">{PRACTICE}</small>;}
// "2026-10-12"~"2026-10-19"(다음 월요일 0시 직전까지) → "10월 12일 ~ 10월 18일"
const md=(day:string)=>`${Number(day.slice(5,7))}월 ${Number(day.slice(8,10))}일`;
export function weekRange(start:string,end:string){const last=new Date(end+"T00:00:00Z");last.setUTCDate(last.getUTCDate()-1);return `${md(start)} ~ ${md(last.toISOString().slice(0,10))}`;}
export const monthDay=md;
export default function WeeklyJourney({state,actions}:{state:State;actions:ReactNode}) {
  const week=state.education,rewards=state.rewards!;
  const current=rewards.items.find(i=>i.status==="estimated"&&i.reward_type==="allowance_bonus");
  const history=rewards.items.filter(i=>i.reward_type==="allowance_bonus"&&i.status!=="estimated");
  const interest=current?.amount??0,base=current?.base??0,rate=(current?.rate_bps??1000)/100;
  const automatic=state.payment_rule?.current==="automatic";
  return <div className="mk-weekly-journey">
    <section className="mk-wallet-hero" aria-label="이번 주 용돈 이야기"><div className="mk-week-label"><span>이번 주 내 용돈</span><small>{week&&weekRange(week.start,week.end)}</small></div><h2>이번 주 남은 용돈</h2><strong key={state.wallet} data-testid="child-balance" className="mk-wallet-number mk-money-change">{won(state.wallet)}</strong><p>엄마 통장에서 온 용돈, 내가 관리해요.</p><span className="mk-wallet-symbol" aria-hidden="true">₩</span></section>
    <section className="mk-interest-connected" aria-label="남은 용돈의 예상 이자"><div className="mk-interest-top"><div><h2>다음 주 예상 이자 <span>아직 안 받았어요</span></h2><strong className="mk-interest-number mk-money-change" key={interest} data-testid="allowance-bonus">+{won(interest)}</strong></div><span className="mk-interest-coin" aria-hidden="true">₩</span></div><p className="mk-interest-formula" data-testid="interest-formula">{won(base)} × {rate}% = {won(interest)}</p><PracticeNote/><p className="mk-interest-promise">남은 용돈의 {rate}%가 다음 주 이자로 돌아와!</p>{base!==state.wallet&&<p className="mk-principal-note">이번 주에 받은 이자에는 이자가 다시 붙지 않아요. 계산하는 돈 {won(base)}.</p>}</section>
    {actions}
    <section className="mk-week-summary" aria-label="용돈 사용 현황"><h2>이번 주, 이렇게 썼어요</h2><dl><div><dt>받은 용돈</dt><dd data-testid="weekly-received">{won(week?.received??0)}</dd></div><div><dt>사용한 돈</dt><dd data-testid="weekly-spent">{won(week?.spent??0)}</dd></div><div><dt>저금한 돈</dt><dd>{won(week?.saved??0)}</dd></div></dl><details><summary>남은 용돈은 어떻게 계산할까?</summary><dl className="mk-reconciliation"><div><dt>지난주에서 가져온 돈</dt><dd>{won(week?.opening??0)}</dd></div><div><dt>이번 주 받은 용돈</dt><dd>+{won(week?.received??0)}</dd></div><div><dt>이번 주 받은 이자</dt><dd>+{won(week?.interest_received??0)}</dd></div><div><dt>저축통장에서 꺼낸 돈</dt><dd>+{won(week?.withdrawn??0)}</dd></div><div><dt>이번 주 사용한 돈</dt><dd>−{won(week?.spent??0)}</dd></div><div><dt>이번 주 저금한 돈</dt><dd>−{won(week?.saved??0)}</dd></div>{!!week?.other_in&&<div><dt>기타 입금</dt><dd>+{won(week.other_in)}</dd></div>}{!!week?.other_out&&<div><dt>기타 출금·이전 용돈 회수</dt><dd>−{won(week.other_out)}</dd></div>}<div><dt>지금 남은 용돈</dt><dd>{won(week?.remaining??state.wallet)}</dd></div></dl><p>이번 주 내 용돈통장 기록이에요. 저축통장으로 옮긴 돈은 쓴 돈이 아니고, 용돈 이자에서는 빠져요.</p></details></section>
    <section className="mk-mini-path" aria-label="다음 주 이자를 받는 흐름"><span>남은 용돈 확인</span><b aria-hidden="true">→</b><span>{automatic?"월요일에 자동으로":"엄마가 확인하면"}</span><b aria-hidden="true">→</b><span>내 용돈통장에 들어와요</span><small>월요일이 되면 지난주 남은 용돈으로 이자가 정해지고, 정해진 금액은 바뀌지 않아요.</small></section>
    {history.length>0&&<details className="mk-week-history"><summary>지난주 용돈 이자 · {history.some(i=>i.status==='awaiting_approval')?'이자를 기다리는 중':'들어왔어요'}</summary>{history.map(i=><article key={i.cycle_id}><small>{weekRange(i.start,i.end)}</small><p>남은 용돈 {won(i.base)}</p><strong>{i.status==="paid"?"받은 이자":"정해진 이자"} {won(i.status==="paid"?i.paid_amount:i.amount)}</strong><p>{i.status==="paid"?"엄마 통장에서 내 용돈통장으로 이자가 들어왔어!":i.payment_mode==="automatic"?"엄마 통장 잔액을 기다려요.":"엄마가 확인하면 내 용돈통장으로 들어와요."}</p></article>)}</details>}
    <section className="mk-piggy-secondary" aria-label="내 저축통장"><div><h2>차곡차곡, 내 저축통장</h2><strong data-testid="child-vault" key={state.vault} className="mk-money-change">{won(state.vault)}</strong></div><div><p>예상 저축 이자</p><strong data-testid="savings-interest">{won(rewards.estimates.savings_interest??0)}</strong><small>용돈 이자와 따로 계산해요</small></div></section>
    <details className="mk-finance-tip"><summary><Izani mood="interest"/>이자니가 알려주는 이자의 비밀</summary><p>이자는 돈을 남겨두었을 때 약속한 규칙에 따라 더 받는 돈이야. 예상 합계 <span data-testid="child-reward">{won(rewards.expected_total)}</span>는 아직 내 돈이 아니야.</p><p>용돈을 남기면 용돈 이자를 받아요. 저축통장에 모아둔 돈에는 저축 이자가 붙어요.</p><p>엄마 통장은 체험용 가상 통장이에요. {rate}%는 배우기 위한 연습용 이자로, 실제 은행보다 훨씬 높아요.</p></details>
  </div>;
}
