"use client";
import { useEffect, useState } from "react";

export type Account = {id:string;family:string;child:string|null;kind:"parent"|"wallet"|"vault";alias:string;balance:number;notice:string};
export type BankTransaction = {account_id:string;transfer_id:string;transaction_id:string|null;child_id:string|null;transaction_type:string;occurred_at:string;merchant:string;category:string;note:string;amount:number;balance_after:number;status:string;legacy:number};
export type BankState = {accounts:Account[];transactions:BankTransaction[]};
export type WorkspaceResult = {demo_id:string;token:string;date:string};
type ParentBank = BankState & {demo_enabled:boolean;business_date:string;workspace:{is_demo:boolean;id:string|null;date:string|null}};
type Api = (path:string,body?:unknown,auth?:string,method?:string)=>Promise<unknown>;
type Run = (action:()=>Promise<void>)=>Promise<void>;
const won=(n:number)=>n.toLocaleString("ko-KR")+"원";
const types:Record<string,string>={DEMO_INITIAL_FUNDING:"데모 시작 잔액",ALLOWANCE_TRANSFER:"용돈 이체",SIMULATED_PURCHASE:"가상 소비",MANUAL_EXPENSE:"수동 지출 기록",PARENT_REWARD_INTEREST:"부모님이 주신 저축 보상 이자",SAVINGS_DEPOSIT:"저축금고로 이동",SAVINGS_WITHDRAWAL:"통장으로 꺼내기",PURCHASE_REVERSAL:"소비 취소",ALLOWANCE_RETURN:"미이월 용돈 반환"};
const categories=["간식","문구","장난감","게임","책","선물","기타"];

function AccountCard({account,owner}:{account:Account;owner?:string}) {
  return <article className={`mo-bank-account ${account.kind}`}><div className="mo-bank-label"><span>{account.kind==="parent"?"PARENT BANKING":account.kind==="vault"?"SAVINGS VAULT":"MY FIRST ACCOUNT"}</span><b>DEMO</b></div><h3>{owner?`${owner} · `:""}{account.alias}</h3><p className="mo-account-id">{account.id}</p><strong className="mo-bank-balance">{won(account.balance)}</strong><p className="mo-bank-notice">가상 계좌 · 실제 금융 거래 아님</p></article>;
}

