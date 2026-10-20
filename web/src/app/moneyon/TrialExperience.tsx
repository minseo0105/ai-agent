"use client";
import { useEffect, useRef, useState } from "react";
import { API_URL, apiFetch } from "@/lib/access";
import ChildExperience from "./ChildExperience";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import RewardSaving from "./RewardSaving";
import type { Child, ChildTransaction, State, RewardItem } from "./types";

export const TRIAL_STORAGE="moneyon-trial-v1";
type Snapshot={token?:string;child:Child;state:State;day:string;generation:number;expires:number};
export function nextWeek(day:string){const value=new Date(day+"T00:00:00Z");value.setUTCDate(value.getUTCDate()+7);return value.toISOString().slice(0,10);}
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";

// 첫 화면(mk-entry)과 같은 파란 레이아웃의 대기·오류 화면. 화면 전환 사이에 다른 디자인이 끼지 않게 한다.
// quiet: 체험 여부를 확인하는 아주 짧은 순간이라 문구 없이 로고·이자니만 보인다.
export function TrialStatus({error,onExit,quiet}:{error?:string;onExit?:()=>void;quiet?:boolean}) {
  return <main className="mk-entry" aria-busy={!error}><div className="mk-entry-shell"><span className="mk-entry-logo">MONEY:ON</span><div className="mk-entry-art"><Izani mood="greeting"/></div>{error?<><p role="alert" className="mk-entry-copy">{error}</p><button className="mk-button" onClick={onExit}>처음 화면으로</button></>:quiet?null:<p role="status" className="mk-entry-copy">통장을 준비하고 있어요…</p>}</div></main>;
}

