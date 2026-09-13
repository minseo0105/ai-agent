from pathlib import Path
import re
import shutil

BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"
CONFIG_PATH = BASE_DIR / ".streamlit" / "config.toml"

RENAMES = {
    "dreamcar.py": "1_내차에서_드림카까지.py",
    "realestate.py": "2_부동산_모니터.py",
    "report.py": "3_보고서_작성기.py",
    "car_selector.py": "4_차량_선택기.py",
    "gif_converter.py": "5_GIF_변환기.py",
}

# 과거 파일명도 함께 인식
KEYWORD_FALLBACKS = {
    "1_내차에서_드림카까지.py": ["내차에서드림카까지", "내차에서_드림카까지"],
    "2_부동산_모니터.py": ["부동산모니터", "부동산_모니터"],
    "3_보고서_작성기.py": ["보고서작성기", "보고서_작성기"],
    "4_차량_선택기.py": ["차량선택기", "차량_선택기"],
    "5_GIF_변환기.py": ["GIF변환기", "GIF_변환기", "gif_converter"],
}

print("=== 1. pages 파일명 정리 ===")

for old_name, new_name in RENAMES.items():
    old_path = PAGES_DIR / old_name
    new_path = PAGES_DIR / new_name

    if new_path.exists():
        print(f"[이미 완료] {new_name}")
        continue

    if old_path.exists():
        old_path.rename(new_path)
        print(f"[변경 완료] {old_name} -> {new_name}")
        continue

    # 예전 숫자+이모지 파일명이 남아 있을 때 키워드로 찾음
    candidates = list(PAGES_DIR.glob("*.py"))
    found = None
    for candidate in candidates:
        stem_lower = candidate.stem.lower()
        for keyword in KEYWORD_FALLBACKS[new_name]:
            if keyword.lower() in stem_lower.replace(" ", ""):
                found = candidate
                break
        if found:
            break

    if found:
        found.rename(new_path)
        print(f"[변경 완료] {found.name} -> {new_name}")
    else:
        print(f"[찾지 못함] {new_name}")


print("\\n=== 2. 각 상세 페이지 인증/사이드바 상태 확인 ===")

for path in sorted(PAGES_DIR.glob("*.py")):
    if path.name == "__init__.py":
        continue

    original = path.read_text(encoding="utf-8")

    # 백업 1회
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)

    updated = original

    # 모바일/웹에서 사이드바가 기본적으로 보이도록 collapsed -> expanded
    updated = updated.replace(
        'initial_sidebar_state="collapsed"',
        'initial_sidebar_state="expanded"'
    )
    updated = updated.replace(
        "initial_sidebar_state='collapsed'",
        "initial_sidebar_state='expanded'"
    )

    # auth import가 없으면 streamlit import 다음에 삽입
    auth_import = "from auth import require_page_auth, show_home_button"
    if auth_import not in updated:
        lines = updated.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip() == "import streamlit as st":
                insert_at = i + 1
                break
        lines.insert(insert_at, auth_import)
        updated = "\\n".join(lines) + "\\n"

    # set_page_config 블록의 끝 찾기
    def config_end_index(lines):
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

    # 인증 호출이 없을 때만 추가
    if "require_page_auth()" not in updated or "show_home_button()" not in updated:
        lines = updated.splitlines()
        end_idx = config_end_index(lines)

        insertion = [
            "",
            "require_page_auth()",
            "show_home_button()",
            "",
        ]

        if end_idx is not None:
            pos = end_idx + 1
        else:
            pos = 0
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    pos = i + 1

        for offset, line in enumerate(insertion):
            lines.insert(pos + offset, line)

        updated = "\\n".join(lines) + "\\n"

    path.write_text(updated, encoding="utf-8")
    print(f"[확인 완료] {path.name}")


print("\\n=== 3. config.toml 기본 페이지 메뉴 다시 켜기 ===")

if CONFIG_PATH.exists():
    config = CONFIG_PATH.read_text(encoding="utf-8")

    # showSidebarNavigation=false 라인만 제거하고 나머지 설정은 보존
    config = re.sub(
        r"(?mi)^\\s*showSidebarNavigation\\s*=\\s*false\\s*$\\n?",
        "",
        config,
    )

    CONFIG_PATH.write_text(config, encoding="utf-8")
    print("[완료] showSidebarNavigation=false 제거")
else:
    print("[안내] config.toml 없음 - 기본 페이지 메뉴가 자동으로 표시됩니다.")


print("\\n=== 현재 pages 폴더 ===")
for path in sorted(PAGES_DIR.glob("*.py")):
    print(" -", path.name)

print("""
완료했습니다.

다음 파일명이 보여야 정상입니다.
 - 1_내차에서_드림카까지.py
 - 2_부동산_모니터.py
 - 3_보고서_작성기.py
 - 4_차량_선택기.py
 - 5_GIF_변환기.py

이제 서버를 다음 명령으로 실행하세요.

python -m streamlit run 메인.py
""")
