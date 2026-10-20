import { COACH_BRAND, type CoachMood } from "@/lib/moneyonCoach";

// One user-supplied Canva bee asset for every context. No invented expressions.
export default function Izani({mood="greeting",className=""}:{mood?:CoachMood;className?:string}) {
  return <img className={`mk-mascot izani ${className}`} data-coach-state={mood} data-character="izani" data-character-variant="single-bee" src="/moneyon/characters/izani-bee.png" width={200} height={200} alt={`${COACH_BRAND.displayName} · 나의 금융 친구 꿀벌`} decoding="async" draggable={false}/>;
}
