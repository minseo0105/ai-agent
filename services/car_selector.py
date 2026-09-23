"""차량 선택기 (Streamlit 무관).

pages/4_차량_선택기.py의 질문 · 페르소나 · 추천 차량 매핑을 그대로 옮긴 것.
3개 질문(2지선다) 8개 조합마다 페르소나와 차량이 정해져 있다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "sample_cars_v2.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_cutout"      # 배경 제거 PNG
FALLBACK_DIR = BASE_DIR / "car_images_real"     # PNG가 없을 때 실사 JPG
CUTOUT_MEDIA = "/media/car-cutout"
REAL_MEDIA = "/media/car-real"
TERMS = [36, 48, 60]

# =========================================================
# QUESTION VISUALS - 라이프스타일 모션 이미지
# =========================================================
CITY = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="csky" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#DDE8FF"/><stop offset="1" stop-color="#F6F8FC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#csky)"/>
<g class="scene-bg" opacity=".75">
<rect x="38" y="54" width="48" height="110" rx="5" fill="#8EA7CE"/><rect x="98" y="28" width="61" height="136" rx="5" fill="#6E8FC4"/>
<rect x="174" y="72" width="47" height="92" rx="5" fill="#B7C5DA"/><rect x="236" y="43" width="70" height="121" rx="5" fill="#91A8CB"/>
<rect x="319" y="81" width="50" height="83" rx="5" fill="#C2CCDA"/>
</g>
<path d="M0 164H420V210H0Z" fill="#D9E0EA"/><path d="M0 187H420" stroke="#FFF" stroke-width="3" stroke-dasharray="26 20"/>
<g class="scene-car"><path d="M120 163L143 143H211L238 163L262 168V184H101V170Z" fill="#162C55"/>
<path d="M150 146H205L224 162H132Z" fill="#8CA8D9"/><circle cx="135" cy="184" r="12" fill="#101827"/><circle cx="229" cy="184" r="12" fill="#101827"/>
<path class="scene-glow" d="M260 172H300" stroke="#88A9FF" stroke-width="5" stroke-linecap="round"/></g>
</svg>
"""

TRIP = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="tsky" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#DCE9FF"/><stop offset="1" stop-color="#F8FAFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#tsky)"/><circle class="scene-glow" cx="330" cy="44" r="22" fill="#FFD98A"/>
<g class="scene-bg"><path d="M0 163L87 81L148 145L224 59L336 163Z" fill="#A9BBDC"/><path d="M78 163L157 103L215 151L288 91L420 163Z" fill="#6F8FC7"/></g>
<path d="M0 163H420V210H0Z" fill="#D9E3DC"/><path d="M0 187H420" stroke="#FFF" stroke-width="3" stroke-dasharray="27 20"/>
<g class="scene-car"><path d="M124 162L146 141H213L241 162L265 168V184H104V170Z" fill="#203758"/>
<path d="M152 145H207L226 161H135Z" fill="#9AB0D1"/><circle cx="138" cy="184" r="12" fill="#182334"/><circle cx="232" cy="184" r="12" fill="#182334"/></g>
</svg>
"""

DUO = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="d" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E4EBFF"/><stop offset="1" stop-color="#F9FAFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#d)"/>
<path d="M64 178C92 113 140 79 210 77C281 75 333 111 356 178" fill="none" stroke="#CAD6EE" stroke-width="24" stroke-linecap="round"/>
<g class="scene-float"><rect x="116" y="69" width="78" height="91" rx="28" fill="#284F9A"/><circle cx="155" cy="74" r="22" fill="#C6D5F5"/></g>
<g class="scene-float" style="animation-delay:.6s"><rect x="226" y="69" width="78" height="91" rx="28" fill="#5D57A8"/><circle cx="265" cy="74" r="22" fill="#D7D0F7"/></g>
<path d="M195 158L210 142L225 158" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/>
</svg>
"""

