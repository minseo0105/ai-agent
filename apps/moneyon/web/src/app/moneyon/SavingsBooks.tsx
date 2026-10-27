"use client";
import {useRef,useState} from "react";
import TrialSheet from "./TrialSheet";
import Izani from "./Izani";
import AiCoach, { CoachButton } from "./AiCoach";
import type { AiStream } from "./AiCard";
import type {MoneyApi,RunAction,State} from "./types";
import "./interest.css";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
// 아이 눈높이 목표. 이름·아이콘이 함께 채워지고, '직접 입력'은 이름을 비워 아이가 쓴다.
// 아이콘은 서버 허용 목록(services/moneyon_savings.py ICONS)과 같아야 한다.
const GOALS=[{label:"장난감",icon:"🧸"},{label:"자전거·킥보드",icon:"🚲"},{label:"책·학용품",icon:"📚"},{label:"엄마·아빠 생일 선물",icon:"🎂"},{label:"친구 선물",icon:"🎁"}] as const;
const CUSTOM="직접 입력",TARGETS=[10000,30000,50000];

// 이름·목표가 미리 채워진 한 장짜리 개설 화면. 만들면 바로 쓰는 게 아니라 엄마 승인을 기다린다(승인은 TrialExperience).
export function BookWizard({child,api,run,busy,onState,onClose}:{child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onClose:()=>void}){
  const [done,setDone]=useState(false),[goal,setGoal]=useState<string>(GOALS[0].label),[name,setName]=useState<string>(GOALS[0].label),[target,setTarget]=useState("30000"),[icon,setIcon]=useState<string>(GOALS[0].icon),[color,setColor]=useState("blue"),[nickname,setNickname]=useState("");
  const request=useRef(crypto.randomUUID());
  const pick=(label:string)=>{setGoal(label);const g=GOALS.find(x=>x.label===label);if(g){setName(g.label);setIcon(g.icon);}else{setName("");setIcon("⭐");}};
  return <TrialSheet title="새 저축통장 만들기" onClose={onClose}>
    {!done?<form className="mk-panel" onSubmit={e=>{e.preventDefault();void run(async()=>{const state=await api(`/children/${child}/books`,{name:name.trim(),target:Number(target),icon,color,nickname,key:request.current}) as State;onState(state);setDone(true);});}}>
      <div className="mk-goal-choices" role="group" aria-label="무엇을 위해 모을까요?">{[...GOALS.map(g=>g.label),CUSTOM].map(l=><button type="button" key={l} aria-pressed={goal===l} onClick={()=>pick(l)}>{GOALS.find(g=>g.label===l)?.icon??"✏️"} {l}</button>)}</div>
      <label>통장 이름<input required maxLength={30} value={name} placeholder="무엇을 위해 모을까요?" autoFocus={goal===CUSTOM} onChange={e=>setName(e.target.value)}/></label>
      <label>모으고 싶은 돈<input required type="number" inputMode="numeric" min={100} max={10000000} step={100} value={target} onChange={e=>setTarget(e.target.value)}/></label>
      <div className="mk-amount-presets" aria-label="목표 금액 고르기">{TARGETS.map(n=><button type="button" key={n} aria-pressed={target===String(n)} onClick={()=>setTarget(String(n))}>{won(n)}</button>)}</div>
      <details className="mk-book-style"><summary>통장 꾸미기 (선택)</summary><div className="mk-filter" aria-label="통장 아이콘">{["🧸","🚲","📚","🎂","🎁","🎮","⭐","🐷","💝","✈️"].map(i=><button key={i} type="button" aria-pressed={icon===i} onClick={()=>setIcon(i)}>{i}</button>)}</div><label>통장 색상<select value={color} onChange={e=>setColor(e.target.value)}>{[["blue","블루"],["mint","민트"],["purple","보라"],["pink","분홍"]].map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label><label>통장 별명<input maxLength={20} value={nickname} onChange={e=>setNickname(e.target.value)}/></label></details>
      <button className="mk-button full" disabled={busy||!name.trim()}>통장 만들기</button>
    </form>:<section className="mk-panel mk-book-created mk-approval-sent" aria-live="polite"><Izani mood="greeting"/><h3>엄마에게 알림을 보냈어요 🔔</h3><p>{icon} {name} · 목표 {won(Number(target))}</p><p className="mk-caption">엄마가 승인하면 이 통장을 쓸 수 있어요. 기다리는 동안은 &lsquo;엄마 승인 기다리는 중&rsquo;으로 보여요.</p>
      <div className="mk-main-actions"><button type="button" className="mk-button" onClick={onClose}>확인</button></div>
    </section>}
  </TrialSheet>;
}

export default function SavingsBooks({state,child,api,run,busy,onState,onTransfer,aiStream}:{state:State;child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void;onTransfer:(id:string,kind:"deposit"|"withdraw")=>void;aiStream?:AiStream}){
 const [open,setOpen]=useState(false);
 const [coach,setCoach]=useState("");
 const coachBook=state.books?.find(b=>b.id===coach&&b.status!=="pending");
 // 승인 기다리는 통장은 맨 위에 흐리게
 const books=[...(state.books??[])].sort((a,b)=>Number(b.status==="pending")-Number(a.status==="pending"));
 return <section className="mk-section"><div className="mk-section-title"><h2>나의 저축통장</h2><button className="mk-text-button" onClick={()=>setOpen(true)}>+ 새 저축통장 만들기</button></div>
 {books.map(b=>b.status==="pending"
  ?<article className={`mk-goal mk-book mk-book-${b.color} mk-book-pending`} key={b.id} aria-label={`${b.name} 승인 대기`}><div><span aria-hidden="true">{b.icon}</span><h3>{b.name}</h3></div>{b.nickname&&<p>{b.nickname}</p>}<p>목표 <span>{won(b.target)}</span></p><p className="mk-pending-badge" role="status" data-testid="book-pending">⏳ 엄마 승인 기다리는 중</p></article>
  :<article className={`mk-goal mk-book mk-book-${b.color}`} key={b.id}><div><span aria-hidden="true">{b.icon}</span><h3>{b.name}</h3><span>{Math.min(100,Math.floor(b.balance/b.target*100))}%</span></div>{b.nickname&&<p>{b.nickname}</p>}<progress value={Math.min(b.balance,b.target)} max={b.target} aria-label={`${b.name} 달성률`}/><p>{won(b.balance)} <span>/ {won(b.target)}</span></p><p className="mk-caption">다음 주 예상 저축 이자 {won(b.interest??0)}</p><div className="mk-main-actions"><button className="mk-button" disabled={busy} onClick={()=>onTransfer(b.id,"deposit")}>저금하기</button><button className="mk-button secondary" disabled={busy||b.balance<100} onClick={()=>onTransfer(b.id,"withdraw")}>꺼내기</button></div>{aiStream&&b.balance<b.target&&<CoachButton onOpen={()=>setCoach(b.id)}/>}<details><summary>저축 내역과 받은 이자</summary><ul>{b.history.map(t=><li key={t.id}>{t.created.slice(0,10)} · {t.kind==="savings_interest"?"저축 이자":t.amount>0?"저금":"꺼냄"} {won(t.amount)}</li>)}</ul></details></article>)}
 {aiStream&&coachBook&&<AiCoach book={coachBook} stream={aiStream} onClose={()=>setCoach("")}/>}
 {open&&<BookWizard child={child} api={api} run={run} busy={busy} onState={onState} onClose={()=>setOpen(false)}/>}
 </section>;
}
