# -*- coding: utf-8 -*-

from pathlib import Path
import shutil
import datetime

ROOT = Path(__file__).resolve().parent

# pages 폴더와 루트 둘 다 자동 탐색
CANDIDATES = [
    ROOT / "pages" / "6_골프장_추천.py",
    ROOT / "6_골프장_추천.py",
]

SOURCE = next(
    (p for p in CANDIDATES if p.exists()),
    None
)

if SOURCE is None:
    raise FileNotFoundError(
        "6_골프장_추천.py를 찾지 못했습니다."
    )

print("원본:", SOURCE)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

BACKUP = SOURCE.with_name(
    f"6_골프장_추천_backup_{stamp}.py"
)

shutil.copy2(
    SOURCE,
    BACKUP,
)

print("백업:", BACKUP)

text = SOURCE.read_text(
    encoding="utf-8-sig"
)


# =========================================================
# 1. IMPORT
# =========================================================

if "from pathlib import Path" not in text:

    anchor = (
        "from datetime import date, timedelta\n"
    )

    if anchor not in text:
        raise RuntimeError(
            "import 삽입 위치를 찾지 못했습니다."
        )

    text = text.replace(
        anchor,
        anchor
        + "from pathlib import Path\n"
        + "import json\n",
        1,
    )


# =========================================================
# 2. MASTER DB HELPERS
# =========================================================

MASTER_BLOCK = r'''

# =========================================================
# MASTER DB
# =========================================================

MASTER_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "golf"
    / "master"
    / "golf_master.json"
)


@st.cache_data(show_spinner=False)
def load_golf_master():

    if not MASTER_DB_PATH.exists():
        return {}

    try:

        data = json.loads(
            MASTER_DB_PATH.read_text(
                encoding="utf-8-sig"
            )
        )

        rows = (
            data.get("clubs", [])
            if isinstance(data, dict)
            else data
        )

        return {
            str(x.get("id") or ""): x
            for x in rows
            if isinstance(x, dict)
        }

    except Exception as ex:

        st.warning(
            f"Golf Master DB를 읽지 못했습니다: {ex}"
        )

        return {}


def attach_master_data(
    club,
    master_by_id,
):

    result = dict(club)

    master = master_by_id.get(
        str(club.get("id") or "")
    ) or {}

    basic = (
        master.get("basic")
        or {}
    )

    # catalog 확정값을 우선 사용하고,
    # 비어 있는 항목만 Master DB로 보완한다.
    for field in (
        "phone",
        "operation_type",
        "holes",
        "courses",
        "official_url",
        "booking_url",
    ):

        if result.get(field) in (
            None,
            "",
            [],
            {},
        ):

            value = basic.get(field)

            if value not in (
                None,
                "",
                [],
                {},
            ):

                result[field] = value

    if (
        not result.get("address")
        and basic.get("address")
    ):
        result["address"] = (
            basic["address"]
        )

    if (
        not result.get("city")
        and basic.get("city")
    ):
        result["city"] = (
            basic["city"]
        )

    if (
        not result.get("area")
        and basic.get("area")
    ):
        result["area"] = (
            basic["area"]
        )

    if master.get("kga"):
        result["kga"] = (
            master["kga"]
        )

    if master.get("evidence"):
        result["evidence"] = (
            master["evidence"]
        )

    result["_master"] = master

    return result


OBJECTIVE_MASTER_KEYS = {

    "2인 플레이":
        "two_person",

    "3인 플레이":
        "three_person",

    "9홀×2 라운드":
        "nine_hole_twice",

    "PAR3 연습장":
        "par3",

    "야외 연습장":
        "driving_range",

    "야간 라운드":
        "night_round",
}


def master_objective_info(
    club,
    label,
):

    key = (
        OBJECTIVE_MASTER_KEYS.get(
            label
        )
    )

    if not key:

        return {
            "status":
                "needs_check"
        }

    master = (
        club.get("_master")
        or {}
    )

    play_facility = (
        master.get(
            "play_facility"
        )
        or {}
    )

    return (
        play_facility.get(key)
        or {
            "status":
                "needs_check"
        }
    )


def objective_status_label(
    status,
):

    return {

        "confirmed":
            "확인됨",

        "conditional":
            "조건부",

        "unavailable":
            "불가 근거",

        "needs_check":
            "확인 필요",

    }.get(
        status,
        "확인 필요",
    )

'''

