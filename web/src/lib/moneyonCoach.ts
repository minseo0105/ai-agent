// Brand review can change these names in one place. No official affiliation claim.
export const COACH_BRAND = {
  displayName: process.env.NEXT_PUBLIC_MONEYON_COACH_NAME?.trim() || "이자니",
  englishName: "IZANI",
  tagline: "용돈과 이자의 비밀을 알려주는 금융 친구",
  notice: "이 서비스만의 오리지널 캐릭터 시안이에요. 우리금융 공식 캐릭터가 아니에요.",
};

export type CoachMood = "greeting" | "allowance" | "spending" | "goal" | "interest" | "help" | "celebration";
export const COACH_MOODS: Record<CoachMood, string> = {
  celebration: "이자 지급 축하", greeting: "반가운 인사", allowance: "용돈 축하", spending: "소비 기록 안내",
  goal: "저축 목표 축하", interest: "보상 알아보기", help: "도움 안내",
};

export type CoachContext = { merchant?: string; amount?: number; eligible?: number; interest?: number };
export type CoachMessage = { mood: CoachMood; text: string };
export interface MoneyCoach { explain(mood: CoachMood, context?: CoachContext): CoachMessage }
const won = (amount: number) => amount.toLocaleString("ko-KR") + "원";

// Receives server-computed facts only. This boundary has no transaction/API access.
export const ruleBasedCoach: MoneyCoach = {
  explain(mood, facts = {}) {
    const messages: Record<CoachMood, string> = {
      greeting: "안녕! 나는 이자니야. 남은 용돈에 이자가 붙는 비밀을 알려줄게!",
      allowance: "엄마 은행에서 용돈이 도착했어!",
      spending: facts.merchant && facts.amount !== undefined
        ? `${facts.merchant}에서 ${won(facts.amount)}을 썼구나. 남은 돈도 살펴볼까?`
        : "쓴 돈을 적어 두면 내 돈을 살펴보기 쉬워!",
      goal: "저금통에 돈을 모았네! 저금통 이자는 따로 계산돼.",
      interest: facts.eligible !== undefined && facts.interest !== undefined
        ? `${won(facts.eligible)}을 남기면 ${won(facts.interest)}을 더 받을 수 있어!`
        : "돈을 남기면 부모님이 보상을 주실 수 있어!",
      celebration: "축하해! 엄마 은행에서 이자가 들어왔어!",
      help: "괜찮아. 입력한 내용을 살펴보고 다시 해 보자!",
    };
    return { mood, text: messages[mood] };
  },
};
