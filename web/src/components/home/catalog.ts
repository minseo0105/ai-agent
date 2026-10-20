import { SERVICES, type Service } from "@/lib/services";
import type { ArtworkKind } from "./ServiceArtwork";

export const CATEGORIES = ["전체", "AI Agent", "Prototype", "API / Search"] as const;
export type Category = typeof CATEGORIES[number];
export type CatalogItem = { service: Service; name: string; subtitle: string; capability: string; category: Exclude<Category, "전체">; artwork: ArtworkKind };

const presentation: Record<string, Omit<CatalogItem, "service">> = {
  moneyon: { name: "MONEY:ON", subtitle: "용돈을 관리하고, 남은 돈에 이자까지!", capability: "용돈 기록 · 저축 · 이자 체험", category: "Prototype", artwork: "moneyon" },
  golf: { name: "TEE:PICK", subtitle: "오늘, 어디서 칠까?", capability: "조건 검색 · 골프장 추천", category: "API / Search", artwork: "golf" },
  dreamcar: { name: "DREAM", subtitle: "시세부터 드림카까지", capability: "내 차 시세 · 맞춤 추천", category: "API / Search", artwork: "dreamcar" },
  realestate: { name: "ZIP:ON", subtitle: "부동산 변화를 한눈에", capability: "실거래 · 청약 · 개발정보", category: "API / Search", artwork: "realestate" },
  report: { name: "AI 보고서", subtitle: "생각을 명확한 문서로", capability: "보고서 구조화 · 작성 지원", category: "Prototype", artwork: "report" },
  saju: { name: "AI 사주", subtitle: "사주 · 대운 분석", capability: "오행과 대운의 흐름 탐색", category: "Prototype", artwork: "saju" },
  "car-selector": { name: "차량 선택기", subtitle: "나에게 맞는 차 찾기", capability: "조건별 차량 탐색", category: "Prototype", artwork: "car-selector" },
  gif: { name: "GIF 변환기", subtitle: "이미지를 움직이게", capability: "이미지로 만드는 GIF", category: "Prototype", artwork: "gif" },
};

// Presentation only. Keep every registered service and its original navigation.
const displayOrder = ["golf", "dreamcar", "realestate", "report", "saju"];
export const CATALOG: CatalogItem[] = [...SERVICES].sort((a, b) => {
  const rank = (id: string) => { const index = displayOrder.indexOf(id); return index < 0 ? displayOrder.length : index; };
  return rank(a.id) - rank(b.id);
}).map(service => ({ service,
  ...(presentation[service.id] ?? { name: service.title, subtitle: service.desc, capability: "AI LAB 서비스", category: "Prototype" as const, artwork: "report" as const }),
}));
export const AGENT: CatalogItem = {
  service: { id: "agent", icon: "", title: "AI 에이전트", desc: "공시·법령·웹 검색을 호출하는 도구형 에이전트", href: "#agent" },
  name: "AI 에이전트", subtitle: "질문에서 인사이트로", capability: "기업 공시 · 법령 · 웹 검색", category: "AI Agent", artwork: "agent",
};
