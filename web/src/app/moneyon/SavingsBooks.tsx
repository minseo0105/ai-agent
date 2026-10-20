"use client";
import {useRef,useState} from "react";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import {PracticeNote} from "./WeeklyJourney";
import type {MoneyApi,RunAction,State} from "./types";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
const NAMES=["여행 자금","닌텐도 모으기","갖고 싶은 장난감","미래의 내 꿈"],TARGETS=[10000,30000,50000],DEPOSITS=[1000,3000,5000];

// 이름·목표가 미리 채워진 한 장짜리 개설 화면. onDeposit이 있으면 개설 직후 같은 화면에서 바로 저금한다.
export function BookWizard({child,api,run,busy,onState,onClose,onCreated,onDeposit,wallet=0}:{child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onClose:()=>void;onCreated?:(id:string)=>void;onDeposit?:(id:string,amount:number)=>Promise<boolean>;wallet?:number}){
  const [done,setDone]=useState(false),[name,setName]=useState(NAMES[0]),[target,setTarget]=useState("30000"),[icon,setIcon]=useState("🐷"),[color,setColor]=useState("blue"),[nickname,setNickname]=useState("");
  const affordable=DEPOSITS.filter(n=>n<=wallet);
  const [deposit,setDeposit]=useState(String(affordable.includes(3000)?3000:affordable.at(-1)??""));
  const request=useRef(crypto.randomUUID()),created=useRef("");
  return <TrialSheet title="새 저축통장 만들기" onClose={onClose}>
    {!done?<form className="mk-panel" onSubmit={e=>{e.preventDefault();void run(async()=>{const state=await api(`/children/${child}/books`,{name,target:Number(target),icon,color,nickname,key:request.current}) as State;created.current=state.books!.find(b=>b.request_key===request.current)?.id??state.books!.at(-1)!.id;onState(state);onCreated?.(created.current);setDone(true);});}}>
      <label>통장 이름<input required maxLength={30} value={name} onChange={e=>setName(e.target.value)}/></label>
      <div className="mk-amount-presets" aria-label="통장 이름 고르기">{NAMES.map(n=><button type="button" key={n} aria-pressed={name===n} onClick={()=>setName(n)}>{n}</button>)}</div>
      <label>모으고 싶은 돈<input required type="number" inputMode="numeric" min={100} max={10000000} step={100} value={target} onChange={e=>setTarget(e.target.value)}/></label>
      <div className="mk-amount-presets" aria-label="목표 금액 고르기">{TARGETS.map(n=><button type="button" key={n} aria-pressed={target===String(n)} onClick={()=>setTarget(String(n))}>{won(n)}</button>)}</div>
      <details className="mk-book-style"><summary>통장 꾸미기 (선택)</summary><div className="mk-filter" aria-label="통장 아이콘">{["🐷","🎮","✈️","🎁","⭐"].map(i=><button key={i} type="button" aria-pressed={icon===i} onClick={()=>setIcon(i)}>{i}</button>)}</div><label>통장 색상<select value={color} onChange={e=>setColor(e.target.value)}>{[["blue","블루"],["mint","민트"],["purple","보라"],["pink","분홍"]].map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label><label>통장 별명<input maxLength={20} value={nickname} onChange={e=>setNickname(e.target.value)}/></label></details>
      <p className="mk-caption">100원 단위로 정해요. 새 통장은 0원부터 시작하고, 원래 있던 저축은 그대로 남아요.</p>
      <button className="mk-button full" disabled={busy}>통장 만들기</button>
    </form>:<section className="mk-panel mk-book-created" aria-live="polite"><Izani mood="celebration"/><h3>축하해! 너만의 저축통장이 생겼어!</h3><p>{icon} {name} · 목표 {won(Number(target))}</p>
      {onDeposit&&affordable.length?<form onSubmit={e=>{e.preventDefault();void onDeposit(created.current,Number(deposit)).then(onClose);}}><h4>이 통장에 바로 저금해 볼까?</h4><div className="mk-amount-presets" aria-label="저금할 돈 고르기">{affordable.map(n=><button type="button" key={n} aria-pressed={deposit===String(n)} onClick={()=>setDeposit(String(n))}>{won(n)}</button>)}</div><PracticeNote/><div className="mk-main-actions"><button className="mk-button" disabled={busy||!deposit}>{won(Number(deposit))} 저금하기</button><button type="button" className="mk-button secondary" onClick={onClose}>나중에</button></div></form>
      :<div className="mk-main-actions"><button type="button" className="mk-button" onClick={onClose}>통장 보기</button></div>}
    </section>}
  </TrialSheet>;
}

export default function SavingsBooks({state,child,api,run,busy,onState,onTransfer,onDeposit}:{state:State;child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onTransfer:(id:string,kind:"deposit"|"withdraw")=>void;onDeposit?:(id:string,amount:number)=>Promise<boolean>}){
 const [open,setOpen]=useState(false);
 return <section className="mk-section"><div className="mk-section-title"><h2>나의 저축통장</h2><button className="mk-text-button" onClick={()=>setOpen(true)}>+ 새 저축통장 만들기</button></div>
 {state.books?.map(b=><article className={`mk-goal mk-book mk-book-${b.color}`} key={b.id}><div><span aria-hidden="true">{b.icon}</span><h3>{b.name}</h3><span>{Math.min(100,Math.floor(b.balance/b.target*100))}%</span></div>{b.nickname&&<p>{b.nickname}</p>}<progress value={Math.min(b.balance,b.target)} max={b.target} aria-label={`${b.name} 달성률`}/><p>{won(b.balance)} <span>/ {won(b.target)}</span></p><p className="mk-caption">다음 주 예상 저축 이자 {won(b.interest??0)}</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>onTransfer(b.id,"deposit")}>저금하기</button><button className="mk-button secondary" disabled={busy||b.balance<100} onClick={()=>onTransfer(b.id,"withdraw")}>꺼내기</button></div><details><summary>저축 내역과 받은 이자</summary><ul>{b.history.map(t=><li key={t.id}>{t.created.slice(0,10)} · {t.kind==="savings_interest"?"저축 이자":t.amount>0?"저금":"꺼냄"} {won(t.amount)}</li>)}</ul></details></article>)}
 {open&&<BookWizard child={child} api={api} run={run} busy={busy} onState={onState} onDeposit={onDeposit} wallet={state.wallet} onClose={()=>setOpen(false)}/>}
 </section>;
}
