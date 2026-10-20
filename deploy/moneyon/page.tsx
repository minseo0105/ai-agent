"use client";
import {useEffect,useState} from "react";
import TrialExperience,{TRIAL_STORAGE,TrialStatus} from "@/app/moneyon/TrialExperience";
import "@/app/moneyon/moneyon.css";
import "@/app/moneyon/child.css";
import "@/app/moneyon/blue.css";
import Izani from "@/app/moneyon/Izani";
export default function Page(){
  // null = 진행 중인 체험이 있는지 아직 모름. 이때 첫 화면을 그리면 새로고침 때 첫 화면이 잠깐 비친다.
  const [open,setOpen]=useState<boolean|null>(null);
  useEffect(()=>{let saved=false;try{saved=!!sessionStorage.getItem(TRIAL_STORAGE);}catch{}setOpen(saved);},[]);
  if(open===null)return <TrialStatus quiet/>;
  if(open)return <TrialExperience onExit={()=>setOpen(false)}/>;
  return <main className="mk-entry"><div className="mk-entry-shell"><span className="mk-entry-logo">MONEY:ON</span><div className="mk-entry-art"><Izani mood="greeting"/></div><h1>내가 남긴 용돈에<br/>이자가 자라요.</h1><p className="mk-entry-copy">안녕! 나는 이자니야.<br/>남은 용돈에 이자가 붙는 비밀을 알려줄게!</p><div className="mk-entry-steps"><span>엄마 은행</span><span aria-hidden="true">→</span><span>나의 용돈</span><span aria-hidden="true">→</span><span>10% 이자</span></div><button className="mk-button" onClick={()=>setOpen(true)}>바로 체험하기</button><p className="mk-entry-note">PIN이나 부모 등록 없이 나만의 샘플 통장으로 시작해요. 남긴 용돈의 10%를 다음 주 약속한 지급 방식으로 내 통장에 받아요. 새 체험은 자동 지급이에요.</p><p className="mk-entry-note">가상 금융교육 거래예요. 10%는 교육용 보상률이며 실제 은행의 일반적인 예금 금리가 아니에요.</p></div></main>;
}
