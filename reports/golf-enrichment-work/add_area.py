from pathlib import Path
r=Path(__file__).resolve().parents[2]
def edit(p,a,b):
 f=r/p;s=f.read_text(encoding='utf-8');assert a in s,p;f.write_text(s.replace(a,b,1),encoding='utf-8')
p='services/realestate_monitor.py'
edit(p,'    year = _xml_text(item, "dealYear")','''    area_keys = (["totalFloorAr", "buildingAr", "excluUseAr", "plottageAr"] if property_type == "단독·다가구" else ["excluUseAr", "area", "buildingAr"])
    area_key = next((key for key in area_keys if _xml_text(item, key).strip()), "")
    area_basis = {"totalFloorAr": "연면적", "buildingAr": "건물면적", "excluUseAr": "전용면적", "plottageAr": "대지면적"}.get(area_key, "면적 기준 미확인")
    year = _xml_text(item, "dealYear")''')
edit(p,'        "area": area,','        "area": area,\n        "area_basis": area_basis,')
edit(p,'def fetch_trade(\n','''def filter_trade_area(rows, max_area=None):
    if max_area is None:
        return list(rows)
    def matches(row):
        if row.get("area_basis") not in {"전용면적", "연면적", "건물면적"}:
            return False
        try:
            area = float(row.get("area"))
        except (TypeError, ValueError):
            return False
        return math.isfinite(area) and 0 < area <= max_area
    return [row for row in rows if matches(row)]


def fetch_trade(
''')
p='api/realestate.py'
edit(p,'    max_price_100m: float | None = Field(None, gt=0, le=10000, allow_inf_nan=False)','    max_price_100m: float | None = Field(None, gt=0, le=10000, allow_inf_nan=False)\n    max_area: float | None = Field(None, gt=0, le=100000, allow_inf_nan=False)')
edit(p,'    rows = rm.filter_trade_price(rows, q.max_price_100m)','    rows = rm.filter_trade_price(rows, q.max_price_100m)\n    rows = rm.filter_trade_area(rows, q.max_area)')
p='web/src/lib/realestate.ts'
edit(p,'  area: number;','  area: number;\n  area_basis?: string;')
edit(p,'month: string; max_price_100m?: number }','month: string; max_price_100m?: number; max_area?: number }')
p='web/src/components/realestate/EstateMonitor.tsx'
edit(p,'  const [maxPrice, setMaxPrice] = useState("");','  const [maxPrice, setMaxPrice] = useState("");\n  const [maxArea, setMaxArea] = useState("");\n  const [appliedArea, setAppliedArea] = useState<number | null>(null);')
edit(p,'    setLoading(true);\n    setResult(null);','    const area = maxArea.trim() === "" ? undefined : Number(maxArea);\n    if (area !== undefined && (!Number.isFinite(area) || area <= 0 || area > 100000)) return setError("최대 면적은 0보다 크고 100,000㎡ 이하로 입력해주세요.");\n    setLoading(true);\n    setResult(null);')
edit(p,'month, max_price_100m: price }','month, max_price_100m: price, max_area: area }')
edit(p,'      setAppliedPrice(price ?? null);','      setAppliedPrice(price ?? null);\n      setAppliedArea(area ?? null);')
edit(p,'      <PrimaryButton onClick={search} disabled={loading}>','''      <Field label="최대 면적" hint="㎡ 단위 · 비워두면 전체 · 입력한 면적 포함 이하">
        <div className="flex items-center gap-2">
          <input aria-label="최대 면적 (㎡)" type="number" inputMode="decimal" min="0.01" max="100000" step="0.01" placeholder="예: 85 → 85㎡ 이하" value={maxArea} onChange={(e) => setMaxArea(e.target.value)} className={`${inputClass} max-w-64`} />
          <span className="shrink-0 text-sm text-muted">㎡ 이하</span>
        </div>
        <div className="mt-2">
          <ChoiceChips accent="estate" options={["면적 전체", "60㎡ 이하", "85㎡ 이하", "102㎡ 이하", "135㎡ 이하"]} selected={[maxArea === "" ? "면적 전체" : `${maxArea}㎡ 이하`]} onToggle={(v) => setMaxArea(v === "면적 전체" ? "" : v.replace("㎡ 이하", ""))} />
        </div>
        {Number(maxArea) > 0 && Number.isFinite(Number(maxArea)) && <p className="mt-2 text-xs text-estate">약 {(Number(maxArea) / 3.3058).toFixed(1)}평 이하 · 입력 면적 환산</p>}
        <p className="mt-2 text-xs text-muted">아파트·연립·오피스텔은 전용면적, 단독·다가구는 연면적 또는 건물면적 기준입니다. 공급면적 기준 평형과 다를 수 있으며, 면적·기준 미확인 및 대지면적만 있는 거래는 면적 조건 적용 시 제외합니다.</p>
      </Field>
      <PrimaryButton onClick={search} disabled={loading}>''')
edit(p,'{appliedPrice === null ? "가격 전체" : `${appliedPrice}억원 이하`}','{appliedPrice === null ? "가격 전체" : `${appliedPrice}억원 이하`} · {appliedArea === null ? "면적 전체" : `${appliedArea}㎡ 이하`}')
edit(p,'가격 상한·지역·계약년월을','가격·면적 상한·지역·계약년월을')
edit(p,'{it.area > 0 ? `${it.area.toFixed(1)}㎡','{it.area_basis ?? "면적 기준 미확인"} · {it.area > 0 ? `${it.area.toFixed(1)}㎡')
print('area filter applied')
