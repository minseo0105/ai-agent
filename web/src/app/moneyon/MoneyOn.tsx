"use client";
import { useEffect, useRef, useState } from "react";
import { accessApi, apiFetch, API_URL, setToken as setAccessToken } from "@/lib/access";
import "./moneyon.css";
import "./banking.css";
import { ParentBanking, type WorkspaceResult } from "./Banking";
import ChildExperience from "./ChildExperience";
import TrialExperience, { TRIAL_STORAGE } from "./TrialExperience";
import type { Child, ChildTransaction, Policy, State } from "./types";

type Dashboard = {states:Record<string,State>; summary:{children:number;paid:number;spent:number;interest:number;pending:number};missions:{all_goals:boolean;all_records:boolean}};
const won = (n: number) => n.toLocaleString("ko-KR") + "원";
const defaults: Policy = {frequency: "weekly", amount: 10000, pay_day: 0, rate_bps: 1000, cap: 1000, rollover: true};
const names: Record<string,string> = {payment:"용돈 지급",expense:"돈 썼어요",interest:"보상 이자",deposit:"금고에 저축",withdraw:"금고에서 꺼내기",expiry:"이월하지 않는 용돈 회수"};
function Character({value}:{value:string}) {return value==="🪙"?<span className="mo-coin" aria-label="코인 캐릭터">₩</span>:<>{value}</>;}