function History({items,book=false,onCategory,busy=false}:{items:BankTransaction[];book?:boolean;onCategory?:(t:BankTransaction,c:string)=>void;busy?:boolean}) {
  return <div className="mo-bank-history">{!items.length&&<p>아직 거래가 없어요. 용돈을 이체하면 통장과 기입장에 함께 나타나요.</p>}{items.map(t=><article className="mo-bank-row" key={`${t.transfer_id}:${t.account_id}`}><div className="mo-bank-row-head"><h3>{book&&t.category?`${t.category} · `:""}{t.merchant||types[t.transaction_type]||t.transaction_type}</h3><strong className={t.amount>0?"mo-money-in":""}>{t.amount>0?"+":""}{won(t.amount)}</strong></div><p>{new Date(t.occurred_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})} · {t.status==="POSTED"?"완료":t.status}</p><p>거래 후 잔액 <b>{won(t.balance_after)}</b> · {types[t.transaction_type]}</p>{t.note&&t.note!==t.merchant&&<p>{t.note}</p>}{t.legacy===1&&<small>이전 용돈 기록에서 연결한 거래 · 부모 계좌 재차감 없음</small>}<details><summary>거래 ID와 이체 ID</summary><p>거래: {t.transaction_id||t.transfer_id}</p><p>이체: {t.transfer_id}</p><p>계좌: {t.account_id}</p></details>{onCategory&&t.transaction_type.match(/PURCHASE|EXPENSE/)&&t.amount<0&&<label>소비 카테고리<select aria-label={`소비 카테고리 ${t.transaction_id}`} value={t.category||"기타"} disabled={busy} onChange={e=>onCategory(t,e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label>}</article>)}</div>;
}

export function ParentBanking({api,run,busy,refresh,children,onWorkspace,onExit,onDateChange,onChooseChild}:{api:Api;run:Run;busy:boolean;refresh:unknown;children:{id:string;name:string}[];onWorkspace:(w:WorkspaceResult)=>Promise<void>;onExit:()=>void;onDateChange:()=>Promise<void>;onChooseChild:()=>void}) {
  const [data,setData]=useState<ParentBank|null>(null);const [error,setError]=useState("");const [selected,setSelected]=useState("");const [date,setDate]=useState("");const [resetOpen,setResetOpen]=useState(false);const [historyOpen,setHistoryOpen]=useState(false);
  async function load(){const d=await api('/banking') as ParentBank;setData(d);setDate(d.business_date);return d;}
  useEffect(()=>{let current=true;void api('/banking').then(d=>{if(current){setData(d as ParentBank);setDate((d as ParentBank).business_date);setError("");}}).catch(e=>{if(current)setError((e as Error).message);});return()=>{current=false;};},[refresh]);
  if(error)return <p role="alert" className="mo-error">통장 조회: {error}<button onClick={()=>void run(async()=>{await load();setError("");})}>다시 조회</button></p>;
  if(!data)return <p role="status">가상 계좌를 불러오고 있어요…</p>;
  const parent=data.accounts.find(a=>a.kind==="parent");
  const account=selected||parent?.id;
  const history=data.transactions.filter(t=>t.account_id===account);
  return <section className="mo-parent-bank" aria-label="부모 가상 은행 계좌">
    <div className="mo-bank-title"><div><span>MONEY:ON · MOCK BANKING</span><h2>우리 가족의 첫 금융 습관</h2></div><small>기준일 {data.business_date}</small></div>
    {parent&&<AccountCard account={parent}/>}
    <div className="mo-bank-actions"><button onClick={onChooseChild}>자녀 선택 · 용돈 이체 ↓</button><button onClick={()=>setHistoryOpen(!historyOpen)} aria-expanded={historyOpen}>전체 거래내역</button></div>
    {historyOpen&&<section className="mo-card"><h3>계좌별 전체 거래내역</h3><label>조회 계좌<select value={account} onChange={e=>setSelected(e.target.value)}>{data.accounts.map(a=><option key={a.id} value={a.id}>{a.child?children.find(c=>c.id===a.child)?.name+" · ":""}{a.alias} · {a.id}</option>)}</select></label><p>가상 계좌 · 실제 금융 거래 아님</p><History items={history}/></section>}
    {data.demo_enabled&&<section className="mo-demo-tools"><h3>DEMO 시연 도구</h3>{!data.workspace.is_demo?<><p>현재 가족 기록을 보존하고, 재현·서연과 부모 잔액 500,000원이 있는 별도 데모 공간을 만들어요.</p><button disabled={busy} onClick={()=>void run(async()=>{const w=await api('/demo/start',{}) as WorkspaceResult;await onWorkspace(w);})}>시연 가족 시작</button></>:<><p>이 공간에서만 가상 날짜와 초기화를 사용할 수 있어요. 기존 가족 데이터는 바뀌지 않아요.</p><label>데모 날짜<input type="date" min={data.business_date} value={date} onChange={e=>setDate(e.target.value)}/></label><button disabled={busy||!date} onClick={()=>void run(async()=>{await api('/demo/date',{date});await load();await onDateChange();})}>가상 날짜 적용</button><button disabled={busy} onClick={()=>setResetOpen(!resetOpen)}>데모 새로 시작</button><button disabled={busy} onClick={onExit}>기존 가족으로 돌아가기</button>{resetOpen&&<div role="group" aria-label="데모 초기화 확인"><p>이 데모를 보관하고 새 시연 가족을 만들까요? 현재 데모 기록도 삭제하지 않아요.</p><button disabled={busy} onClick={()=>void run(async()=>{const w=await api('/demo/reset',{}) as WorkspaceResult;setResetOpen(false);await onWorkspace(w);})}>새 시연 가족 만들기</button><button onClick={()=>setResetOpen(false)}>계속 사용하기</button></div>}</>}</section>}
  </section>;
}

export function ChildBanking({banking,child,name,view,api,run,busy,onState,onPurchase}:{banking:BankState;child:string;name:string;view:"home"|"account"|"book";api:Api;run:Run;busy:boolean;onState:(s:unknown)=>void;onPurchase:(merchant:string,amount:number)=>void}) {
  const [filter,setFilter]=useState("전체");
  const wallet=banking.accounts.find(a=>a.kind==="wallet");
  if(!wallet)return null;
  const tx=banking.transactions.filter(t=>t.account_id===wallet.id);
  const received=tx.find(t=>t.transaction_type==="ALLOWANCE_TRANSFER");
  const latest=tx[0];
  const items=tx.filter(t=>filter==="전체"||(filter==="입금"?t.amount>=0:filter==="출금"?t.amount<0:t.category===filter));
  return <section className="mo-child-bank" aria-label="나의 가상 통장">
    {view!=="book"&&<AccountCard account={wallet} owner={name}/>}
    {view==="home"&&<><div className="mo-card mo-arrival">{received?<p>🎉 용돈 {won(received.amount)}이 도착했어요!</p>:<p>부모님이 보내 주신 용돈을 여기서 확인해요.</p>}{latest?.transaction_type==="SIMULATED_PURCHASE"&&<p>{latest.merchant}에서 {won(-latest.amount)}을 사용했네! 통장과 용돈기입장에 함께 기록했어.</p>}<small>받은 용돈과 쓴 돈은 하나의 거래 원장에서 함께 보여줘요.</small></div><section className="mo-card"><h3>가상 소비 체험</h3><p>실제 결제가 발생하지 않는 시뮬레이션이에요.</p><div className="mo-purchases">{[["편의점",2000],["문구점",4000],["서점",5000],["게임",3000]].map(([merchant,amount])=><button disabled={busy} key={merchant} onClick={()=>onPurchase(String(merchant),Number(amount))}>{merchant}<strong>{won(Number(amount))}</strong></button>)}</div></section></>}
    {view!=="home"&&<section className="mo-card"><h2>{view==="book"?"용돈기입장":"통장 입출금 내역"}</h2><p>가상 계좌 · 실제 금융 거래 아님</p><label>{view==="book"?"카테고리로 보기":"거래 구분"}<select value={filter} onChange={e=>setFilter(e.target.value)}>{(view==="book"?["전체",...categories]:["전체","입금","출금"]).map(c=><option key={c}>{c}</option>)}</select></label><History items={items} book={view==="book"} busy={busy} onCategory={view==="book"?(t,c)=>void run(async()=>{onState(await api(`/children/${child}/transactions/${t.transaction_id}/category`,{category:c},undefined,"PATCH"));}):undefined}/></section>}
  </section>;
}
