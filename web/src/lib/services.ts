// 홈 화면에 노출되는 서비스 목록.
// streamlitPath: 아직 Next.js로 옮기지 않은 서비스는 기존 Streamlit 페이지로 연결한다.
// href: Next.js로 옮긴 서비스는 streamlitPath 대신 href를 채우면 된다.

export type Service = {
  id: string;
  icon: string;
  title: string;
  desc: string;
  tags?: string[];
  featured?: boolean;
  secondary?: boolean;
  href?: string;
  streamlitPath?: string;
};

export const SERVICES: Service[] = [
  {
    id: "golf",
    icon: "⛳",
    title: "나에게 맞는 골프장 찾기",
    desc: "전국 골프장을 조건이나 AI 문장으로 탐색하고, KGA 코스정보와 실제 후기까지 한 곳에서 살펴봅니다.",
    tags: ["전국 골프장", "KGA 코스정보", "AI 문장검색", "실제 후기"],
    featured: true,
    href: "/golf",
  },
  {
    id: "dreamcar",
    icon: "🚙",
    title: "내차에서 드림카까지",
    desc: "내 차 시세를 확인하고 다음 차량을 탐색·추천받습니다.",
    streamlitPath: "내차에서_드림카까지",
  },
  {
    id: "realestate",
    icon: "🏠",
    title: "부동산 모니터",
    desc: "청약 · 실거래 · 관심지역을 모니터링합니다.",
    href: "/realestate",
  },
  {
    id: "report",
    icon: "📄",
    title: "보고서 작성기",
    desc: "업무 내용을 경영진 보고 구조로 정리합니다.",
    streamlitPath: "보고서_작성기",
  },
  {
    id: "saju",
    icon: "🔮",
    title: "AI 사주 · 대운 분석",
    desc: "사주팔자 · 오행 · 대운 흐름을 분석합니다.",
    streamlitPath: "saju",
  },
  {
    id: "car-selector",
    icon: "🚗",
    title: "차량 선택기",
    desc: "조건에 맞는 차량을 골라봅니다.",
    secondary: true,
    streamlitPath: "차량_선택기",
  },
  {
    id: "gif",
    icon: "🎞️",
    title: "GIF 변환기",
    desc: "이미지를 GIF로 변환합니다.",
    secondary: true,
    streamlitPath: "GIF_변환기",
  },
];

const STREAMLIT_URL = (process.env.NEXT_PUBLIC_STREAMLIT_URL || "http://localhost:8501").replace(/\/$/, "");

export function serviceLink(s: Service): { href: string; external: boolean } {
  if (s.href) return { href: s.href, external: false };
  return { href: `${STREAMLIT_URL}/${encodeURI(s.streamlitPath ?? "")}`, external: true };
}
