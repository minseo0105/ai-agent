from pathlib import Path
from datetime import datetime
import shutil, ast

BASE=Path(__file__).resolve().parents[1]
PAGE=BASE/"pages"/"6_골프장_추천.py"
BACKUPS=BASE/"data"/"golf"/"backups"
IMPORT="from services.golf_skill_match import personalized_sort_key, personalized_reason\\n"

def main():
    text=PAGE.read_text(encoding="utf-8")
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=BACKUPS/f"6_골프장_추천_before_skill_{datetime.now():%Y%m%d_%H%M%S}.py"

    marker="from services.golf_public_data import dual_verification_summary\\n"
    if IMPORT.strip() not in text:
        if marker not in text: raise RuntimeError("import 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(marker,marker+IMPORT,1)

    ui_anchor='''            st.markdown("##### 추가 조건 <span style='font-size:.72rem;font-weight:500;opacity:.55'>선택사항</span>", unsafe_allow_html=True)
'''
    ui_block='''            st.markdown("##### 내 실력 · 원하는 난이도 <span style='font-size:.72rem;font-weight:500;opacity:.55'>선택사항</span>", unsafe_allow_html=True)
            c_score, c_level = st.columns(2)
            with c_score:
                avg_score_label = st.selectbox("내 평균타수", ["미선택", "80타대", "90타대", "100타대", "110타 이상"], index=0, key="golf_avg_score")
            with c_level:
                challenge = st.segmented_control("원하는 난이도", ["편하게", "적당히", "도전"], default="적당히", key="golf_challenge")
            avg_score_map = {"80타대":85, "90타대":95, "100타대":105, "110타 이상":115}
            avg_score = avg_score_map.get(avg_score_label)

'''
    if "avg_score_label = st.selectbox" not in text:
        if ui_anchor not in text: raise RuntimeError("실력 UI 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(ui_anchor,ui_block+ui_anchor,1)

    old='''                    "players": 4,
                }
'''
    new='''                    "players": 4,
                    "avg_score": avg_score,
                    "challenge": challenge,
                }
'''
    if '"avg_score": avg_score' not in text:
        if old not in text: raise RuntimeError("검색조건 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(old,new,1)

    old='''                filtered = sorted(filtered, key=_condition_sort_key)
'''
    new='''                filtered = sorted(filtered, key=_condition_sort_key)
                if cond.get("avg_score"):
                    filtered = sorted(
                        filtered,
                        key=lambda club: (
                            _condition_sort_key(club)[:-1],
                            personalized_sort_key(club, cond["avg_score"], cond.get("challenge") or "적당히"),
                        ),
                    )
'''
    if "personalized_sort_key(club, cond" not in text:
        if old not in text: raise RuntimeError("정렬 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(old,new,1)

    old='''                st.session_state.golf_recs = [
                    (club, ["검색조건 충족"]) for club in page_clubs
                ]
'''
    new='''                st.session_state.golf_recs = [
                    (club, ["검색조건 충족"] + ([personalized_reason(club, cond["avg_score"], cond.get("challenge") or "적당히")] if cond.get("avg_score") else []))
                    for club in page_clubs
                ]
'''
    if "personalized_reason(club, cond" not in text:
        if old not in text: raise RuntimeError("결과 근거 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(old,new,1)

    old='''                if cond.get("objective_features"):
                    chips.extend(cond["objective_features"])
'''
    new='''                if cond.get("objective_features"):
                    chips.extend(cond["objective_features"])
                if cond.get("avg_score"):
                    chips.append(f'평균 {cond["avg_score"]}타 참고')
                    chips.append(cond.get("challenge") or "적당히")
'''
    if "chips.append(f'평균 {cond" not in text:
        if old not in text: raise RuntimeError("검색조건 표시 위치를 찾지 못했습니다. 원본 변경 없음.")
        text=text.replace(old,new,1)

    ast.parse(text)
    shutil.copy2(PAGE,backup)
    PAGE.write_text(text,encoding="utf-8")
    print("="*64)
    print("평균타수 기반 맞춤 난이도 검색 적용 완료")
    print("="*64)
    print("추가 UI     : 평균타수 + 편하게/적당히/도전")
    print("근거        : KGA Course/Slope Rating")
    print("핸디캡 환산 : 하지 않음")
    print("백업        :",backup)

if __name__=="__main__":
    main()
