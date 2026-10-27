"use client";
import { useEffect, useRef, useState } from "react";
import { API_URL, apiFetch } from "@/lib/access";
import ChildExperience from "./ChildExperience";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import RewardSaving from "./RewardSaving";
import { PRACTICE, PracticeNote, monthDay, weekRange } from "./WeeklyJourney";
import { FROM, formula } from "./TrialHome";
import type { Child, ChildTransaction, State } from "./types";
import AiCard, { type AiFeature, type AiStream } from "./AiCard";

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

export default function TrialExperience({onExit,startDemo=false}:{onExit:()=>void;startDemo?:boolean}) {
  // AI 기능(오라클): 서버가 켠 기능만 보인다. 꺼져 있으면 화면은 예전과 같다.
  const [aiFeatures,setAiFeatures]=useState<AiFeature[]>([]);
  useEffect(()=>{let live=true;void apiFetch(`${API_URL}/api/moneyon/trial/ai/config`).then(r=>r.ok?r.json():null).then(c=>{if(live&&c?.enabled)setAiFeatures(c.features);}).catch(()=>{});return()=>{live=false;};},[]);
  const aiStream:AiStream=(feature,body,signal)=>apiFetch(`${API_URL}/api/moneyon/trial/ai/${feature}`,{method:"POST",signal,timeoutMs:30000,headers:{"Content-Type":"application/json","X-Moneyon-Trial":credentials.current.token,"X-Moneyon-Trial-Version":String(credentials.current.generation)},body:JSON.stringify(body)});
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[expired,setExpired]=useState(false);
  // amount: 엄마 화면에서 보낼 용돈(10,000원으로 시작).
  const [panel,setPanel]=useState(""),[amount,setAmount]=useState("10000"),[message,setMessage]=useState("");
  const [rewardTab,setRewardTab]=useState<"allowance_bonus"|"savings_interest">("allowance_bonus");
  const [celebrating,setCelebrating]=useState(false);
  // 시간을 옮기거나 이자를 받은 직후의 한 줄 장면: 무슨 일이 있었는지와 들어온 이자(통장별).
  const [scene,setScene]=useState<{headline:string;wallet:number;vault:number}|null>(null);
  useEffect(()=>{
    if(scene)document.querySelector<HTMLDialogElement>('.mk-sheet')?.scrollTo({top:0,behavior:"instant"});
  },[scene]);
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
  async function run(action:()=>Promise<void>){if(running.current)return;running.current=true;setBusy(true);setError("");setMessage("");setCelebrating(false);setScene(null);try{await action();}catch(e){fail(e);}finally{running.current=false;setBusy(false);}}
  useEffect(()=>{
    let current=true;
    async function open(){
      try{
        // 시연 모드: 저장된 체험 대신 시연 데이터가 채워진 새 체험 통장(각자 자기 복사본)
        if(startDemo)sessionStorage.removeItem(TRIAL_STORAGE);
        credentials.current.token=sessionStorage.getItem(TRIAL_STORAGE)||"";
        const next:Snapshot=await api(credentials.current.token?"/state":startDemo?"/demo":"/start",credentials.current.token?undefined:{});
        if(!current)return;
        if(next.token){credentials.current.token=next.token;sessionStorage.setItem(TRIAL_STORAGE,next.token);}
        apply(next);
      }catch(e){if(current)fail(e);}finally{if(current)setBusy(false);}
    }
    void open();return()=>{current=false;};
  },[]);
  function exit(){sessionStorage.removeItem(TRIAL_STORAGE);onExit();}
  function key(signature:string){if(retry.current?.signature!==signature)retry.current={signature,key:crypto.randomUUID()};return retry.current.key;}

  async function transact(payload:ChildTransaction){let ok=false;await run(async()=>{const state=await api(`/children/${snapshot!.child.id}/transactions`,{...payload,key:key(JSON.stringify(payload))});retry.current=null;setSnapshot(s=>s?{...s,state}:s);setMessage(payload.kind==="expense"?`${payload.category?payload.category+"에 ":""}${won(payload.amount)}을 썼다고 적었어!`:payload.kind==="deposit"?`저축통장에 ${won(payload.amount)} 저금했어!`:`내 용돈통장으로 ${won(payload.amount)} 꺼냈어!`);ok=true;});return ok;}
  async function action(kind:"allowance"|"date"|"month"|"claim"|"reset"){
    await run(async()=>{
      const body=kind==="allowance"?{amount:Number(amount),key:key("allowance:"+amount)}:kind==="date"?{day:nextWeek(snapshot!.day)}:kind==="month"?{day:addDays(snapshot!.day,28)}:kind==="claim"?{key:key("claim:"+snapshot!.day+":"+snapshot!.generation)}:{key:key("reset:"+snapshot!.generation)};
      const next:Snapshot=await api(kind==="reset"?"/reset":`/children/${snapshot!.child.id}/${kind==="month"?"date":kind}`,body);
      const interest=(s:State)=>s.transactions.filter(t=>t.kind==="allowance_bonus"||t.kind==="savings_interest");
      const sum=(s:State,to:"wallet"|"vault")=>interest(s).reduce((n,t)=>n+t[to],0);
      const wallet=Math.max(0,sum(next.state,"wallet")-sum(snapshot!.state,"wallet")),vault=Math.max(0,sum(next.state,"vault")-sum(snapshot!.state,"vault"));
      const travel=kind==="date"||kind==="month",waiting=(next.state.rewards?.items??[]).some(i=>i.status==="awaiting_approval");
      apply(next);retry.current=null;
      // 시간을 옮기면 먼저 "이번 주 정산"을 보여주고, 아이가 "이자 받기"를 눌러야 통장에 들어온다.
      if(kind==="claim"){setScene({headline:wallet+vault?`이자 ${won(wallet+vault)}이 들어왔어요!`:"정산을 마쳤어요",wallet,vault});setCelebrating(wallet+vault>0);setPanel("reward");}
      else setPanel(travel&&waiting?"settle":"");
      setMessage(kind==="allowance"?`엄마가 용돈 ${won(Number(amount))}을 보내줬어!`:travel?`${kind==="month"?"한 달":"일주일"}이 지났어! 정산을 보고 이자를 받아 봐.`:kind==="claim"?(wallet+vault?`이자 ${won(wallet+vault)}이 들어왔어! 남은 용돈이 늘었지?`:"정산을 마쳤어!"):"처음 통장으로 돌아왔어!");
    });
  }
  // 만료·재시작은 저장된 체험을 지우고, 잠깐 바쁜 오류는 체험을 남겨 두어 다시 들어오면 이어진다.
  if(expired)return <TrialStatus error={EXPIRED} onExit={exit}/>;
  if(!snapshot)return busy?<TrialStatus/>:<TrialStatus error={error} onExit={onExit}/>;
  const state=snapshot.state;
  const paid=state.transactions.filter(t=>t.kind==="interest");
  const items=state.rewards?.items??[];
  const waiting=items.filter(i=>i.status==="awaiting_approval");
  const pendingTotal=waiting.reduce((n,i)=>n+i.amount,0);
  const weeks=[...new Set(waiting.map(i=>i.cycle_id))].map(id=>({id,allowance:waiting.find(i=>i.cycle_id===id&&i.reward_type==="allowance_bonus"),saving:waiting.find(i=>i.cycle_id===id&&i.reward_type==="savings_interest")}));
  const spentIn=(start:string,end:string)=>-state.transactions.filter(t=>(t.kind==="expense"||t.kind==="expense_cancel")&&start<=t.created.slice(0,10)&&t.created.slice(0,10)<end).reduce((n,t)=>n+t.wallet,0);
  const openReward=()=>{setPanel("reward");setRewardTab("allowance_bonus");setMessage("");setCelebrating(false);setScene(null);};
  const openSettle=()=>{setPanel("settle");setScene(null);};
  // 체험 도구: 시간 이동·초기화는 아이 홈이 아니라 발표자용 작은 메뉴에. 체험마다 날짜가 따로라 다른 사람에게는 영향이 없다.
  const toolsButton=<button className="mk-tools-button" aria-label="체험 도구" onClick={()=>setPanel("tools")}><span aria-hidden="true">🧰</span></button>;
  const sent=state.transactions.filter(t=>t.kind==="payment"||t.kind==="allowance_bonus"||t.kind==="savings_interest").sort((x,y)=>y.created.localeCompare(x.created)).slice(0,3);
  const parentView=<section className="mk-parent-view" aria-label="엄마 화면">
    <p className="mk-caption">엄마가 쓰는 화면이에요(체험). 아이에게 용돈을 보내면 아이 기록에 &lsquo;엄마가 보내줬어요&rsquo;로 남아요.</p>
    {aiFeatures.includes("parent")&&<AiCard feature="parent" stream={aiStream} audience="parent" title="이번 주 리포트" button="이번 주 리포트 받기" again="리포트 다시 받기" className="mk-ai-parent"/>}
    <div className="mk-parent-balance"><span>엄마 통장</span><strong data-testid="parent-balance">{won(state.education?.parent_balance??0)}</strong></div>
    <form className="mk-spend-form" onSubmit={e=>{e.preventDefault();void action("allowance");}}>
      <label>아이에게 보낼 용돈<span className="mk-bank-amount"><input required type="number" inputMode="numeric" min={100} max={10000000} step={100} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label>
      <div className="mk-amount-presets">{[3000,10000,30000].map(n=><button type="button" key={n} aria-pressed={amount===String(n)} onClick={()=>setAmount(String(n))}>{won(n)}</button>)}</div>
      <button className="mk-button full" disabled={busy}>{won(Number(amount)||0)} 보내기</button>
    </form>
    <section className="mk-week-records"><div className="mk-section-title"><h2>최근에 보낸 돈</h2></div><ul>{sent.map(t=><li key={t.id}><span className="mk-record-icon" aria-hidden="true">{t.kind==="payment"?"💸":"✨"}</span><span className="mk-record-name">{t.kind==="payment"?"용돈을 보냈어요":t.kind==="allowance_bonus"?"용돈 이자를 보냈어요":"저축 이자를 보냈어요"}<small>{monthDay(t.created.slice(0,10))}</small></span><span className="mk-record-amount">{won(t.wallet+t.vault)}</span></li>)}</ul></section>
  </section>;
  const settle=<div className="mk-settle">
    {weeks.length===1?(()=>{const w=weeks[0],item=w.allowance??w.saving!;return <>
      <p className="mk-settle-week">{weekRange(item.start,item.end)} 정산</p>
      <dl className="mk-settle-sum"><div><dt>이번 주 쓴 돈</dt><dd>−{won(spentIn(item.start,item.end))}</dd></div><div><dt>남은 용돈</dt><dd>{won(w.allowance?.base??0)}</dd></div></dl>
    </>;})():<p className="mk-settle-week">{weeks.length}주 정산이 밀려 있어요</p>}
    <ul className="mk-settle-lines">{weeks.map(w=>[w.allowance,w.saving].map(i=>i&&<li key={i.cycle_id+i.reward_type}><span>{weeks.length>1&&<small>{weekRange(i.start,i.end)}</small>}{i.reward_type==="allowance_bonus"?"용돈 이자":"저축 이자"}<small>{i.amount?formula(i):FROM[i.reward_type]}</small></span><b>{won(i.amount)}</b></li>))}</ul>
    <p className="mk-caption">100원 미만은 버려요.</p>
    <PracticeNote/>
    <button className="mk-button full" disabled={busy} onClick={()=>void action("claim")}>{pendingTotal?`이자 ${won(pendingTotal)} 받기`:"확인"}</button>
  </div>;
  const sheet=panel&&<TrialSheet title={panel==="settle"?"이번 주 정산":panel==="reward"?(scene?"이자 받기":"이자 기록"):panel==="tools"?"체험 도구":"처음 상태로 돌아가기"} onClose={()=>setPanel("")}>
      {error&&<p className="mk-sheet-error" role="alert">{error}</p>}
      {panel==="settle"&&settle}
      {panel==="tools"&&<div className="mk-tools">
        <p className="mk-caption">발표·시연용 도구예요. 체험 속 날짜 {monthDay(snapshot.day)} · 실제 날짜와 달라요. 시간을 옮겨도 다른 사람 체험에는 영향이 없어요.</p>
        <button className="mk-button full" disabled={busy||nextWeek(snapshot.day)>LAST_DAY} onClick={()=>void action("date")}>일주일 뒤 보기</button>
        <button className="mk-button secondary full" disabled={busy||addDays(snapshot.day,28)>LAST_DAY} onClick={()=>void action("month")}>한 달 뒤 보기</button>
        <button className="mk-text-button" disabled={busy} onClick={()=>setPanel("reset")}>처음 상태로 돌아가기</button>
        <details className="mk-reward-policy"><summary>체험 기록은 언제까지 남나요?</summary><p>새로고침하면 24시간 동안 이어져요. 일반 새 탭·다른 브라우저는 새 체험이에요. 복제·복원 탭은 같은 체험과 초기화를 공유할 수 있어요.</p>{process.env.NEXT_PUBLIC_MONEYON_EPHEMERAL==="1"&&<p>Hugging Face Space 서버가 다시 만들어지거나 재배포되면 체험 기록이 사라질 수 있어요.</p>}</details>
      </div>}
      {panel==="reward"&&<div className="mk-reward-flow">
        {scene&&<><section className="mk-paid-celebration" role="status"><Izani mood={scene.wallet+scene.vault?"celebration":"greeting"}/><h3>{scene.headline}</h3>{scene.wallet+scene.vault>0&&<><strong className="mk-arrived">+{won(scene.wallet+scene.vault)}</strong><p>{[scene.wallet&&`용돈통장 +${won(scene.wallet)}`,scene.vault&&`저축통장 +${won(scene.vault)}`].filter(Boolean).join(" · ")}</p></>}</section>
        <button className="mk-button full" onClick={()=>setPanel("")}>확인</button></>}
        {(()=>{const detail=<>
        {!scene&&waiting.length>0&&<button className="mk-button full" onClick={openSettle}>{`이자 ${won(pendingTotal)} 받기`}</button>}
        <div className="mk-filter" aria-label="이자 종류">{([['allowance_bonus','용돈 이자'],['savings_interest','저축 이자']] as const).map(([key,label])=><button key={key} aria-pressed={rewardTab===key} onClick={()=>setRewardTab(key)}>{label}</button>)}</div>
        <p className="mk-caption">{rewardTab==="allowance_bonus"?"남긴 용돈의 10%를 다음 주 내 용돈통장으로 받아요.":"저축통장에 모은 돈은 2%를 따로 계산해서 저축통장으로 받아요."} 정산 뒤 &lsquo;이자 받기&rsquo;를 눌러야 내 돈이 돼요.</p>{!scene&&<PracticeNote/>}
        <ul className="mk-reward-items">{items.filter(i=>i.reward_type===rewardTab).map(item=><li key={item.cycle_id+item.reward_type} data-payment-state={item.status}><div className="mk-reward-item-head"><small>{weekRange(item.start,item.end)}</small><span>{item.status==="paid"?"들어왔어요":item.status==="awaiting_approval"?"받기를 기다려요":"쌓이는 중"}</span></div><p>{item.amount||item.status==="paid"?formula(item):FROM[item.reward_type]}</p><strong>{item.status==="paid"?"받은 이자 ":item.status==="awaiting_approval"?"정해진 이자 ":"예상 이자 "}{won(item.status==="paid"?item.paid_amount:item.amount)}</strong><small>{item.destination==="wallet"?"엄마 통장 → 내 용돈통장":"엄마 통장 → 저축통장"}{item.paid_at&&` · ${monthDay(item.paid_at.slice(0,10))} 들어옴`}</small></li>)}</ul>
        {state.payout_choices?.map(p=><RewardSaving key={p.payout} payout={p} state={state} child={snapshot.child.id} api={api} run={run} busy={busy} onState={next=>setSnapshot(s=>s?{...s,state:next}:s)}/>)}
        <details className="mk-reward-policy"><summary>이자 규칙과 이전 기록</summary><p>{PRACTICE}. 월요일에 정해진 금액은 바뀌지 않고, 같은 주 이자는 한 번만 받아요. 이자는 100원 미만을 버려요({FROM.allowance_bonus}, {FROM.savings_interest}). 저축 이자는 2%이고 한 주에 최대 2,000원까지예요.</p><ul>{paid.map(t=><li key={t.id}>{t.created.slice(0,10)} · 이전 용돈 이자 {won(t.wallet)}</li>)}</ul></details>
        </>;return scene?<details className="mk-reward-more"><summary>이자 자세히 보기</summary>{detail}</details>:detail;})()}
      </div>}
      {panel==="reset"&&<section aria-describedby="trial-reset-description"><Izani mood="help"/><p id="trial-reset-description">체험한 내용만 처음 상태로 돌아가요.</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>void action("reset")}>확인하고 초기화</button><button className="mk-button secondary" disabled={busy} onClick={()=>setPanel("")}>계속 체험하기</button></div></section>}
    </TrialSheet>;
  return <ChildExperience key={snapshot.child.id} child={snapshot.child} state={state} api={api} run={run} busy={busy} error={error} demo onLock={exit} onDismissError={()=>{setError("");setMessage("");}} onState={next=>setSnapshot(s=>s?{...s,state:next}:s)} onTransact={transact} trialControls={toolsButton} trialParent={parentView} trialPending={waiting.length?pendingTotal:null} onSettle={openSettle} trialRecords={<button type="button" className="mk-text-button" onClick={openReward}>이자 기록 보기</button>} trialOverlay={sheet} trialCelebrating={celebrating} onHome={onExit} trialMessage={message}
    trialLetter={aiFeatures.includes("letter")?<AiCard feature="letter" stream={aiStream} title="꿀벌의 주간 편지" button="꿀벌 편지 받기" again="편지 다시 받기" className="mk-ai-letter"/>:undefined}
    aiStream={aiFeatures.includes("coach")?aiStream:undefined}/>;
}
