from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"

TARGETS = {
    "내차에서드림카까지": "dreamcar.py",
    "부동산모니터": "realestate.py",
    "보고서작성기": "report.py",
    "차량선택기": "car_selector.py",
    "GIF변환기": "gif_converter.py",
}

print(f"[pages 폴더] {PAGES_DIR}")
print()

if not PAGES_DIR.exists():
    raise SystemExit("pages 폴더를 찾을 수 없습니다.")

files = list(PAGES_DIR.glob("*.py"))

for keyword, new_name in TARGETS.items():
    new_path = PAGES_DIR / new_name

    if new_path.exists():
        print(f"[이미 완료] {new_name}")
        continue

    matches = [p for p in files if keyword.lower() in p.stem.lower()]

    if not matches:
        print(f"[찾지 못함] 키워드={keyword}")
        continue

    old_path = matches[0]
    old_path.rename(new_path)
    print(f"[변경 완료] {old_path.name}  ->  {new_name}")

print("\n=== 현재 pages 폴더 ===")
for p in sorted(PAGES_DIR.glob("*.py")):
    print(" -", p.name)

print("\n위 목록에 dreamcar.py, realestate.py, report.py, car_selector.py, gif_converter.py가 모두 보이면 성공입니다.")
