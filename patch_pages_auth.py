from pathlib import Path
import shutil

BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"

TARGETS = [
    "dreamcar.py",
    "realestate.py",
    "report.py",
    "car_selector.py",
    "gif_converter.py",
]

IMPORT_LINE = "from auth import require_page_auth, show_home_button"
CALL_BLOCK = "require_page_auth()\\nshow_home_button()\\n"

def find_set_page_config_end(lines):
    start = None
    depth = 0

    for i, line in enumerate(lines):
        if start is None and "st.set_page_config(" in line:
            start = i

        if start is not None:
            depth += line.count("(")
            depth -= line.count(")")
            if depth <= 0:
                return i

    return None

for filename in TARGETS:
    path = PAGES_DIR / filename

    if not path.exists():
        print(f"[없음] {filename}")
        continue

    original = path.read_text(encoding="utf-8")
    backup = path.with_suffix(path.suffix + ".bak")

    if not backup.exists():
        shutil.copy2(path, backup)

    lines = original.splitlines()

    # auth import 추가
    if IMPORT_LINE not in original:
        streamlit_import_idx = next(
            (i for i, line in enumerate(lines) if line.strip() == "import streamlit as st"),
            None
        )
        if streamlit_import_idx is not None:
            lines.insert(streamlit_import_idx + 1, IMPORT_LINE)
        else:
            lines.insert(0, IMPORT_LINE)

    updated = "\\n".join(lines) + "\\n"

    # 기존 호출이 없을 때 set_page_config 다음에 추가
    if "show_home_button()" not in updated or "require_page_auth()" not in updated:
        lines = updated.splitlines()
        config_end = find_set_page_config_end(lines)

        if config_end is not None:
            insertion = ["", "require_page_auth()", "show_home_button()", ""]
            for offset, item in enumerate(insertion, start=1):
                lines.insert(config_end + offset, item)
        else:
            # set_page_config가 없는 페이지면 import 구간 뒤에 추가
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    insert_idx = i + 1
            insertion = ["", "require_page_auth()", "show_home_button()", ""]
            for offset, item in enumerate(insertion):
                lines.insert(insert_idx + offset, item)

        updated = "\\n".join(lines) + "\\n"

    path.write_text(updated, encoding="utf-8")
    print(f"[완료] {filename}")

print("\\n모든 상세 페이지에 인증 + 한글 사이드바 호출을 확인했습니다.")
print("문제가 생기면 각 .py.bak 파일로 원복할 수 있습니다.")
