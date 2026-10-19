from pathlib import Path
r=Path(__file__).resolve().parents[2]
def edit(p,a,b):
 f=r/p;s=f.read_text(encoding='utf-8');assert a in s,p;f.write_text(s.replace(a,b,1),encoding='utf-8')
p='web/src/app/realestate/page.tsx'
edit(p,'부동산 모니터 · 디지털전략부 AI LAB','ZIP:ON · 디지털전략부 AI LAB')
edit(p,'서울·경기 청약과 실거래를 조건별로 조회하고, 관심지역의 새 변화를 자동으로 알려줍니다.','관심지역의 변화를 켜두세요. 청약부터 실거래까지, 내가 보고 있는 지역의 새로운 변화를 찾아냅니다.')
edit(p,'🏠 부동산 모니터','🏠 ZIP:ON')
edit(p,'REAL ESTATE MONITORING AGENT','Real Estate Signal Agent')
edit(p,'          내가 기다리던 청약과 부동산 변화,\n          <br />\n          놓치지 않도록.','          ZIP:ON')
edit(p,'        <p className="mt-3 max-w-xl','        <p className="mt-3 text-lg font-bold sm:text-xl">관심지역의 변화를 켜두세요.</p>\n        <p className="mt-3 max-w-xl')
edit(p,'서울·경기의 청약과 아파트·빌라·단독/다가구·오피스텔 실거래를 조건별로 조회하고, 관심지역의 새로운 변화를 자동으로 탐지합니다.','청약부터 실거래까지,<br />내가 보고 있는 지역의 새로운 변화를 찾아냅니다.')
edit('web/src/lib/services.ts','title: "부동산 모니터"','title: "ZIP:ON"')
edit('web/src/components/access/AccessProvider.tsx','realestate: "🏠 부동산 모니터"','realestate: "🏠 ZIP:ON"')
p='web/src/lib/realestate.ts'
with (r/p).open('a',encoding='utf-8') as f:f.write('''
export type TradeSort = "최근 거래일 순" | "가격 낮은 순" | "가격 높은 순" | "면적 작은 순" | "면적 큰 순";
export function sortTrades(items: Trade[], order: TradeSort): Trade[] {
  return [...items].sort((a, b) => {
    if (order === "최근 거래일 순") return b.date.localeCompare(a.date);
    const key = order.startsWith("가격") ? "price_100m" : "area";
    const av = a[key], bv = b[key];
    const validA = Number.isFinite(av) && av > 0;
    const validB = Number.isFinite(bv) && bv > 0;
    if (validA !== validB) return validA ? -1 : 1;
    const descending = order === "가격 높은 순" || order === "면적 큰 순";
    const delta = validA && validB ? (av - bv) * (descending ? -1 : 1) : 0;
    return delta || b.date.localeCompare(a.date);
  });
}
''')
p='web/src/components/realestate/EstateMonitor.tsx'
edit(p,'  currentMonth,','  currentMonth,\n  sortTrades,\n  type TradeSort,')
edit(p,'  const [typeFilter, setTypeFilter] = useState<string[]>([]);','  const [typeFilter, setTypeFilter] = useState<string[]>([]);\n  const [sort, setSort] = useState<TradeSort>("최근 거래일 순");')
edit(p,'  const items = (result?.items ?? []).filter((x) => !typeFilter.length || typeFilter.includes(x.property_type));','  const items = sortTrades((result?.items ?? []).filter((x) => !typeFilter.length || typeFilter.includes(x.property_type)), sort);')
edit(p,'          <p className="text-xs text-subtle">\n            {items.length}건 · 최근 거래일 순','''          <label className="flex items-center gap-2 text-sm font-semibold">
            결과 정렬
            <select aria-label="실거래 결과 정렬" value={sort} onChange={(e) => { setSort(e.target.value as TradeSort); setVisible(40); }} className={`${inputClass} max-w-48`}>
              {(["최근 거래일 순", "가격 낮은 순", "가격 높은 순", "면적 작은 순", "면적 큰 순"] as TradeSort[]).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <p className="text-xs text-subtle">
            {items.length}건 · {sort}''')
edit(p,'ariaLabel="부동산 모니터 메뉴"','ariaLabel="ZIP:ON 메뉴"')
print('ZIP:ON and sorting applied')
