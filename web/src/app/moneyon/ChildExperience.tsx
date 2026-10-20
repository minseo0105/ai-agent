"use client";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { COACH_BRAND, ruleBasedCoach, type CoachMessage, type CoachMood } from "@/lib/moneyonCoach";
import type { BankTransaction } from "./Banking";
import type { Child, ChildTransaction, MoneyApi, RunAction, State } from "./types";
import KidIcon from "./KidIcon";
import Izani from "./Izani";
import WeeklyJourney from "./WeeklyJourney";
import SavingsBooks from "./SavingsBooks";
import "./child.css";
import "./blue.css";

type View="home"|"account"|"savings"|"record"|"growth"|"interest";
type Experiment={left:number;eligible:number;interest:number;total:number};
type Props={child:Child;state:State;api:MoneyApi;run:RunAction;busy:boolean;error:string;demo:boolean;onLock:()=>void;onState:(state:State)=>void;onTransact:(payload:ChildTransaction)=>Promise<boolean>;onDismissError:()=>void;trialControls?:ReactNode;trialMessage?:string;trialReceipt?:ReactNode;trialAllowance?:ReactNode;trialCelebrating?:boolean};
const won=(value:number)=>value.toLocaleString("ko-KR")+"원";
const categories=["간식","문구","장난감","게임","책","선물","기타"];
const merchants=[{name:"편의점",amount:2000},{name:"문구점",amount:4000},{name:"서점",amount:5000},{name:"게임",amount:3000}];
const shortDate=(stamp:string)=>new Date(stamp).toLocaleDateString("ko-KR",{timeZone:"Asia/Seoul",month:"long",day:"numeric"});

export function friendlyTransaction(t:BankTransaction) {
  switch(t.transaction_type){
    case "ALLOWANCE_TRANSFER":return "용돈이 들어왔어요";
    case "PARENT_REWARD_INTEREST":return t.amount>0?"부모님이 보상을 주셨어요":"보상 확인을 마쳤어요";
    case "ALLOWANCE_SAVING_BONUS":return "엄마 은행에서 용돈 이자가 들어왔어요";
    case "PIGGY_BANK_INTEREST":return "저금통 이자가 들어왔어요";
    case "SAVINGS_DEPOSIT":return "저금통에 넣었어요";
    case "SAVINGS_WITHDRAWAL":return "저금통에서 꺼냈어요";
    case "PURCHASE_REVERSAL":return "쓴 돈 기록을 취소했어요";
    case "ALLOWANCE_RETURN":return "남은 용돈을 부모님께 돌려드렸어요";
    default:return t.merchant?`${t.merchant}에서 샀어요`:t.note||"사용한 돈을 기록했어요";
  }
}

function CoachCard({message,compact=false}:{message:CoachMessage;compact?:boolean}) {
  return <aside className={`mk-coach ${compact?"compact":""}`} aria-label={`${COACH_BRAND.displayName}의 한마디`}>
    <Izani mood={message.mood}/><div><span className="mk-coach-name">{COACH_BRAND.displayName}<small>나의 금융 친구</small></span><p>{message.text}</p></div>
  </aside>;
}

