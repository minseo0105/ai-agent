"use client";
import { useEffect, useRef, useState } from "react";
import { API_URL, apiFetch } from "@/lib/access";
import ChildExperience from "./ChildExperience";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import RewardSaving from "./RewardSaving";
import { PRACTICE, PracticeNote, monthDay, weekRange } from "./WeeklyJourney";
import type { Child, ChildTransaction, State, RewardItem } from "./types";

export const TRIAL_STORAGE="moneyon-trial-v1";
type Snapshot={token?:string;child:Child;state:State;day:string;generation:number;expires:number};
export function addDays(day:string,days:number){const value=new Date(day+"T00:00:00Z");value.setUTCDate(value.getUTCDate()+days);return value.toISOString().slice(0,10);}
export function nextWeek(day:string){return addDays(day,7);}
// 서버가 허용하는 체험 날짜의 끝(services/moneyon_trial.py advance).
const LAST_DAY="2027-10-12";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
const BUSY="서버가 잠시 바빠요. 잠시 후 다시 시도해 주세요.";
const EXPIRED="체험 시간이 끝났거나 서버가 새로 시작됐어요. 처음부터 다시 체험해 볼까요?";
// expired: 이 체험 통장을 더 이상 쓸 수 없어 처음부터 시작해야 하는 오류.
class TrialError extends Error{constructor(message:string,readonly expired=false){super(message);}}
// 서버 응답을 아이가 읽을 수 있는 안내로 바꾼다. JSON이 아닌 응답(재시작 중 HTML 등)의 원문은 보여주지 않는다.
function trialError(status:number,data:{detail?:unknown}|null){
  const detail=(typeof data?.detail==="string"?data.detail:"").replace("부모 가상 계좌","엄마 통장");
  if(status===403)return new TrialError(EXPIRED,true);
  if(status>=500||!data)return new TrialError(status===503&&detail?detail:BUSY);
  if(status===429)return new TrialError(detail||"지금 체험하는 사람이 많아요. 잠시 후 다시 눌러 주세요.");
  return new TrialError(detail||"입력 내용을 확인해 주세요.");
}

// 첫 화면(mk-entry)과 같은 파란 레이아웃의 대기·오류 화면. 화면 전환 사이에 다른 디자인이 끼지 않게 한다.
// quiet: 체험 여부를 확인하는 아주 짧은 순간이라 문구 없이 로고·이자니만 보인다.
export function TrialStatus({error,onExit,quiet}:{error?:string;onExit?:()=>void;quiet?:boolean}) {
  return <main className="mk-entry" aria-busy={!error}><div className="mk-entry-shell"><span className="mk-entry-logo">MONEY:ON</span><span className="mk-demo-label">체험 모드 · 가상 돈이에요</span><div className="mk-entry-art"><Izani mood={error?"help":"greeting"}/></div>{error?<><p role="alert" className="mk-entry-copy">{error}</p><button className="mk-button" onClick={onExit}>처음으로</button></>:quiet?null:<p role="status" className="mk-entry-copy">통장을 준비하고 있어요…</p>}</div></main>;
}

