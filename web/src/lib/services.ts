// 홈 화면에 노출되는 서비스 목록.
// streamlitPath: 아직 Next.js로 옮기지 않은 서비스는 기존 Streamlit 페이지로 연결한다.
// href: Next.js로 옮긴 서비스는 streamlitPath 대신 href를 채우면 된다.

// MONEY:ON(별도 앱)은 같은 서버의 /moneyon/ 경로. 상대 경로라 접속한 주소(wai-labs.com·sslip.io) 안에서 이동한다.
export const MONEYON_URL = "/moneyon/";
// HF 예비 AI LAB(*.hf.space)에는 머니온이 없어 그곳에서만 이 주소를 앞에 붙인다(oracleOnly).
// HF 체험 Space(minseo2-moneyon-demo)는 예비로 남겨 둔다.
export const ORACLE_ORIGIN = "https://wai-labs.com";

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
  /** 같은 주소 안이어도 새 탭으로 연다(별도 앱). */
  newTab?: boolean;
  /** 오라클 서버에만 있는 경로. HF 예비 서버에서는 ORACLE_ORIGIN을 붙인다. */
  oracleOnly?: boolean;
  streamlitPath?: string;
};

// 홈 카드 순서 = 이 배열 순서(10-29: 드림카 → 머니온 → 스탁온 → 집온 → 보고서 작성기 → 티픽, 그 밖은 뒤에). 관리자 화면은 보임/숨김만.
export const SERVICES: Service[] = [
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
    id: "moneyon",
    category: "Prototype",
    image: "/ailab/money.webp", // 머니온 꿀벌 캐릭터 '이자니'(얼굴·동전)
    imageFallback: "/ailab/money.png",
    icon: "🐝",
    title: "MONEY:ON",
    desc: "용돈을 관리하고, 남은 돈에 이자까지!",
    href: MONEYON_URL,
    newTab: true,
    oracleOnly: true,
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
    id: "report",
    category: "AI Agent",
    image: "/ailab/report.svg",
    icon: "📄",
    title: "보고서 작성기",
    desc: "업무 내용을 경영진 보고 구조로 정리합니다.",
    href: "/report",
  },
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
];

const STREAMLIT_URL = (process.env.NEXT_PUBLIC_STREAMLIT_URL || "http://localhost:8501").replace(/\/$/, "");

/** origin: HF 예비 서버일 때만 ORACLE_ORIGIN, 그 밖에는 "" (접속한 주소 그대로). */
export function serviceLink(s: Service, origin = ""): { href: string; external: boolean } {
  if (s.href) {
    const href = s.oracleOnly && origin ? origin + s.href : s.href;
    return { href, external: !!s.newTab || /^https?:\/\//.test(href) };
  }
  return { href: `${STREAMLIT_URL}/${encodeURI(s.streamlitPath ?? "")}`, external: true };
}