export default function MoneyOn() {
  const [trial,setTrial]=useState(false);
  useEffect(()=>{try{if(sessionStorage.getItem(TRIAL_STORAGE))setTrial(true);}catch{/* Storage errors are shown when opening a trial. */}},[]);
  const [token,setToken] = useState(""); const [pin,setPin] = useState("");
  const [children,setChildren] = useState<Child[]>([]); const [child,setChild] = useState<Child|null>(null);
  const [state,setState] = useState<State|null>(null); const [mode,setMode] = useState("start");
  const [tab,setTab] = useState("홈"); const [error,setError] = useState(""); const [message,setMessage] = useState(""); const [busy,setBusy] = useState(false);
  const [name,setName] = useState(""); const [grade,setGrade] = useState(1); const [theme,setTheme] = useState("moneyon"); const [avatar,setAvatar] = useState("🪙"); const [policy,setPolicy] = useState<Policy>(defaults); const [editing,setEditing] = useState(false); const [step,setStep] = useState(1);
  const [dashboard,setDashboard] = useState<Dashboard|null>(null); const [code,setCode] = useState(""); const [reason,setReason] = useState("");
  const running=useRef(false); const requestKey=useRef<{signature:string;key:string}|null>(null);
  const [demoId,setDemoId]=useState(""); const [bankRevision,setBankRevision]=useState(0);
  async function api(path: string, body?: unknown, auth=token, method="POST", workspace=demoId) {
    const r = await apiFetch(`${API_URL}/api/moneyon${path}`, {method: body === undefined ? "GET" : method, headers:{"Content-Type":"application/json","X-Moneyon-Session":auth,"X-Moneyon-Demo":workspace}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
    const data = await r.json(); if(!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "입력 내용을 확인해 주세요."); return data;
  }
  async function run(fn:()=>Promise<void>) { if(running.current)return;running.current=true; setBusy(true);setError("");setMessage("");try{await fn();}catch(e){setError((e as Error).message);}finally{running.current=false;setBusy(false);} }
  async function load(c=child, auth=token) { if(c) {setState(null);setState(await api(`/children/${c.id}`,undefined,auth));} }
  async function transact(kind:string, cycle_id?:string, override?:ChildTransaction) {
    let successful=false;
    await run(async()=>{
      const payload={kind,amount:0,note:"",category:"",cycle_id,...override};
      const signature=JSON.stringify({child:child!.id,...payload});
      if(requestKey.current?.signature!==signature)requestKey.current={signature,key:crypto.randomUUID()};
      const next=await api(`/children/${child!.id}/transactions`,{...payload,key:requestKey.current.key});
      requestKey.current=null;setState(next);setBankRevision(r=>r+1);successful=true;
      setMessage(kind==="payment"?`기록 완료! ${child!.profile.name}에게 ${won(child!.policy.amount)}을 보냈어요.`:kind==="interest"?"기록 완료! 보상 이자를 통장에 입금했어요.":"기록 완료!");
    });
    return successful;
  }
  function lock(){if(token)void api("/lock",{}).catch(()=>{});setToken("");setState(null);setChild(null);setChildren([]);setDashboard(null);setMode("start");setPin("");setError("");setMessage("");}
  async function enterWorkspace(w:WorkspaceResult){setDemoId(w.demo_id);setToken(w.token);setChild(null);setState(null);setDashboard(null);setChildren(await api('/children',undefined,w.token,'GET',w.demo_id));setTab('가족');setBankRevision(r=>r+1);setMessage('DEMO 시연 가족을 준비했어요. 기존 가족 기록은 그대로 보존했어요.');}
  function exitWorkspace(){if(token)void api('/lock',{}).catch(()=>{});setDemoId('');setToken('');setChild(null);setState(null);setChildren([]);setDashboard(null);setMode('unlock');setMessage('기존 가족으로 돌아왔어요. 부모 PIN으로 다시 열어 주세요.');}
  function startEdit(c?:Child) {setEditing(!!c);setName(c?.profile.name||"");setGrade(c?.profile.grade||1);setAvatar(c?.profile.avatar||"🪙");setTheme(c?.profile.theme||"moneyon");setPolicy(c?.policy||defaults);setStep(1);setTab("아이 설정");}
  const active = state?.cycles.find(c=>!c.ended);
  useEffect(()=>{if(mode!=="parent"||!token)return;let current=true;void api('/dashboard').then(d=>{if(current)setDashboard(d);}).catch(e=>{if(current)setError((e as Error).message);});return()=>{current=false;};},[mode,token,tab,state,children,bankRevision,demoId]);
  const themeClass = child?.profile.theme || "moneyon";
  if(trial)return <TrialExperience onExit={()=>setTrial(false)}/>;
  if(mode==="child"&&child&&state)return <ChildExperience key={child.id} child={child} state={state} api={api} run={run} busy={busy} error={error} demo={!!demoId} onLock={lock} onState={setState} onDismissError={()=>setError("")} onTransact={payload=>transact(payload.kind,undefined,payload)}/>;
  return <main className={`mo ${themeClass} ${mode==="parent"?"mo-parent":mode==="child"?"mo-banking-child":""}`} aria-busy={busy}>
    <header><a href="/">← AI LAB</a><strong>MONEY:ON <small>머니온</small></strong><button onClick={lock}>잠그기 🔒</button></header>
    <section className="mo-hero"><span>MY LITTLE MONEY WORLD</span><h1>돈을 쓰는 것도,<br/>모으는 것도 내가 결정해요!</h1><p>용돈을 관리하면 저축이 자라고, 저축하면 내 꿈도 자라요.</p><div className="mo-mascot" aria-hidden>🐷 🌱 💰</div></section>
    <p className="mo-disclaimer">부모가 관리하는 교육용 가상 용돈 원장 · 실제 은행 계좌가 아니에요. 보상 이자는 부모님이 주는 교육용 보상이에요.</p>
    {demoId&&<p className="mo-demo-banner" role="note">DEMO 시연 가족 · 가상 날짜를 사용하는 별도 공간이에요. 기존 가족 기록과 분리돼요.</p>}
    {error&&<p role="alert" className="mo-error">{error}</p>}{message&&<p role="status" className="mo-success">{message}</p>}
    {mode==="start"&&<section className="mo-card"><h2>우리 가족의 금융 놀이터</h2><p>이미 채워진 통장에서 돈을 받고, 쓰고, 모아 보세요.</p><button className="mo-trial-start" onClick={()=>setTrial(true)}>바로 체험하기</button><button onClick={()=>setMode("unlock")}>부모님과 직접 시작하기</button><details><summary>기존 가족으로 시작하기</summary><p>AI LAB 로그인 후 부모님이 PIN으로 열어 주세요. 처음 입력한 PIN이 가족 PIN으로 등록돼요.</p><form onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await accessApi.login(code.trim());setAccessToken(r.token);setCode("");setMode("unlock");});}}><label>AI LAB 개인 접속 코드<input value={code} onChange={e=>setCode(e.target.value)} autoComplete="one-time-code"/></label><button disabled={busy||!code.trim()}>접속 코드로 로그인</button></form><button onClick={()=>setMode("unlock")}>부모로 시작하기</button><button onClick={()=>setMode("unlock")}>어린이 모드 · 부모님과 아이 선택</button><p>개발 버전은 MONEYON_LOCAL_DEV=1 설정이 필요해요.</p></details></section>}
    {mode==="unlock"&&<form className="mo-card" onSubmit={e=>{e.preventDefault();void run(async()=>{const r=await api("/unlock",{pin});setToken(r.token);setPin("");setChildren(await api("/children",undefined,r.token));setMode("parent");setTab("가족");});}}><h2>부모 인증</h2><label>가족 PIN (숫자 6~12자리)<input type="password" inputMode="numeric" pattern="[0-9]{6,12}" value={pin} onChange={e=>setPin(e.target.value)} required autoComplete="off"/></label><button disabled={busy}>열기</button></form>}
    {mode==="parent"&&<><ParentBanking key={token} api={api} run={run} busy={busy} refresh={bankRevision} children={children.map(c=>({id:c.id,name:c.profile.name}))} onWorkspace={enterWorkspace} onChooseChild={()=>{setTab("가족");setTimeout(()=>document.querySelector(".mo-child")?.scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"center"}),0);}} onExit={exitWorkspace} onDateChange={async()=>{if(child)await load(child);setBankRevision(r=>r+1);}}/><nav className="mo-tabs"><button onClick={()=>setTab("가족")}>가족 대시보드</button><button onClick={()=>{setChild(null);startEdit();}}>+ 아이 추가하기</button>{child&&<><button onClick={()=>setTab("관리")}>용돈·이자 관리</button><button onClick={()=>startEdit(child)}>아이 정보·규칙</button></>}</nav>
      {tab==="가족"&&<section><h2>우리 가족, 함께 자라요 <small>{children.filter(c=>c.status!=="archived").length}명</small></h2>{dashboard&&<><div className="mo-grid mo-stats">{[["이번 달 지급",dashboard.summary.paid],["이번 달 지출",dashboard.summary.spent],["보상 이자",dashboard.summary.interest],["승인 대기",dashboard.summary.pending]].map(([label,n])=><article className="mo-card" key={label}><p>{label}</p><strong>{label==="승인 대기"?`${n}건`:won(Number(n))}</strong></article>)}</div><section className="mo-card"><h3>🌳 가족 공동 미션</h3><p>모두 목표 하나 만들기 {dashboard.missions.all_goals?"✅ 가족 꽃나무 획득!":"함께 도전 중"}</p><p>모두 이번 달 3일 이상 기록하기 {dashboard.missions.all_records?"✅ 가족 정원 장식 획득!":"함께 도전 중"}</p><small>가상 정원 보상이에요. 실제 돈은 바뀌지 않아요.</small></section></>}{!children.length&&<p className="mo-card">아직 등록한 아이가 없어요. 첫 번째 아이를 추가해 주세요!</p>}<div className="mo-grid">{children.map(c=><button className="mo-card mo-child" key={c.id} onClick={()=>void run(async()=>{setChild(c);await load(c);setTab("관리");})}><span><Character value={c.profile.avatar}/></span><h3>{c.profile.name}</h3><p>{c.profile.grade}학년 · {c.status==="active"?"활동 중":c.status==="paused"?"일시중지":"보관됨"}</p><strong>{c.policy.frequency==="weekly"?"매주":"매월"} {won(c.policy.amount)}</strong><p>보상 {c.policy.rate_bps/100}% · 현황 보기 →</p>{dashboard?.states[c.id]&&<><p>잔액 {won(dashboard.states[c.id].wallet)} · 금고 {won(dashboard.states[c.id].vault)}</p><p>예상 보상 {won(dashboard.states[c.id].cycles.find(x=>!x.ended)?.interest||0)} · 다음 지급 {dashboard.states[c.id].next_payday}</p><p>목표 {dashboard.states[c.id].goals[0]?`${Math.min(100,Math.floor(dashboard.states[c.id].vault/dashboard.states[c.id].goals[0].amount*100))}%`:"설정 전"}</p></>}</button>)}</div></section>}
      {tab==="아이 설정"&&<form className="mo-card" onSubmit={e=>{e.preventDefault();if(step<3){setStep(step+1);return;}void run(async()=>{await api(editing?`/children/${child!.id}`:"/children",{name,grade,avatar,theme,policy,status:child?.status||"active"},token,editing?"PUT":"POST");setChildren(await api("/children"));setTab("가족");setMessage("가족 설정을 저장했어요!");});}}><h2>{editing?"아이 정보 수정":"새로운 모험 친구"} · {step}/3</h2>
        {step===1&&<><label>별명<input required maxLength={30} value={name} onChange={e=>setName(e.target.value)}/></label><label>학년<input type="number" min={1} max={6} value={grade} onChange={e=>setGrade(+e.target.value)}/></label><label>캐릭터<select value={avatar} onChange={e=>setAvatar(e.target.value)}>{["🪙","🐰","🐻","🧑‍🚀"].map(a=><option key={a} value={a}>{a==="🪙"?"코인 친구":a}</option>)}</select></label></>}
        {step===2&&<label>나만의 월드<select value={theme} onChange={e=>setTheme(e.target.value)}><option value="moneyon">민트 · 기본 머니온</option><option value="adventure">블루 · 어드벤처 월드</option><option value="animals">핑크 · 동물 마을</option></select></label>}
        {step===3&&<><label>지급 주기<select value={policy.frequency} onChange={e=>setPolicy({...policy,frequency:e.target.value as Policy['frequency'],pay_day:e.target.value==="weekly"?0:1})}><option value="weekly">매주</option><option value="monthly">매월</option></select></label>{([["amount","지급 금액 (원)",1,10000000],["pay_day",policy.frequency==="weekly"?"요일 (월 0 ~ 일 6)":"날짜 (1~31, 없는 날짜는 월말)",policy.frequency==="weekly"?0:1,policy.frequency==="weekly"?6:31],["rate_bps","보상 이자율 (100 = 1%)",0,10000],["cap","보상 최대 금액 (원)",0,1000000]] as const).map(([k,label,min,max])=><label key={k}>{label}<input type="number" required min={min} max={max} value={policy[k]} onChange={e=>setPolicy({...policy,[k]:+e.target.value})}/></label>)}<label><input type="checkbox" checked={policy.rollover} onChange={e=>setPolicy({...policy,rollover:e.target.checked})}/> 남은 신규 용돈 이월하기</label><p>변경한 규칙은 다음 지급부터 적용돼요. 초기 잔액은 지급 이력으로 시작해요.</p></>}
        {step>1&&<button type="button" onClick={()=>setStep(step-1)}>이전</button>}<button disabled={busy}>{step<3?"다음":"설정 저장"}</button></form>}
    </>}
    {child&&state&&tab!=="아이 설정"&&tab!=="가족"&&<>
      <section className="mo-child-heading"><span><Character value={child.profile.avatar}/></span><h2>{child.profile.name}의 용돈 월드</h2>{mode==="parent"&&<button disabled={busy||child.status!=="active"} onClick={()=>void run(async()=>{const r=await api(`/children/${child.id}/select`,{});setToken(r.token);setMode("child");setTab("홈");})}>이 아이로 시작 →</button>}</section>
      <div className="mo-grid mo-stats">{[["지금 남은 돈",state.wallet],["저축금고",state.vault],["이번 주기 받은 용돈",active?.policy.amount||0],["예상 보상 이자",active?.interest||0]].map(([label,value])=><article className="mo-card" key={label}><p>{label}</p><strong>{won(Number(value))}</strong></article>)}</div>
      {mode==="parent"&&tab==="관리"&&<section className="mo-card"><h2>용돈 지급 · 부모 승인</h2><p>다음 정기 지급일 {state.next_payday} · 지급 버튼은 현재 주기의 용돈을 한 번 지급해요. 이 버튼은 부모 통장 출금과 아이 통장 입금을 함께 처리하는 가상 이체예요.</p><button disabled={busy||child.status!=="active"} onClick={()=>void transact("payment")}>현재 주기 용돈 지급</button>{state.cycles.map(c=><div className="mo-cycle" key={c.id}><p>{c.start} ~ {c.end} (종료일 제외) · 적격 잔액 {won(c.eligible)} · 보상 {won(c.interest)}</p><button disabled={busy||!c.ended||!!c.settled} onClick={()=>void transact("interest",c.id)}>{c.settled?"승인 완료":c.ended?"보상 이자 승인":"진행 중 · 예상 금액"}</button></div>)}<p>이월 금액·이전 보상·금고 금액은 이자에서 제외해요. 주기 종료 후에는 승인부터 해 주세요.</p><div className="mo-actions">{["paused","active","archived"].map(status=><button disabled={busy} key={status} onClick={()=>void run(async()=>{await api(`/children/${child.id}`,{...child.profile,policy:child.policy,status},token,"PUT");setChildren(await api("/children"));setChild({...child,status});setMessage("상태를 저장했어요.");})}>{status==="paused"?"이용 일시중지":status==="active"?"이용 재개":"보관 처리"}</button>)}</div></section>}
      {mode==="parent"&&tab==="관리"&&<section className="mo-card"><h2>이번 달 금융습관 리포트</h2><p>지급 {won(state.report.paid)} · 지출 {won(state.report.spent)} · 보상 {won(state.report.interest)}</p><p>기록한 날 {state.report.record_days}일 · 남긴 비율 {state.report.savings_rate===null?"지급 기록 없음":`${state.report.savings_rate}%`}</p>{Object.entries(state.report.categories).map(([c,n])=><p key={c}>{c} · {won(n)} ({state.report.spent?Math.round(n/state.report.spent*100):0}%)</p>)}<p>{state.report.record_days?"용돈 기록을 이어 가고 있어요. 이번 소비를 함께 돌아보고 다음 예산을 정해 보세요.":"작은 소비부터 아이와 함께 기록해 보세요."}</p><label>지출 취소 사유 (정정할 때는 취소 후 다시 기록)<input maxLength={200} value={reason} onChange={e=>setReason(e.target.value)}/></label></section>}
      {(tab==="소비 내역"||tab==="관리")&&<section className="mo-card"><h2>용돈 기록</h2>{!state.transactions.length&&<p>아직 기록이 없어요.</p>}{state.transactions.filter(t=>t.kind!=="eligibility").map(t=><article className="mo-transaction" key={t.id}><div><strong>{t.kind==="expense_cancel"?"지출 취소":names[t.kind]||t.kind}</strong><p>{new Date(t.created).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})} · {t.category} {t.note}</p></div><span>{won(t.wallet)}{t.vault!==0&&<small> / 금고 {won(t.vault)}</small>}</span>{mode==="parent"&&t.kind==="expense"&&<button disabled={busy||!reason.trim()} onClick={()=>void run(async()=>{setState(await api(`/children/${child.id}/transactions/${t.id}/cancel`,{reason}));setMessage("취소 이력을 남겼어요. 정정할 금액은 새로 기록해 주세요.");})}>사유를 남기고 취소</button>}</article>)}</section>}
    </>}
    {busy&&<p role="status">안전하게 저장하고 있어요…</p>}
  </main>;
}