LOAD_MARKER = """# =========================================================
# LOAD DATA
# ========================================================="""

if "MASTER_DB_PATH =" not in text:

    if LOAD_MARKER not in text:
        raise RuntimeError(
            "LOAD DATA 위치를 찾지 못했습니다."
        )

    text = text.replace(
        LOAD_MARKER,
        MASTER_BLOCK
        + "\n"
        + LOAD_MARKER,
        1,
    )


# =========================================================
# 3. OBJECTIVE STATUS
# =========================================================

start = text.find(
    "def _objective_feature_status(club, key):"
)

end = text.find(
    "\ndef _kga_num",
    start,
)

if start == -1 or end == -1:

    raise RuntimeError(
        "_objective_feature_status 함수를 찾지 못했습니다."
    )

NEW_OBJECTIVE = '''def _objective_feature_status(club, key):
    """
    Master DB 기준 객관조건 판정.

    confirmed   -> True
    unavailable -> False

    conditional / needs_check
        -> None

    확인되지 않았다는 이유로
    불가로 판단하지 않는다.
    """

    info = master_objective_info(
        club,
        key,
    )

    status = info.get(
        "status"
    )

    if status == "confirmed":
        return True

    if status == "unavailable":
        return False

    return None
'''

text = (
    text[:start]
    + NEW_OBJECTIVE
    + text[end:]
)


# =========================================================
# 4. LOAD DATA MASTER 연결
# =========================================================

OLD_LOAD = '''all_clubs = load_catalog()
clubs = [c for c in all_clubs if c["service_status"] != "excluded"]
service_clubs = [c for c in all_clubs if c["service_status"] == "service"]
'''

NEW_LOAD = '''master_by_id = load_golf_master()

raw_clubs = load_catalog()

all_clubs = [
    attach_master_data(
        club,
        master_by_id,
    )
    for club in raw_clubs
]

clubs = [
    c
    for c in all_clubs
    if c.get("service_status")
    != "excluded"
]

service_clubs = [
    c
    for c in all_clubs
    if c.get("service_status")
    == "service"
]
'''

if OLD_LOAD not in text:

    raise RuntimeError(
        "기존 LOAD DATA 코드를 찾지 못했습니다."
    )

text = text.replace(
    OLD_LOAD,
    NEW_LOAD,
    1,
)


# =========================================================
# 5. 검색 결과 카드 3인
# =========================================================

OLD_THREE = '''                            three_raw = (course.get("play") or {}).get("three_person")
                            if three_raw in (True, "가능", "yes", "Y"):
                                three_text = "가능"
                            elif three_raw in (False, "불가", "no", "N"):
                                three_text = "불가"
                            else:
                                three_text = "확인 필요"
'''

NEW_THREE = '''                            three_status = master_objective_info(
                                course,
                                "3인 플레이",
                            ).get("status")

                            three_text = objective_status_label(
                                three_status
                            )
'''

if OLD_THREE in text:

    text = text.replace(
        OLD_THREE,
        NEW_THREE,
        1,
    )


# =========================================================
# 6. 검색 결과 카드 2인
# =========================================================

OLD_TWO = '''                            if "2인 플레이" in selected_features:
                                two_raw = (course.get("play") or {}).get("two_person")
                                two_text = "가능" if two_raw in (True, "가능", "yes", "Y") else "확인 필요"
                                facts.append(f"2인 {two_text}")
'''

NEW_TWO = '''                            if "2인 플레이" in selected_features:

                                two_status = master_objective_info(
                                    course,
                                    "2인 플레이",
                                ).get("status")

                                two_text = objective_status_label(
                                    two_status
                                )

                                facts.append(
                                    f"2인 {two_text}"
                                )
'''

if OLD_TWO in text:

    text = text.replace(
        OLD_TWO,
        NEW_TWO,
        1,
    )


# =========================================================
# 7. AI 문장검색 3인
# =========================================================

OLD_AI_THREE = '''                    if int(cond.get("players") or 4) == 3:
                        three = (club.get("play") or {}).get("three_person")
                        if three in (False, "불가", "no", "N"):
                            ok = False
'''

