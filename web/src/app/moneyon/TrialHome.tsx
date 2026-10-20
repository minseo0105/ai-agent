import type { ReactNode } from "react";
import type { CoachMood } from "@/lib/moneyonCoach";
import type { State } from "./types";
import Izani from "./Izani";
import { PracticeNote } from "./WeeklyJourney";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";

// 체험 홈: 주인공은 "내 돈 모두" 숫자 하나와 이자니 말풍선 한 줄.
// 통장별 금액은 한 줄 요약으로, 이자와 계산식은 요약을 눌러야 펼쳐진다. 금액은 서버가 준 값을 더해 보여주기만 한다.
export default function TrialHome({state,say,mood,actions,week,records,settings}:{state:State;say:string;mood:CoachMood;actions:ReactNode;week:ReactNode;records:ReactNode;settings:ReactNode}) {
  const current=state.rewards?.items.find(i=>i.status==="estimated"&&i.reward_type==="allowance_bonus");
  const interest=current?.amount??0,base=current?.base??0,rate=(current?.rate_bps??1000)/100;
  const automatic=state.payment_rule?.current==="automatic";
  return <div className="mk-trial-home">
    <section className="mk-total" aria-label="내 돈 모두">
      <div className="mk-say" role="status"><Izani mood={mood}/><p>{say}</p></div>
      <span className="mk-total-label">내 돈 모두</span>
      <strong key={state.wallet+state.vault} className="mk-total-number mk-money-change" data-testid="trial-total">{won(state.wallet+state.vault)}</strong>
      <details className="mk-total-detail"><summary><span>용돈통장 <b data-testid="child-balance">{won(state.wallet)}</b></span><span>저축통장 <b data-testid="child-vault">{won(state.vault)}</b></span></summary>
        <div className="mk-total-interest">
          <p>다음 주 예상 용돈 이자 <strong data-testid="allowance-bonus">+{won(interest)}</strong></p>
          <p className="mk-interest-formula" data-testid="interest-formula">{won(base)} × {rate}% = {won(interest)}</p>
          <p>다음 주 예상 저축 이자 <strong data-testid="savings-interest">+{won(state.rewards?.estimates.savings_interest??0)}</strong></p>
          <PracticeNote/>
          <small>{automatic?"다음 주 월요일에 자동으로 들어와요.":"엄마가 확인하면 들어와요."}{base!==state.wallet&&" 이번 주에 받은 이자에는 이자가 다시 붙지 않아요."}</small>
          {records}
        </div>
      </details>
    </section>
    <div className="mk-home-actions">{actions}</div>
    {week}
    {settings}
  </div>;
}
