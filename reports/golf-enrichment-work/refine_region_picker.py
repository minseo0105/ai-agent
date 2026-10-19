from pathlib import Path
p=Path(__file__).resolve().parents[2]/'web'/'src'/'components'/'realestate'/'RegionPicker.tsx'
s=p.read_text(encoding='utf-8')
s=s.replace('  const selectedShort = value.filter((v) => visible.includes(v)).map(short);','  const wholeSelected = selectWholeScope && pool.length > 0 && pool.every((r) => value.includes(r));\n  const selectedShort = wholeSelected ? [] : value.filter((v) => visible.includes(v)).map(short);\n  const wholeLabel = scope === "전체" ? "서울·경기 전체" : `${scope} 전체`;')
s=s.replace('          if (selectWholeScope) onChange(next === "서울" ? [...regions.서울] : next === "경기" ? [...regions.경기] : [...regions.서울, ...regions.경기]);','')
s=s.replace('서울·경기를 누르면 해당 지역 전체가 선택됩니다. 전체는 서울+경기이며, 아래에서 개별 지역을 선택하거나 해제할 수 있습니다.','아래에서 전체 또는 원하는 시·군·구를 선택하세요. 전체 선택 후 개별 지역을 누르면 해당 지역만 선택됩니다. 다른 시도의 선택은 유지됩니다.')
s=s.replace('        <ChoiceChips','''        {selectWholeScope && (
          <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-border pb-3">
            <button type="button" aria-pressed={wholeSelected} onClick={() => onChange(wholeSelected ? value.filter((r) => !pool.includes(r)) : [...new Set([...value, ...pool])])} className={`rounded-full border px-3 py-1.5 text-xs font-bold ${wholeSelected ? "border-estate bg-estate text-white" : "border-border text-estate"}`}>
              {wholeSelected ? "✓ " : ""}{wholeLabel}
            </button>
            <button type="button" onClick={() => onChange(value.filter((r) => !pool.includes(r)))} className="text-xs text-muted hover:text-fg">이 지역 선택 해제</button>
          </div>
        )}
        <ChoiceChips''',1)
s=s.replace('            onChange(value.includes(full) ? value.filter((x) => x !== full) : [...value, full]);','            onChange(wholeSelected ? [...value.filter((r) => !pool.includes(r)), full] : value.includes(full) ? value.filter((x) => x !== full) : [...value, full]);')
p.write_text(s,encoding='utf-8')
print('Updated hierarchical selection')