FAMILY = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="f" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E1EAFF"/><stop offset="1" stop-color="#FAFBFD"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#f)"/>
<path d="M68 177C99 112 146 82 210 82C277 82 326 114 352 177" fill="none" stroke="#CDD8EE" stroke-width="25" stroke-linecap="round"/>
<g class="scene-float"><rect x="91" y="67" width="70" height="94" rx="27" fill="#284F98"/><circle cx="126" cy="71" r="21" fill="#C7D7F6"/></g>
<g class="scene-float" style="animation-delay:.5s"><rect x="259" y="67" width="70" height="94" rx="27" fill="#58549E"/><circle cx="294" cy="71" r="21" fill="#D7D1F7"/></g>
<g class="scene-float" style="animation-delay:1s"><rect x="176" y="101" width="68" height="64" rx="25" fill="#4771C4"/><circle cx="210" cy="105" r="18" fill="#D5E1FA"/></g>
</svg>
"""

STYLE = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="s" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E4EBFF"/><stop offset="1" stop-color="#F8F7FF"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#s)"/>
<ellipse cx="210" cy="172" rx="124" ry="13" fill="#CAD2DF" opacity=".55"/>
<g class="scene-car"><path d="M92 148L126 119H242L286 148L325 156V174H73V158Z" fill="#142A51"/>
<path d="M137 123H234L268 147H109Z" fill="#7F9CCB"/><circle cx="124" cy="174" r="16" fill="#101827"/><circle cx="275" cy="174" r="16" fill="#101827"/>
<path class="scene-glow" d="M77 157H104M289 153H319" stroke="#87A9FF" stroke-width="6" stroke-linecap="round"/></g>
<path class="scene-glow" d="M95 68C164 40 258 40 326 70" fill="none" stroke="#718FF1" stroke-width="3" opacity=".55"/>
</svg>
"""

