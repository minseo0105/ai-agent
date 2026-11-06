// 1,190건 고정 데이터(결정적). 실제 운영 DB의 개수 구성(1,190건 중 좌표 849건)을 따른 합성 데이터이며
// 실제 사업 좌표가 아니다. 클러스터·필터 회귀 검증에만 쓴다.
export const TOTAL = 1190;
export const LOCATED = 849;

function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const DISTRICTS = ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구", "노원구", "도봉구",
  "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구", "양천구", "영등포구", "용산구",
  "은평구", "종로구", "중구", "중랑구"];
const TYPES = [["재개발", 0.4], ["재건축", 0.2], ["모아타운", 0.25], ["정비사업", 0.15]];
const STAGES = ["세부 진행단계 확인 중", "조합설립 인가", "사업시행 인가", "관리처분 인가", "추진위원회 승인", "정비구역 지정",
  "철거", "착공", "준공", "이전고시", "조합 해산", "조합 청산"];

function pick(rand, table) {
  let x = rand();
  for (const [value, weight] of table) { if ((x -= weight) < 0) return value; }
  return table[table.length - 1][0];
}

export function makeProjects() {
  const rand = mulberry32(20261106);
  const projects = [];
  for (let i = 0; i < TOTAL; i++) {
    const district = DISTRICTS[Math.floor(rand() * DISTRICTS.length)];
    const type_label = pick(rand, TYPES);
    const program_label = type_label === "모아타운" ? "모아타운" : rand() < 0.12 ? "신속통합기획" : null;
    const stage = STAGES[Math.floor(rand() * STAGES.length)];
    const dong = `${["천호", "둔촌", "길", "상계", "공릉", "신길", "마천", "거여", "장위", "미아"][i % 10]}동`;
    projects.push({
      project_id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
      name: `${dong}${(i % 37) + 1}구역 ${type_label}`,
      address: i % 9 === 0 ? null : `서울 ${district} ${dong} ${i % 400 + 1}-${i % 17 + 1}`,
      dong: i % 11 === 0 ? null : dong, district, type_label, program_label, stage: { label: stage },
    });
  }
  return projects;
}

/** 좌표가 있는 정확히 849건(서울 경계 상자 안, 일부는 같은 좌표·가까운 좌표)과 없는 341건. */
export function makePoints(projects) {
  const rand = mulberry32(777);
  const order = projects.map((_, i) => i);
  for (let i = order.length - 1; i > 0; i--) { // 결정적 셔플
    const j = Math.floor(rand() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const located = new Set(order.slice(0, LOCATED));
  return projects.map((p, i) => {
    if (!located.has(i)) return { project_id: p.project_id, latitude: null, longitude: null };
    if (i % 50 === 0) return { project_id: p.project_id, latitude: 37.5, longitude: 127.0 }; // 같은 좌표
    const dense = i % 5 === 0; // 일부는 서로 가깝게 몰려 있다
    const latitude = dense ? 37.55 + rand() * 0.04 : 37.43 + rand() * 0.2;
    const longitude = dense ? 126.95 + rand() * 0.06 : 126.8 + rand() * 0.3;
    return { project_id: p.project_id, latitude, longitude };
  });
}