export default function TrialExperience({onExit}:{onExit:()=>void}) {
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[expired,setExpired]=useState(false);
  const [panel,setPanel]=useState(""),[amount,setAmount]=useState(""),[message,setMessage]=useState("");
  const [approval,setApproval]=useState(false);
  const [rewardTab,setRewardTab]=useState<"allowance_bonus"|"savings_interest">("allowance_bonus");
  const [celebrating,setCelebrating]=useState(false),[arrivedAmount,setArrivedAmount]=useState(0);
  useEffect(()=>{
    if(celebrating)document.querySelector<HTMLDialogElement>('.mk-sheet')?.scrollTo({top:0,behavior:"instant"});
  },[celebrating]);
  const [receipt,setReceipt]=useState<{title:string;before:State;after:State}|null>(null);
  const credentials=useRef({token:"",generation:0});const running=useRef(false);
  const retry=useRef<{signature:string;key:string}|null>(null);
  async function api(path:string,body?:unknown,_auth?:string,method="POST") {
    const response=await apiFetch(`${API_URL}/api/moneyon/trial${path}`,{method:body===undefined?"GET":method,headers:{"Content-Type":"application/json","X-Moneyon-Trial":credentials.current.token,"X-Moneyon-Trial-Version":String(credentials.current.generation)},...(body===undefined?{}:{body:JSON.stringify(body)})});
    let data=null;try{data=await response.json();}catch{}
    if(!response.ok||data===null)throw trialError(response.status,data);
    return data;
  }
  function fail(e:unknown){if(e instanceof TrialError&&e.expired)setExpired(true);else setError((e as Error).message||BUSY);}
  function apply(next:Snapshot){credentials.current.generation=next.generation;setSnapshot(next);}
  async function run(action:()=>Promise<void>){if(running.current)return;running.current=true;setBusy(true);setError("");setMessage("");setCelebrating(false);try{await action();}catch(e){fail(e);}finally{running.current=false;setBusy(false);}}
  useEffect(()=>{
    let current=true;
    async function open(){
      try{
        credentials.current.token=sessionStorage.getItem(TRIAL_STORAGE)||"";
        const next:Snapshot=await api(credentials.current.token?"/state":"/start",credentials.current.token?undefined:{});
        if(!current)return;
        if(next.token){credentials.current.token=next.token;sessionStorage.setItem(TRIAL_STORAGE,next.token);}
        apply(next);
      }catch(e){if(current)fail(e);}finally{if(current)setBusy(false);}
    }
    void open();return()=>{current=false;};
  },[]);
  function exit(){sessionStorage.removeItem(TRIAL_STORAGE);onExit();}
  function key(signature:string){if(retry.current?.signature!==signature)retry.current={signature,key:crypto.randomUUID()};return retry.current.key;}

  async function transact(payload:ChildTransaction){let ok=false;await run(async()=>{const before=snapshot!.state;const state=await api(`/children/${snapshot!.child.id}/transactions`,{...payload,key:key(JSON.stringify(payload))});retry.current=null;setSnapshot(s=>s?{...s,state}:s);setReceipt({title:payload.kind==="expense"?`${won(payload.amount)}을 썼어!`:payload.kind==="deposit"?"저축통장에 저금했어!":"내 용돈통장으로 꺼냈어!",before,after:state});setMessage(payload.kind==="expense"?"돈을 썼구나! 남은 용돈과 다음 주 이자가 어떻게 바뀌었는지 볼까?":payload.kind==="deposit"?"저축통장에 돈을 모았네! 저축 이자는 따로 계산돼.":"저축통장에서 내 용돈통장으로 돈을 꺼냈어!");ok=true;});return ok;}
  async function action(kind:"allowance"|"date"|"month"|"approve"|"reset",item?:RewardItem){
    await run(async()=>{
      const cycle=snapshot!.state.cycles.find(c=>c.ended&&!c.settled);
      const body=kind==="allowance"?{amount:Number(amount),key:key("allowance:"+amount)}:kind==="date"?{day:nextWeek(snapshot!.day)}:kind==="month"?{day:addDays(snapshot!.day,28)}:kind==="approve"?{cycle_id:item?.cycle_id??cycle?.id,reward_type:item?.reward_type,approved:true,key:key("approve:"+(item?.cycle_id??cycle?.id)+":"+item?.reward_type)}:{key:key("reset:"+snapshot!.generation)};
      const next:Snapshot=await api(kind==="reset"?"/reset":`/children/${snapshot!.child.id}/${kind==="month"?"date":kind}`,body);
      // 시간을 옮긴 뒤 이자가 실제로 들어왔으면 바로 축하 화면을 보여준다.
      const travel=kind==="date"||kind==="month",span=kind==="month"?"한 달":"1주일";
      const interest=(s:State)=>s.transactions.filter(t=>t.kind==="allowance_bonus"||t.kind==="savings_interest");
      const arrived=travel&&interest(next.state).length>interest(snapshot!.state).length;
      const total=(s:State)=>interest(s).reduce((sum,t)=>sum+t.wallet+t.vault,0);
      setArrivedAmount(Math.max(0,total(next.state)-total(snapshot!.state)));
      apply(next);setCelebrating(kind==="approve"||arrived);retry.current=null;setPanel(kind==="approve"||travel?"reward":"");setAmount("");setApproval(false);
      if(travel)setRewardTab("allowance_bonus");
      setReceipt(kind==="allowance"||kind==="approve"||travel?{title:kind==="allowance"?"엄마 통장에서 용돈이 도착했어!":kind==="approve"?"축하해! 엄마 통장에서 이자가 들어왔어!":`${span}이 지났어!${arrived?" 이자가 들어왔어!":""}`,before:snapshot!.state,after:next.state}:null);
      setMessage(kind==="allowance"?"엄마 통장에서 용돈이 도착했어!":travel?`${span}이 지났어! ${arrived?"들어온 이자를 확인해 봐.":"이번 주 이자가 정해졌어."}`:kind==="approve"?"이자를 받았어! 용돈 이자는 내 용돈통장, 저축 이자는 저축통장으로 들어와!":"처음 통장으로 돌아왔어! 다시 자유롭게 체험해 봐.");
    });
  }
  // 만료·재시작은 저장된 체험을 지우고, 잠깐 바쁜 오류는 체험을 남겨 두어 다시 들어오면 이어진다.
  if(expired)return <TrialStatus error={EXPIRED} onExit={exit}/>;
  if(!snapshot)return busy?<TrialStatus/>:<TrialStatus error={error} onExit={onExit}/>;
  const paid=snapshot.state.transactions.filter(t=>t.kind==="interest");
  const items=snapshot.state.rewards?.items??[];
  const needsApproval=items.some(i=>i.status==="awaiting_approval"&&i.payment_mode!=="automatic");
  const automatic=snapshot.state.payment_rule?.current==="automatic";
  const openBank=()=>{setPanel("allowance");setAmount("10000");setMessage("");setCelebrating(false);};
  const openReward=()=>{setPanel("reward");setRewardTab("allowance_bonus");setMessage("");setCelebrating(false);};
  // 체험마다 날짜가 따로 있어 시간을 옮겨도 다른 사람의 체험은 그대로다.
  const timeButtons=(link:boolean)=><section className="mk-time-actions" aria-label="시간 지나 보기">
    <button className="mk-button full" disabled={busy||nextWeek(snapshot.day)>LAST_DAY} onClick={()=>void action("date")}>1주일 지나 보기</button>
    <button className="mk-button secondary full" disabled={busy||addDays(snapshot.day,28)>LAST_DAY} onClick={()=>void action("month")}>한 달 지나 보기</button>
    <p className="mk-caption">체험 속 날짜 {monthDay(snapshot.day)} · 실제 날짜와 달라요. 시간을 옮겨도 실제 은행 거래는 없고, 다른 사람 체험에도 영향이 없어요.</p>
    {link&&<button type="button" className="mk-text-button" onClick={openReward}>이자 기록 보기</button>}
  </section>;
  const approvalCheck=<label className="mk-trial-check"><input type="checkbox" checked={approval} onChange={e=>setApproval(e.target.checked)}/>엄마 확인(체험용)에 동의해요</label>;
  const controls=<div className="mk-trial-tools">
    <details className="mk-trial-settings"><summary>체험 설정</summary><p>내 돈 전체 <strong data-testid="trial-total">{won(snapshot.state.wallet+snapshot.state.vault)}</strong> · 쌓이는 이자는 빼고</p><button className="mk-text-button" disabled={busy} onClick={()=>setPanel("reset")}>처음 상태로 돌아가기</button><details><summary>체험 기록은 언제까지 남나요?</summary><p>새로고침하면 24시간 동안 이어져요. 일반 새 탭·다른 브라우저는 새 체험이에요. 복제·복원 탭은 같은 체험과 초기화를 공유할 수 있어요.</p>{process.env.NEXT_PUBLIC_MONEYON_EPHEMERAL==="1"&&<p>Hugging Face Space 서버가 다시 만들어지거나 재배포되면 체험 기록이 사라질 수 있어요.</p>}</details></details>
  </div>;
  const sheet=panel&&<TrialSheet title={panel==="allowance"?"엄마 통장에서 용돈 받기":panel==="reward"?"이자 받기":"처음 상태로 돌아가기"} onClose={()=>setPanel("")}>
      {error&&<p className="mk-sheet-error" role="alert">{error}</p>}
      {panel==="allowance"&&<form className="mk-bank-form" onSubmit={e=>{e.preventDefault();void action("allowance");}}>
        <div className="mk-bank-route"><article><span>보내는 곳</span><strong>엄마 통장</strong><small>{won(snapshot.state.education?.parent_balance??0)}</small></article><span className="mk-flow-arrow" aria-hidden="true">→</span><article><span>받는 곳</span><strong>내 용돈통장</strong><small>{won(snapshot.state.wallet)}</small></article></div>
        <label>얼마를 받을까요?<span className="mk-bank-amount"><input required type="number" inputMode="numeric" min={100} max={10000000} step={100} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label>
        <div className="mk-amount-presets">{[3000,10000,30000].map(n=><button type="button" key={n} aria-pressed={amount===String(n)} onClick={()=>setAmount(String(n))}>{won(n)}</button>)}</div>
        <p className="mk-caption">100원 단위로 입력해요. 엄마 통장에서 빠진 돈이 내 용돈통장에 들어오고, 두 통장 모두에 기록돼요.</p>
        <button className="mk-button full" disabled={busy}>{won(Number(amount)||0)} 용돈 받기</button><div className="mk-inline-character"><Izani mood="allowance"/><p>엄마 통장 → 용돈 {won(Number(amount)||0)} → 내 용돈통장<br/><small>실제 계좌이체가 아닌 연습이에요.</small></p></div>
      </form>}
      {panel==="reward"&&<div className="mk-reward-flow">
        {celebrating&&<section className="mk-paid-celebration" role="status"><Izani mood="celebration"/><h3>{arrivedAmount?`축하해! 이자 ${won(arrivedAmount)}이 들어왔어!`:"축하해! 이자가 들어왔어!"}</h3><p>엄마 통장에서 내 용돈통장과 저축통장으로 들어왔어</p></section>}
        <div className="mk-filter" aria-label="이자 종류">{([['allowance_bonus','용돈 이자'],['savings_interest','저축 이자']] as const).map(([key,label])=><button key={key} aria-pressed={rewardTab===key} onClick={()=>{setRewardTab(key);setCelebrating(false);}}>{label}</button>)}</div>
        <p className="mk-caption">{rewardTab==="allowance_bonus"?"남긴 용돈의 10%를 다음 주 내 용돈통장으로 받아요.":"저축통장에 모은 돈은 2%를 따로 계산해서 저축통장으로 받아요."} 쌓이는 중인 이자는 아직 내 돈이 아니에요.</p><PracticeNote/>
        {needsApproval&&approvalCheck}
        <ul className="mk-reward-items">{items.filter(i=>i.reward_type===rewardTab).map(item=><li key={item.cycle_id+item.reward_type} data-payment-state={item.status}><div className="mk-reward-item-head"><small>{weekRange(item.start,item.end)}</small><span>{item.status==="paid"?"들어왔어요":item.status==="awaiting_approval"?(item.payment_mode==="automatic"?"엄마 통장 잔액을 기다려요":"엄마 확인을 기다려요"):"쌓이는 중"}</span></div><p>{won(item.base)} × {item.rate_bps/100}%</p><strong>{item.status==="paid"?"받은 이자 ":item.status==="awaiting_approval"?"정해진 이자 ":"예상 이자 "}{won(item.status==="paid"?item.paid_amount:item.amount)}</strong><small>{item.destination==="wallet"?"엄마 통장 → 내 용돈통장":"엄마 통장 → 저축통장"}{item.paid_at&&` · ${monthDay(item.paid_at.slice(0,10))} 들어옴`}</small>{item.status==="awaiting_approval"&&<button className="mk-button full" disabled={busy||!approval} onClick={()=>void action("approve",item)}>{item.reward_type==="allowance_bonus"?"엄마 확인: 용돈 이자 보내기":"엄마 확인: 저축 이자 보내기"}</button>}</li>)}</ul>
        {timeButtons(false)}
        {snapshot.state.payout_choices?.map(p=><RewardSaving key={p.payout} payout={p} state={snapshot.state} child={snapshot.child.id} api={api} run={run} busy={busy} onState={state=>setSnapshot(s=>s?{...s,state}:s)}/>)}
        <details className="mk-reward-policy"><summary>이자 받는 방식 바꾸기 (체험용)</summary><p>지금은 {automatic?"월요일에 자동으로":"엄마가 확인하면"} 들어와요 · 바꾸면 다음 주부터 적용돼요. 엄마 통장 잔액이 모자라면 기다려요.</p>{snapshot.state.payment_rule?.scheduled.map(r=><p key={r.effective}>{monthDay(r.effective)}부터 {r.mode==="automatic"?"월요일에 자동으로":"엄마가 확인하면"}</p>)}{!needsApproval&&approvalCheck}<button className="mk-button secondary" disabled={busy||!approval} onClick={()=>void run(async()=>{const state=await api(`/children/${snapshot.child.id}/payment-rule`,{mode:automatic?"manual":"automatic",approved:true}) as State;setSnapshot(s=>s?{...s,state}:s);})}>다음 주부터 받는 방식 바꾸기</button></details>
        <details className="mk-reward-policy"><summary>이자 규칙과 이전 기록</summary><p>{PRACTICE}. 월요일에 정해진 금액은 바뀌지 않고, 같은 주 이자는 한 번만 받아요. 용돈 이자는 1원 미만을 버려요. 저축 이자는 2%이고 한 주에 최대 2,000원까지예요.</p><ul>{paid.map(t=><li key={t.id}>{t.created.slice(0,10)} · 이전 용돈 이자 {won(t.wallet)}</li>)}</ul></details>
      </div>}
      {panel==="reset"&&<section aria-describedby="trial-reset-description"><Izani mood="help"/><p id="trial-reset-description">체험한 내용만 처음 상태로 돌아가요.</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>void action("reset")}>확인하고 초기화</button><button className="mk-button secondary" disabled={busy} onClick={()=>setPanel("")}>계속 체험하기</button></div></section>}
    </TrialSheet>;
  return <ChildExperience key={snapshot.child.id} child={snapshot.child} state={snapshot.state} api={api} run={run} busy={busy} error={error} demo onLock={exit} onDismissError={()=>{setError("");setMessage("");}} onState={state=>setSnapshot(s=>s?{...s,state}:s)} onTransact={transact} trialControls={controls} trialTime={timeButtons(true)} trialOverlay={sheet} trialAllowance={<button className="mk-quick-bank" disabled={busy} onClick={openBank}><span aria-hidden="true">↓</span>용돈 받기</button>} trialCelebrating={celebrating} onHome={onExit} trialMessage={message} trialReceipt={receipt&&<section className="mk-change-receipt" aria-label="거래 전후 변화"><h2>{receipt.title}</h2><dl>{([ ["남은 용돈",receipt.before.wallet,receipt.after.wallet],["예상 용돈 이자",receipt.before.rewards?.estimates.allowance_bonus??0,receipt.after.rewards?.estimates.allowance_bonus??0],["저축통장",receipt.before.vault,receipt.after.vault],["예상 저축 이자",receipt.before.rewards?.estimates.savings_interest??0,receipt.after.rewards?.estimates.savings_interest??0],["엄마 통장",receipt.before.education?.parent_balance??0,receipt.after.education?.parent_balance??0] ] as const).filter(([,before,after])=>before!==after).map(([label,before,after])=><div key={label}><dt>{label}</dt><dd>{won(before)} → {won(after)}</dd></div>)}</dl><p>필요한 곳에는 쓰고, 남은 돈도 잘 관리해 보자.</p></section>}/>;
}
