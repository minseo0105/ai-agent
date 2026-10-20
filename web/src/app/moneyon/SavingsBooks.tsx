"use client";
import {useRef,useState} from "react";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import type {MoneyApi,RunAction,State} from "./types";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";

export function BookWizard({child,api,run,busy,onState,onClose,onCreated}:{child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onClose:()=>void;onCreated?:(id:string)=>void}){
  const [step,setStep]=useState(1),[name,setName]=useState(""),[target,setTarget]=useState(""),[icon,setIcon]=useState("🐷"),[color,setColor]=useState("blue"),[nickname,setNickname]=useState("");
  const request=useRef(crypto.randomUUID()),created=useRef("");
  return <TrialSheet title="새 저축통장 만들기" onClose={onClose}><p className="mk-caption">{step}/4 · 교육용 가상 저축통장</p>
    <form className="mk-panel" onSubmit={e=>{e.preventDefault();if(step<3){setStep(step+1);return;}if(step===4){onCreated?.(created.current);onClose();return;}void run(async()=>{const state=await api(`/children/${child}/books`,{name,target:Number(target),icon,color,nickname,key:request.current}) as State;created.current=state.books!.find(b=>b.request_key===request.current)?.id??state.books!.at(-1)!.id;onState(state);setStep(4);});}}>
      {step===1&&<><h3>통장 이름을 정해 볼까?</h3><div className="mk-amount-presets">{["닌텐도 모으기","여행 자금","갖고 싶은 장난감","미래의 내 꿈"].map(n=><button type="button" key={n} onClick={()=>setName(n)}>{n}</button>)}</div><label>통장 이름<input required maxLength={30} value={name} onChange={e=>setName(e.target.value)}/></label></>}
      {step===2&&<><h3>얼마를 모으고 싶어?</h3><label>목표 금액<input required type="number" inputMode="numeric" min={100} max={10000000} step={100} value={target} onChange={e=>setTarget(e.target.value)}/></label><p className="mk-caption">100원 단위로 정해요. 새 통장은 0원부터 시작하며 기존 저축은 그대로 남아요.</p></>}
      {step===3&&<><h3>나만의 통장 꾸미기</h3><div className="mk-filter" aria-label="통장 아이콘">{["🐷","🎮","✈️","🎁","⭐"].map(i=><button key={i} type="button" aria-pressed={icon===i} onClick={()=>setIcon(i)}>{i}</button>)}</div><label>통장 색상<select value={color} onChange={e=>setColor(e.target.value)}>{[["blue","블루"],["mint","민트"],["purple","보라"],["pink","분홍"]].map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label><label>통장 별명 (선택)<input maxLength={20} value={nickname} onChange={e=>setNickname(e.target.value)}/></label></>}
      {step===4&&<><Izani mood="celebration"/><h3>축하해! 너만의 저축통장이 생겼어!</h3><p>{icon} {name} · 목표 {won(Number(target))}</p></>}
      <div className="mk-main-actions">{step>1&&step<4&&<button type="button" className="mk-button secondary" disabled={busy} onClick={()=>setStep(step-1)}>이전</button>}<button className="mk-button" disabled={busy}>{step===4?"통장 보기":step===3?"통장 개설하기":"다음"}</button></div>
    </form></TrialSheet>;
}

export default function SavingsBooks({state,child,api,run,busy,onState,onTransfer}:{state:State;child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onTransfer:(id:string,kind:"deposit"|"withdraw")=>void}){
 const [open,setOpen]=useState(false);
 return <section className="mk-section"><div className="mk-section-title"><h2>나의 저축통장</h2><button className="mk-text-button" onClick={()=>setOpen(true)}>+ 새 저축통장 만들기</button></div>
 {state.books?.map(b=><article className={`mk-goal mk-book mk-book-${b.color}`} key={b.id}><div><span aria-hidden="true">{b.icon}</span><h3>{b.name}</h3><span>{Math.min(100,Math.floor(b.balance/b.target*100))}%</span></div>{b.nickname&&<p>{b.nickname}</p>}<progress value={Math.min(b.balance,b.target)} max={b.target} aria-label={`${b.name} 달성률`}/><p>{won(b.balance)} <span>/ {won(b.target)}</span></p><p className="mk-caption">다음 주 예상 저금통 이자 {won(b.interest??0)}</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>onTransfer(b.id,"deposit")}>입금하기</button><button className="mk-button secondary" disabled={busy||b.balance<100} onClick={()=>onTransfer(b.id,"withdraw")}>꺼내기</button></div><details><summary>저축 내역과 받은 이자</summary><ul>{b.history.map(t=><li key={t.id}>{t.created.slice(0,10)} · {t.kind==="savings_interest"?"저금통 이자":t.amount>0?"입금":"출금"} {won(t.amount)}</li>)}</ul></details></article>)}
 {open&&<BookWizard child={child} api={api} run={run} busy={busy} onState={onState} onClose={()=>setOpen(false)}/>}
 </section>;
}
