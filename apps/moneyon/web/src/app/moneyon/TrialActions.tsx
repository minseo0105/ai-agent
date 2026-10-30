"use client";
import { useState } from "react";
import TrialSheet from "./TrialSheet";
import type { ChildTransaction, SavingsBook, State } from "./types";
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
export const CATEGORY_ICONS:Record<string,string>={간식:"🍪",문구:"✏️",장난감:"🧸",게임:"🎮",책:"📚",선물:"🎁",기타:"📦"};

// 금액 입력: 버튼이나 직접 입력, 100원 단위. 넘치거나 단위가 맞지 않으면 그 자리에서 알려준다.
function AmountField({label,amount,setAmount,max,presets,verb="쓸"}:{label:string;amount:string;setAmount:(v:string)=>void;max:number;presets:number[];verb?:string}) {
  const value=Number(amount);
  const hint=!amount?"":value%100?"100원 단위로 적어요.":value>max?`남은 용돈은 ${won(max)}이에요. 그보다 많이는 ${verb} 수 없어요.`:"";
  return <>
    <p className="mk-remaining" data-testid="remaining-allowance">남은 용돈 <strong>{won(max)}</strong></p>
    <label>{label}<span className="mk-bank-amount"><input type="number" inputMode="numeric" min={100} max={max} step={100} placeholder="0" value={amount} onChange={e=>setAmount(e.target.value)}/><span>원</span></span></label>
    {/* 금액 버튼은 누를 때마다 더해진다(1,000원 두 번 = 2,000원). 넘치면 그 버튼은 잠기고, 처음부터 다시 하려면 '다시 입력' */}
    <div className="mk-amount-presets" aria-label="금액 더하기">{presets.map(n=><button type="button" key={n} disabled={value+n>max} onClick={()=>setAmount(String(value+n))}>+{won(n)}</button>)}<button type="button" className="mk-amount-reset" disabled={!amount} onClick={()=>setAmount("")}>다시 입력</button></div>
    {hint&&<p className="mk-caption" role="status">{hint}</p>}
  </>;
}
const ok=(amount:string,max:number)=>{const v=Number(amount);return v>=100&&v%100===0&&v<=max;};

// 쓴 돈 기록: 무엇에, 얼마를 썼는지 아이가 직접 고른다(미리 골라 두지 않음).
export function SpendSheet({wallet,books=[],busy,onClose,onSave}:{wallet:number;books?:SavingsBook[];busy:boolean;onClose:()=>void;onSave:(p:ChildTransaction)=>Promise<boolean>}) {
  const [category,setCategory]=useState(""),[amount,setAmount]=useState("");
  const valid=!!category&&ok(amount,wallet);
  // 남은 용돈보다 많이 쓰려 하면, 저축통장에 돈이 있을 때 모자란 만큼(100원 단위)을 꺼내 올 수 있게 한다.
  const value=Number(amount),source=[...books].filter(b=>b.status!=="pending"&&b.balance>=100).sort((a,b)=>b.balance-a.balance)[0];
  const short=value>wallet&&value%100===0&&source?Math.min(value-wallet,Math.floor(source.balance/100)*100):0;
  return <TrialSheet title="쓴 돈 기록하기" onClose={onClose}>
    <form className="mk-spend-form" onSubmit={e=>{e.preventDefault();if(valid)void onSave({kind:"expense",amount:Number(amount),category,note:category}).then(saved=>{if(saved)onClose();});}}>
      <fieldset><legend>무엇에 썼나요?</legend><div className="mk-category-grid">{Object.entries(CATEGORY_ICONS).map(([name,icon])=><button type="button" key={name} aria-pressed={category===name} onClick={()=>setCategory(name)}><span aria-hidden="true">{icon}</span>{name}</button>)}</div></fieldset>
      <AmountField label="얼마를 썼나요?" amount={amount} setAmount={setAmount} max={wallet} presets={[1000,3000,5000]}/>
      {short>0&&<button type="button" className="mk-button secondary full" disabled={busy} onClick={()=>void onSave({kind:"withdraw",amount:short,book_id:source!.id})}>통장에서 꺼내 올까요? ({source!.icon} {source!.name}에서 {won(short)})</button>}
      <button className="mk-button full" disabled={busy||!valid}>{ok(amount,wallet)?`${won(Number(amount))} 기록하기`:"기록하기"}</button>
    </form>
  </TrialSheet>;
}

// 저금하기: 내 용돈통장에서 저축통장으로. 통장이 여러 개면 고른다.
export function DepositSheet({state,busy,onClose,onSave}:{state:State;busy:boolean;onClose:()=>void;onSave:(p:ChildTransaction)=>Promise<boolean>}) {
  // 엄마 승인을 기다리는 통장에는 저금할 수 없다
  const books=(state.books??[]).filter(b=>b.status!=="pending");
  const [book,setBook]=useState(books[0]?.id??"");
  const [amount,setAmount]=useState(state.wallet>=3000?"3000":"");
  const target=books.find(b=>b.id===book);
  return <TrialSheet title="저금하기" onClose={onClose}>
    <form className="mk-spend-form" onSubmit={e=>{e.preventDefault();if(ok(amount,state.wallet))void onSave({kind:"deposit",amount:Number(amount),book_id:book}).then(saved=>{if(saved)onClose();});}}>
      <p className="mk-bank-line">내 용돈통장 {won(state.wallet)} <span aria-hidden="true">→</span> {target?`${target.icon} ${target.name}`:"저축통장"}</p>
      {books.length>1&&<label>어느 저축통장에 넣을까요?<select value={book} onChange={e=>setBook(e.target.value)}>{books.map(b=><option key={b.id} value={b.id}>{b.icon} {b.name}</option>)}</select></label>}
      <AmountField label="얼마를 저금할까요?" amount={amount} setAmount={setAmount} max={state.wallet} presets={[1000,3000,5000]} verb="저금할"/>
      <button className="mk-button full" disabled={busy||!ok(amount,state.wallet)}>{ok(amount,state.wallet)?`${won(Number(amount))} 저금하기`:"저금하기"}</button>
    </form>
  </TrialSheet>;
}
