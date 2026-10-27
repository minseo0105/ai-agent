"use client";
import {useRef,useState} from "react";
import Izani from "./Izani";
import {BookWizard} from "./SavingsBooks";
import type {State,MoneyApi,RunAction,PayoutChoice} from "./types";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
export default function RewardSaving({payout,state,child,api,run,busy,onState}:{payout:PayoutChoice;state:State;child:string;api:MoneyApi;run:RunAction;busy:boolean;onState:(s:State)=>void}){
 const [choice,setChoice]=useState("keep"),[amount,setAmount]=useState(0),[book,setBook]=useState(state.books?.[0]?.id??""),[open,setOpen]=useState(false),[hint,setHint]=useState("");
 const request=useRef({signature:"",key:""});
 const max=Math.floor(Math.min(payout.available,state.wallet)/100)*100;
 const selected=choice==="all"?payout.amount:choice==="partial"?amount:0;
 function change(n:number){const normalized=Math.max(0,Math.min(max,Math.floor(n/100)*100));setAmount(normalized);setHint(n!==normalized?"100원 단위로 맞췄어요.":"");}
 return <section className="mk-panel mk-reward-saving" aria-label="받은 이자 저축하기"><Izani mood="celebration"/><h3>축하해! 이번 주 이자가 도착했어!</h3><p>이번에 받은 이자 <strong>{won(payout.amount)}</strong></p>
 {payout.choice?<p role="status">{payout.choice.choice==="keep"?"내 용돈통장에 그대로 두었어요.":`${won(payout.choice.amount)}을 저축했어요!`}</p>:<form onSubmit={e=>{e.preventDefault();void run(async()=>{const body={payout:payout.payout,choice,amount:selected,book_id:choice==="keep"?null:book};const signature=JSON.stringify(body);if(request.current.signature!==signature)request.current={signature,key:crypto.randomUUID()};onState(await api(`/children/${child}/reward-saving`,{...body,key:request.current.key}) as State);});}}>
 <label><input type="radio" name={`saving-${payout.payout}`} checked={choice==="all"} disabled={payout.available<payout.amount||state.wallet<payout.amount} onChange={()=>setChoice("all")}/>이자 전액 저축하기 · {won(payout.amount)}</label>
 <label><input type="radio" name={`saving-${payout.payout}`} checked={choice==="partial"} disabled={max<100} onChange={()=>{setChoice("partial");setAmount(Math.min(1000,max));}}/>원하는 금액만 저축하기</label>
 <label><input type="radio" name={`saving-${payout.payout}`} checked={choice==="keep"} onChange={()=>setChoice("keep")}/>내 용돈통장에 그대로 두기</label>
 {choice==="partial"&&<><label>저축할 이자<input type="number" required min={100} max={max} step={100} value={amount} onChange={e=>change(Number(e.target.value))}/></label><input aria-label="저축할 이자 조절" type="range" min={0} max={max} step={100} value={amount} onChange={e=>change(Number(e.target.value))}/><div className="mk-main-actions"><button type="button" onClick={()=>change(amount-100)}>-100원</button><button type="button" onClick={()=>change(amount+100)}>+100원</button></div><p role="status">{hint}</p></>}
 {choice!=="keep"&&<><label>저축할 통장<select required value={book} onChange={e=>setBook(e.target.value)}>{state.books?.filter(b=>b.status!=="pending").map(b=><option key={b.id} value={b.id}>{b.icon} {b.name}</option>)}</select></label><button type="button" className="mk-text-button" onClick={()=>setOpen(true)}>+ 새 저축통장 만들기</button><p>내 용돈통장 {won(state.wallet)} → {won(state.wallet-selected)}<br/>선택한 통장 {won(state.books?.find(b=>b.id===book)?.balance??0)} → {won((state.books?.find(b=>b.id===book)?.balance??0)+selected)}</p></>}
 <p className="mk-caption">저축은 선택이에요. 이미 쓴 이자는 다시 저축할 수 없고, 한 번 고른 이자는 두 번 저금되지 않아요.</p><button className="mk-button full" disabled={busy||(choice==="partial"&&amount<100)}>{choice==="keep"?"그대로 두고 계속하기":"선택한 이자 저축하기"}</button></form>}
 {payout.choice&&payout.choice.choice!=="keep"&&<p>받은 이자를 다시 저축했네! 돈을 모으는 습관이 생기고 있어!</p>}
 {open&&<BookWizard child={child} api={api} run={run} busy={busy} onState={onState} onClose={()=>setOpen(false)}/>}
 </section>;
}
