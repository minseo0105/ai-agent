import { useId } from "react";
import { COACH_BRAND, COACH_MOODS, type CoachMood } from "@/lib/moneyonCoach";

// Original floppy-eared coin puppy. One shared silhouette for all seven states.
export default function Izani({mood="greeting",className=""}:{mood?:CoachMood;className?:string}) {
  const id=useId().replace(/:/g,"");
  const happy=["allowance","celebration","goal"].includes(mood);
  return <svg className={`mk-mascot izani ${mood==="celebration"?"izani-celebrate":""} ${className}`} data-coach-state={mood} data-character="izani" viewBox="0 0 160 160" role="img" aria-label={`${COACH_BRAND.displayName} · ${COACH_MOODS[mood]}`}>
    <defs><linearGradient id={`${id}-fur`} x2="0.7" y2="1"><stop stopColor="#ffffff"/><stop offset="1" stopColor="#e4f3ff"/></linearGradient></defs>
    <ellipse cx="82" cy="146" rx="42" ry="6" fill="#084A86" opacity=".09"/>
    <path d="M115 112q27-13 26 3-1 13-20 10" fill="#DCEFFF" stroke="#2497E3" strokeWidth="3"/>
    <path d="M53 100q-7 20-4 36 4 11 17 4h30q17 8 19-6l-4-35" fill={`url(#${id}-fur)`} stroke="#92c6e8" strokeWidth="2.5"/>
    <path d={mood==="greeting"?"M52 109Q25 84 27 105q4 18 24 18":"M52 109q-23-6-22 9 3 12 23 7"} fill="#f4fbff" stroke="#92c6e8" strokeWidth="2.5" strokeLinecap="round"/>
    <path d="M109 107q22-10 23 5 1 13-22 13" fill="#f4fbff" stroke="#92c6e8" strokeWidth="2.5"/>
    <path d="M54 39q-23-18-26 13-4 30 12 39 10 3 16-24m49-28q25-18 29 13 5 31-11 39-10 3-17-24" fill="#0067AC"/>
    <path d="M43 67q0-36 38-36t38 36v16q-3 31-38 31T43 83Z" fill={`url(#${id}-fur)`} stroke="#92c6e8" strokeWidth="2.5"/>
    <path d="M65 34q8-16 23-6l-5 7" fill="#fff" stroke="#92c6e8" strokeWidth="2.5" strokeLinejoin="round"/>
    <ellipse cx="58" cy="83" rx="8" ry="5" fill="#FF8FB3" opacity=".45"/><ellipse cx="104" cy="83" rx="8" ry="5" fill="#FF8FB3" opacity=".45"/>
    {happy?<g fill="none" stroke="#084A86" strokeWidth="3.5" strokeLinecap="round"><path d="m59 71 5-5 6 5m22 0 5-5 6 5"/></g>:<g fill="#084A86"><ellipse cx="65" cy="73" rx="4.5" ry="6"/><ellipse cx="98" cy="73" rx="4.5" ry="6"/><circle cx="66" cy="71" r="1.6" fill="white"/><circle cx="99" cy="71" r="1.6" fill="white"/></g>}
    <path d="m77 82 5 5 5-5q-5-5-10 0" fill="#084A86"/>
    <path d={happy?"M73 90q9 15 18 0Z":"M73 91q9 8 18 0"} fill={happy?"#FF8FB3":"none"} stroke="#084A86" strokeWidth="2.4" strokeLinecap="round"/>
    <path d="M57 109q25 9 48 0" stroke="#0067AC" strokeWidth="6" strokeLinecap="round"/>
    <circle cx="82" cy="116" r="10" fill="#FFCB57" stroke="#e4a62c" strokeWidth="1.5"/><path d="M82 110v12m-4-10h8m-8 8h8" stroke="#996717" strokeWidth="2" strokeLinecap="round"/>
    {mood==="allowance"&&<g><rect x="110" y="111" width="31" height="23" rx="5" fill="#DCEFFF" stroke="#0067AC" strokeWidth="2"/><path d="m113 116 12 8 13-8" fill="none" stroke="#0067AC" strokeWidth="2"/></g>}
    {mood==="spending"&&<g transform="rotate(12 128 117)"><path d="M116 100h24v32l-4-3-4 3-4-3-4 3-4-3-4 3Z" fill="white" stroke="#2497E3" strokeWidth="2"/><path d="M121 108h14m-14 6h10m-10 6h12" stroke="#2497E3" strokeWidth="2"/></g>}
    {mood==="interest"&&<g><rect x="113" y="102" width="30" height="32" rx="7" fill="#DCEFFF" stroke="#2497E3" strokeWidth="2"/><path d="m123 124 11-12" stroke="#0067AC" strokeWidth="2"/><circle cx="122" cy="113" r="2" fill="#0067AC"/><circle cx="135" cy="124" r="2" fill="#0067AC"/></g>}
    {mood==="goal"&&<path d="m128 102 4 9 10 1-7 7 2 10-9-5-9 5 2-10-7-7 10-1Z" fill="#FFCB57" stroke="#dba027" strokeWidth="2"/>}
    {mood==="help"&&<path d="m29 38 5-7 7 5m78-10 7 5-5 7" fill="none" stroke="#2497E3" strokeWidth="3" strokeLinecap="round"/>}
    {mood==="celebration"&&<g className="izani-confetti" fill="#FFCB57"><path d="m24 27 3 8 9 2-8 5-1 9-6-7-9 1 5-8-2-9Z"/><path d="m134 29 3 6 7 1-5 5 1 7-6-4-6 4 1-7-5-5 7-1Z"/><circle cx="19" cy="68" r="4" fill="#2497E3"/><circle cx="143" cy="74" r="4" fill="#FF8FB3"/></g>}
  </svg>;
}
