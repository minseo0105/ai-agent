from pathlib import Path
import re
import streamlit as st

from services.site_link import new_site_button


# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "pages"

# 파일명에 따라 보기 좋은 이름/아이콘을 지정하고 싶은 경우만 등록
PAGE_META = {
    "6_골프장_추천.py": ("⛳", "골프장 추천", "service"),
    "1_내차에서_드림카까지.py": ("🚙", "내차에서 드림카까지", "service"),
    "2_부동산_모니터.py": ("🏠", "부동산 모니터", "service"),
    "3_보고서_작성기.py": ("📄", "보고서 작성기", "service"),
    "4_차량_선택기.py": ("🚗", "차량 선택기", "tool"),
    "5_GIF_변환기.py": ("🎞️", "GIF 변환기", "tool"),
    "saju.py": ("🔮", "AI 사주 · 대운 분석", "service"),
}

# 메뉴에서 숨기고 싶은 파일
HIDDEN_PAGES = {
    "__init__.py",
}


def _pretty_name(filename: str):
    stem = Path(filename).stem

    # 앞 숫자 제거: 1_페이지명 -> 페이지명
    stem = re.sub(r"^\d+_", "", stem)

    # 언더바를 공백으로
    stem = stem.replace("_", " ")

    return stem


def _sort_key(path: Path):
    """숫자 prefix가 있으면 먼저 정렬."""
    m = re.match(r"^(\d+)_", path.name)
    if m:
        return (0, int(m.group(1)), path.name.lower())
    return (1, 9999, path.name.lower())


def discover_pages():
    """
    pages 폴더의 .py 파일을 자동 검색.
    PAGE_META에 없는 새 파일도 자동으로 메뉴에 나타납니다.
    """
    if not PAGES_DIR.exists():
        return []

    results = []

    for p in sorted(PAGES_DIR.glob("*.py"), key=_sort_key):
        if p.name in HIDDEN_PAGES:
            continue
        if p.name.startswith("_"):
            continue

        if p.name in PAGE_META:
            icon, label, group = PAGE_META[p.name]
        else:
            # 새 페이지 자동 등록
            icon = "✨"
            label = _pretty_name(p.name)
            group = "service"

        results.append({
            "filename": p.name,
            "page_path": f"pages/{p.name}",
            "icon": icon,
            "label": label,
            "group": group,
        })

    return results


def _nav_button(item, current_page=None):
    is_current = current_page == item["filename"]

    label = f"{item['icon']}  {item['label']}"

    if is_current:
        st.markdown(
            f"""
            <div style="
                padding:13px 14px;
                border-radius:13px;
                border:1px solid #D9B96E;
                background:#FFF2CC;
                font-weight:800;
                margin-bottom:8px;
            ">
                {label}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if st.button(
            label,
            key=f"nav_{item['filename']}",
            use_container_width=True,
        ):
            st.switch_page(item["page_path"])


def render_sidebar(current_page=None):
    """
    모든 서비스 페이지에서 동일한 왼쪽 메뉴를 출력합니다.

    사용 예:
        from services.navigation import render_sidebar
        render_sidebar(current_page="saju.py")
    """

    with st.sidebar:
        st.markdown("## ✦ AI WORKBENCH")
        st.caption("디지털전략부 AI LAB · 기존 화면")
        new_site_button()

        if st.button(
            "🏠  처음 화면",
            key=f"nav_home_{current_page}",
            use_container_width=True,
        ):
            st.switch_page("app.py")

        st.divider()

        pages = discover_pages()
        services = [x for x in pages if x["group"] == "service"]
        tools = [x for x in pages if x["group"] == "tool"]

        st.markdown("### 서비스")
        for item in services:
            _nav_button(item, current_page=current_page)

        if tools:
            st.divider()
            st.markdown("### 빠른 도구")
            for item in tools:
                _nav_button(item, current_page=current_page)
