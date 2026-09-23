"""내 차에서 드림카까지 — 추천·시세·견적 로직 (Streamlit 무관).

pages/1_내차에서_드림카까지.py의 로직 부분을 그대로 옮기고,
FastAPI(api/dreamcar.py)용 카탈로그·추천 응답 함수를 추가했다.
"""

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
EXCEL_PATH = BASE_DIR / "sample_cars_v3.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_mobile_39"
ASSET_DIR = BASE_DIR / "dreamcar_assets"

# 시연용 고정 금리
DEMO_APR = 5.9
TERMS = [24, 36, 48, 60]
DEPOSIT_RATES = [0, 10, 20, 30]


def normalize_plate(value):
    return re.sub(r"\s+", "", value.strip())


def valid_plate(value):
    """
    프로토타입용 간단한 번호판 형식 검증.
    실제 서비스에서는 차량등록정보 조회 API의 응답으로 검증해야 합니다.
    """
    value = normalize_plate(value)
    patterns = [
        r"^\d{2,3}[가-힣]\d{4}$",
        r"^[가-힣]{1,2}\d{2}[가-힣]\d{4}$",
    ]
    return any(re.match(p, value) for p in patterns)


def demo_used_car_lookup(plate):
    """
    시연용 중고차 조회 함수.
    번호판을 기반으로 항상 동일한 차량/시세가 반환되도록 구성했습니다.

    실제 서비스 적용 시 이 함수만
    - 차량등록정보 API
    - 중고차 시세 API
    로 교체하면 됩니다.
    """
    demo_cars = [
        {
            "model": "2020 그랜저",
            "year": 2020,
            "mileage": 52000,
            "market": 2350,
            "range_low": 2200,
            "range_high": 2490,
            "grade": "양호"
        },
        {
            "model": "2021 쏘나타",
            "year": 2021,
            "mileage": 41000,
            "market": 1840,
            "range_low": 1710,
            "range_high": 1970,
            "grade": "양호"
        },
        {
            "model": "2020 팰리세이드",
            "year": 2020,
            "mileage": 63000,
            "market": 3080,
            "range_low": 2920,
            "range_high": 3260,
            "grade": "보통"
        },
        {
            "model": "2021 카니발",
            "year": 2021,
            "mileage": 57000,
            "market": 2980,
            "range_low": 2810,
            "range_high": 3150,
            "grade": "양호"
        },
        {
            "model": "2019 싼타페",
            "year": 2019,
            "mileage": 76000,
            "market": 2060,
            "range_low": 1910,
            "range_high": 2180,
            "grade": "보통"
        },
        {
            "model": "2022 아반떼",
            "year": 2022,
            "mileage": 29000,
            "market": 1870,
            "range_low": 1760,
            "range_high": 1990,
            "grade": "우수"
        },
    ]

    digest = hashlib.sha256(plate.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(demo_cars)
    car = demo_cars[index].copy()
    car["plate"] = plate
    return car


def monthly_installment(principal_manwon, months, annual_rate=DEMO_APR):
    """
    원리금균등 방식 월 납입금.
    principal_manwon: 만원 단위
    return: 월 납입금(만원), 총 이자(만원)
    """
    if principal_manwon <= 0:
        return 0.0, 0.0

    principal = principal_manwon * 10000
    monthly_rate = annual_rate / 100 / 12

    if monthly_rate == 0:
        monthly = principal / months
    else:
        monthly = (
            principal
            * monthly_rate
            * (1 + monthly_rate) ** months
            / ((1 + monthly_rate) ** months - 1)
        )

    total_payment = monthly * months
    total_interest = total_payment - principal

    return monthly / 10000, total_interest / 10000



questions = [
    {
        "title": "평소 차량을 가장 많이 쓰는 장면은?",
        "desc": "일상에서 가장 자주 반복되는 이동 장면을 골라주세요.",
        "options": [
            {"art": "q1_city.webp", "label": "출퇴근 · 도심 이동", "desc": "주차와 기동성, 일상 편의가 중요해요", "scores": {"city": 3, "comfort": 1}},
            {"art": "q1_trip.webp", "label": "주말 여행 · 장거리", "desc": "장거리 안정감과 승차감을 중요하게 봐요", "scores": {"trip": 3, "comfort": 2}},
            {"art": "q1_mix.webp", "label": "도심과 여행을 반반", "desc": "평일과 주말을 모두 만족시키고 싶어요", "scores": {"city": 2, "trip": 2, "versatility": 2}},
        ]
    },
    {
        "title": "차 안에서 가장 자주 함께하는 사람은?",
        "desc": "동승 인원이 차량 크기와 공간의 기준을 크게 바꿉니다.",
        "options": [
            {"art": "q2_duo.webp", "label": "혼자 또는 둘이", "desc": "운전자 중심의 편안함과 감도가 중요해요", "scores": {"solo": 3, "style": 1}},
            {"art": "q2_family.webp", "label": "3~4인 가족", "desc": "가족이 편하면서도 너무 크지 않았으면 해요", "scores": {"family": 3, "space": 2}},
            {"art": "q2_large.webp", "label": "5인 이상 · 다인승", "desc": "사람과 짐을 넉넉하게 태울 공간이 필요해요", "scores": {"large_family": 4, "space": 4}},
        ]
    },
    {
        "title": "차를 고를 때 가장 중요하게 보는 것은?",
        "desc": "한 가지를 가장 우선한다면 무엇인가요?",
        "options": [
            {"art": "q3_style.webp", "label": "디자인 · 고급감", "desc": "볼 때마다 만족스럽고 품격 있는 차", "scores": {"style": 4, "premium": 3}},
            {"art": "q3_space.webp", "label": "공간 · 실용성", "desc": "짐과 사람을 편하게 담는 활용성", "scores": {"space": 4, "versatility": 3}},
            {"art": "q3_efficiency.webp", "label": "편안함 · 효율", "desc": "매일 타기 편하고 부담이 적은 차", "scores": {"comfort": 3, "value": 3}},
        ]
    },
    {
        "title": "새 차를 고를 때 가장 가까운 생각은?",
        "desc": "차급과 가격에 대한 선호를 반영해 추천을 정교하게 만듭니다.",
        "options": [
            {"art": "q4_value.webp", "label": "합리적인 가격이 우선", "desc": "필요한 기능은 충분하되 부담은 낮게", "scores": {"value": 5}},
            {"art": "q4_balance.webp", "label": "가격과 만족의 균형", "desc": "예산 안에서 한 단계 좋은 차를 원해요", "scores": {"balanced": 4, "premium": 1}},
            {"art": "q4_premium.webp", "label": "마음에 들면 차급을 올려도 좋아요", "desc": "가격보다 만족도와 완성도가 중요해요", "scores": {"premium": 5, "style": 2}},
        ]
    },
]

vehicle_profiles = {
    "아반떼": {
        "scores": {"city":6,"trip":1,"comfort":3,"solo":6,"family":1,"large_family":0,"space":1,"style":3,"premium":0,"value":6,"balanced":3,"versatility":2},
        "tagline":"가볍고 합리적인 도심형 준중형 세단",
        "reason_pool":["도심 주행 편의","합리적인 차량가격","초기 교체 부담 절감","데일리 효율성"],
    },
    "쏘나타": {
        "scores": {"city":5,"trip":3,"comfort":5,"solo":5,"family":3,"large_family":0,"space":2,"style":3,"premium":1,"value":5,"balanced":5,"versatility":3},
        "tagline":"편안함과 실용성을 고르게 갖춘 중형 세단",
        "reason_pool":["데일리 편안함","도심·장거리 균형","합리적인 가격","안정적인 승차감"],
    },
    "K5": {
        "scores": {"city":5,"trip":3,"comfort":4,"solo":5,"family":2,"large_family":0,"space":2,"style":5,"premium":2,"value":4,"balanced":4,"versatility":3},
        "tagline":"스타일을 중시하는 감각적인 중형 세단",
        "reason_pool":["스포티한 디자인","도심 주행 감도","가격·스타일 균형","운전자 중심 만족감"],
    },
    "디 올 뉴 그랜저": {
        "scores": {"city":4,"trip":4,"comfort":6,"solo":4,"family":3,"large_family":0,"space":2,"style":5,"premium":6,"value":2,"balanced":6,"versatility":3},
        "tagline":"편안함과 고급감을 함께 잡는 프리미엄 세단",
        "reason_pool":["프리미엄 감성","정숙한 승차감","도심·장거리 균형","높은 소유 만족감"],
    },
    "K8": {
        "scores": {"city":4,"trip":4,"comfort":5,"solo":4,"family":3,"large_family":0,"space":2,"style":5,"premium":5,"value":3,"balanced":6,"versatility":3},
        "tagline":"품격과 합리성의 균형을 갖춘 준대형 세단",
        "reason_pool":["준대형 세단의 여유","세련된 디자인","가격·차급 균형","편안한 장거리 주행"],
    },
    "투싼": {
        "scores": {"city":5,"trip":4,"comfort":4,"solo":4,"family":4,"large_family":1,"space":4,"style":3,"premium":1,"value":5,"balanced":5,"versatility":5},
        "tagline":"도심과 주말을 연결하는 실용적인 SUV",
        "reason_pool":["도심 친화적 크기","주말 활용성","SUV 실용 공간","균형 잡힌 차량가격"],
    },
    "스포티지": {
        "scores": {"city":5,"trip":4,"comfort":4,"solo":4,"family":4,"large_family":1,"space":4,"style":4,"premium":1,"value":5,"balanced":5,"versatility":5},
        "tagline":"스타일과 실용성을 함께 갖춘 준중형 SUV",
        "reason_pool":["감각적인 SUV 디자인","도심 활용성","가족 일상 적합","가격 대비 공간"],
    },
    "싼타페": {
        "scores": {"city":3,"trip":6,"comfort":5,"solo":2,"family":6,"large_family":3,"space":6,"style":4,"premium":3,"value":4,"balanced":5,"versatility":6},
        "tagline":"가족의 일상과 여행에 강한 중형 SUV",
        "reason_pool":["가족 이동 최적화","넉넉한 적재공간","여행·캠핑 활용성","편안한 장거리 주행"],
    },
    "쏘렌토": {
        "scores": {"city":3,"trip":6,"comfort":5,"solo":2,"family":6,"large_family":3,"space":6,"style":4,"premium":3,"value":4,"balanced":6,"versatility":6},
        "tagline":"패밀리와 장거리 활용의 균형형 SUV",
        "reason_pool":["패밀리 SUV 균형","도심·여행 대응력","넉넉한 공간","높은 활용 범위"],
    },
    "디 올 뉴 팰리세이드": {
        "scores": {"city":2,"trip":6,"comfort":6,"solo":1,"family":6,"large_family":5,"space":7,"style":5,"premium":5,"value":2,"balanced":4,"versatility":6},
        "tagline":"가족과 여행의 반경을 넓히는 대형 SUV",
        "reason_pool":["넉넉한 실내공간","가족 이동 최적화","장거리 안정감","대형 SUV의 존재감"],
    },
    "더 뉴 카니발": {
        "scores": {"city":1,"trip":6,"comfort":5,"solo":0,"family":6,"large_family":8,"space":8,"style":2,"premium":2,"value":3,"balanced":3,"versatility":8},
        "tagline":"사람과 짐을 모두 담는 패밀리 모빌리티",
        "reason_pool":["최대 공간 활용","다인승 편의성","가족·레저 활용성","다양한 좌석 활용"],
    },
    "GV70": {
        "scores": {"city":4,"trip":5,"comfort":5,"solo":5,"family":3,"large_family":0,"space":3,"style":7,"premium":7,"value":1,"balanced":4,"versatility":4},
        "tagline":"운전 감성과 고급감을 강조한 프리미엄 SUV",
        "reason_pool":["프리미엄 디자인","도심 주행 감성","고급 실내 만족감","SUV의 활용성"],
    },
    "GV80": {
        "scores": {"city":2,"trip":6,"comfort":7,"solo":2,"family":5,"large_family":3,"space":6,"style":7,"premium":8,"value":0,"balanced":4,"versatility":5},
        "tagline":"공간과 품격을 모두 원하는 프리미엄 대형 SUV",
        "reason_pool":["프리미엄 대형 SUV","최상급 승차감","가족과 비즈니스 활용","높은 소유 만족감"],
    },
}

def calculate_user_scores(answers):
    user_scores = {}
    for q_idx, option_idx in enumerate(answers):
        option = questions[q_idx]["options"][option_idx]
        for key, value in option["scores"].items():
            user_scores[key] = user_scores.get(key, 0) + value
    return user_scores

def rank_vehicles(answers, available_models):
    user_scores = calculate_user_scores(answers)
    ranked = []
    for model in available_models:
        if model not in vehicle_profiles:
            continue
        profile = vehicle_profiles[model]
        score = sum(v * profile["scores"].get(k, 0) for k, v in user_scores.items())
        ranked.append({"model": model, "score": score, "profile": profile})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    if not ranked:
        return []
    max_score = ranked[0]["score"] or 1
    for idx, item in enumerate(ranked):
        relative = item["score"] / max_score
        item["match"] = max(82, min(98, round(82 + relative * 16 - idx * 2)))
    return ranked

def build_persona(answers, ranked):
    s = calculate_user_scores(answers)
    family = s.get("family",0)+s.get("large_family",0)+s.get("space",0)
    premium = s.get("premium",0)+s.get("style",0)
    value = s.get("value",0)
    trip = s.get("trip",0)+s.get("versatility",0)

    if family >= 10:
        return {"name":"LIFE EXPANDER","sub":"가족의 모든 이동을 넓게 설계하는 사람","copy":"사람과 짐, 평일과 주말을 모두 고려하며 차량 한 대의 활용 범위를 크게 보는 타입입니다.","quote":"“차 한 대가 가족의 활동 반경을 넓혀준다.”","art":"persona_life.webp"}
    if premium >= 9:
        return {"name":"PREMIUM CURATOR","sub":"이동의 감도까지 고르는 사람","copy":"편안함과 디자인, 소유 만족도를 중요하게 보며 한 단계 높은 완성도를 선호합니다.","quote":"“매일 타는 차일수록 만족감이 중요하다.”","art":"persona_premium.webp"}
    if value >= 6:
        return {"name":"SMART SELECTOR","sub":"필요한 만큼 정확하게 고르는 사람","copy":"차량가격과 실용성을 함께 보며 매일 쓰는 기능에 집중해 효율적인 선택을 하는 타입입니다.","quote":"“좋은 차는 내 생활에 정확히 맞는 차.”","art":"persona_smart.webp"}
    if trip >= 7:
        return {"name":"WEEKEND VOYAGER","sub":"주말의 반경을 넓히는 사람","copy":"평일의 이동뿐 아니라 여행과 장거리 주행까지 고려해 활용성과 편안함을 함께 봅니다.","quote":"“차가 바뀌면 갈 수 있는 곳도 달라진다.”","art":"persona_weekend.webp"}
    return {"name":"BALANCE DRIVER","sub":"평일과 주말의 균형을 고르는 사람","copy":"편안함, 가격, 공간, 디자인 어느 하나에 치우치기보다 전체 균형을 중요하게 생각합니다.","quote":"“매일 타도 좋고, 주말에는 더 좋은 차.”","art":"persona_balance.webp"}


# =========================================================
# API용: 카탈로그 · 추천 응답 (이미지는 FastAPI가 /media 로 서빙)
# =========================================================
CAR_MEDIA = "/media/cars"
ASSET_MEDIA = "/media/dreamcar"


def _car_image_url(filename):
    """엑셀에는 .png로 적혀 있어도 실제 파일(.jpg/.jpeg/.png)을 같은 이름(stem)으로 찾는다."""
    stem = Path(str(filename)).stem
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if (IMAGE_DIR / f"{stem}{ext}").exists():
            return f"{CAR_MEDIA}/{stem}{ext}"
    return None


@lru_cache(maxsize=1)
def load_catalog():
    """{모델: {price, segment, seats, colors: [{color, price, image}]}} — 엑셀 순서 유지."""
    df = pd.read_excel(EXCEL_PATH, sheet_name="차량목록")
    catalog = {}
    for _, row in df.iterrows():
        model = str(row["모델"]).strip()
        item = catalog.setdefault(model, {"model": model, "segment": str(row.get("세그먼트") or ""),
                                          "seats": str(row.get("좌석") or ""), "colors": []})
        item["colors"].append({"color": str(row["색상"]).strip(), "price": int(float(row["차량가격(만원)"])),
                               "image": _car_image_url(row["이미지파일명"])})
    for item in catalog.values():
        item["price"] = item["colors"][0]["price"]
    return catalog


def public_questions():
    return [
        {"title": q["title"], "desc": q["desc"],
         "options": [{"label": o["label"], "desc": o["desc"], "art": f"{ASSET_MEDIA}/lifestyle/{o['art']}"}
                     for o in q["options"]]}
        for q in questions
    ]


def lookup_car(plate):
    """번호판 검증 후 시연용 시세. 형식이 틀리면 None."""
    clean = normalize_plate(plate or "")
    if not clean or not valid_plate(clean):
        return None
    return demo_used_car_lookup(clean)


def recommend(answers, top_n=3):
    """라이프스타일 답변(질문별 선택지 index) → 페르소나 + TOP N 차량(색상별 가격·이미지 포함)."""
    if len(answers) != len(questions) or any(
            not (0 <= a < len(q["options"])) for a, q in zip(answers, questions)):
        raise ValueError("모든 질문에 답해 주세요.")
    catalog = load_catalog()
    ranked = rank_vehicles(answers, list(catalog))
    persona = build_persona(answers, ranked)
    persona["art"] = f"{ASSET_MEDIA}/persona/{persona['art']}"
    return {
        "persona": persona,
        "total_models": len(catalog),
        "top": [
            {"model": r["model"], "match": r["match"], "tagline": r["profile"]["tagline"],
             "reasons": r["profile"]["reason_pool"][:3], **{k: catalog[r["model"]][k] for k in ("price", "segment", "seats", "colors")}}
            for r in ranked[:top_n]
        ],
    }

