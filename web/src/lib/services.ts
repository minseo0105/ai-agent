// 홈 화면에 노출되는 서비스 목록.
// streamlitPath: 아직 Next.js로 옮기지 않은 서비스는 기존 Streamlit 페이지로 연결한다.
// href: Next.js로 옮긴 서비스는 streamlitPath 대신 href를 채우면 된다.

// MONEY:ON(별도 앱) 주소는 여기 한 곳에서만 관리한다. 도메인을 바꾸면 이 줄만 고친다.
// HF AI LAB에서도 같은 주소(오라클)로 연결된다. HF 체험 Space(minseo2-moneyon-demo)는 예비로 남겨 둔다.
export const MONEYON_URL = "https://140-245-88-198.sslip.io/moneyon";

export type ServiceCategory = "AI Agent" | "Prototype" | "API·Search";
export const CATEGORIES: ServiceCategory[] = ["AI Agent", "Prototype", "API·Search"];

export type Service = {
  id: string;
  icon: string;
  title: string;
  desc: string;
  tags?: string[];
  /** 홈 필터 분류 */
  category: ServiceCategory;
  /** public/ailab 아래 텍스트 없는 비주얼. 서비스명·설명은 항상 HTML로 따로 그린다. */
  image: string;
  /** image 로드에 실패하면 대신 쓰는 이미지(기존 SVG). */
  imageFallback?: string;
  featured?: boolean;
  secondary?: boolean;
  href?: string;
  streamlitPath?: string;
};

export const SERVICES: Service[] = [
  {
    id: "golf",
    category: "API·Search",
    image: "/ailab/tee.webp",
    imageFallback: "/ailab/tee.svg",
    icon: "⛳",
    title: "TEE:PICK · 오늘, 어디서 칠까?",
    desc: "지역 · 시간 · 라운드 조건만 골라주세요. 내 조건에 맞는 골프장을 AI가 찾아드립니다.",
    tags: ["수도권·충청·강원", "KGA 코스정보", "AI 문장검색", "실제 후기"],
    featured: true,
    href: "/golf",
  },
  {
    id: "dreamcar",
    category: "Prototype",
    image: "/ailab/dream.webp",
    imageFallback: "/ailab/dream.svg",
    icon: "🚙",
    title: "내차에서 드림카까지",
    desc: "내 차 시세를 확인하고 다음 차량을 탐색·추천받습니다.",
    href: "/dreamcar",
  },
  {
    id: "realestate",
    category: "API·Search",
    image: "/ailab/zip.webp",
    imageFallback: "/ailab/zip.svg",
    icon: "🏠",
    title: "ZIP:ON · 부동산 변화를 한눈에",
    desc: "실거래가 · 청약 · 재개발을 확인하고 관심지역의 변화를 모니터링합니다.",
    tags: ["실거래가", "청약", "개발사업", "관심지역 모니터링"],
    href: "/realestate",
  },
  {
    id: "stockon",
    category: "Prototype",
    image: "/ailab/stock.svg",
    icon: "📈",
    title: "STOCK:ON · 뉴스 한 줄, 연결된 회사까지",
    desc: "오늘의 뉴스가 어떤 회사들에 영향을 줄 수 있는지 AI가 해석하고, 실제 등락(등락률)과 나란히 보여 줍니다. 지수·히트맵·등락 상위도 함께.",
    tags: ["뉴스 속 숨은 종목", "AI 해석", "실제 등락", "히트맵"],
    href: "/stock",
  },
  {
    id: "report",
    category: "AI Agent",
    image: "/ailab/report.svg",
    icon: "📄",
    title: "보고서 작성기",
    desc: "업무 내용을 경영진 보고 구조로 정리합니다.",
    href: "/report",
  },
  {
    id: "saju",
    category: "AI Agent",
    image: "/ailab/saju.svg",
    icon: "🔮",
    title: "AI 사주 · 대운 분석",
    desc: "사주팔자 · 오행 · 대운 흐름을 분석합니다.",
    href: "/saju",
  },
  {
    id: "car-selector",
    category: "Prototype",
    image: "/ailab/car-selector.svg",
    icon: "🚗",
    title: "차량 선택기",
    desc: "조건에 맞는 차량을 골라봅니다.",
    secondary: true,
    href: "/car-selector",
  },
  {
    id: "gif",
    category: "Prototype",
    image: "/ailab/gif.svg",
    icon: "🎞️",
    title: "GIF 변환기",
    desc: "이미지를 GIF로 변환합니다.",
    secondary: true,
    href: "/gif",
  },
  {
    id: "moneyon",
    category: "Prototype",
    image: "/ailab/money.webp", // 머니온 꿀벌 캐릭터 '이자니'(얼굴·동전)
    imageFallback: "/ailab/money.png",
    icon: "🐝",
    title: "MONEY:ON",
    desc: "용돈을 관리하고, 남은 돈에 이자까지!",
    href: MONEYON_URL,
  },
];

const STREAMLIT_URL = (process.env.NEXT_PUBLIC_STREAMLIT_URL || "http://localhost:8501").replace(/\/$/, "");

export function serviceLink(s: Service): { href: string; external: boolean } {
  if (s.href) return { href: s.href, external: /^https?:\/\//.test(s.href) };
  return { href: `${STREAMLIT_URL}/${encodeURI(s.streamlitPath ?? "")}`, external: true };
}
