"use client";
import { useState } from "react";
import TrialSheet from "./TrialSheet";
import type { ChildTransaction, State } from "./types";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
export const CATEGORY_ICONS:Record<string,string>={간식:"🍪",문구:"✏️",장난감:"🧸",게임:"🎮",책:"📚",선물:"🎁",기타:"📦"};

// 금액 입력: 버튼이나 직접 입력, 100원 단위. 넘치거나 단위가 맞지 않으면 그 자리에서 알려준다.
function AmountField({label,amount,setAmount,max,presets}:{label:string;amount:string;setAmount:(v:string)=>void;max:number;presets:number[]}) {
  const value=Number(amount);
  const hint=!amount?"":value%100?"100원 단위로 적어요.":value>max?`${won(max)}까지 적을 수 있어요.`:"";
  return <>
    <label>{label}<span className="mk-bank-amount"><input type="number" inputMode="numeric" min={100} max={max} step={100} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label>
    <div className="mk-amount-presets">{presets.map(n=><button type="button" key={n} disabled={n>max} aria-pressed={amount===String(n)} onClick={()=>setAmount(String(n))}>{won(n)}</button>)}</div>
    {hint&&<p className="mk-caption" role="status">{hint}</p>}
  </>;
}
const ok=(amount:string,max:number)=>{const v=Number(amount);return v>=100&&v%100===0&&v<=max;};

// 쓴 돈 기록: 무엇에, 얼마를 썼는지 아이가 직접 고른다(미리 골라 두지 않음).
export function SpendSheet({wallet,busy,onClose,onSave}:{wallet:number;busy:boolean;onClose:()=>void;onSave:(p:ChildTransaction)=>Promise<boolean>}) {
  const [category,setCategory]=useState(""),[amount,setAmount]=useState("");
  const valid=!!category&&ok(amount,wallet);
  return <TrialSheet title="쓴 돈 기록하기" onClose={onClose}>
    <form className="mk-spend-form" onSubmit={e=>{e.preventDefault();if(valid)void onSave({kind:"expense",amount:Number(amount),category,note:category}).then(saved=>{if(saved)onClose();});}}>
      <fieldset><legend>무엇에 썼나요?</legend><div className="mk-category-grid">{Object.entries(CATEGORY_ICONS).map(([name,icon])=><button type="button" key={name} aria-pressed={category===name} onClick={()=>setCategory(name)}><span aria-hidden="true">{icon}</span>{name}</button>)}</div></fieldset>
      <AmountField label="얼마를 썼나요?" amount={amount} setAmount={setAmount} max={wallet} presets={[1000,3000,5000]}/>
      <button className="mk-button full" disabled={busy||!valid}>{ok(amount,wallet)?`${won(Number(amount))} 기록하기`:"기록하기"}</button>
    </form>
  </TrialSheet>;
}

// 저금하기: 내 용돈통장에서 저축통장으로. 통장이 여러 개면 고른다.
export function DepositSheet({state,busy,onClose,onSave}:{state:State;busy:boolean;onClose:()=>void;onSave:(p:ChildTransaction)=>Promise<boolean>}) {
  const books=state.books??[];
  const [book,setBook]=useState(books[0]?.id??"");
  const [amount,setAmount]=useState(state.wallet>=3000?"3000":"");
  const target=books.find(b=>b.id===book);
  return <TrialSheet title="저금하기" onClose={onClose}>
    <form className="mk-spend-form" onSubmit={e=>{e.preventDefault();if(ok(amount,state.wallet))void onSave({kind:"deposit",amount:Number(amount),book_id:book}).then(saved=>{if(saved)onClose();});}}>
      <p className="mk-bank-line">내 용돈통장 {won(state.wallet)} <span aria-hidden="true">→</span> {target?`${target.icon} ${target.name}`:"저축통장"}</p>
      {books.length>1&&<label>어느 저축통장에 넣을까요?<select value={book} onChange={e=>setBook(e.target.value)}>{books.map(b=><option key={b.id} value={b.id}>{b.icon} {b.name}</option>)}</select></label>}
      <AmountField label="얼마를 저금할까요?" amount={amount} setAmount={setAmount} max={state.wallet} presets={[1000,3000,5000]}/>
      <button className="mk-button full" disabled={busy||!ok(amount,state.wallet)}>{ok(amount,state.wallet)?`${won(Number(amount))} 저금하기`:"저금하기"}</button>
    </form>
  </TrialSheet>;
}