NEW_AI_THREE = '''                    if int(cond.get("players") or 4) == 3:

                        if (
                            _objective_feature_status(
                                club,
                                "3인 플레이",
                            )
                            is False
                        ):
                            ok = False
'''

if OLD_AI_THREE in text:

    text = text.replace(
        OLD_AI_THREE,
        NEW_AI_THREE,
        1,
    )


# =========================================================
# 8. 상세화면 이용/시설정보
# =========================================================

OLD_KGA = '''    # KGA 공인 코스정보
    render_kga_course_intelligence(club)
'''

NEW_DETAIL = '''    # =====================================================
    # MASTER DB · 이용 / 시설 정보
    # =====================================================

    st.markdown(
        "**이용 · 시설 정보**"
    )

    usage_labels = [

        "2인 플레이",
        "3인 플레이",
        "9홀×2 라운드",

        "야간 라운드",
        "PAR3 연습장",
        "야외 연습장",
    ]

    usage_cols = st.columns(3)

    for i, label in enumerate(
        usage_labels
    ):

        info = master_objective_info(
            club,
            label,
        )

        status = info.get(
            "status",
            "needs_check",
        )

        with usage_cols[
            i % 3
        ]:

            st.markdown(
                f"**{label}**"
            )

            if status == "confirmed":

                st.success(
                    "✓ 확인됨"
                )

            elif status == "conditional":

                st.warning(
                    "△ 조건부"
                )

            elif status == "unavailable":

                st.error(
                    "불가 근거"
                )

            else:

                st.caption(
                    "○ 확인 필요"
                )

            notes = (
                info.get(
                    "condition_notes"
                )
                or []
            )

            if (
                status == "conditional"
                and notes
            ):

                note = str(
                    notes[0]
                )

                if len(note) > 110:

                    note = (
                        note[:110]
                        + "…"
                    )

                st.caption(
                    note
                )

    st.caption(
        "※ '확인 필요'는 불가를 의미하지 않습니다. "
        "현재 확보한 자료만으로 판단하지 못한 항목입니다."
    )

    # KGA 공인 코스정보
    render_kga_course_intelligence(club)
'''

if OLD_KGA not in text:

    raise RuntimeError(
        "KGA 상세정보 위치를 찾지 못했습니다."
    )

text = text.replace(
    OLD_KGA,
    NEW_DETAIL,
    1,
)


# =========================================================
# 9. 상세 snapshot 3인 표시
# =========================================================

OLD_SNAPSHOT = '''    three_text = str(
        club.get("play", {}).get("three_person", "확인 필요")
    )
'''

NEW_SNAPSHOT = '''    three_text = objective_status_label(
        master_objective_info(
            club,
            "3인 플레이",
        ).get("status")
    )
'''

if OLD_SNAPSHOT in text:

    text = text.replace(
        OLD_SNAPSHOT,
        NEW_SNAPSHOT,
        1,
    )


# =========================================================
# 10. 저장
# =========================================================

OUTPUT = SOURCE.with_name(
    "6_골프장_추천_MASTER완성.py"
)

OUTPUT.write_text(
    text,
    encoding="utf-8",
)


# =========================================================
# 11. 문법검사
# =========================================================

try:

    compile(
        text,
        str(OUTPUT),
        "exec",
    )

except SyntaxError as ex:

    if OUTPUT.exists():
        OUTPUT.unlink()

    raise RuntimeError(
        "문법검사 실패. "
        "완성본은 저장하지 않았습니다.\n"
        f"{ex}"
    )


print()
print("=" * 70)
print("완료")
print("=" * 70)

print(
    "원본 유지:",
    SOURCE,
)

print(
    "원본 백업:",
    BACKUP,
)

print(
    "완성본:",
    OUTPUT,
)

print()
print(
    "Master DB:",
    ROOT
    / "data"
    / "golf"
    / "master"
    / "golf_master.json",
)

print()
print(
    "추가 Tavily 호출: 0"
)

print(
    "추가 LLM 조사: 0"
)

print(
    "catalog.json 수정: 0"
)

print(
    "문법검사: OK"
)

print("=" * 70)