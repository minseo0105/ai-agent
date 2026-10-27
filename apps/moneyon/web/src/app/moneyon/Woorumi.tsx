import { useId } from "react";
import { COACH_BRAND, COACH_MOODS, type CoachMood } from "@/lib/moneyonCoach";

// Original mint cloud friend: six finite expressions, no looping animation.
export default function Woorumi({mood="greeting",className=""}:{mood?:CoachMood;className?:string}) {
  const id=useId().replace(/:/g,"");
  const happy=mood==="goal"||mood==="allowance";
  return <svg className={`mk-mascot ${className}`} data-coach-state={mood} viewBox="0 0 160 160" role="img" aria-label={`${COACH_BRAND.displayName} · ${COACH_MOODS[mood]}`}>
    <defs><linearGradient id={`${id}-mint`} x1="40" y1="35" x2="130" y2="140" gradientUnits="userSpaceOnUse"><stop stopColor="#d9faf0"/><stop offset="1" stopColor="#83d7c4"/></linearGradient></defs>
    <ellipse cx="80" cy="144" rx="47" ry="7" fill="#315c6c" opacity=".08"/>
    {happy&&<g fill="#e6bd58"><path d="m22 33 3 7 8 2-7 4-1 8-5-7-8 1 5-7-2-8z"/><path d="m140 51 2 5 6 1-5 4-1 6-4-5-6 1 3-5-1-6z"/></g>}
    <path d={mood==="greeting"?"M37 92C17 84 12 64 20 60c8-4 15 17 26 19":"M37 91c-20 1-23 18-14 21 9 3 17-10 22-12"} fill="#a8e4d4" stroke="#4f9f94" strokeWidth="2.5" strokeLinecap="round"/>
    <path d="M121 93c16-5 24 5 20 12-5 9-16-3-24-5" fill="#a8e4d4" stroke="#4f9f94" strokeWidth="2.5"/>
    <path d="M46 127c-4 9-1 15 10 15 7 0 12-4 14-10m23 0c4 9 10 11 18 8 8-2 8-9 3-14" fill="#8dcebf" stroke="#4f9f94" strokeWidth="2.5"/>
    <path d="M31 91c0-26 9-45 24-51-1-17 21-24 31-10 16-13 34-2 30 15 14 9 19 27 16 49-2 31-20 43-51 43-32 0-50-14-50-46Z" fill={`url(#${id}-mint)`} stroke="#4f9f94" strokeWidth="2.5"/>
    <path d="M76 35c2-16 18-22 30-15-3 12-16 21-30 15Z" fill="#b1ddf0" stroke="#72aec7" strokeWidth="2"/><path d="m81 31 17-7" stroke="#72aec7" strokeWidth="2" strokeLinecap="round"/>
    <ellipse cx="82" cy="91" rx="39" ry="31" fill="#fffdf0"/>
    <ellipse cx="54" cy="94" rx="7" ry="4" fill="#f1b9a8" opacity=".7"/><ellipse cx="109" cy="94" rx="7" ry="4" fill="#f1b9a8" opacity=".7"/>
    {happy?<g fill="none" stroke="#284e58" strokeWidth="3.6" strokeLinecap="round"><path d="m59 82 5-5 6 5m22 0 5-5 6 5"/></g>:<g fill="#284e58"><ellipse cx="65" cy="83" rx={mood==="interest"?4.5:3.5} ry="5"/><ellipse cx="98" cy="83" rx="3.5" ry="5"/><circle cx="66" cy="81" r="1.2" fill="white"/><circle cx="99" cy="81" r="1.2" fill="white"/></g>}
    {mood==="help"?<><path d="m59 72 11-3m22 0 11 3M76 101q6-6 12 0" fill="none" stroke="#284e58" strokeWidth="2.7" strokeLinecap="round"/><circle cx="138" cy="41" r="12" fill="#e1edf9"/><text x="138" y="46" textAnchor="middle" fontSize="16" fontWeight="800" fill="#426e89">?</text></>:<path d={happy?"M73 95q9 18 18 0Z":"M75 97q7 7 14 0"} fill={happy?"#da9e8b":"none"} stroke="#284e58" strokeWidth="2.7" strokeLinecap="round"/>}
    {mood==="interest"&&<path d="m92 70 12-3" stroke="#284e58" strokeWidth="2.7" strokeLinecap="round"/>}
    <path d="M71 125h20" stroke="#4f9f94" strokeWidth="2.5" strokeLinecap="round"/>
    {mood==="allowance"&&<g><circle cx="126" cy="123" r="13" fill="#f6dc8d" stroke="#c2a255" strokeWidth="2"/><path d="M126 116v14m-4-12h8m-8 10h8" stroke="#8c6b27" strokeWidth="2" strokeLinecap="round"/></g>}
    {mood==="spending"&&<g transform="rotate(13 125 121)"><rect x="113" y="108" width="24" height="29" rx="4" fill="#f6fbff" stroke="#72aec7" strokeWidth="2"/><path d="M119 116h12m-12 6h9" stroke="#72aec7" strokeWidth="2" strokeLinecap="round"/><path d="m132 134 8-18" stroke="#d7b86b" strokeWidth="5" strokeLinecap="round"/></g>}
    {mood==="goal"&&<g><path d="m126 110 3 6 7 1-5 5 1 7-6-4-6 4 1-7-5-5 7-1Z" fill="#f6dc8d" stroke="#c2a255" strokeWidth="1.5"/></g>}
  </svg>;
}