function TransactionRow({transaction:t,detail=false,busy,onCategory}:{transaction:BankTransaction;detail?:boolean;busy?:boolean;onCategory?:(transaction:BankTransaction,category:string)=>void}) {
  const purchase=(t.transaction_type==="SIMULATED_PURCHASE"||t.transaction_type==="MANUAL_EXPENSE")&&t.amount<0;
  const content=<><span className={`mk-transaction-icon ${t.amount>=0?"in":"out"}`}><KidIcon name={t.transaction_type.startsWith("SAVINGS")?"savings":t.amount>=0?"down":"up"}/></span><span className="mk-transaction-name"><strong>{friendlyTransaction(t)}</strong><small>{shortDate(t.occurred_at)}{t.category?` · ${t.category}`:""}</small></span><span className={`mk-transaction-amount ${t.amount>0?"in":""}`}>{t.amount>0?"+":""}{won(t.amount)}</span></>;
  if(!detail)return <li className="mk-transaction-row">{content}</li>;
  return <li className="mk-transaction-detail"><details><summary>{content}</summary><div className="mk-transaction-body">
    <dl><div><dt>거래일</dt><dd>{new Date(t.occurred_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})}</dd></div><div><dt>거래처</dt><dd>{t.merchant||((t.transaction_type==="ALLOWANCE_TRANSFER"||t.transaction_type==="PARENT_REWARD_INTEREST")?"부모님":t.note||"내 통장")}</dd></div><div><dt>거래 금액</dt><dd>{won(t.amount)}</dd></div><div><dt>거래 후 남은 돈</dt><dd>{won(t.balance_after)}</dd></div></dl>
    {purchase&&onCategory?<label>소비 카테고리<select aria-label={`소비 카테고리 ${t.transaction_id}`} value={t.category||"기타"} disabled={busy} onChange={e=>onCategory(t,e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label>:t.category&&<p>소비 카테고리 · {t.category}</p>}
    {t.legacy===1&&<small>이전 용돈 기록을 연결했어요.</small>}
  </div></details></li>;
}

export default function ChildExperience({child,state,api,run,busy,error,demo,onLock,onState,onTransact,onDismissError,trialControls,trialMessage,trialReceipt,trialAllowance,trialCelebrating}:Props) {
  const [view,setView]=useState<View>("home");const [feedback,setFeedback]=useState("");
  const [amount,setAmount]=useState("");const [note,setNote]=useState("");const [category,setCategory]=useState("간식");
  const [filter,setFilter]=useState("전체");const [categoryFilter,setCategoryFilter]=useState("전체");
  const [selectedBook,setSelectedBook]=useState("");
  const [savingAction,setSavingAction]=useState<"deposit"|"withdraw"|null>(null);
  const [goalOpen,setGoalOpen]=useState(false);const [goalName,setGoalName]=useState("");const [goalAmount,setGoalAmount]=useState("");
  const [growthTab,setGrowthTab]=useState("정원");const [spend,setSpend]=useState(0);const [experiment,setExperiment]=useState<Experiment|null>(null);const [experimentError,setExperimentError]=useState("");
  const [spendHint,setSpendHint]=useState("");
  const heading=useRef<HTMLHeadingElement>(null);
  const wallet=state.banking.accounts.find(a=>a.kind==="wallet");
  const vault=state.banking.accounts.find(a=>a.kind==="vault");
  const transactions=state.banking.transactions.filter(t=>t.account_id===wallet?.id);
  const cycle=state.cycles.find(c=>!c.ended&&!c.settled)||state.cycles.find(c=>!c.settled);
  const activeCycle=state.cycles.find(c=>!c.ended&&!c.settled);
  const reward=cycle?.interest??0;
  const dual=state.rewards;
  const bonus=dual?.estimates.allowance_bonus??0, piggyInterest=dual?.estimates.savings_interest??0;
  const dualCards=dual&&<WeeklyJourney state={state} actions={<><div className="mk-quick-actions"><button onClick={()=>navigate("record")}><KidIcon name="edit"/>돈 쓰기</button><button onClick={()=>navigate("savings")}><KidIcon name="savings"/>저금하기</button>{trialAllowance}</div>{trialControls}</>}/>;
  const received=transactions.filter(t=>t.transaction_type==="ALLOWANCE_TRANSFER"||t.transaction_type==="PARENT_REWARD_INTEREST").reduce((sum,t)=>sum+t.amount,0);
  const spent=-transactions.filter(t=>["SIMULATED_PURCHASE","MANUAL_EXPENSE","PURCHASE_REVERSAL"].includes(t.transaction_type)).reduce((sum,t)=>sum+t.amount,0);
  const latest=transactions[0];
  let homeCoach=ruleBasedCoach.explain("greeting");
  if(state.goals.some(g=>(vault?.balance??0)>=g.amount))homeCoach=ruleBasedCoach.explain("goal");
  else if(latest?.transaction_type==="ALLOWANCE_TRANSFER")homeCoach=ruleBasedCoach.explain("allowance");
  else if(latest?.transaction_type==="SIMULATED_PURCHASE"||latest?.transaction_type==="MANUAL_EXPENSE")homeCoach=ruleBasedCoach.explain("spending",{merchant:latest.merchant||undefined,amount:Math.abs(latest.amount)});
  else if(latest?.transaction_type==="SAVINGS_DEPOSIT")homeCoach={mood:"greeting",text:"저금통에 돈을 모았네! 목표에 가까워지고 있어."};
  else if(latest?.transaction_type==="PARENT_REWARD_INTEREST"&&latest.amount>0)homeCoach={mood:"allowance",text:"부모님이 보상을 주셨어! 통장에 들어온 돈을 살펴볼까?"};

  if(dual)homeCoach={mood:"interest",text:"이번 주 남은 용돈의 10%가 다음 주 이자가 돼!"};

  function navigate(next:View){setView(next);setFeedback("");onDismissError();}
  useEffect(()=>{window.scrollTo({top:0,behavior:"instant"});heading.current?.focus({preventScroll:true});},[view]);
  useEffect(()=>{
    if(view!=="interest"||!activeCycle||!wallet)return;
    if(spend>Math.floor(wallet.balance/100)*100){setSpend(Math.floor(wallet.balance/100)*100);return;}
    let current=true;setExperiment(null);setExperimentError("");
    void api(`/children/${child.id}/experiment`,{spend}).then(data=>{if(current)setExperiment(data as Experiment);}).catch(e=>{if(current)setExperimentError((e as Error).message);});
    return()=>{current=false;};
  },[view,spend,wallet?.balance,activeCycle?.id,child.id]);

  function changeSpend(value:number){const next=Math.max(0,Math.min(Math.floor((wallet?.balance??0)/100)*100,Math.floor((Number.isFinite(value)?value:0)/100)*100));setSpendHint(next!==value?"100원 단위로 입력해요. 사용할 수 있는 범위에서 100원 단위로 맞췄어요.":"");setSpend(next);}

  async function refresh(){onState(await api(`/children/${child.id}`) as State);}
  async function record(){if(await onTransact({kind:"expense",amount:Number(amount),note,category})){setView("home");setAmount("");setNote("");setFeedback("기록 완료! 쓴 돈을 통장에 적었어요.");}}
  async function transfer(){if(!savingAction)return;if(await onTransact({kind:savingAction,amount:Number(amount),...(state.books?{book_id:selectedBook||state.books?.[0]?.id}:{})})){setFeedback(savingAction==="deposit"?"기록 완료! 저금통에 넣었어요.":"기록 완료! 통장으로 꺼냈어요.");setSavingAction(null);setAmount("");}}
  async function purchase(merchant:string,price:number){if(await onTransact({kind:"expense",amount:price,merchant})){setView("account");setFeedback("기록 완료! 통장에 쓴 돈을 적었어요.");}}
  async function changeCategory(t:BankTransaction,next:string){await run(async()=>{onState(await api(`/children/${child.id}/transactions/${t.transaction_id}/category`,{category:next},undefined,"PATCH") as State);setFeedback("분류를 바꿨어요. 남은 돈은 그대로예요.");});}
  async function answer(quest:string,value:number){await run(async()=>{const result=await api(`/children/${child.id}/quiz`,{quest,answer:value}) as {correct:boolean;message:string};setFeedback(result.correct?"정답! 새로운 금융 이야기를 배웠어요.":quest==="needs"?"다시 생각해 볼까? 생활에 꼭 필요한 것을 골라 봐!":child.profile.grade<=3?"다시 생각해 볼까? 10%는 똑같이 나눈 열 조각 중 하나야.":"다시 생각해 볼까? 5%는 똑같이 나눈 백 조각 중 다섯이야.");await refresh();});}

  const primary=view==="account"?"account":["savings","interest"].includes(view)?"savings":"home";
  const title={home:`안녕, ${child.profile.name}!`,account:"나의 통장",savings:"차곡차곡, 나의 저축",record:"돈 썼어요",growth:"나의 성장",interest:"이자 알아보기"}[view];
  const rows=transactions.filter(t=>(filter==="전체"||(filter==="받은 돈"?t.amount>0:filter==="쓴 돈"?["SIMULATED_PURCHASE","MANUAL_EXPENSE","PURCHASE_REVERSAL"].includes(t.transaction_type):t.transaction_type.startsWith("SAVINGS")))&&(categoryFilter==="전체"||t.category===categoryFilter));
  const rewardCoach=ruleBasedCoach.explain("interest",cycle?{eligible:cycle.eligible,interest:cycle.interest}:{});

  return <main className={`mk ${child.profile.theme}`} data-testid="child-experience" data-theme={child.profile.theme} aria-busy={busy}>
    <div className="mk-container">
      <header className="mk-header"><a href="/" aria-label="AI LAB으로 가기"><span className="mk-brand-dot"/>MONEY:ON</a><button className="mk-parent-button" aria-label={trialControls?"체험 나가기":"잠그기 🔒"} onClick={onLock}><KidIcon name="lock"/>{trialControls?"나가기":"부모님"}</button></header>
      {demo&&<span className="mk-demo-label">DEMO · 연습용 통장이에요</span>}
      <div className="mk-page-heading">{!["home","account","savings"].includes(view)&&<button className="mk-back" onClick={()=>navigate(view==="interest"?"savings":"home")} aria-label={view==="interest"?"저축으로 돌아가기":"홈으로 돌아가기"}><KidIcon name="back"/></button>}<div><h1 ref={heading} tabIndex={-1}>{title}</h1>{view==="home"&&<p>이자니와 함께, 용돈이 자라는 일주일</p>}</div>{view==="home"&&trialControls?<Izani mood="greeting" className="mk-header-character"/>:view==="home"&&<span className="mk-profile" aria-label={`${child.profile.name}의 캐릭터`}>{child.profile.avatar==="🪙"?<span className="mk-profile-coin">₩</span>:child.profile.avatar==="🧑‍🚀"?<svg viewBox="0 0 44 44" width="37" height="37" role="img" aria-label="우주인 캐릭터"><path d="M13 35v5h18v-5" fill="#b5cbe7" stroke="#6483af" strokeWidth="1.5"/><circle cx="22" cy="21" r="17" fill="#dceaf6" stroke="#6483af" strokeWidth="1.5"/><rect x="9" y="12" width="26" height="21" rx="10" fill="#7898be"/><ellipse cx="22" cy="24" rx="9" ry="8" fill="#fff0d5"/><circle cx="18" cy="23" r="1.2" fill="#294953"/><circle cx="26" cy="23" r="1.2" fill="#294953"/><path d="M19 27q3 3 6 0" fill="none" stroke="#294953" strokeWidth="1.3" strokeLinecap="round"/><path d="M13 12q8-5 17-1" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round"/></svg>:child.profile.avatar}</span>}</div>

      {error&&<section className="mk-error" role="alert"><Izani mood="help"/><div><strong>{COACH_BRAND.displayName}가 도와줄게!</strong><p>{error}</p><button onClick={()=>void run(refresh)} disabled={busy}>통장 다시 보기</button></div></section>}
      {feedback&&!trialControls&&<p className="mk-feedback" role="status"><KidIcon name="check"/>{feedback}</p>}
      {(trialMessage||feedback)&&trialControls&&<div role="status"><CoachCard compact message={{text:trialMessage||feedback,mood:trialCelebrating?"celebration":"greeting"}}/></div>}
      {trialReceipt}
      {!wallet||!vault?<section className="mk-panel"><CoachCard message={ruleBasedCoach.explain("help")}/><button className="mk-button" disabled={busy} onClick={()=>void run(refresh)}>통장을 다시 불러오기</button></section>:<>

      {view==="home"&&<>
        {dual?dualCards:<><section className="mk-balance-card" aria-label="내 통장 잔액"><div><span>내 통장에 있는 돈</span><strong key={wallet.balance} className="mk-money-change" data-testid="child-balance">{won(wallet.balance)}</strong><small>가상 통장 · 실제 금융 거래 아님</small></div><div className="mk-balance-art" aria-hidden="true"><KidIcon name="account"/><span/><i/></div></section>
        <div className="mk-two-stats"><section className="mk-mini-stat mint"><span><KidIcon name="savings"/>저금통에 모은 돈</span><strong key={vault.balance} className="mk-money-change" data-testid="child-vault">{won(vault.balance)}</strong></section><section className="mk-mini-stat blue"><span><KidIcon name="gift"/>받을 수 있는 보상</span><strong key={reward} className="mk-money-change" data-testid="child-reward">{won(reward)}</strong><small>예상 금액 · 아직 안 들어왔어요</small></section></div></>}
        {!dual&&<><div className="mk-main-actions"><button className="mk-button" onClick={()=>navigate("record")}><KidIcon name="edit"/>돈 썼어요</button><button className="mk-button secondary" onClick={()=>navigate("account")}><KidIcon name="account"/>통장 보기</button></div>
        {trialControls}</>}
        <section className="mk-section"><div className="mk-section-title"><h2>최근 내 돈 이야기</h2><button className="mk-text-button" onClick={()=>navigate("account")}>모두 보기<KidIcon name="arrow"/></button></div>{transactions.length?<ul className="mk-transactions" data-testid="recent-transactions">{transactions.slice(0,3).map(t=><TransactionRow key={`${t.transfer_id}:${t.account_id}`} transaction={t}/>)}</ul>:<p className="mk-empty">아직 기록이 없어요. 용돈이 들어오면 여기서 볼 수 있어요.</p>}</section>
        <details className="mk-home-more"><summary>금융교육 팁과 나의 성장</summary><button className="mk-growth-link" aria-label="나의 성장" onClick={()=>navigate("growth")}><span className="mk-growth-icon"><KidIcon name="leaf"/></span><span><strong>나의 성장</strong><small>정원 · 퀘스트 · 배지</small></span><KidIcon name="arrow"/></button>
        {!error&&!(trialControls&&(trialMessage||feedback))&&<CoachCard message={homeCoach}/>}</details>
      </>}

      {view==="account"&&<>
        <section className="mk-account-balance"><span>내 통장에 있는 돈</span><strong key={wallet.balance} className="mk-money-change" data-testid="child-balance">{won(wallet.balance)}</strong><small>가상 통장 · 실제 금융 거래 아님</small></section>
        <div className="mk-account-totals"><div><KidIcon name="down"/><span>받은 돈<strong>{won(received)}</strong></span></div><div><KidIcon name="up"/><span>사용한 돈<strong>{won(spent)}</strong></span></div></div><p className="mk-caption">전체 기록 기준 · 저금통 이동은 사용한 돈에 넣지 않아요</p>
        <div className="mk-section-title"><h2>입출금 내역</h2><button className="mk-text-button" onClick={()=>navigate("record")}><KidIcon name="plus"/>직접 기록</button></div>
        <div className="mk-filter" aria-label="거래 구분">{["전체","받은 돈","쓴 돈","저축"].map(f=><button key={f} aria-pressed={filter===f} onClick={()=>setFilter(f)}>{f}</button>)}</div>
        <details className="mk-category-filter"><summary>소비 분류로 찾아보기</summary><label>소비 분류<select value={categoryFilter} onChange={e=>setCategoryFilter(e.target.value)}>{["전체",...categories].map(c=><option key={c}>{c}</option>)}</select></label></details>
        <ul className="mk-transactions" data-testid="account-transactions">{rows.map(t=><TransactionRow key={`${t.transfer_id}:${t.account_id}`} transaction={t} detail busy={busy} onCategory={(entry,c)=>void changeCategory(entry,c)}/>)}</ul>{!rows.length&&<p className="mk-empty">이 분류의 기록은 아직 없어요.</p>}
        <details className="mk-account-info"><summary>내 가상 통장 정보</summary><p>{wallet.id}</p><small>가상 계좌 · 실제 금융 거래 아님</small></details>
      </>}

      {view==="record"&&<>
        <div className="mk-spend-intro"><Izani mood="spending"/><p>필요한 곳에는 쓰고,<br/>남은 돈도 잘 관리해 보자.</p></div><form className="mk-panel mk-record-form" onSubmit={e=>{e.preventDefault();void record();}}><label>무엇을 샀나요?<input required maxLength={200} placeholder="예: 공책 한 권" value={note} onChange={e=>setNote(e.target.value)}/></label><label>얼마를 썼나요?<span className="mk-amount-input"><input required type="number" inputMode="numeric" min={trialControls?100:1} max={wallet.balance} step={trialControls?100:1} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label><label>어떤 종류인가요?<select value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label><p className="mk-caption">{trialControls&&"100원 단위로 입력해 주세요. "}지금 쓸 수 있는 돈 {won(wallet.balance)}</p><button className="mk-button full" disabled={busy}>기록 완료</button></form>
        <details className="mk-simulation"><summary>가상 소비로 연습하기</summary><p>실제 결제가 일어나지 않는 연습이에요. 통장에는 한 번만 기록돼요.</p><div className="mk-merchants">{merchants.map(m=><button key={m.name} disabled={busy} onClick={()=>void purchase(m.name,m.amount)}>{m.name}<strong>{won(m.amount)}</strong></button>)}</div></details>
        {!error&&<CoachCard compact message={ruleBasedCoach.explain("spending")}/>}
      </>}

      {view==="savings"&&<>
        <section className="mk-savings-balance"><div><span>내가 모은 돈</span><strong key={vault.balance} className="mk-money-change" data-testid="child-vault">{won(vault.balance)}</strong><small>내 저금통</small></div><div className="mk-pig-art" aria-hidden="true"><KidIcon name="savings"/></div></section>
        <div className="mk-main-actions"><button className="mk-button" onClick={()=>{setSelectedBook(state.books?.[0]?.id??"");setSavingAction("deposit");setAmount("");}}>저금통에 넣기</button><button className="mk-button secondary" onClick={()=>{setSelectedBook(state.books?.[0]?.id??"");setSavingAction("withdraw");setAmount("");}}>꺼내기</button></div>
        {savingAction&&<form className="mk-panel" onSubmit={e=>{e.preventDefault();void transfer();}}><label>{savingAction==="deposit"?"저금통에 얼마를 넣을까요?":"통장으로 얼마를 꺼낼까요?"}<input autoFocus required type="number" inputMode="numeric" min={trialControls?100:1} max={savingAction==="deposit"?wallet.balance:(state.books?.find(b=>b.id===(selectedBook||state.books?.[0]?.id))?.balance??vault.balance)} step={trialControls?100:1} value={amount} onChange={e=>setAmount(e.target.value)}/></label><p className="mk-caption">{state.books?.find(b=>b.id===(selectedBook||state.books?.[0]?.id))?.name} {trialControls&&"100원 단위로 입력해 주세요."}</p><div className="mk-main-actions"><button className="mk-button" disabled={busy}>옮기기</button><button className="mk-button secondary" type="button" onClick={()=>setSavingAction(null)}>나중에</button></div></form>}
        {state.books?<SavingsBooks state={state} child={child.id} api={api} run={run} busy={busy} onState={onState} onTransfer={(id,kind)=>{setSelectedBook(id);setSavingAction(kind);setAmount("");}}/>:<>
        <section className="mk-section"><div className="mk-section-title"><h2>나의 저축 목표</h2><button className="mk-text-button" onClick={()=>setGoalOpen(!goalOpen)}><KidIcon name="plus"/>목표 만들기</button></div>{state.goals.map(g=><article className="mk-goal" key={g.id}><div><KidIcon name="star"/><h3>{g.name}</h3><span>{Math.min(100,Math.floor(vault.balance/g.amount*100))}%</span></div><progress value={Math.min(vault.balance,g.amount)} max={g.amount} aria-label={`${g.name} 달성률`}/><p>{won(vault.balance)} <span>/ {won(g.amount)}</span></p>{vault.balance>=g.amount&&<span className="mk-goal-done"><KidIcon name="check"/>목표를 이뤘어요!</span>}</article>)}{!state.goals.length&&<p className="mk-empty">갖고 싶은 것, 해 보고 싶은 것을 목표로 정해 봐요.</p>}{state.goals.length>1&&<small className="mk-caption">각 목표는 같은 저금통 금액과 비교해요.</small>}
        {goalOpen&&<form className="mk-panel" onSubmit={e=>{e.preventDefault();void run(async()=>{await api(`/children/${child.id}/goals`,{name:goalName,amount:Number(goalAmount)});await refresh();setGoalOpen(false);setGoalName("");setGoalAmount("");setFeedback("목표를 만들었어요. 천천히 모아 봐요!");});}}><label>목표 이름<input required maxLength={60} value={goalName} onChange={e=>setGoalName(e.target.value)} placeholder="예: 나의 첫 자전거"/></label><label>목표 금액<input required type="number" inputMode="numeric" min={1} max={10000000} step={1} value={goalAmount} onChange={e=>setGoalAmount(e.target.value)}/></label><button className="mk-button full" disabled={busy}>목표 저장</button></form>}</section>
        </>}
        {dual? <section className="mk-panel"><h2>저금통 이자</h2><strong data-testid="savings-interest">{won(piggyInterest)}</strong><p>다음 주 예상 금액 · 약속한 지급 방식으로 저금통에 들어와요.</p><p>용돈 이자 {won(bonus)}는 별도로 계산하고 내 통장으로 받아요.</p><ul>{state.banking.transactions.filter(t=>t.account_id===vault.id&&["PIGGY_BANK_INTEREST"].includes(t.transaction_type)).map(t=><TransactionRow key={t.transfer_id} transaction={t}/>)}</ul></section>:<section className="mk-reward-panel"><span className="mk-reward-icon"><KidIcon name="gift"/></span><div><h2>받을 수 있는 보상</h2><strong data-testid="child-reward">{won(reward)}</strong><p>예상 금액이에요. 부모님이 확인하면 통장에 들어와요.</p></div></section>}
        <button className="mk-discovery-link" aria-label="이자 알아보기" onClick={()=>navigate("interest")}><KidIcon name="help"/><span>이자 알아보기<small>돈을 남기면 어떤 일이 생길까?</small></span><KidIcon name="arrow"/></button>
        {!dual&&!error&&!(trialControls&&(trialMessage||feedback))&&<CoachCard compact message={rewardCoach}/>}
      </>}

      {view==="interest"&&<>
        <CoachCard message={dual?{mood:"greeting",text:"돈을 쓰면 용돈이 줄고, 저금하면 저금통이 늘어나! 두 보상은 부모님이 주는 교육용 보상이야."}:ruleBasedCoach.explain("interest",experiment?{eligible:experiment.eligible,interest:experiment.interest}:undefined)}/>
        <section className="mk-panel"><h2>얼마를 써 볼까?</h2><p className="mk-caption">여기서 움직여도 실제 용돈은 바뀌지 않아!</p>{activeCycle?<><label>써 볼 돈<span className="mk-experiment-amount">{won(spend)}</span><input type="range" min={0} max={Math.floor(wallet.balance/100)*100} step={100} value={spend} onChange={e=>changeSpend(Number(e.target.value))}/></label><div className="mk-spend-stepper"><button type="button" aria-label="100원 줄이기" disabled={spend<100} onClick={()=>changeSpend(spend-100)}>−100원</button><button type="button" aria-label="100원 늘리기" disabled={spend+100>wallet.balance} onClick={()=>changeSpend(spend+100)}>+100원</button></div><label>직접 금액 입력<input type="number" inputMode="numeric" min={0} max={Math.floor(wallet.balance/100)*100} step={100} value={spend} onChange={e=>changeSpend(Number(e.target.value))}/></label><p className="mk-caption" aria-live="polite">{spendHint||"100원씩 조절해요. 계산된 이자는 1원 단위 그대로 보여줘요."}</p>{experiment?<div className="mk-experiment-result" data-testid="experiment-result"><div><span>남는 돈</span><strong>{won(experiment.left)}</strong></div><div><span>{dual?"용돈 이자":"받을 수 있는 보상"}</span><strong>+{won(experiment.interest)}</strong></div><small>부모님이 주실 수 있는 예상 보상이에요.</small></div>:!experimentError&&<p role="status">얼마나 남을지 살펴보고 있어요…</p>}{experimentError&&<p role="alert">{experimentError}</p>}</>:<p>새 용돈을 받으면 같이 움직여 보자! 지난 보상은 부모님과 확인해 봐요.</p>}</section>
      </>}

      {view==="growth"&&<>
        <div className="mk-filter" aria-label="성장 살펴보기">{["정원","퀘스트","배지"].map(t=><button aria-pressed={growthTab===t} key={t} onClick={()=>setGrowthTab(t)}>{t}</button>)}</div>
        {growthTab==="정원"&&<section className="mk-panel mk-garden"><h2>나의 저축 정원</h2><div className={`mk-tree stage-${state.stage}`} aria-hidden="true"><KidIcon name="leaf"/><i/><span/></div><h3>{["씨앗","새싹","작은 나무","큰 나무","열매 나무","황금 저축 나무"][state.stage]}</h3><p>기록하고 배운 만큼 자라고 있어요.</p><small>{state.xp} XP · 돈의 크기로 겨루지 않아요</small></section>}
        {growthTab==="배지"&&<section className="mk-panel"><h2>나의 성취 배지</h2>{state.badges.length?<ul className="mk-badges">{state.badges.map(b=><li key={b}><KidIcon name="star"/><strong>{b}</strong></li>)}</ul>:<p className="mk-empty">첫 기록이나 목표를 만들면 배지가 생겨요.</p>}</section>}
        {growthTab==="퀘스트"&&<section className="mk-panel"><h2>짧게 배우는 금융 이야기</h2><p className="mk-caption">한 번 배우면 완료예요. 오늘 다 하지 않아도 괜찮아요.</p><div className="mk-quest"><h3>쓴 돈을 적어 보기 {state.transactions.some(t=>t.kind==="expense")&&<KidIcon name="check"/>}</h3><button className="mk-text-button" onClick={()=>navigate("record")}>기록하러 가기<KidIcon name="arrow"/></button></div><div className="mk-quest"><h3>저축 목표 만들기 {state.goals.length>0&&<KidIcon name="check"/>}</h3><button className="mk-text-button" onClick={()=>{setGoalOpen(true);navigate("savings");}}>목표 세우러 가기<KidIcon name="arrow"/></button></div>
          <div className="mk-quest"><h3>{child.profile.grade<=3?"1,000원의 10%는?":"15,000원의 5%는?"}</h3>{state.quests.includes("interest")?<p className="mk-complete"><KidIcon name="check"/>배웠어요!</p>:<div className="mk-main-actions"><button className="mk-choice" disabled={busy} onClick={()=>void answer("interest",10)}>10원</button><button className="mk-choice" disabled={busy} onClick={()=>void answer("interest",child.profile.grade<=3?100:750)}>{child.profile.grade<=3?"100원":"750원"}</button></div>}</div>
          <div className="mk-quest"><h3>생활에 꼭 필요한 것은?</h3>{state.quests.includes("needs")?<p className="mk-complete"><KidIcon name="check"/>배웠어요!</p>:<><button className="mk-choice full" disabled={busy} onClick={()=>void answer("needs",1)}>다 쓴 공책 대신 새 공책</button><button className="mk-choice full" disabled={busy} onClick={()=>void answer("needs",0)}>이미 가진 장난감의 다른 색</button></>}</div>
        </section>}
        <CoachCard compact message={{mood:"greeting",text:"오늘 살펴본 돈 이야기를 부모님과 나눠 봐!"}}/>
      </>}
      </>}

      {busy&&<p className="mk-caption" role="status">안전하게 기록하고 있어요…</p>}
      <footer className="mk-footer"><p>가상 계좌 · 실제 금융 거래 아님</p><details><summary>{COACH_BRAND.displayName} 소개</summary><p>{COACH_BRAND.tagline}</p><p>{COACH_BRAND.notice}</p></details></footer>
    </div>
    <nav className="mk-bottom-nav" aria-label="어린이 주요 메뉴">{([{key:"home",name:"홈",icon:"home"},{key:"account",name:"통장",icon:"account"},{key:"savings",name:"저축",icon:"savings"}] as const).map(t=><button key={t.key} aria-current={primary===t.key?"page":undefined} onClick={()=>navigate(t.key)}><KidIcon name={t.icon}/><span>{t.name}</span></button>)}</nav>
  </main>;
}