SPACE = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="sp" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E5ECFA"/><stop offset="1" stop-color="#FAFBFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#sp)"/>
<path d="M80 166V83C80 59 99 40 123 40H297C321 40 340 59 340 83V166" fill="#E8EDF5" stroke="#AEBED6" stroke-width="4"/>
<path d="M111 68H309V161H111Z" fill="#F8FAFD"/>
<g class="scene-float"><rect x="130" y="100" width="65" height="57" rx="10" fill="#345FAE"/><path d="M143 100V87H182V100" fill="none" stroke="#345FAE" stroke-width="7"/></g>
<g class="scene-float" style="animation-delay:.6s"><rect x="209" y="84" width="78" height="73" rx="11" fill="#7167B6"/><path d="M225 84V68H271V84" fill="none" stroke="#7167B6" stroke-width="7"/></g>
<path class="scene-glow" d="M103 167H317" stroke="#7294DF" stroke-width="5" stroke-linecap="round"/>
</svg>
"""

# =========================================================
# QUESTIONS
# =========================================================
questions = [
    {
        "title":"당신의 주말은 어느 장면에 더 가깝나요?",
        "desc":"가장 자연스럽게 반복되는 이동 장면부터 읽어볼게요.",
        "options":[
            {"art":CITY,"label":"도심을 가볍게 누비는 편","desc":"맛집 · 카페 · 쇼핑 · 근거리 이동"},
            {"art":TRIP,"label":"주말이면 멀리 떠나는 편","desc":"여행 · 캠핑 · 레저 · 장거리 이동"},
        ]
    },
    {
        "title":"차 안에서 가장 자주 함께하는 사람은?",
        "desc":"누구와 이동하는지가 공간과 편안함의 기준을 바꿉니다.",
        "options":[
            {"art":DUO,"label":"혼자 또는 둘이","desc":"나의 감도와 이동 편의가 중요해요"},
            {"art":FAMILY,"label":"가족과 함께","desc":"사람과 짐, 일정까지 함께 담아야 해요"},
        ]
    },
    {
        "title":"차를 고를 때 마지막까지 포기하기 어려운 것은?",
        "desc":"마지막 선택으로 추천 방향을 완성합니다.",
        "options":[
            {"art":STYLE,"label":"볼 때마다 마음에 드는 디자인","desc":"스타일 · 주행감 · 소유 만족감"},
            {"art":SPACE,"label":"필요할 때 든든한 공간","desc":"수납 · 안정감 · 다양한 상황 대응력"},
        ]
    },
]


# =========================================================
# PERSONAS + 추천 차량 로직
# 3개 질문의 8개 조합마다 별도 페르소나와 추천 차량을 지정합니다.
# =========================================================
recommendation_map = {
    # 도심 / 혼자·둘 / 디자인
    (0, 0, 0): {
        "name": "CITY CURATOR",
        "sub": "도시의 장면을 고르는 사람",
        "copy": "복잡한 도심에서도 편하고 세련된 이동을 중요하게 생각합니다. "
                "차를 단순한 이동수단보다 나의 하루와 분위기를 완성하는 오브제로 보는 타입입니다.",
        "quote": "“내 일상의 템포와 가장 자연스럽게 맞는 차.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["도심 활용성", "정제된 승차감", "디자인 만족도"],
        "art": CITY,
        "match": 96
    },

    # 도심 / 혼자·둘 / 공간·실용
    (0, 0, 1): {
        "name": "SMART MINIMALIST",
        "sub": "필요한 만큼 정확하게 고르는 사람",
        "copy": "과한 크기나 기능보다 실제 일상에서 자주 쓰는 편의와 효율을 중요하게 봅니다. "
                "부담 없이 운전하고 합리적으로 이용할 수 있는 균형 잡힌 선택을 선호합니다.",
        "quote": "“좋은 선택은 더 많이 갖는 것이 아니라, 딱 맞게 갖는 것.”",
        "model": "쏘나타",
        "reasons": ["운전 편의성", "합리적 이용", "데일리 실용성"],
        "art": SPACE,
        "match": 93
    },

    # 도심 / 가족 / 디자인
    (0, 1, 0): {
        "name": "URBAN HOST",
        "sub": "함께 타는 순간까지 세련되게 만드는 사람",
        "copy": "가족이나 동승자와 함께 이동하지만, 큰 차만을 답으로 생각하지 않습니다. "
                "편안함과 디자인, 도심에서의 세련된 주행감을 함께 중요하게 봅니다.",
        "quote": "“함께 타는 사람도, 나도 만족하는 균형.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["동승자 편안함", "도심 주행감", "프리미엄 감성"],
        "art": FAMILY,
        "match": 94
    },

    # 도심 / 가족 / 공간
    (0, 1, 1): {
        "name": "FAMILY NAVIGATOR",
        "sub": "가족의 매일을 더 여유롭게 설계하는 사람",
        "copy": "등하원, 장보기, 주말 외출처럼 가족의 일상이 차 안에서 연결됩니다. "
                "도심에서도 다루기 편하면서 공간과 안정감까지 충분한 차량을 선호합니다.",
        "quote": "“가족의 하루가 편해지면, 내 하루도 편해진다.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["가족 이동 최적화", "넉넉한 실내", "도심·주말 균형"],
        "art": FAMILY,
        "match": 97
    },

    # 여행 / 혼자·둘 / 디자인
    (1, 0, 0): {
        "name": "ROAD VOYAGER",
        "sub": "가는 길의 감도를 즐기는 사람",
        "copy": "목적지뿐 아니라 이동하는 시간 자체를 중요하게 생각합니다. "
                "장거리에서도 편안하고, 도착했을 때까지 운전의 감성과 만족감이 이어지는 차를 선호합니다.",
        "quote": "“목적지보다 가는 길이 기억에 남는 차.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["장거리 승차감", "주행 감성", "디자인 완성도"],
        "art": TRIP,
        "match": 92
    },

    # 여행 / 혼자·둘 / 공간
    (1, 0, 1): {
        "name": "FREEDOM EXPLORER",
        "sub": "주말의 반경을 자유롭게 넓히는 사람",
        "copy": "평소에는 여유 있게, 필요할 때는 짐과 활동 범위를 크게 확장하고 싶어합니다. "
                "여행과 레저를 위해 SUV의 공간과 안정감을 적극적으로 활용하는 타입입니다.",
        "quote": "“차가 커지는 것이 아니라, 갈 수 있는 곳이 많아진다.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["여행 활용성", "적재 공간", "장거리 안정감"],
        "art": TRIP,
        "match": 95
    },

    # 여행 / 가족 / 디자인
    (1, 1, 0): {
        "name": "WEEKEND DIRECTOR",
        "sub": "가족의 특별한 주말을 만드는 사람",
        "copy": "가족 여행의 편안함도 중요하지만 차량의 존재감과 스타일도 포기하지 않습니다. "
                "일상과 여행 모두에서 만족감을 주는 프리미엄 패밀리 SUV가 잘 맞습니다.",
        "quote": "“함께하는 시간도, 그 장면도 특별하게.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["패밀리 여행", "프리미엄 디자인", "편안한 주행"],
        "art": STYLE,
        "match": 96
    },

    # 여행 / 가족 / 공간
    (1, 1, 1): {
        "name": "LIFE ORCHESTRATOR",
        "sub": "가족의 모든 장면을 담아내는 사람",
        "copy": "사람도 많고, 짐도 많고, 하고 싶은 일도 많습니다. "
                "여행·레저·일상까지 한 대의 차가 여러 역할을 해내는 압도적인 공간 활용성을 가장 중요하게 봅니다.",
        "quote": "“차 한 대가 가족의 가능성을 더 크게 만든다.”",
        "model": "더 뉴 카니발",
        "reasons": ["최대 공간 활용", "다인승 편의성", "여행·레저 확장성"],
        "art": SPACE,
        "match": 98
    },
}


def get_recommendation(answers):
    """
    3개 질문의 선택값을 기반으로 추천 페르소나와 차량을 반환합니다.
    answers 예시: [0, 1, 1]
    """
    key = tuple(answers)

    if key in recommendation_map:
        return recommendation_map[key]

    # 예외 상황에서는 가족/공간 활용성이 높은 기본 추천
    return recommendation_map[(0, 1, 1)]


# =========================================================
# 웹 API용
# =========================================================

def _image_url(filename):
    original = Path(str(filename))
    png = original.with_suffix(".png").name
    if (IMAGE_DIR / png).exists():
        return f"{CUTOUT_MEDIA}/{png}"
    if (FALLBACK_DIR / original.name).exists():
        return f"{REAL_MEDIA}/{original.name}"
    return None


@lru_cache(maxsize=1)
def load_catalog():
    """{모델: [{color, price, image, monthly:{36,48,60}}]}"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="차량목록")
    catalog = {}
    for _, row in df.iterrows():
        model = str(row["모델"]).strip()
        if not model or model == "nan" or pd.isna(row.get("색상")):
            continue
        monthly = {}
        for t in TERMS:
            v = row.get(f"{t}개월")
            monthly[str(t)] = float(v) if pd.notna(v) else 0.0
        catalog.setdefault(model, []).append({
            "color": str(row["색상"]).strip(),
            "price": int(float(row["차량가격(만원)"])),
            "image": _image_url(row["이미지파일명"]),
            "monthly": monthly,
        })
    return catalog


def public_questions():
    return [
        {"title": q["title"], "desc": q["desc"],
         "options": [{"label": o["label"], "desc": o["desc"], "art": o["art"].strip()} for o in q["options"]]}
        for q in questions
    ]


def recommend(answers):
    if len(answers) != len(questions) or any(a not in (0, 1) for a in answers):
        raise ValueError("3개 질문에 각각 0 또는 1로 답해야 합니다.")
    rec = get_recommendation(answers)
    catalog = load_catalog()
    model = rec["model"] if rec["model"] in catalog else next(iter(catalog))
    return {
        "persona": {k: rec[k] for k in ("name", "sub", "copy", "quote")} | {"art": rec["art"].strip()},
        "model": model,
        "match": rec["match"],
        "reasons": rec["reasons"],
        "colors": catalog[model],
        "terms": TERMS,
    }