export default function TrialExperience({onExit}:{onExit:()=>void}) {
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState("");
  const [panel,setPanel]=useState(""),[amount,setAmount]=useState(""),[message,setMessage]=useState("");
  const [approval,setApproval]=useState(false);
  const [rewardTab,setRewardTab]=useState<"allowance_bonus"|"savings_interest">("allowance_bonus");
  const [celebrating,setCelebrating]=useState(false);
  useEffect(()=>{
    if(celebrating)document.querySelector<HTMLDialogElement>('.mk-sheet')?.scrollTo({top:0,behavior:"instant"});
  },[celebrating]);
  const [receipt,setReceipt]=useState<{title:string;before:State;after:State}|null>(null);
  const credentials=useRef({token:"",generation:0});const running=useRef(false);
  const retry=useRef<{signature:string;key:string}|null>(null);
  async function api(path:string,body?:unknown,_auth?:string,method="POST") {
    const response=await apiFetch(`${API_URL}/api/moneyon/trial${path}`,{method:body===undefined?"GET":method,headers:{"Content-Type":"application/json","X-Moneyon-Trial":credentials.current.token,"X-Moneyon-Trial-Version":String(credentials.current.generation)},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"입력 내용을 확인해 주세요.");return data;
  }
  function apply(next:Snapshot){credentials.current.generation=next.generation;setSnapshot(next);}
  async function run(action:()=>Promise<void>){if(running.current)return;running.current=true;setBusy(true);setError("");setMessage("");setCelebrating(false);try{await action();}catch(e){setError((e as Error).message);}finally{running.current=false;setBusy(false);}}
  useEffect(()=>{
    let current=true;
    async function open(){
      try{
        credentials.current.token=sessionStorage.getItem(TRIAL_STORAGE)||"";
        const next:Snapshot=await api(credentials.current.token?"/state":"/start",credentials.current.token?undefined:{});
        if(!current)return;
        if(next.token){credentials.current.token=next.token;sessionStorage.setItem(TRIAL_STORAGE,next.token);}
        apply(next);
      }catch(e){if(current)setError((e as Error).message);}finally{if(current)setBusy(false);}
    }
    void open();return()=>{current=false;};
  },[]);
  function exit(){sessionStorage.removeItem(TRIAL_STORAGE);onExit();}
  function key(signature:string){if(retry.current?.signature!==signature)retry.current={signature,key:crypto.randomUUID()};return retry.current.key;}

  async function transact(payload:ChildTransaction){let ok=false;await run(async()=>{const before=snapshot!.state;const state=await api(`/children/${snapshot!.child.id}/transactions`,{...payload,key:key(JSON.stringify(payload))});retry.current=null;setSnapshot(s=>s?{...s,state}:s);setReceipt({title:payload.kind==="expense"?`${won(payload.amount)}을 썼어!`:payload.kind==="deposit"?"저금통으로 옮겼어!":"통장으로 꺼냈어!",before,after:state});setMessage(payload.kind==="expense"?"돈을 썼구나! 남은 용돈과 다음 주 이자가 어떻게 바뀌었는지 볼까?":payload.kind==="deposit"?"저금통에 돈을 모았네! 저금통 이자는 따로 계산돼.":"저금통에서 내 통장으로 돈을 옮겼어!");ok=true;});return ok;}
  async function action(kind:"allowance"|"date"|"approve"|"reset",item?:RewardItem){
    await run(async()=>{
      const cycle=snapshot!.state.cycles.find(c=>c.ended&&!c.settled);
      const body=kind==="allowance"?{amount:Number(amount),key:key("allowance:"+amount)}:kind==="date"?{day:nextWeek(snapshot!.day)}:kind==="approve"?{cycle_id:item?.cycle_id??cycle?.id,reward_type:item?.reward_type,approved:true,key:key("approve:"+(item?.cycle_id??cycle?.id)+":"+item?.reward_type)}:{key:key("reset:"+snapshot!.generation)};
      const next:Snapshot=await api(kind==="reset"?"/reset":`/children/${snapshot!.child.id}/${kind}`,body);
      apply(next);setCelebrating(kind==="approve");retry.current=null;setPanel(kind==="approve"||kind==="date"?"reward":"");setAmount("");setApproval(false);
      setReceipt(kind==="allowance"||kind==="approve"?{title:kind==="allowance"?"엄마 은행에서 용돈이 도착했어!":"축하해! 엄마 은행에서 이자가 들어왔어!",before:snapshot!.state,after:next.state}:null);
      setMessage(kind==="allowance"?"엄마 은행에서 용돈이 도착했어!":kind==="date"?`체험 속 날짜가 ${next.day}로 이동했어! 지난주를 마감했어. 도착한 이자와 지급 상태를 확인해 봐.`:kind==="approve"?"승인한 이자를 한 번 받았어. 용돈 이자는 내 통장, 저금통 이자는 저금통으로 들어와!":"처음 통장으로 돌아왔어! 다시 자유롭게 체험해 봐.");
    });
  }
  if(!snapshot)return busy?<TrialStatus/>:<TrialStatus error={error} onExit={exit}/>;
  const paid=snapshot.state.transactions.filter(t=>t.kind==="interest");
  const openBank=()=>{setPanel("allowance");setAmount("");setMessage("");setCelebrating(false);};
  const controls=<div className="mk-trial-tools">
    <button className="mk-interest-link" disabled={busy} onClick={()=>{setPanel("reward");setRewardTab("allowance_bonus");setMessage("");setCelebrating(false);}}>다음 주 이자 받기 <span aria-hidden="true">→</span></button>
    <details className="mk-trial-settings"><summary>체험 관리</summary><p>총 보유금액 <strong data-testid="trial-total">{won(snapshot.state.wallet+snapshot.state.vault)}</strong> · 예상 이자 제외</p><button className="mk-text-button" disabled={busy} onClick={()=>setPanel("reset")}>처음 상태로 돌아가기</button><details><summary>체험 기록은 언제까지 남나요?</summary><p>새로고침하면 24시간 동안 이어져요. 일반 새 탭·다른 브라우저는 새 체험이에요. 복제·복원 탭은 같은 체험과 초기화를 공유할 수 있어요.</p>{process.env.NEXT_PUBLIC_MONEYON_EPHEMERAL==="1"&&<p>Hugging Face Space 서버가 다시 만들어지거나 재배포되면 체험 기록이 사라질 수 있어요.</p>}</details></details>
    {panel&&<TrialSheet title={panel==="allowance"?"엄마 은행":panel==="reward"?"다음 주 이자 받기":"처음 상태로 돌아가기"} onClose={()=>setPanel("")}>
      {error&&<p className="mk-sheet-error" role="alert">{error}</p>}
      {panel==="allowance"&&<form className="mk-bank-form" onSubmit={e=>{e.preventDefault();void action("allowance");}}>
        <p className="mk-eyebrow">가상 용돈 보내기 · 체험 전용</p>
        <div className="mk-bank-route"><article><span>보내는 곳</span><strong>엄마 은행</strong><small>{won(snapshot.state.education?.parent_balance??0)}</small></article><span className="mk-flow-arrow" aria-hidden="true">→</span><article><span>받는 곳</span><strong>{snapshot.child.profile.name}이 통장</strong><small>{won(snapshot.state.wallet)}</small></article></div>
        <label>얼마를 받을까요?<span className="mk-bank-amount"><input autoFocus required type="number" inputMode="numeric" min={100} max={10000000} step={100} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label><p className="mk-caption">100원 단위로 입력해요. 엄마 은행 출금과 내 통장 입금이 함께 기록돼요.</p>
        <div className="mk-amount-presets">{[3000,10000,30000].map(n=><button type="button" key={n} onClick={()=>setAmount(String(n))}>{won(n)}</button>)}</div>
        <button className="mk-button full" disabled={busy}>가상 용돈 받기</button><div className="mk-inline-character"><Izani mood="allowance"/><p>엄마 은행 → 용돈 {won(Number(amount)||0)} → 아이 통장<br/><small>실제 계좌이체가 아닌 연습이에요.</small></p></div>
      </form>}
      {panel==="reward"&&<div className="mk-reward-flow">
        <div className="mk-filter" aria-label="이자 종류">{([['allowance_bonus','용돈 이자'],['savings_interest','저금통 이자']] as const).map(([key,label])=><button key={key} aria-pressed={rewardTab===key} onClick={()=>{setRewardTab(key);setCelebrating(false);}}>{label}</button>)}</div>
        {celebrating&&<section className="mk-paid-celebration" role="status"><Izani mood="celebration"/><h3>축하해! 이자가 들어왔어!</h3><p>엄마 은행에서 {rewardTab==="allowance_bonus"?"내 통장":"저금통"}으로 지급 완료</p></section>}
        <ol className="mk-approval-steps"><li>이번 주 이자 계산</li><li>{snapshot.state.payment_rule?.current==="automatic"?"약속한 자동 지급":"부모 승인"}</li><li>통장 입금</li></ol>
        <p className="mk-caption">{rewardTab==="allowance_bonus"?"남긴 용돈의 10%를 다음 주 내 통장으로 받아요.":"저금통에 모은 돈은 별도 규칙으로 계산해 저금통으로 받아요."} 예상 이자는 아직 내 돈이 아니에요.</p>
        <ul className="mk-reward-items">{snapshot.state.rewards?.items.filter(i=>i.reward_type===rewardTab).map(item=><li key={item.cycle_id+item.reward_type} data-payment-state={item.status}><div className="mk-reward-item-head"><small>{item.start} ~ {item.end} 직전</small><span>{item.status==="paid"?"입금 완료":item.status==="awaiting_approval"?(item.payment_mode==="automatic"?"엄마 은행 잔액 준비 중":"부모 승인 대기"):"예상 · 진행 중"}</span></div><p>{won(item.base)} × {item.rate_bps/100}%</p><strong>{item.status==="paid"?"받은 이자 ":item.status==="awaiting_approval"?"마감 확정 이자 ":"예상 이자 "}{won(item.status==="paid"?item.paid_amount:item.amount)}</strong><small>{item.destination==="wallet"?"엄마 은행 → 아이 통장":"엄마 은행 → 저금통"}{item.paid_at&&` · ${item.paid_at.slice(0,10)} 입금`}</small>{item.status==="awaiting_approval"&&<button className="mk-button full" disabled={busy||!approval} onClick={()=>void action("approve",item)}>{item.reward_type==="allowance_bonus"?"용돈 이자 승인":"저금통 이자 승인"}</button>}</li>)}</ul>
        <section className="mk-date-form" aria-label="다음 주 체험"><h3>다음 주를 체험해 볼까?</h3><p className="mk-caption">체험 속 날짜 {snapshot.day}<br/>실제 오늘 날짜와는 달라요. 날짜를 옮겨도 실제 은행 거래는 일어나지 않아요.</p><button type="button" className="mk-button secondary full" disabled={busy||nextWeek(snapshot.day)>"2027-10-12"} onClick={()=>void action("date")}>1주일 뒤로 이동</button><p className="mk-caption">{snapshot.state.rewards?.items.some(i=>i.status==="awaiting_approval")?"승인을 기다려도 용돈을 쓰고 저축할 수 있어요.":`체험 속 ${nextWeek(snapshot.day)}로 이동해요. 월요일 0시에 주간 잔액을 마감해요.`}</p></section><label className="mk-trial-check"><input type="checkbox" checked={approval} onChange={e=>setApproval(e.target.checked)}/>체험 전용 부모 승인에 동의해요</label>
        {snapshot.state.payout_choices?.map(p=><RewardSaving key={p.payout} payout={p} state={snapshot.state} child={snapshot.child.id} api={api} run={run} busy={busy} onState={state=>setSnapshot(s=>s?{...s,state}:s)}/>)}
        <details className="mk-reward-policy"><summary>체험 전용 부모 지급 설정</summary><p>현재 {snapshot.state.payment_rule?.current==="automatic"?"자동 지급":"매주 승인"} · 변경은 다음 주부터 적용돼요. 잔액이 부족하면 지급을 기다려요.</p>{snapshot.state.payment_rule?.scheduled.map(r=><p key={r.effective}>{r.effective}부터 {r.mode==="automatic"?"자동 지급":"매주 승인"}</p>)}<button className="mk-button secondary" disabled={busy||!approval} onClick={()=>void run(async()=>{const state=await api(`/children/${snapshot.child.id}/payment-rule`,{mode:snapshot.state.payment_rule?.current==="automatic"?"manual":"automatic",approved:true}) as State;setSnapshot(s=>s?{...s,state}:s);})}>부모 동의 후 다음 주 지급 방식 변경</button></details>
        <details className="mk-reward-policy"><summary>이자 규칙과 이전 기록</summary><p>10%는 교육용 보상률이며 실제 은행의 일반적인 예금 금리가 아니에요. 마감 금액은 고정되고 같은 주 이자는 한 번만 받아요. 용돈 이자는 상한 없이 1원 미만을 버려요. 저금통 이자는 2%·주간 상한 2,000원으로 별도 계산해요.</p><ul>{paid.map(t=><li key={t.id}>{t.created.slice(0,10)} · 이전 용돈 이자 {won(t.wallet)}</li>)}</ul></details>
      </div>}
      {panel==="reset"&&<section aria-describedby="trial-reset-description"><Izani mood="help"/><p id="trial-reset-description">체험한 내용만 처음 상태로 돌아가요.</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>void action("reset")}>확인하고 초기화</button><button className="mk-button secondary" disabled={busy} onClick={()=>setPanel("")}>계속 체험하기</button></div></section>}
    </TrialSheet>}
  </div>;
  return <ChildExperience key={snapshot.child.id} child={snapshot.child} state={snapshot.state} api={api} run={run} busy={busy} error={error} demo onLock={exit} onDismissError={()=>{setError("");setMessage("");}} onState={state=>setSnapshot(s=>s?{...s,state}:s)} onTransact={transact} trialControls={controls} trialAllowance={<button className="mk-quick-bank" disabled={busy} onClick={openBank}><span aria-hidden="true">↓</span>용돈 받기</button>} trialCelebrating={celebrating} trialMessage={message} trialReceipt={receipt&&<section className="mk-change-receipt" aria-label="거래 전후 변화"><h2>{receipt.title}</h2><dl>{([ ["남은 용돈",receipt.before.wallet,receipt.after.wallet],["예상 용돈 이자",receipt.before.rewards?.estimates.allowance_bonus??0,receipt.after.rewards?.estimates.allowance_bonus??0],["저금통",receipt.before.vault,receipt.after.vault],["예상 저금통 이자",receipt.before.rewards?.estimates.savings_interest??0,receipt.after.rewards?.estimates.savings_interest??0],["엄마 은행",receipt.before.education?.parent_balance??0,receipt.after.education?.parent_balance??0] ] as const).filter(([,before,after])=>before!==after).map(([label,before,after])=><div key={label}><dt>{label}</dt><dd>{won(before)} → {won(after)}</dd></div>)}</dl><p>필요한 곳에는 쓰고, 남은 돈도 잘 관리해 보자.</p></section>}/>;
}
