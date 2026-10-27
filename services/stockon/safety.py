"""AI 문장 안전장치: 매수·매도 권유처럼 읽히는 표현을 막고, 출처 번호가 실제 출처를 가리키는지 확인한다.

사실 서술("외국인이 순매도했다")은 허용하고, 권유·전망·평가 단정만 막는다.
검사는 AI가 만든 문장에만 적용한다. 뉴스 제목은 언론사 원문 그대로 보여 준다.
"""

import html
import re

DISCLAIMER = "정보 제공용이며 투자 권유가 아닙니다"

# 권유 · 목표가 · 평가 단정 · 수익 보장 · 방향 예측
BANNED_PATTERNS = [
    r"추천", r"권유", r"권합니다", r"권장",
    r"매수\s*(의견|기회|타이밍|시점|적기)", r"매도\s*(의견|기회|타이밍|시점|적기)",
    r"(매수|매도|투자|진입)(를|을)?\s*(고려|검토)해", r"(매수|매도|투자)하(세요|십시오|기 바랍니다)",
    r"저가\s*매수", r"추격\s*매수", r"분할\s*매수", r"손절", r"익절",
    r"사세요", r"파세요", r"사야\s*(한다|합니다|할)", r"팔아야", r"팔아라", r"담아라", r"담으세요", r"사라고",
    r"목표\s*주?가", r"적정\s*주가", r"비중\s*(확대|축소)",
    r"저평가", r"고평가", r"싸다", r"비싸다",
    r"수익\s*(을\s*)?보장", r"확실한\s*수익", r"원금\s*보장", r"대박",
    r"유망", r"투자\s*기회", r"지금이\s*기회", r"놓치지\s*마",
    r"(오를|내릴|상승할|하락할|반등할|급등할|급락할)\s*(것|가능성|전망)", r"(상승|하락|반등)\s*(이\s*)?(예상|기대)",
]
_BANNED = [re.compile(p) for p in BANNED_PATTERNS]


def banned_hits(text: str) -> list[str]:
    """문장에서 걸린 금지 표현 목록(없으면 빈 목록)."""
    return [m.group(0) for p in _BANNED for m in [p.search(text or "")] if m]


def is_safe(text: str) -> bool:
    return not banned_hits(text)


_TAG = re.compile(r"<[^>]+>")


def clean_text(text: str, limit: int = 400) -> str:
    """검색 결과의 <b> 태그·HTML 엔티티를 지우고 공백을 정리한다."""
    text = html.unescape(_TAG.sub("", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def keep_valid_sources(source_ids, n_sources: int) -> list[int]:
    """AI가 붙인 출처 번호 중 실제로 있는 번호만 남긴다(1부터 시작, 중복 제거)."""
    out = []
    for s in source_ids or []:
        if isinstance(s, int) and 1 <= s <= n_sources and s not in out:
            out.append(s)
    return out
