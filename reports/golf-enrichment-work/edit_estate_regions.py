from pathlib import Path
r=Path(__file__).resolve().parents[2]
def edit(p,a,b):
 f=r/p;s=f.read_text(encoding='utf-8');assert a in s,p;f.write_text(s.replace(a,b,1),encoding='utf-8')
p='web/src/components/realestate/RegionPicker.tsx'
edit(p,'  defaultScope = "전체",','  defaultScope = "전체",\n  selectWholeScope = false,')
edit(p,'  defaultScope?: "서울" | "경기" | "전체";','  defaultScope?: "서울" | "경기" | "전체";\n  selectWholeScope?: boolean;')
edit(p,'onChange={setScope} ariaLabel="지역 범위"','onChange={(next) => {\n          setScope(next);\n          setQ("");\n          if (selectWholeScope) onChange(next === "서울" ? [...regions.서울] : next === "경기" ? [...regions.경기] : [...regions.서울, ...regions.경기]);\n        }} ariaLabel="지역 범위"')
edit(p,'      <div className="max-h-44','      {selectWholeScope && <p className="text-xs text-muted">서울·경기를 누르면 해당 지역 전체가 선택됩니다. 전체는 서울+경기이며, 아래에서 개별 지역을 선택하거나 해제할 수 있습니다.</p>}\n      <div className="max-h-44')
p='web/src/components/realestate/EstateMonitor.tsx'
edit(p,'  const [appliedPrice, setAppliedPrice] = useState<number | null>(null);','  const [appliedPrice, setAppliedPrice] = useState<number | null>(null);\n  const [progress, setProgress] = useState({ done: 0, total: 0 });')
edit(p,'    setResult(null);\n    try {\n      setResult(await estateApi.trades({ regions, property_types: types, month, max_price_100m: price }));','    setResult(null);\n    setProgress({ done: 0, total: regions.length });\n    try {\n      setResult(await estateApi.trades({ regions, property_types: types, month, max_price_100m: price }, (done, total) => setProgress({ done, total })));')
edit(p,'      <Field label="조회지역">\n        <RegionPicker regions={options.regions} value={regions} onChange={setRegions} />','      <Field label="조회지역">\n        <RegionPicker regions={options.regions} value={regions} onChange={setRegions} selectWholeScope />')
edit(p,'{loading && <Spinner label={`${regions.length * types.length}개 조합을 조회하고 있어요…`} />}','{loading && <Spinner label={`지역 ${progress.done}/${progress.total}곳 조회 완료 · 전체 지역은 나누어 조회하므로 시간이 걸릴 수 있어요…`} />}')
p='web/src/lib/realestate.ts'
edit(p,'  trades: (q: { regions: string[]; property_types: string[]; month: string; max_price_100m?: number }) =>\n    post<{ items: Trade[]; errors: string[]; counts: Record<string, number>; requests: number }>("/trades", q),','''  trades: async (q: { regions: string[]; property_types: string[]; month: string; max_price_100m?: number }, onProgress?: (done: number, total: number) => void) => {
    const regions = [...new Set(q.regions)];
    const result = { items: [] as Trade[], errors: [] as string[], counts: {} as Record<string, number>, requests: 0 };
    // 서버의 40개 조합 제한을 유지하고 긴 요청을 줄이기 위해 지역을 5개씩 순차 조회한다.
    for (let start = 0; start < regions.length; start += 5) {
      const batch = regions.slice(start, start + 5);
      try {
        const response = await post<typeof result>("/trades", { ...q, regions: batch });
        result.items.push(...response.items);
        result.errors.push(...response.errors);
        result.requests += response.requests;
      } catch (e) {
        result.errors.push(`${batch.join(", ")}: ${(e as Error).message}`);
      }
      onProgress?.(Math.min(start + batch.length, regions.length), regions.length);
    }
    result.items.sort((a, b) => b.date.localeCompare(a.date));
    for (const item of result.items) result.counts[item.property_type] = (result.counts[item.property_type] ?? 0) + 1;
    return result;
  },''')
print('region selection and batching applied')
